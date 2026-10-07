"""Acciones contractuales y derivaciones.

R11: el bot **nunca** ejecuta un cambio contractual. Crea una `AccionPendiente`
y la aprueba un funcionario con `puede_aprobar`. El efecto real (dar de baja la
póliza, agregar el conductor, abrir el siniestro) ocurre recién al aprobar, en
la misma transacción que deja la acción en `ejecutada`.

La base también lo hace cumplir: el trigger `acciones_pendientes_control`
rechaza una acción que nace resuelta, un `ejecutada` sin `aprobada` previa y
una resolución firmada por alguien sin permiso.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import connection, transaction
from django.utils import timezone

from datos.limpieza import normalizar_dni
from datos.models import (
    AccionPendiente,
    ConductorPoliza,
    ConsultaBot,
    Derivacion,
    EstadoAccion,
    EstadoConsulta,
    EstadoPoliza,
    EstadoSiniestro,
    Funcionario,
    Direccion,
    Emisor,
    EstadoEnvio,
    Mensaje,
    ModoConversacion,
    Poliza,
    Prioridad,
    Relacion,
    Siniestro,
    TipoAccion,
)
from negocio.bot.plantillas import (
    ACCION_APROBADA,
    ACCION_RECHAZADA,
    formatear_monto,
)
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    ParametrosIncompletos,
    PermisoDenegado,
)
from negocio.whatsapp import enviar_pendientes

# Llave del advisory lock que serializa la numeración de siniestros (AC-T3-18).
LOCK_NUMERO_SINIESTRO = 4243

MOTIVO_MINIMO = 3

# Qué parámetros necesita cada acción para poder ejecutarse.
PARAMETROS_REQUERIDOS = {
    TipoAccion.AGREGAR_CONDUCTOR: ("nombre", "dni"),
    TipoAccion.MODIFICAR_POLIZA: ("detalle",),
    TipoAccion.REEMBOLSO: ("importe",),
    TipoAccion.APERTURA_SINIESTRO: ("fecha_ocurrencia", "descripcion"),
}
# Acciones que no se pueden ejecutar sin una póliza concreta.
REQUIEREN_POLIZA = {TipoAccion.BAJA_POLIZA, TipoAccion.AGREGAR_CONDUCTOR}


def _aprobador(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id).first()
    if funcionario is None:
        raise NoEncontrado("El funcionario no existe.")
    if not funcionario.activo or not funcionario.puede_aprobar:
        raise PermisoDenegado("Hace falta un funcionario con permiso de aprobación.")
    return funcionario


def _accion(accion_id: int) -> AccionPendiente:
    accion = (
        AccionPendiente.objects.select_related(
            "poliza", "consulta", "consulta__conversacion"
        )
        .filter(pk=accion_id)
        .first()
    )
    if accion is None:
        raise NoEncontrado("La acción no existe.")
    return accion


def _consulta(consulta_id: int) -> ConsultaBot:
    consulta = (
        ConsultaBot.objects.select_related("conversacion").filter(pk=consulta_id).first()
    )
    if consulta is None:
        raise NoEncontrado("La consulta no existe.")
    return consulta


def _normalizar_parametros(parametros: dict | None) -> dict:
    limpios = dict(parametros or {})
    if limpios.get("dni") is not None:
        limpios["dni"] = normalizar_dni(str(limpios["dni"]))
    return limpios


def solicitar_accion(
    consulta_id: int,
    tipo: str,
    poliza_id: int | None = None,
    parametros: dict | None = None,
) -> AccionPendiente:
    """Deja pedida una acción contractual. No cambia nada todavía (AC-T3-16)."""
    if tipo not in TipoAccion.values:
        raise DatosInvalidos(f"Tipo de acción inválido: {tipo}")
    consulta = _consulta(consulta_id)

    # Misma conversación + mismo tipo + misma póliza y todavía pendiente: es la misma.
    existentes = AccionPendiente.objects.filter(
        tipo_accion=tipo,
        estado=EstadoAccion.PENDIENTE,
        poliza_id=poliza_id,
    )
    if consulta.conversacion_id is not None:
        existentes = existentes.filter(
            consulta__conversacion_id=consulta.conversacion_id
        )
    else:
        existentes = existentes.filter(consulta_id=consulta_id)
    repetida = existentes.order_by("id").first()
    if repetida is not None:
        return repetida

    return AccionPendiente.objects.create(
        consulta=consulta,
        poliza_id=poliza_id,
        tipo_accion=tipo,
        parametros=_normalizar_parametros(parametros),
        estado=EstadoAccion.PENDIENTE,
    )


def completar_parametros(
    accion_id: int, funcionario_id: int, parametros: dict
) -> AccionPendiente:
    """Mezcla parámetros nuevos con los que ya tenía la acción (AC-T3-22)."""
    _aprobador(funcionario_id)
    accion = _accion(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya fue resuelta.")
    accion.parametros = {
        **(accion.parametros or {}),
        **_normalizar_parametros(parametros),
    }
    accion.save(update_fields=["parametros"])
    return accion


def _faltantes(accion: AccionPendiente) -> list[str]:
    parametros = accion.parametros or {}
    faltan = [
        nombre
        for nombre in PARAMETROS_REQUERIDOS.get(accion.tipo_accion, ())
        if parametros.get(nombre) in (None, "")
    ]
    if accion.tipo_accion in REQUIEREN_POLIZA and accion.poliza_id is None:
        faltan.append("poliza")
    return faltan


def _proximo_numero_siniestro() -> str:
    """`SIN-<año>-<5 dígitos>` secuencial, serializado por advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_NUMERO_SINIESTRO])
    anio = timezone.now().year
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(MAX(SUBSTRING(numero_siniestro FROM 'SIN-[0-9]{4}-([0-9]+)$')::int), 0)
            FROM siniestros
            WHERE numero_siniestro ~ %s
            """,
            [f"^SIN-{anio}-[0-9]+$"],
        )
        maximo = cursor.fetchone()[0] or 0
    return f"SIN-{anio}-{maximo + 1:05d}"


def _ejecutar(accion: AccionPendiente) -> None:
    """Aplica el efecto real de la acción. Corre dentro de la transacción."""
    faltan = _faltantes(accion)
    if faltan:
        raise ParametrosIncompletos(
            "Faltan datos para ejecutar la acción: " + ", ".join(faltan)
        )
    parametros = accion.parametros or {}
    tipo = accion.tipo_accion

    if tipo == TipoAccion.BAJA_POLIZA:
        poliza = Poliza.objects.select_for_update().get(pk=accion.poliza_id)
        if poliza.estado == EstadoPoliza.DADA_DE_BAJA:
            raise EstadoInvalido("La póliza ya está dada de baja.")
        poliza.estado = EstadoPoliza.DADA_DE_BAJA
        poliza.save(update_fields=["estado"])

    elif tipo == TipoAccion.AGREGAR_CONDUCTOR:
        relacion = parametros.get("relacion") or Relacion.OTRO
        if relacion not in Relacion.values:
            relacion = Relacion.OTRO
        ConductorPoliza.objects.create(
            poliza_id=accion.poliza_id,
            nombre=parametros["nombre"],
            dni=normalizar_dni(str(parametros["dni"])),
            relacion=relacion,
            activo=True,
        )

    elif tipo == TipoAccion.APERTURA_SINIESTRO:
        numero = _proximo_numero_siniestro()
        Siniestro.objects.create(
            numero_siniestro=numero,
            poliza_id=accion.poliza_id,
            consulta_id=accion.consulta_id,
            fecha_ocurrencia=parametros["fecha_ocurrencia"],
            descripcion=parametros["descripcion"],
            estado=EstadoSiniestro.DENUNCIADO,
        )
        # Queda en los parámetros para poder nombrarlo en el aviso al cliente.
        accion.parametros = {**parametros, "numero_siniestro": numero}

    # `reembolso` y `modificar_poliza` quedan `ejecutada` sin tocar datos:
    # el movimiento real lo hace administración por fuera del sistema.


def _descripcion(accion: AccionPendiente) -> str:
    """El `{descripcion}` de `ACCION_APROBADA` (sección 5 de la spec)."""
    numero = accion.poliza.numero_poliza if accion.poliza_id else "-"
    parametros = accion.parametros or {}
    if accion.tipo_accion == TipoAccion.BAJA_POLIZA:
        return f"baja de la póliza {numero}"
    if accion.tipo_accion == TipoAccion.AGREGAR_CONDUCTOR:
        return f"alta de conductor en la póliza {numero}"
    if accion.tipo_accion == TipoAccion.MODIFICAR_POLIZA:
        return f"modificación de la póliza {numero}"
    if accion.tipo_accion == TipoAccion.REEMBOLSO:
        try:
            monto = formatear_monto(Decimal(str(parametros.get("importe", 0))))
        except (InvalidOperation, ValueError):
            monto = str(parametros.get("importe", ""))
        return f"reembolso de {monto}"
    if accion.tipo_accion == TipoAccion.APERTURA_SINIESTRO:
        return (
            "denuncia de siniestro "
            f"(número {parametros.get('numero_siniestro', '-')})"
        )
    return accion.tipo_accion


def _avisar_al_cliente(accion: AccionPendiente, texto: str, funcionario: Funcionario) -> None:
    """AC-T3-19: el aviso va después del commit y su falla no revierte nada."""
    conversacion = accion.consulta.conversacion
    if conversacion is None:
        return
    Mensaje.objects.create(
        conversacion=conversacion,
        consulta=accion.consulta,
        direccion=Direccion.SALIENTE,
        emisor=Emisor.FUNCIONARIO,
        funcionario=funcionario,
        texto=texto,
        estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
        fecha_hora=timezone.now(),
    )
    enviar_pendientes(conversacion.id)


def aprobar_accion(
    accion_id: int, funcionario_id: int, motivo: str | None = None
) -> AccionPendiente:
    """Aprueba y ejecuta la acción en una sola transacción (AC-T3-17)."""
    funcionario = _aprobador(funcionario_id)
    accion = _accion(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya fue resuelta.")

    with transaction.atomic():
        accion.estado = EstadoAccion.APROBADA
        accion.resuelta_por = funcionario
        accion.resuelta_en = timezone.now()
        accion.motivo = motivo
        accion.save(
            update_fields=["estado", "resuelta_por", "resuelta_en", "motivo"]
        )
        _ejecutar(accion)
        accion.estado = EstadoAccion.EJECUTADA
        accion.save(update_fields=["estado", "parametros"])

    _avisar_al_cliente(
        accion, ACCION_APROBADA.format(descripcion=_descripcion(accion)), funcionario
    )
    return accion


def rechazar_accion(
    accion_id: int, funcionario_id: int, motivo: str
) -> AccionPendiente:
    """Rechaza la acción. El motivo es obligatorio (AC-T3-20)."""
    funcionario = _aprobador(funcionario_id)
    if not motivo or len(motivo.strip()) < MOTIVO_MINIMO:
        raise DatosInvalidos("Hay que indicar un motivo para rechazar la acción.")
    accion = _accion(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya fue resuelta.")

    with transaction.atomic():
        accion.estado = EstadoAccion.RECHAZADA
        accion.resuelta_por = funcionario
        accion.resuelta_en = timezone.now()
        accion.motivo = motivo.strip()
        accion.save(
            update_fields=["estado", "resuelta_por", "resuelta_en", "motivo"]
        )

    _avisar_al_cliente(accion, ACCION_RECHAZADA, funcionario)
    return accion


def derivar(
    consulta_id: int, derivado_a_id: int, prioridad: str = "normal", motivo: str = ""
) -> Derivacion:
    """Pasa el caso a un funcionario y saca al bot de la conversación."""
    if prioridad not in Prioridad.values:
        raise DatosInvalidos(f"Prioridad inválida: {prioridad}")
    consulta = _consulta(consulta_id)
    funcionario = Funcionario.objects.filter(pk=derivado_a_id).first()
    if funcionario is None:
        raise NoEncontrado("El funcionario no existe.")

    with transaction.atomic():
        derivacion = Derivacion.objects.create(
            consulta=consulta,
            derivado_a=funcionario,
            prioridad=prioridad,
            motivo=motivo or "Derivación automática",
        )
        conversacion = consulta.conversacion
        if conversacion is not None:
            conversacion.modo = ModoConversacion.HUMANO
            conversacion.funcionario = funcionario
            conversacion.save(update_fields=["modo", "funcionario"])
        consulta.estado = EstadoConsulta.DERIVADO
        consulta.funcionario_asignado = funcionario
        consulta.save(update_fields=["estado", "funcionario_asignado"])
    return derivacion


def atender_derivacion(derivacion_id: int, funcionario_id: int) -> Derivacion:
    """La marca atendida. Solo puede hacerlo la persona asignada (AC-T3-23)."""
    derivacion = Derivacion.objects.filter(pk=derivacion_id).first()
    if derivacion is None:
        raise NoEncontrado("La derivación no existe.")
    if derivacion.derivado_a_id != funcionario_id:
        raise PermisoDenegado("La derivación es de otro funcionario.")
    if derivacion.atendida_en is not None:
        raise EstadoInvalido("La derivación ya fue atendida.")
    derivacion.atendida_en = timezone.now()
    derivacion.save(update_fields=["atendida_en"])
    return derivacion
