"""El canal WhatsApp: recibir, enviar y seguir el estado de entrega.

`WHATSAPP_MODO=simulado` (lo normal en desarrollo) no toca la red: marca los
mensajes como enviados y los escribe en el log. `real` usa la API de WhatsApp
Cloud con `urllib`.

Solo sale lo que está en `pendiente_envio` (R14): `retenido` y `descartado`
nunca se envían.
"""

import hashlib
import hmac
import json
import logging
import os
import threading
from urllib import request
from urllib.error import HTTPError

from django.db import close_old_connections
from django.utils import timezone

from datos.limpieza import normalizar_telefono
from datos.models import (
    ContactoWhatsapp,
    Conversacion,
    Direccion,
    Emisor,
    EstadoConversacion,
    EstadoEnvio,
    Mensaje,
    ModoConversacion,
)
from datos.selectors import contacto_por_numero, conversacion_abierta
from negocio.reglas import ventana_24h_abierta

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10

# Orden de avance de la entrega: un estado nunca vuelve para atrás (AC-T3-11).
ORDEN_ENTREGA = {
    EstadoEnvio.PENDIENTE_ENVIO: 0,
    EstadoEnvio.ENVIADO: 1,
    EstadoEnvio.ENTREGADO: 2,
    EstadoEnvio.LEIDO: 3,
}
ESTADO_POR_STATUS = {
    "sent": EstadoEnvio.ENVIADO,
    "delivered": EstadoEnvio.ENTREGADO,
    "read": EstadoEnvio.LEIDO,
    "failed": EstadoEnvio.FALLIDO,
}
# `failed` no puede pisar una entrega ya confirmada.
NO_ADMITEN_FALLIDO = {EstadoEnvio.ENTREGADO, EstadoEnvio.LEIDO}
NO_SE_ENVIAN = {
    EstadoEnvio.RETENIDO,
    EstadoEnvio.DESCARTADO,
    EstadoEnvio.ENVIADO,
    EstadoEnvio.ENTREGADO,
    EstadoEnvio.LEIDO,
    EstadoEnvio.FALLIDO,
}


def _normalizar_numero(numero_raw: str | None) -> str:
    """Usa la normalización de T4; si el número es impresentable, lo deja crudo."""
    try:
        return normalizar_telefono(numero_raw or "")
    except ValueError:
        logger.warning("Número de WhatsApp con formato inesperado: %r", numero_raw)
        return (numero_raw or "").strip()


def verificar_suscripcion(
    mode: str | None, token: str | None, challenge: str | None
) -> str | None:
    esperado = os.getenv("WHATSAPP_VERIFY_TOKEN")
    if mode == "subscribe" and token and esperado and token == esperado and challenge:
        return challenge
    return None


