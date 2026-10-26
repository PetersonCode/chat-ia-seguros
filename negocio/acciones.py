"""Acciones contractuales y derivaciones.

R11: el bot **nunca** ejecuta un cambio contractual. Crea una `AccionPendiente`
y la aprueba un funcionario con `puede_aprobar`. Solo los efectos implementados
se aplican al aprobar y dejan la acción en `ejecutada`; lo que requiere gestión
externa queda `aprobada`.

La base también lo hace cumplir: el trigger `acciones_pendientes_control`
rechaza una acción que nace resuelta, un `ejecutada` sin `aprobada` previa y
una resolución firmada por alguien sin permiso.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction
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
    Funcionario,
    Direccion,
    Emisor,
    EstadoEnvio,
    Mensaje,
    ModoConversacion,
    Poliza,
    Prioridad,
    Relacion,
    TipoAccion,
)
from negocio.bot.plantillas import (
    ACCION_APROBADA,
    ACCION_APROBADA_PENDIENTE,
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
from negocio.siniestros import registrar_denuncia_desde_accion

MOTIVO_MINIMO = 3

# Qué parámetros necesita cada acción para poder ejecutarse.
PARAMETROS_REQUERIDOS = {
    TipoAccion.AGREGAR_CONDUCTOR: ("nombre", "dni"),
    TipoAccion.MODIFICAR_POLIZA: ("detalle",),
    TipoAccion.REEMBOLSO: ("importe",),
    TipoAccion.APERTURA_SINIESTRO: ("fecha_ocurrencia", "descripcion"),
    # El bot junta nombre, DNI y teléfono de la conversación. El apellido puede
    # faltar —si la persona escribió una sola palabra— y entonces el panel se
    # lo pide a quien va a aprobar antes de dejarla ejecutar.
    TipoAccion.ALTA_CLIENTE: ("nombre", "apellido", "dni", "telefono"),
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
            "poliza",
            "consulta",
            "consulta__contacto",
            "consulta__conversacion",
            "consulta__conversacion__contacto",
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


@transaction.atomic
def completar_parametros(
    accion_id: int, funcionario_id: int, parametros: dict
) -> AccionPendiente:
    """Mezcla parámetros nuevos con los que ya tenía la acción (AC-T3-22)."""
    _aprobador(funcionario_id)
    accion = _accion_bloqueada(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya fue resuelta.")

    nuevos = _normalizar_parametros(parametros)
    poliza_seleccionada = nuevos.pop("poliza", None)
    if "poliza" in parametros:
        if accion.tipo_accion != TipoAccion.BAJA_POLIZA:
            raise DatosInvalidos("La selección de póliza solo aplica a una baja.")
        cliente_id = _cliente_validado_para_accion(accion)
        if isinstance(poliza_seleccionada, bool) or not isinstance(
            poliza_seleccionada, (int, str)
        ):
            raise DatosInvalidos("Seleccioná una póliza válida del cliente.")
        if isinstance(poliza_seleccionada, str):
            poliza_seleccionada = poliza_seleccionada.strip()
            if not poliza_seleccionada.isdigit():
                raise DatosInvalidos("Seleccioná una póliza válida del cliente.")
        poliza = Poliza.objects.filter(pk=poliza_seleccionada).first()
        if poliza is None:
            raise NoEncontrado("La póliza seleccionada no existe.")
        if poliza.cliente_id != cliente_id:
            raise DatosInvalidos(
                "La póliza seleccionada no pertenece al cliente vinculado."
            )
        accion.poliza = poliza

    accion.parametros = {
        **(accion.parametros or {}),
        **nuevos,
    }
    update_fields = ["parametros"]
    if "poliza" in parametros:
        update_fields.append("poliza")
    accion.save(update_fields=update_fields)
    return accion


def _cliente_validado_para_accion(accion: AccionPendiente) -> int:
    """Devuelve el cliente asociado al contacto que originó la consulta."""
    consulta = accion.consulta
    contacto_conversacion = (
        consulta.conversacion.contacto if consulta.conversacion_id is not None else None
    )
    contacto = consulta.contacto or contacto_conversacion
    if contacto is None or contacto.cliente_id is None:
        raise DatosInvalidos(
            "No se puede seleccionar una póliza sin un contacto vinculado a un cliente."
        )
    if (
        contacto_conversacion is not None
        and contacto_conversacion.id != contacto.id
    ):
        raise DatosInvalidos(
            "El contacto de la consulta no coincide con el de la conversación."
        )
    return contacto.cliente_id


def polizas_disponibles_para_baja(accion_id: int) -> list[Poliza]:
    """Lista pólizas del cliente validado para completar una baja pendiente."""
    accion = _accion(accion_id)
    if accion.tipo_accion != TipoAccion.BAJA_POLIZA:
        raise DatosInvalidos("La selección de póliza solo aplica a una baja.")
    cliente_id = _cliente_validado_para_accion(accion)
    return list(
        Poliza.objects.filter(cliente_id=cliente_id).order_by("numero_poliza", "id")
    )


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


def _ejecutar(accion: AccionPendiente, funcionario: Funcionario) -> bool:
    """Aplica el efecto implementado y confirma si ocurrió dentro de la transacción."""
    faltan = _faltantes(accion)
    if faltan:
        raise ParametrosIncompletos(
            "Faltan datos para ejecutar la acción: " + ", ".join(faltan)
        )
    parametros = accion.parametros or {}
    tipo = accion.tipo_accion

    if tipo == TipoAccion.BAJA_POLIZA:
        poliza = Poliza.objects.select_for_update().get(pk=accion.poliza_id)
        cliente_id = _cliente_validado_para_accion(accion)
        if poliza.cliente_id != cliente_id:
            raise DatosInvalidos(
                "La póliza seleccionada no pertenece al cliente vinculado."
            )
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
        cliente_id = _cliente_validado_para_accion(accion)
        siniestro = registrar_denuncia_desde_accion(
            cliente_id=cliente_id,
            poliza_id=accion.poliza_id,
            consulta_id=accion.consulta_id,
            fecha_ocurrencia=parametros["fecha_ocurrencia"],
            descripcion=parametros["descripcion"],
            funcionario_id=funcionario.id,
        )
        # Queda en los parámetros para poder nombrarlo en el aviso al cliente.
        accion.parametros = {
            **parametros,
            "numero_siniestro": siniestro.numero_siniestro,
        }

    elif tipo == TipoAccion.ALTA_CLIENTE:
        # El alta real es la misma del panel, con sus validaciones: un DNI
        # repetido, un teléfono que ya es de otro cliente o un nombre con
        # dígitos lanzan `DatosInvalidos` y revierten la aprobación entera.
        # Si el número ya existía sin cliente —lo creó el webhook cuando esta
        # persona escribió— se adopta, y la conversación queda enganchada al
        # cliente nuevo sin duplicar el contacto.
        from negocio.clientes import alta_cliente

        alta_cliente(
            dni=str(parametros["dni"]),
            nombre=str(parametros["nombre"]),
            apellido=str(parametros["apellido"]),
            telefono=str(parametros["telefono"]),
            email=(parametros.get("email") or None),
        )

    elif tipo in (TipoAccion.REEMBOLSO, TipoAccion.MODIFICAR_POLIZA):
        return False

    return True


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
    if accion.tipo_accion == TipoAccion.ALTA_CLIENTE:
        # Sin nombre ni DNI: este texto se le manda al cliente y no hay por qué
        # devolverle sus propios datos personales por WhatsApp.
        return "alta como cliente"
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


def _accion_bloqueada(accion_id):
    # Lock sobre la fila propia, sin bloquear los outer joins de _accion.
    if not AccionPendiente.objects.select_for_update().filter(pk=accion_id).exists():
        raise NoEncontrado("La acción no existe.")
    return _accion(accion_id)


def aprobar_accion(
    accion_id: int, funcionario_id: int, motivo: str | None = None
) -> AccionPendiente:
    """Aprueba y ejecuta solo los efectos implementados (AC-T3-17)."""
    funcionario = _aprobador(funcionario_id)
    with transaction.atomic():
        accion = _accion_bloqueada(accion_id)
        if accion.estado != EstadoAccion.PENDIENTE:
            raise EstadoInvalido("La acción ya fue resuelta.")
        accion.estado = EstadoAccion.APROBADA
        accion.resuelta_por = funcionario
        accion.resuelta_en = timezone.now()
        accion.motivo = motivo
        accion.save(
            update_fields=["estado", "resuelta_por", "resuelta_en", "motivo"]
        )
        if _ejecutar(accion, funcionario):
            accion.estado = EstadoAccion.EJECUTADA
            accion.save(update_fields=["estado", "parametros"])

    plantilla = (
        ACCION_APROBADA
        if accion.estado == EstadoAccion.EJECUTADA
        else ACCION_APROBADA_PENDIENTE
    )
    _avisar_al_cliente(
        accion, plantilla.format(descripcion=_descripcion(accion)), funcionario
    )
    return accion


def rechazar_accion(
    accion_id: int, funcionario_id: int, motivo: str
) -> AccionPendiente:
    """Rechaza la acción. El motivo es obligatorio (AC-T3-20)."""
    funcionario = _aprobador(funcionario_id)
    if not motivo or len(motivo.strip()) < MOTIVO_MINIMO:
        raise DatosInvalidos("Hay que indicar un motivo para rechazar la acción.")
    with transaction.atomic():
        accion = _accion_bloqueada(accion_id)
        if accion.estado != EstadoAccion.PENDIENTE:
            raise EstadoInvalido("La acción ya fue resuelta.")
        accion.estado = EstadoAccion.RECHAZADA
        accion.resuelta_por = funcionario
        accion.resuelta_en = timezone.now()
        accion.motivo = motivo.strip()
        accion.save(
            update_fields=["estado", "resuelta_por", "resuelta_en", "motivo"]
        )

    _avisar_al_cliente(accion, ACCION_RECHAZADA, funcionario)
    return accion


@transaction.atomic
def finalizar_gestion_externa(
    accion_id: int, funcionario_id: int, *, referencia: str, motivo: str
) -> AccionPendiente:
    """Registra evidencia de una gestión manual; no mueve dinero ni contratos."""
    from datos.models import FinalizacionAccion

    funcionario = _aprobador(funcionario_id)
    accion = AccionPendiente.objects.select_for_update().filter(pk=accion_id).first()
    if accion is None:
        raise NoEncontrado("La acción no existe.")
    if accion.estado != EstadoAccion.APROBADA or accion.tipo_accion not in (
        TipoAccion.REEMBOLSO, TipoAccion.MODIFICAR_POLIZA
    ):
        raise EstadoInvalido("Solo se puede completar una gestión externa aprobada.")
    referencia = referencia.strip()
    motivo = motivo.strip()
    if not 3 <= len(referencia) <= 100 or len(motivo) < MOTIVO_MINIMO:
        raise DatosInvalidos("Indicá una referencia de 3 a 100 caracteres y un motivo de al menos 3.")
    FinalizacionAccion.objects.create(
        accion=accion, funcionario=funcionario, referencia=referencia, motivo=motivo
    )
    accion.refresh_from_db()
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
