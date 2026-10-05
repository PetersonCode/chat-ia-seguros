from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from datos.limpieza import normalizar_dni
from datos.models import (
    AccionPendiente,
    ConductorPoliza,
    ConsultaBot,
    Derivacion,
    EstadoAccion,
    EstadoPoliza,
    Funcionario,
    Mensaje,
    Poliza,
    Prioridad,
    Siniestro,
    TipoAccion,
)
from datos.selectors import funcionario_por_email
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    ParametrosIncompletos,
    PermisoDenegado,
)
from negocio.whatsapp import enviar_pendientes


def _funcionario_aprobador(funcionario_id: int) -> Funcionario:
    try:
        funcionario = Funcionario.objects.get(pk=funcionario_id)
    except Funcionario.DoesNotExist as exc:
        raise NoEncontrado("Funcionario no encontrado") from exc
    if not funcionario.activo or not funcionario.puede_aprobar:
        raise PermisoDenegado("El funcionario no puede aprobar acciones.")
    return funcionario


def _accion_por_id(accion_id: int) -> AccionPendiente:
    try:
        return AccionPendiente.objects.select_related("consulta", "consulta__conversacion", "consulta__conversacion__contacto").get(pk=accion_id)
    except AccionPendiente.DoesNotExist as exc:
        raise NoEncontrado("Acción no encontrada") from exc


def solicitar_accion(consulta_id: int, tipo: str, poliza_id: int | None = None, parametros: dict | None = None) -> AccionPendiente:
    if tipo not in TipoAccion.values:
        raise DatosInvalidos("Tipo de acción inválido.")
    consulta = ConsultaBot.objects.get(pk=consulta_id)
    params = dict(parametros or {})
    existente = (
        AccionPendiente.objects.filter(
            consulta_id=consulta_id,
            tipo_accion=tipo,
            estado=EstadoAccion.PENDIENTE,
            poliza_id=poliza_id,
        )
        .order_by("-id")
        .first()
    )
    if existente:
        return existente
    conversacion_id = consulta.conversacion_id
    if conversacion_id:
        ya_existe = AccionPendiente.objects.filter(
            consulta__conversacion_id=conversacion_id,
            tipo_accion=tipo,
            estado=EstadoAccion.PENDIENTE,
            poliza_id=poliza_id,
        ).first()
        if ya_existe:
            return ya_existe
    return AccionPendiente.objects.create(
        consulta=consulta,
        poliza_id=poliza_id,
        tipo_accion=tipo,
        parametros=params,
        estado=EstadoAccion.PENDIENTE,
    )