def verificar_firma(cuerpo: bytes, firma: str | None) -> bool:
    if not firma or not firma.startswith("sha256="):
        return False
    secreto = os.getenv("WHATSAPP_APP_SECRET", "")
    digest = hmac.new(secreto.encode("utf-8"), cuerpo or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", firma)


def en_segundo_plano(funcion, *args) -> None:
    """Corre `funcion` en un hilo. Una excepción adentro se loguea y muere ahí."""

    def _correr():
        try:
            funcion(*args)
        except Exception:
            logger.exception("Falló una tarea en segundo plano: %s", funcion)
        finally:
            close_old_connections()

    threading.Thread(target=_correr, daemon=True).start()


def _conversacion_para(contacto: ContactoWhatsapp) -> Conversacion:
    """La conversación abierta del contacto, o una nueva si no hay (AC-T3-07)."""
    conversacion = conversacion_abierta(contacto.id)
    if conversacion is not None:
        return conversacion
    return Conversacion.objects.create(
        contacto=contacto,
        estado=EstadoConversacion.ABIERTA,
        modo=ModoConversacion.BOT,
    )


def registrar_entrante(
    wa_message_id: str,
    numero_raw: str,
    texto: str,
    payload: dict | None = None,
    nombre_perfil: str | None = None,
) -> Mensaje | None:
    """Guarda un mensaje del cliente. `None` si el `wa_message_id` ya estaba."""
    if not wa_message_id:
        return None
    if Mensaje.objects.filter(wa_message_id=wa_message_id).exists():
        return None

    numero = _normalizar_numero(numero_raw)
    contacto = contacto_por_numero(numero)
    if contacto is None:
        contacto = ContactoWhatsapp.objects.create(
            numero=numero, cliente=None, nombre_perfil=nombre_perfil
        )
    elif nombre_perfil and not contacto.nombre_perfil:
        # Se completa una sola vez: los contactos que ya existían no lo tienen,
        # y no se pisa un nombre ya guardado en cada mensaje.
        contacto.nombre_perfil = nombre_perfil
        contacto.save(update_fields=["nombre_perfil"])
    conversacion = _conversacion_para(contacto)

    mensaje = Mensaje.objects.create(
        conversacion=conversacion,
        direccion=Direccion.ENTRANTE,
        emisor=Emisor.CLIENTE,
        texto=texto,
        estado_envio=EstadoEnvio.RECIBIDO,
        wa_message_id=wa_message_id,
        payload=payload,
        fecha_hora=timezone.now(),
    )
    conversacion.ultimo_mensaje_cliente_en = mensaje.fecha_hora
    conversacion.save(update_fields=["ultimo_mensaje_cliente_en"])
    return mensaje


def _avisar_solo_texto(conversacion: Conversacion) -> None:
    """AC-T3-09: a un adjunto se le contesta que solo leemos texto."""
    from negocio.bot.plantillas import SOLO_TEXTO

    Mensaje.objects.create(
        conversacion=conversacion,
        direccion=Direccion.SALIENTE,
        emisor=Emisor.BOT,
        texto=SOLO_TEXTO,
        estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
        fecha_hora=timezone.now(),
    )
    enviar_pendientes(conversacion.id)


def procesar_webhook(payload: dict) -> None:
    """Recorre el payload de Meta. Nunca lanza: lo raro va al log (AC-T3-10)."""
    from negocio.bot.orquestador import procesar_mensaje

    try:
        for entry in (payload or {}).get("entry", []) or []:
            for cambio in entry.get("changes", []) or []:
                valor = cambio.get("value", {}) or {}
                # Meta manda el nombre de perfil aparte de los mensajes, en
                # `contacts`. Es lo único que sabemos de un desconocido, y sirve
                # para prellenar su alta como cliente desde el panel.
                perfiles = {
                    str(contacto.get("wa_id")): (contacto.get("profile") or {}).get("name")
                    for contacto in (valor.get("contacts") or [])
                    if contacto.get("wa_id")
                }
                for entrante in valor.get("messages", []) or []:
                    wa_message_id = entrante.get("id")
                    numero = entrante.get("from")
                    if not wa_message_id or not numero:
                        logger.warning("Mensaje de WhatsApp sin id o sin número: %s", entrante)
                        continue
                    tipo = entrante.get("type")
                    es_texto = tipo == "text"
                    texto = (
                        (entrante.get("text", {}) or {}).get("body", "")
                        if es_texto
                        else f"[mensaje de tipo {tipo or 'desconocido'} no soportado]"
                    )
                    mensaje = registrar_entrante(
                        wa_message_id,
                        numero,
                        texto,
                        payload=entrante,
                        nombre_perfil=perfiles.get(str(numero)),
                    )
                    if mensaje is None:
                        continue
                    if es_texto:
                        en_segundo_plano(procesar_mensaje, mensaje.id)
                    else:
                        _avisar_solo_texto(mensaje.conversacion)
                for estado in valor.get("statuses", []) or []:
                    wa_message_id = estado.get("id")
                    nombre = estado.get("status")
                    if wa_message_id and nombre:
                        actualizar_estado_entrega(wa_message_id, nombre)
    except Exception:
        logger.exception("Payload de WhatsApp con forma inesperada: %s", payload)


def actualizar_estado_entrega(wa_message_id: str, estado: str) -> None:
    """Avanza el estado de entrega de un saliente. Solo hacia adelante."""
    if not wa_message_id:
        return
    nuevo = ESTADO_POR_STATUS.get(estado)
    if nuevo is None:
        return
    mensaje = Mensaje.objects.filter(wa_message_id=wa_message_id).first()
    if mensaje is None:
        return

    actual = mensaje.estado_envio
    if nuevo == EstadoEnvio.FALLIDO:
        if actual in NO_ADMITEN_FALLIDO:
            return
    elif ORDEN_ENTREGA.get(nuevo, 0) <= ORDEN_ENTREGA.get(actual, -1):
        return

    mensaje.estado_envio = nuevo
    mensaje.save(update_fields=["estado_envio"])


def _destino_api(numero: str) -> str:
    """El número como lo quiere la API de envío, no como lo guardamos.

    WhatsApp identifica a los móviles argentinos con un 9 después del 54
    (`5491126914442`): así llega en el `from` del webhook y así queda en la base.
    Pero la API de envío rechaza ese formato con `(#131030) Recipient phone
    number not in allowed list`, aunque el número esté autorizado. Para
    Argentina hay que mandarlo sin ese 9; Meta devuelve igual el `wa_id` con 9.
    Sin esto no sale un solo mensaje a un número argentino.
    """
    destino = str(numero).lstrip("+")
    if destino.startswith("549") and len(destino) == 13:
        return "54" + destino[3:]
    return destino


def _detalle_error_meta(fallo: HTTPError) -> str:
    """El motivo que manda Meta, que `str(HTTPError)` se come.

    `str(fallo)` es solo "HTTP Error 400: Bad Request": el motivo real
    (p. ej. "(#131030) Recipient phone number not in allowed list") viaja en el
    JSON del cuerpo, y si no se lee acá se pierde y el mensaje queda `fallido`
    sin explicación.
    """
    try:
        datos = json.loads(fallo.read().decode("utf-8"))
    except Exception:
        return str(fallo)
    detalle = (datos.get("error") or {}).get("message")
    return f"HTTP {fallo.code}: {detalle}" if detalle else str(fallo)


def _enviar_por_api(mensaje: Mensaje) -> None:
    """POST a la API de WhatsApp Cloud. Lanza si la red o la API fallan."""
    url = (
        f"https://graph.facebook.com/{os.getenv('WHATSAPP_API_VERSION', 'v21.0')}"
        f"/{os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')}/messages"
    )
    cuerpo = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": _destino_api(mensaje.conversacion.contacto.numero),
            "type": "text",
            "text": {"body": mensaje.texto},
        }
    ).encode("utf-8")
    peticion = request.Request(
        url,
        data=cuerpo,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.getenv('WHATSAPP_ACCESS_TOKEN', '')}",
        },
        method="POST",
    )
    try:
        with request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except HTTPError as fallo:
        raise RuntimeError(_detalle_error_meta(fallo)) from fallo
    mensajes = datos.get("messages") or [{}]
    mensaje.wa_message_id = mensajes[0].get("id")


