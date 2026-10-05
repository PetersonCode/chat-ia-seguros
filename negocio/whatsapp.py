import hashlib
import hmac
import json
import logging
import os
import threading
from typing import Any
from urllib import request, error

from django.db import close_old_connections
from django.utils import timezone

from datos.models import (
    ContactoWhatsapp,
    Conversacion,
    EstadoConversacion,
    EstadoEnvio,
    Mensaje,
)
from datos.selectors import contacto_por_numero, conversacion_abierta
from negocio.errores import EstadoInvalido

logger = logging.getLogger(__name__)


def _normalizar_numero(numero_raw: str | None) -> str:
    if not numero_raw:
        return ""
    numero = numero_raw.strip()
    numero = numero.replace(" ", "").replace("-", "")
    if numero.startswith("+"):
        numero = numero[1:]
    if numero.startswith("549"):
        return "+549" + numero[3:]
    if numero.startswith("54"):
        return "+54" + numero[2:]
    if numero.startswith("11"):
        return "+54911" + numero[2:]
    if numero.startswith("9"):
        return "+549" + numero
    return "+549" + numero.lstrip("0")


def verificar_suscripcion(mode: str | None, token: str | None, challenge: str | None) -> str | None:
    if mode == "subscribe" and token == os.getenv("WHATSAPP_VERIFY_TOKEN") and challenge:
        return challenge
    return None


def verificar_firma(cuerpo: bytes, firma: str | None) -> bool:
    if firma is None:
        return False
    if not firma.startswith("sha256="):
        return False
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    digest = hmac.new(secret.encode("utf-8"), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", firma)


def en_segundo_plano(funcion, *args) -> None:
    def _runner():
        try:
            funcion(*args)
        except Exception:
            logger.exception("Error en ejecución en segundo plano")
        finally:
            close_old_connections()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()


def registrar_entrante(wa_message_id: str, numero_raw: str, texto: str, payload: dict | None = None, nombre_perfil: str | None = None) -> Mensaje | None:
    if not wa_message_id:
        return None
    if Mensaje.objects.filter(wa_message_id=wa_message_id).exists():
        return None
    numero = _normalizar_numero(numero_raw)
    contacto = contacto_por_numero(numero)
    if contacto is None:
        contacto = ContactoWhatsapp.objects.create(numero=numero, cliente=None, nombre_perfil=nombre_perfil)
    conversacion = conversacion_abierta(contacto.id)
    if conversacion is None:
        conversacion = Conversacion.objects.create(
            contacto=contacto,
            estado=EstadoConversacion.ABIERTA,
            modo="bot",
            ultimo_mensaje_cliente_en=timezone.now(),
        )
    else:
        conversacion.estado = EstadoConversacion.ABIERTA
        conversacion.modo = "bot"
        conversacion.save(update_fields=["estado", "modo"])
    mensaje = Mensaje.objects.create(
        conversacion=conversacion,
        direccion="entrante",
        emisor="cliente",
        texto=texto,
        estado_envio=EstadoEnvio.RECIBIDO,
        wa_message_id=wa_message_id,
        payload=payload,
        fecha_hora=timezone.now(),
    )
    conversacion.ultimo_mensaje_cliente_en = mensaje.fecha_hora
    conversacion.save(update_fields=["ultimo_mensaje_cliente_en"])
    en_segundo_plano(_procesar_mensaje_luego, mensaje.id)
    return mensaje


def _procesar_mensaje_luego(mensaje_id: int) -> None:
    from negocio.bot.orquestador import procesar_mensaje

    procesar_mensaje(mensaje_id)


def procesar_webhook(payload: dict) -> None:
    try:
        entries = payload.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                for mensaje in value.get("messages", []):
                    text = mensaje.get("text", {}).get("body") if mensaje.get("type") == "text" else None
                    if text is None:
                        tipo = mensaje.get("type", "desconocido")
                        texto = f"[mensaje de tipo {tipo} no soportado]"
                        wa_message_id = mensaje.get("id")
                        numero = mensaje.get("from")
                        if wa_message_id and numero:
                            registrar_entrante(wa_message_id, numero, texto, payload=mensaje)
                        continue
                    wa_message_id = mensaje.get("id")
                    numero = mensaje.get("from")
                    if wa_message_id and numero:
                        registrar_entrante(wa_message_id, numero, text, payload=mensaje)
                for status in value.get("statuses", []):
                    wa_message_id = status.get("id")
                    estado = status.get("status")
                    if wa_message_id and estado:
                        actualizar_estado_entrega(wa_message_id, estado)
    except Exception:
        logger.exception("Payload de WhatsApp con formato inesperado: %s", payload)


def actualizar_estado_entrega(wa_message_id: str, estado: str) -> None:
    if not wa_message_id:
        return
    mensaje = Mensaje.objects.filter(wa_message_id=wa_message_id).first()
    if mensaje is None:
        return
    mapa = {
        "sent": "enviado",
        "delivered": "entregado",
        "read": "leido",
        "failed": "fallido",
    }
    nuevo = mapa.get(estado)
    if nuevo is None:
        return
    actual = mensaje.estado_envio
    if nuevo == "enviado":
        if actual in {"pendiente_envio", "retenido", "descartado", "enviado", "entregado", "leido", "fallido"}:
            mensaje.estado_envio = "enviado"
    elif nuevo == "entregado":
        if actual not in {"entregado", "leido", "fallido"}:
            mensaje.estado_envio = "entregado"
    elif nuevo == "leido":
        if actual not in {"leido", "fallido"}:
            mensaje.estado_envio = "leido"
    elif nuevo == "fallido":
        if actual not in {"entregado", "leido"}:
            mensaje.estado_envio = "fallido"
    mensaje.save(update_fields=["estado_envio"])


def enviar_pendientes(conversacion_id: int) -> int:
    mensajes = Mensaje.objects.filter(
        conversacion_id=conversacion_id,
        direccion="saliente",
        estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
    ).order_by("fecha_hora")
    enviados = 0
    for mensaje in mensajes:
        if mensaje.estado_envio in {EstadoEnvio.RETENIDO, EstadoEnvio.DESCARTADO, EstadoEnvio.ENVIADO, EstadoEnvio.FALLIDO}:
            continue
        if os.getenv("WHATSAPP_MODO", "simulado") == "simulado":
            mensaje.estado_envio = EstadoEnvio.ENVIADO
            mensaje.enviado_en = timezone.now()
            logger.info("WhatsApp simulado: envío de mensaje %s a %s", mensaje.id, conversacion_id)
            mensaje.save(update_fields=["estado_envio", "enviado_en"])
            enviados += 1
            continue
        try:
            access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
            phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
            api_version = os.getenv("WHATSAPP_API_VERSION", "v17.0")
            url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": str(mensaje.conversacion.contacto.numero).replace("+", ""),
                "type": "text",
                "text": {"body": mensaje.texto},
            }
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                method="POST",
            )
            with request.urlopen(req, timeout=10) as resp:
                response = json.loads(resp.read().decode("utf-8"))
            wa_message_id = response.get("messages", [{}])[0].get("id")
            mensaje.wa_message_id = wa_message_id
            mensaje.estado_envio = EstadoEnvio.ENVIADO
            mensaje.enviado_en = timezone.now()
            mensaje.save(update_fields=["wa_message_id", "estado_envio", "enviado_en"])
            enviados += 1
        except Exception as exc:  # pragma: no cover - red real se simula en tests
            mensaje.estado_envio = EstadoEnvio.FALLIDO
            mensaje.error = str(exc)
            mensaje.save(update_fields=["estado_envio", "error"])
    return enviados
