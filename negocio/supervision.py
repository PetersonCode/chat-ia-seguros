"""Supervisión humana: qué hace un funcionario con lo que el bot retuvo.

Un mensaje `retenido` nunca sale solo: alguien lo libera tal cual, lo corrige o
lo descarta. Las tres cosas cierran las alertas que lo retuvieron, y las dos
primeras disparan el envío.

Aprobador obligatorio en `liberar_respuesta`, `descartar_respuesta` y
`reabrir_consulta` (contrato, sección 6).
"""

from __future__ import annotations

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from datos.models import (
    AccionPendiente,
    AdjuntoSiniestro,
    BorradorPoliza,
    Cotizacion,
    FinalizacionAccion,
    Interesado,
    InteresadoHistorial,
    ContactoWhatsapp,
    RecordatorioPoliza,
    Rol,
    Conversacion,
    ContextoCobertura,
    ConsultaBot,
    Direccion,
    Emisor,
    EstadoAlerta,
    EstadoAccion,
    EstadoConsulta,
    EstadoConversacion,
    EstadoEnvio,
    Funcionario,
    Mensaje,
    ModoConversacion,
    Alerta,
    Derivacion,
    Siniestro,
    TrabajoWhatsApp,
)
from datos.selectors import alertas_abiertas
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)
from negocio.reglas import ventana_24h_abierta
from negocio.whatsapp import descartar_automaticos_pendientes, enviar_pendientes

# Un caso sigue "vivo" mientras esté en alguno de estos estados.
ESTADOS_CASO_ABIERTO = (
    EstadoConsulta.ABIERTO,
    EstadoConsulta.PENDIENTE_REVISION,
    EstadoConsulta.DERIVADO,
)
ESTADOS_ACCION_PENDIENTE = (
    EstadoAccion.PENDIENTE,
    EstadoAccion.APROBADA,
)

MOTIVO_MINIMO = 5
RESOLUCION_LIBERADA = "Liberada sin cambios"
RESOLUCION_DESBLOQUEO = "Número desbloqueado manualmente"
RESOLUCION_ALERTAS_VACIADAS = "Alertas vaciadas desde la conversación"
RESOLUCION_CORREGIDA = "Respuesta corregida por el funcionario"
RESOLUCION_DESBLOQUEO = "Número desbloqueado manualmente"


def _funcionario(funcionario_id: int, *, aprobador: bool) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id, activo=True).first()
    if funcionario is None:
        raise PermisoDenegado("El funcionario no existe o no está activo.")
    if aprobador and not funcionario.puede_aprobar:
        raise PermisoDenegado("Hace falta un funcionario con permiso de aprobación.")
    return funcionario


def _mensaje_retenido(mensaje_id: int) -> Mensaje:
    mensaje = (
        Mensaje.objects.select_related("conversacion", "consulta")
        .filter(pk=mensaje_id)
        .first()
    )
    if mensaje is None:
        raise NoEncontrado("El mensaje no existe.")
    if mensaje.estado_envio != EstadoEnvio.RETENIDO:
        raise EstadoInvalido("El mensaje ya no está retenido.")
    return mensaje


def _conversacion(conversacion_id: int) -> Conversacion:
    conversacion = Conversacion.objects.filter(pk=conversacion_id).first()
    if conversacion is None:
        raise NoEncontrado("La conversación no existe.")
    return conversacion


def _cerrar_alertas(
    mensaje: Mensaje, funcionario: Funcionario, estado: str, resolucion: str
) -> None:
    alertas_abiertas(mensaje_id=mensaje.id).update(
        estado=estado,
        resuelta_por=funcionario,
        resuelta_en=timezone.now(),
        resolucion=resolucion,
    )


def _registrar_revision(
    consulta: ConsultaBot | None, funcionario: Funcionario, texto: str
) -> None:
    if consulta is None:
        return
    consulta.respuesta_corregida = texto
    consulta.revisado_por = funcionario
    consulta.revisado_en = timezone.now()
    consulta.save(
        update_fields=["respuesta_corregida", "revisado_por", "revisado_en"]
    )