def completar_parametros(accion_id: int, funcionario_id: int, parametros: dict) -> AccionPendiente:
    accion = _accion_por_id(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya no está pendiente.")
    _funcionario_aprobador(funcionario_id)
    nuevos = dict(accion.parametros or {})
    for nombre, valor in (parametros or {}).items():
        if nombre == "dni" and valor is not None:
            nuevos[nombre] = normalizar_dni(str(valor))
        else:
            nuevos[nombre] = valor
    accion.parametros = nuevos
    accion.save(update_fields=["parametros"])
    return accion


def _crear_mensaje_funcionario(conversacion_id: int | None, texto: str):
    if conversacion_id is None:
        return None
    return Mensaje.objects.create(
        conversacion_id=conversacion_id,
        direccion="saliente",
        emisor="funcionario",
        texto=texto,
        estado_envio="pendiente_envio",
    )


def _plantilla_accion(accion: AccionPendiente, aprobada: bool) -> str:
    poliza = accion.poliza
    numero = poliza.numero_poliza if poliza else ""
    if accion.tipo_accion == TipoAccion.BAJA_POLIZA:
        descripcion = f"baja de la póliza {numero}"
    elif accion.tipo_accion == TipoAccion.AGREGAR_CONDUCTOR:
        descripcion = f"alta de conductor en la póliza {numero}"
    elif accion.tipo_accion == TipoAccion.MODIFICAR_POLIZA:
        descripcion = f"modificación de la póliza {numero}"
    elif accion.tipo_accion == TipoAccion.REEMBOLSO:
        importe = accion.parametros.get("importe") or "0"
        descripcion = f"reembolso de ${importe}"
    elif accion.tipo_accion == TipoAccion.APERTURA_SINIESTRO:
        descripcion = f"denuncia de siniestro (número {accion.parametros.get('numero_siniestro', '')})"
    else:
        descripcion = accion.tipo_accion
    if aprobada:
        return f"Tu solicitud de {descripcion} fue aprobada y procesada."
    return "No pudimos procesar tu solicitud. Un asesor se va a comunicar con vos."


def aprobar_accion(accion_id: int, funcionario_id: int, motivo: str | None = None) -> AccionPendiente:
    accion = _accion_por_id(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya fue resuelta.")
    _funcionario_aprobador(funcionario_id)
    params = accion.parametros or {}
    tipo = accion.tipo_accion
    with transaction.atomic():
        accion.resuelta_por_id = funcionario_id
        accion.resuelta_en = timezone.now()
        accion.motivo = motivo
        accion.estado = EstadoAccion.APROBADA
        accion.save(update_fields=["estado", "resuelta_por", "resuelta_en", "motivo"])

        if tipo == TipoAccion.BAJA_POLIZA:
            if accion.poliza_id is None:
                raise ParametrosIncompletos("Falta la póliza para la baja.")
            poliza = Poliza.objects.get(pk=accion.poliza_id)
            if poliza.estado == EstadoPoliza.DADA_DE_BAJA:
                raise EstadoInvalido("La póliza ya está dada de baja.")
            poliza.estado = EstadoPoliza.DADA_DE_BAJA
            poliza.save(update_fields=["estado"])
        elif tipo == TipoAccion.AGREGAR_CONDUCTOR:
            if "nombre" not in params or "dni" not in params:
                raise ParametrosIncompletos("Faltan nombre o DNI para agregar conductor.")
            poliza = Poliza.objects.get(pk=accion.poliza_id)
            ConductorPoliza.objects.create(
                poliza=poliza,
                nombre=params["nombre"],
                dni=normalizar_dni(str(params["dni"])),
                relacion=params.get("relacion", "otro"),
                activo=True,
            )
        elif tipo == TipoAccion.REEMBOLSO:
            if "importe" not in params:
                raise ParametrosIncompletos("Falta el importe del reembolso.")
        elif tipo == TipoAccion.MODIFICAR_POLIZA:
            if "detalle" not in params:
                raise ParametrosIncompletos("Falta el detalle de la modificación.")
        elif tipo == TipoAccion.APERTURA_SINIESTRO:
            if "fecha_ocurrencia" not in params or "descripcion" not in params:
                raise ParametrosIncompletos("Faltan fecha y descripción.")
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(4243)")
            anio = timezone.now().year
            secuencia = 1 + Siniestro.objects.filter(numero_siniestro__startswith=f"SIN-{anio}-").count()
            Siniestro.objects.create(
                numero_siniestro=f"SIN-{anio}-{secuencia:05d}",
                poliza_id=accion.poliza_id,
                consulta_id=accion.consulta_id,
                fecha_ocurrencia=params["fecha_ocurrencia"],
                descripcion=params["descripcion"],
                estado="denunciado",
            )
        accion.estado = EstadoAccion.EJECUTADA
        accion.save(update_fields=["estado"])

    conversacion = accion.consulta.conversacion
    texto = _plantilla_accion(accion, True)
    if conversacion:
        _crear_mensaje_funcionario(conversacion.id, texto)
        enviar_pendientes(conversacion.id)
    return accion


def rechazar_accion(accion_id: int, funcionario_id: int, motivo: str) -> AccionPendiente:
    if not motivo or len(motivo.strip()) < 3:
        raise DatosInvalidos("Debe indicar un motivo válido.")
    accion = _accion_por_id(accion_id)
    if accion.estado != EstadoAccion.PENDIENTE:
        raise EstadoInvalido("La acción ya fue resuelta.")
    _funcionario_aprobador(funcionario_id)
    accion.estado = EstadoAccion.RECHAZADA
    accion.resuelta_por_id = funcionario_id
    accion.resuelta_en = timezone.now()
    accion.motivo = motivo
    accion.save(update_fields=["estado", "resuelta_por", "resuelta_en", "motivo"])

    conversacion = accion.consulta.conversacion
    texto = "No pudimos procesar tu solicitud. Un asesor se va a comunicar con vos."
    if conversacion:
        _crear_mensaje_funcionario(conversacion.id, texto)
        enviar_pendientes(conversacion.id)
    return accion


def derivar(consulta_id: int, derivado_a_id: int, prioridad: str = "normal", motivo: str = "") -> Derivacion:
    consulta = ConsultaBot.objects.get(pk=consulta_id)
    funcionario = Funcionario.objects.get(pk=derivado_a_id)
    derivacion = Derivacion.objects.create(
        consulta=consulta,
        derivado_a=funcionario,
        prioridad=prioridad,
        motivo=motivo or "Derivación automática",
    )
    if consulta.conversacion_id:
        conversacion = consulta.conversacion
        conversacion.modo = "humano"
        conversacion.funcionario = funcionario
        conversacion.save(update_fields=["modo", "funcionario"])
    consulta.estado = "derivado"
    consulta.funcionario_asignado = funcionario
    consulta.save(update_fields=["estado", "funcionario_asignado"])
    return derivacion


def atender_derivacion(derivacion_id: int, funcionario_id: int) -> Derivacion:
    derivacion = Derivacion.objects.select_related("derivado_a", "consulta").get(pk=derivacion_id)
    if derivacion.derivado_a_id != funcionario_id:
        raise PermisoDenegado("No sos el responsable de esta derivación.")
    if derivacion.atendida_en is not None:
        raise EstadoInvalido("La derivación ya fue atendida.")
    derivacion.atendida_en = timezone.now()
    derivacion.save(update_fields=["atendida_en"])
    return derivacion