def enviar_pendientes(conversacion_id: int) -> int:
    """Envía los salientes `pendiente_envio` de la conversación. Devuelve cuántos."""
    conversacion = Conversacion.objects.filter(pk=conversacion_id).first()
    if conversacion is None:
        return 0

    pendientes = Mensaje.objects.filter(
        conversacion_id=conversacion_id,
        direccion=Direccion.SALIENTE,
        estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
    ).order_by("fecha_hora", "id")

    # AC-T3-15: fuera de la ventana de 24 h WhatsApp no deja escribir libre.
    if not ventana_24h_abierta(conversacion.ultimo_mensaje_cliente_en, timezone.now()):
        for mensaje in pendientes:
            mensaje.estado_envio = EstadoEnvio.FALLIDO
            mensaje.error = "ventana_24h_cerrada"
            mensaje.save(update_fields=["estado_envio", "error"])
        return 0

    simulado = os.getenv("WHATSAPP_MODO", "simulado").strip().lower() != "real"
    enviados = 0
    for mensaje in pendientes:
        if mensaje.estado_envio in NO_SE_ENVIAN:
            continue
        if simulado:
            mensaje.estado_envio = EstadoEnvio.ENVIADO
            mensaje.enviado_en = timezone.now()
            mensaje.save(update_fields=["estado_envio", "enviado_en"])
            logger.info(
                "WhatsApp simulado | conversación %s | mensaje %s | %s",
                conversacion_id,
                mensaje.id,
                mensaje.texto,
            )
            enviados += 1
            continue
        try:
            _enviar_por_api(mensaje)
        except Exception as error:
            mensaje.estado_envio = EstadoEnvio.FALLIDO
            mensaje.error = str(error)
            mensaje.save(update_fields=["estado_envio", "error"])
            logger.warning("Falló el envío del mensaje %s: %s", mensaje.id, error)
            continue
        mensaje.estado_envio = EstadoEnvio.ENVIADO
        mensaje.enviado_en = timezone.now()
        mensaje.save(update_fields=["wa_message_id", "estado_envio", "enviado_en"])
        enviados += 1
    return enviados