def liberar_respuesta(
    mensaje_id: int, funcionario_id: int, texto_corregido: str | None = None
) -> Mensaje:
    """Libera la respuesta retenida, tal cual o reemplazada por otra."""
    funcionario = _funcionario(funcionario_id, aprobador=True)
    mensaje = _mensaje_retenido(mensaje_id)
    corregido = (texto_corregido or "").strip()

    with transaction.atomic():
        conversacion = Conversacion.objects.select_for_update().get(
            pk=mensaje.conversacion_id
        )
        mensaje = Mensaje.objects.select_for_update().get(pk=mensaje_id)
        if mensaje.estado_envio != EstadoEnvio.RETENIDO:
            raise EstadoInvalido("El mensaje ya no está retenido.")
        if corregido:
            # AC-T3-25: lo del bot se descarta y sale el texto del funcionario.
            mensaje.estado_envio = EstadoEnvio.DESCARTADO
            mensaje.save(update_fields=["estado_envio"])
            sale = Mensaje.objects.create(
                conversacion=conversacion,
                consulta=mensaje.consulta,
                direccion=Direccion.SALIENTE,
                emisor=Emisor.FUNCIONARIO,
                funcionario=funcionario,
                texto=corregido,
                estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
                fecha_hora=timezone.now(),
            )
            _cerrar_alertas(
                mensaje, funcionario, EstadoAlerta.RESUELTA, RESOLUCION_CORREGIDA
            )
            _registrar_revision(mensaje.consulta, funcionario, corregido)
        else:
            # AC-T3-24: sale tal cual y las alertas quedan descartadas.
            mensaje.estado_envio = EstadoEnvio.PENDIENTE_ENVIO
            mensaje.save(update_fields=["estado_envio"])
            sale = mensaje
            if mensaje.consulta is not None:
                mensaje.consulta.revisado_por = funcionario
                mensaje.consulta.revisado_en = timezone.now()
                mensaje.consulta.nota_revision = RESOLUCION_LIBERADA
                mensaje.consulta.save(
                    update_fields=["revisado_por", "revisado_en", "nota_revision"]
                )
            _cerrar_alertas(
                mensaje, funcionario, EstadoAlerta.DESCARTADA, RESOLUCION_LIBERADA
            )

    enviar_pendientes(conversacion.id)
    sale.refresh_from_db()
    return sale


def descartar_respuesta(mensaje_id: int, funcionario_id: int, motivo: str) -> Mensaje:
    """Descarta la respuesta retenida: no sale nada al cliente (AC-T3-26)."""
    if not motivo or len(motivo.strip()) < MOTIVO_MINIMO:
        raise DatosInvalidos(
            f"El motivo tiene que tener al menos {MOTIVO_MINIMO} caracteres."
        )
    funcionario = _funcionario(funcionario_id, aprobador=True)
    mensaje = _mensaje_retenido(mensaje_id)
    motivo = motivo.strip()

    with transaction.atomic():
        mensaje.estado_envio = EstadoEnvio.DESCARTADO
        mensaje.error = motivo
        mensaje.save(update_fields=["estado_envio", "error"])
        _cerrar_alertas(mensaje, funcionario, EstadoAlerta.RESUELTA, motivo)
    return mensaje


