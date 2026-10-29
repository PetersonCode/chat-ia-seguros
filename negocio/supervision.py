"""Supervisión humana: qué hace un funcionario con lo que el bot retuvo.

Un mensaje `retenido` nunca sale solo: alguien lo libera tal cual, lo corrige o
lo descarta. Las tres cosas cierran las alertas que lo retuvieron, y las dos
primeras disparan el envío.

Aprobador obligatorio en `liberar_respuesta`, `descartar_respuesta`,
`reabrir_consulta` (contrato, sección 6) y `desbloquear_numero`.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from datos.models import (
    Conversacion,
    ConsultaBot,
    Direccion,
    Emisor,
    EstadoAlerta,
    EstadoConsulta,
    EstadoConversacion,
    EstadoEnvio,
    Funcionario,
    Mensaje,
    ModoConversacion,
)
from datos.selectors import alertas_abiertas
from negocio.bot.orquestador import RESOLUCION_DESBLOQUEO, bloqueo_vigente
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)
from negocio.reglas import ventana_24h_abierta
from negocio.whatsapp import enviar_pendientes

# Un caso sigue "vivo" mientras esté en alguno de estos estados.
ESTADOS_CASO_ABIERTO = (
    EstadoConsulta.ABIERTO,
    EstadoConsulta.PENDIENTE_REVISION,
    EstadoConsulta.DERIVADO,
)

MOTIVO_MINIMO = 5
RESOLUCION_LIBERADA = "Liberada sin cambios"
RESOLUCION_CORREGIDA = "Respuesta corregida por el funcionario"


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
    conversacion = mensaje.conversacion
    corregido = (texto_corregido or "").strip()

    with transaction.atomic():
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
    """El funcionario se queda con la conversación y el bot deja de responder."""
    funcionario = _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
    conversacion.modo = ModoConversacion.HUMANO
    conversacion.funcionario = funcionario
    conversacion.save(update_fields=["modo", "funcionario"])
    return conversacion


def devolver_al_bot(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """Devuelve la conversación al bot y la deja sin responsable."""
    _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
    conversacion.modo = ModoConversacion.BOT
    conversacion.funcionario = None
    conversacion.save(update_fields=["modo", "funcionario"])
    return conversacion


def desbloquear_numero(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """Levanta antes de tiempo el bloqueo de 48 horas por insistencia.

    El bloqueo es del número, no de la conversación, así que vale desde
    cualquiera de sus chats. Se resuelve la alerta de insistencia con una
    resolución fija: queda registrado quién y cuándo, y como sigue siendo la
    última insistencia, la cuenta de intentos arranca de cero igual que cuando
    vencen las 48 horas.
    """
    funcionario = _funcionario(funcionario_id, aprobador=True)
    conversacion = _conversacion(conversacion_id)
    insistencia = (
        bloqueo_vigente(conversacion.contacto_id)
        if conversacion.contacto_id is not None
        else None
    )
    if insistencia is None:
        raise EstadoInvalido("El número no está bloqueado.")
    insistencia.estado = EstadoAlerta.RESUELTA
    insistencia.resuelta_por = funcionario
    insistencia.resuelta_en = timezone.now()
    insistencia.resolucion = RESOLUCION_DESBLOQUEO
    insistencia.save(
        update_fields=["estado", "resuelta_por", "resuelta_en", "resolucion"]
    )
    return conversacion


def responder_como_humano(
    conversacion_id: int, funcionario_id: int, texto: str
) -> Mensaje:
    """Mensaje escrito por un funcionario. Requiere la ventana de 24 h abierta."""
    if not texto or not texto.strip():
        raise DatosInvalidos("El mensaje no puede estar vacío.")
    funcionario = _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
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