def tomar_conversacion(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """Toma o reasigna el chat; cualquier funcionario activo puede hacerlo."""
    funcionario = _funcionario(funcionario_id, aprobador=False)
    with transaction.atomic():
        conversacion = (
            Conversacion.objects.select_for_update()
            .filter(pk=conversacion_id)
            .first()
        )
        if conversacion is None:
            raise NoEncontrado("La conversación no existe.")
        if conversacion.estado == EstadoConversacion.CERRADA:
            raise EstadoInvalido("No se puede tomar una conversación cerrada.")
        conversacion.modo = ModoConversacion.HUMANO
        conversacion.funcionario = funcionario
        conversacion.save(update_fields=["modo", "funcionario"])
        descartar_automaticos_pendientes(conversacion.id)
    # Las derivaciones y las respuestas ya liberadas siguen saliendo; la pausa
    # cancela solo las respuestas automáticas comunes que estaban en cola.
    enviar_pendientes(conversacion.id)
    return conversacion


def devolver_al_bot(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """Solo el funcionario asignado puede devolver el chat al bot."""
    funcionario = _funcionario(funcionario_id, aprobador=False)
    with transaction.atomic():
        conversacion = (
            Conversacion.objects.select_for_update()
            .filter(pk=conversacion_id)
            .first()
        )
        if conversacion is None:
            raise NoEncontrado("La conversación no existe.")
        if conversacion.modo != ModoConversacion.HUMANO:
            raise EstadoInvalido("La conversación no está en atención humana.")
        if conversacion.funcionario_id != funcionario.id:
            raise PermisoDenegado(
                "Solo el funcionario asignado puede devolverla al bot."
            )
        conversacion.modo = ModoConversacion.BOT
        conversacion.funcionario = None
        conversacion.save(update_fields=["modo", "funcionario"])
    return conversacion


def responder_como_humano(
    conversacion_id: int, funcionario_id: int, texto: str
) -> Mensaje:
    """Mensaje escrito por un funcionario. Requiere la ventana de 24 h abierta."""
    if not texto or not texto.strip():
        raise DatosInvalidos("El mensaje no puede estar vacío.")
    funcionario = _funcionario(funcionario_id, aprobador=False)
    with transaction.atomic():
        conversacion = (
            Conversacion.objects.select_for_update()
            .filter(pk=conversacion_id)
            .first()
        )
        if conversacion is None:
            raise NoEncontrado("La conversación no existe.")
        if conversacion.modo != ModoConversacion.HUMANO:
            raise EstadoInvalido("La conversación no está en atención humana.")
        if conversacion.funcionario_id != funcionario.id:
            raise PermisoDenegado("Solo el funcionario asignado puede responder.")
        if not ventana_24h_abierta(
            conversacion.ultimo_mensaje_cliente_en, timezone.now()
        ):
            raise EstadoInvalido(
                "Pasaron más de 24 h desde el último mensaje del cliente.",
                codigo="ventana_24h_cerrada",
            )

        mensaje = Mensaje.objects.create(
            conversacion=conversacion,
            direccion=Direccion.SALIENTE,
            emisor=Emisor.FUNCIONARIO,
            funcionario=funcionario,
            texto=texto.strip(),
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            fecha_hora=timezone.now(),
        )
    enviar_pendientes(conversacion.id)
    mensaje.refresh_from_db()
    return mensaje


def reabrir_consulta(consulta_id: int, funcionario_id: int) -> ConsultaBot:
    """Vuelve a poner en revisión una consulta que se había cerrado (AC-T3-29)."""
    _funcionario(funcionario_id, aprobador=True)
    consulta = ConsultaBot.objects.filter(pk=consulta_id).first()
    if consulta is None:
        raise NoEncontrado("La consulta no existe.")
    if consulta.estado != EstadoConsulta.CERRADO:
        raise EstadoInvalido("Solo se puede reabrir una consulta cerrada.")
    consulta.estado = EstadoConsulta.PENDIENTE_REVISION
    consulta.save(update_fields=["estado"])
    return consulta


def cerrar_casos(conversacion_id: int, funcionario_id: int) -> list[ConsultaBot]:
    """Da por terminados los casos de la conversación. El chat queda abierto.

    Cerrar el chat sería otra cosa: lo sacaría de la bandeja y el cliente puede
    volver a escribir sobre lo mismo en cualquier momento. Acá se cierra el
    trabajo —los `CASO-###`—, no el canal.

    Un caso con una respuesta del bot todavía retenida no se cierra: esa
    retención es una decisión pendiente (liberarla, corregirla o descartarla) y
    cerrar el caso la enterraría sin que nadie la haya tomado.
    """
    _funcionario(funcionario_id, aprobador=False)
    _conversacion(conversacion_id)

    abiertos = ConsultaBot.objects.filter(
        conversacion_id=conversacion_id, estado__in=ESTADOS_CASO_ABIERTO
    ).order_by("id")
    casos = list(abiertos)
    if not casos:
        raise EstadoInvalido("La conversación no tiene casos abiertos.")

    retenidas = Mensaje.objects.filter(
        conversacion_id=conversacion_id, estado_envio=EstadoEnvio.RETENIDO
    ).count()
    if retenidas:
        raise EstadoInvalido(
            f"Hay {retenidas} respuesta(s) retenida(s) sin resolver. "
            "Liberalas o descartalas antes de cerrar el caso."
        )

    with transaction.atomic():
        acciones_pendientes = list(
            AccionPendiente.objects.select_for_update()
            .filter(
                consulta_id__in=[caso.pk for caso in casos],
                estado__in=ESTADOS_ACCION_PENDIENTE,
            )
            .order_by("id")
        )
        if acciones_pendientes:
            por_aprobar = sum(
                accion.estado == EstadoAccion.PENDIENTE
                for accion in acciones_pendientes
            )
            gestion_externa = sum(
                accion.estado == EstadoAccion.APROBADA
                for accion in acciones_pendientes
            )
            detalles = []
            if por_aprobar:
                detalles.append(f"{por_aprobar} pendiente(s) de aprobación")
            if gestion_externa:
                detalles.append(
                    f"{gestion_externa} aprobada(s), pendiente(s) de gestión externa"
                )
            raise EstadoInvalido(
                "No se pueden cerrar los casos: quedan acciones administrativas "
                "sin resolver (" + "; ".join(detalles) + "). "
                "Resolvelas o completá su gestión antes de cerrar."
            )
        ConsultaBot.objects.filter(pk__in=[caso.pk for caso in casos]).update(
            estado=EstadoConsulta.CERRADO,
            fecha_resolucion=timezone.localdate(),
        )
    for caso in casos:
        caso.refresh_from_db()
    return casos


def vaciar_chat(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """Borra el contexto del bot: el próximo mensaje arranca de cero.

    Todo lo que el bot recuerda —el historial que le pasa al LLM, el alta de
    datos a medio pedir, cuántas veces preguntó "¿qué necesitás?", los intentos
    de manipulación— se lee de los mensajes **de la conversación**. Así que no
    hace falta borrar nada: se cierra esta y el siguiente mensaje del cliente
    abre una nueva (`whatsapp._conversacion_para`), sin pasado.

    Los mensajes, casos y alertas no se tocan. Son el registro de auditoría, y
    un caso derivado o una alerta abierta siguen pendientes aunque el chat se
    haya vaciado.

    Igual que `cerrar_casos`, no se vacía con una respuesta retenida: es una
    decisión pendiente que quedaría enterrada en una conversación cerrada.
    """
    _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
    if conversacion.estado == EstadoConversacion.CERRADA:
        raise EstadoInvalido("La conversación ya está cerrada.")

    retenidas = Mensaje.objects.filter(
        conversacion_id=conversacion_id, estado_envio=EstadoEnvio.RETENIDO
    ).count()
    if retenidas:
        raise EstadoInvalido(
            f"Hay {retenidas} respuesta(s) retenida(s) sin resolver. "
            "Liberalas o descartalas antes de vaciar el chat."
        )

    conversacion.estado = EstadoConversacion.CERRADA
    conversacion.cerrada_en = timezone.now()
    # La próxima la atiende el bot, como cualquier conversación nueva.
    conversacion.modo = ModoConversacion.BOT
    conversacion.funcionario = None
    conversacion.save(update_fields=["estado", "cerrada_en", "modo", "funcionario"])
    return conversacion


@transaction.atomic
def vaciar_alertas(conversacion_id: int, funcionario_id: int) -> int:
    """Descarta todas las alertas abiertas de la conversación. Devuelve cuántas.

    No se borran: pasan a `descartada`, firmadas por quien las vació, así que
    siguen en el historial pero salen del panel y de los contadores. Es la misma
    salida que tienen las alertas de una respuesta que se descarta.

    Aprobador obligatorio: descartar una alerta es dar por revisado lo que el
    bot dijo o lo que intentó el cliente. Y no se vacía con una respuesta
    retenida, porque esa respuesta existe justamente por una alerta: habría que
    liberarla o descartarla antes, que es lo que cierra sus alertas con criterio.

    Ojo: la alerta de insistencia es la que mantiene bloqueado un número, así que
    vaciarla también lo desbloquea.
    """
    funcionario = _funcionario(funcionario_id, aprobador=True)
    _conversacion(conversacion_id)

    retenidas = Mensaje.objects.filter(
        conversacion_id=conversacion_id, estado_envio=EstadoEnvio.RETENIDO
    ).count()
    if retenidas:
        raise EstadoInvalido(
            f"Hay {retenidas} respuesta(s) retenida(s) sin resolver. "
            "Liberalas o descartalas antes de vaciar las alertas."
        )

    ids = list(
        alertas_abiertas(conversacion_id=conversacion_id).values_list("id", flat=True)
    )
    return Alerta.objects.filter(pk__in=ids).update(
        estado=EstadoAlerta.DESCARTADA,
        resuelta_por=funcionario,
        resuelta_en=timezone.now(),
        resolucion=RESOLUCION_ALERTAS_VACIADAS,
    )


@transaction.atomic
def borrar_conversacion(conversacion_id: int, funcionario_id: int) -> dict[str, int]:
    """Borra la conversación con sus mensajes, casos y alertas. No tiene vuelta atrás.

    Aprobador obligatorio. Se niega si algo del expediente depende de ella: una
    acción administrativa todavía pendiente, un siniestro o una foto de
    siniestro. Esos registros son de auditoría —la base misma impide modificar
    una finalización o un adjunto— y borrarles el chat de origen los dejaría sin
    contexto. Para esos casos existe `vaciar_chat`, que corta el contexto del
    bot sin borrar nada.

    Las acciones ya resueltas (aprobada, rechazada, ejecutada) no bloquean: el
    caso que las respalda se conserva, desvinculado del chat (`conversacion_id`
    nulo) y con su derivación, para que el registro de auditoría siga entero.
    Lo único que sale de la bandeja es el chat, sus mensajes y sus alertas.

    El contacto no se toca: si el cliente vuelve a escribir, arranca una
    conversación nueva.
    """
    _funcionario(funcionario_id, aprobador=True)
    conversacion = (
        Conversacion.objects.select_for_update().filter(pk=conversacion_id).first()
    )
    if conversacion is None:
        raise NoEncontrado("La conversación no existe.")

    casos_chat = ConsultaBot.objects.filter(conversacion_id=conversacion_id)
    todos_los_ids = list(casos_chat.values_list("id", flat=True))
    # Los casos con una acción ya resuelta se conservan como auditoría.
    conservados = set(
        AccionPendiente.objects.filter(consulta_id__in=todos_los_ids)
        .exclude(estado=EstadoAccion.PENDIENTE)
        .values_list("consulta_id", flat=True)
    )
    caso_ids = [pk for pk in todos_los_ids if pk not in conservados]
    casos = ConsultaBot.objects.filter(pk__in=caso_ids)

    dependientes = []
    acciones = AccionPendiente.objects.filter(
        consulta_id__in=todos_los_ids, estado=EstadoAccion.PENDIENTE
    ).count()
    if acciones:
        dependientes.append(f"{acciones} acción(es) administrativa(s) pendiente(s)")
    siniestros = Siniestro.objects.filter(consulta_id__in=todos_los_ids).count()
    if siniestros:
        dependientes.append(f"{siniestros} siniestro(s)")
    adjuntos = AdjuntoSiniestro.objects.filter(
        mensaje_origen__conversacion_id=conversacion_id
    ).count()
    if adjuntos:
        dependientes.append(f"{adjuntos} foto(s) de siniestro")
    if dependientes:
        raise EstadoInvalido(
            "No se puede borrar: tiene " + ", ".join(dependientes) + ", que quedan "
            "como registro de auditoría. Usá «Vaciar chat» para que el bot arranque "
            "sin contexto sin borrar nada."
        )

    mensajes = Mensaje.objects.filter(conversacion_id=conversacion_id)
    cantidad_mensajes = mensajes.count()
    alertas = Alerta.objects.filter(
        Q(consulta_id__in=todos_los_ids) | Q(mensaje__conversacion_id=conversacion_id)
    )
    cantidad_alertas = alertas.count()

    # De las hojas hacia la raíz: la base no cascadea desde la conversación.
    alertas.delete()
    Derivacion.objects.filter(consulta_id__in=caso_ids).delete()
    TrabajoWhatsApp.objects.filter(mensaje__conversacion_id=conversacion_id).delete()
    mensajes.update(respuesta_a=None)
    mensajes.delete()
    casos.delete()
    casos_chat.update(conversacion=None)  # los casos con acción resuelta quedan sueltos
    ContextoCobertura.objects.filter(conversacion_id=conversacion_id).delete()
    conversacion.delete()
    return {
        "mensajes": cantidad_mensajes,
        "casos": len(caso_ids),
        "alertas": cantidad_alertas,
    }


@transaction.atomic
def eliminacion_total(conversacion_id: int, funcionario_id: int) -> dict[str, int]:
    """Borra FÍSICAMENTE todo rastro del número de esta conversación.

    Solo el rol administrador (usuario de pruebas). Es un DELETE real, no una
    marca ni un cambio de estado: tras la eliminación el número queda como uno
    que nunca escribió, y su próximo mensaje arranca desde cero (contacto nuevo,
    interesado nuevo). Borra, en el orden que pide la base:

    alertas, derivaciones, borradores de alta, acciones pendientes (en cualquier
    estado), trabajos de WhatsApp, avisos/encuestas/tareas de gestión,
    recordatorios, mensajes, casos, contexto de cobertura, TODAS las
    conversaciones del número, sus interesados (con historial y cotizaciones) y
    el contacto de WhatsApp.

    No toca al cliente ni a sus pólizas: solo se pierde su vínculo con este
    número. Se niega, sin borrar nada, si hay siniestros, fotos de siniestro o
    acciones finalizadas: la base los declara inmutables y borrarlos es
    manipular un expediente, no limpiar un chat de prueba.

    La auditoría de seguridad no se borra (la base la declara inmutable): solo
    registra la ruta y el usuario, sin teléfonos ni textos.
    """
    funcionario = _funcionario(funcionario_id, aprobador=False)
    if funcionario.rol != Rol.ADMINISTRADOR:
        raise PermisoDenegado("Solo el administrador puede hacer la eliminación total.")

    conversacion = (
        Conversacion.objects.select_for_update().filter(pk=conversacion_id).first()
    )
    if conversacion is None:
        raise NoEncontrado("La conversación no existe.")

    contacto_id = conversacion.contacto_id
    if contacto_id is not None:
        conversaciones = list(
            Conversacion.objects.filter(contacto_id=contacto_id).values_list("id", flat=True)
        )
    else:
        conversaciones = [conversacion_id]
    return borrar_rastro_del_numero(contacto_id, conversaciones)


def borrar_rastro_del_numero(
    contacto_id: int | None, conversaciones: list[int]
) -> dict[str, int]:
    """DELETE físico de todo lo que cuelga de un contacto y sus conversaciones.

    Sin permisos: lo usan `eliminacion_total` y el borrado definitivo de un
    cliente, que ya verificaron que quien llama es administrador. Debe correr
    dentro de una transacción. Se niega, sin borrar nada, ante registros que la
    base declara inmutables.
    """
    filtro_casos = Q(conversacion_id__in=conversaciones)
    if contacto_id is not None:
        filtro_casos |= Q(contacto_id=contacto_id)
    casos = list(ConsultaBot.objects.filter(filtro_casos).values_list("id", flat=True))
    mensajes = list(
        Mensaje.objects.filter(
            Q(conversacion_id__in=conversaciones) | Q(consulta_id__in=casos)
        ).values_list("id", flat=True)
    )
    interesados = (
        list(Interesado.objects.filter(contacto_id=contacto_id).values_list("id", flat=True))
        if contacto_id is not None
        else []
    )

    # Lo inmutable no se toca: se avisa antes de borrar nada.
    bloqueos = []
    n = Siniestro.objects.filter(consulta_id__in=casos).count()
    if n:
        bloqueos.append(f"{n} siniestro(s)")
    n = AdjuntoSiniestro.objects.filter(mensaje_origen_id__in=mensajes).count()
    if n:
        bloqueos.append(f"{n} foto(s) de siniestro")
    n = FinalizacionAccion.objects.filter(accion__consulta_id__in=casos).count()
    if n:
        bloqueos.append(f"{n} acción(es) finalizada(s)")
    if bloqueos:
        raise EstadoInvalido(
            "No se puede hacer la eliminación total: hay " + ", ".join(bloqueos)
            + ", que la base declara inmutables. No se borró nada."
        )

    alertas, _ = Alerta.objects.filter(
        Q(consulta_id__in=casos) | Q(mensaje_id__in=mensajes)
    ).delete()
    Derivacion.objects.filter(consulta_id__in=casos).delete()
    BorradorPoliza.objects.filter(
        Q(conversacion_id__in=conversaciones)
        | Q(accion__consulta_id__in=casos)
        | Q(ultimo_mensaje_id__in=mensajes)
    ).delete()
    acciones, _ = AccionPendiente.objects.filter(consulta_id__in=casos).delete()
    TrabajoWhatsApp.objects.filter(mensaje_id__in=mensajes).delete()
    with connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM gestion_avisos WHERE contacto_id = %s OR mensaje_id = ANY(%s)"
            " OR interesado_id = ANY(%s)",
            [contacto_id, mensajes, interesados],
        )
        cursor.execute("DELETE FROM gestion_encuestas WHERE contacto_id = %s", [contacto_id])
        cursor.execute("DELETE FROM gestion_tareas WHERE interesado_id = ANY(%s)", [interesados])
    RecordatorioPoliza.objects.filter(
        Q(contacto_id=contacto_id) | Q(mensaje_id__in=mensajes)
    ).delete()
    from negocio.adjuntos_chat import borrar_archivos_de_mensajes

    borrar_archivos_de_mensajes(mensajes)
    Mensaje.objects.filter(pk__in=mensajes).update(respuesta_a=None)
    Mensaje.objects.filter(pk__in=mensajes).delete()
    ConsultaBot.objects.filter(pk__in=casos).delete()
    ContextoCobertura.objects.filter(conversacion_id__in=conversaciones).delete()
    Conversacion.objects.filter(pk__in=conversaciones).delete()
    Cotizacion.objects.filter(interesado_id__in=interesados).delete()
    InteresadoHistorial.objects.filter(interesado_id__in=interesados).delete()
    Interesado.objects.filter(pk__in=interesados).delete()
    if contacto_id is not None:
        ContactoWhatsapp.objects.filter(pk=contacto_id).delete()
    return {
        "conversaciones": len(conversaciones),
        "mensajes": len(mensajes),
        "casos": len(casos),
        "alertas": alertas,
        "acciones": acciones,
        "interesados": len(interesados),
        "contacto": 1 if contacto_id is not None else 0,
    }


@transaction.atomic
def desbloquear_numero(conversacion_id: int, funcionario_id: int) -> Conversacion:
    funcionario = _funcionario(funcionario_id, aprobador=True)
    conversacion = _conversacion(conversacion_id)

    if conversacion.contacto_id is None:
        raise EstadoInvalido("La conversación no tiene un contacto asociado.")

    from negocio.bot.orquestador import (
        _ultima_insistencia,
        DURACION_BLOQUEO,
    )

    insistencia = _ultima_insistencia(conversacion.contacto_id)

    if (
        insistencia is None
        or insistencia.estado != EstadoAlerta.ABIERTA
        or insistencia.creada_en + DURACION_BLOQUEO <= timezone.now()
    ):
        raise EstadoInvalido("El número no está bloqueado.")

    insistencia.estado = EstadoAlerta.RESUELTA
    insistencia.resuelta_por = funcionario
    insistencia.resuelta_en = timezone.now()
    insistencia.resolucion = RESOLUCION_DESBLOQUEO

    insistencia.save(
        update_fields=[
            "estado",
            "resuelta_por",
            "resuelta_en",
            "resolucion",
        ]
    )

    return conversacion
