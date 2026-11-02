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
from datetime import timedelta
from urllib import request
from urllib.error import HTTPError

from django.db import IntegrityError, transaction
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
    TipoTrabajoWhatsApp,
    TrabajoWhatsApp,
)
from datos.selectors import contacto_por_numero, conversacion_abierta
from negocio.reglas import ventana_24h_abierta

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 10
MAX_INTENTOS_ENVIO = 8

# Con qué arranca el texto que se guarda cuando llega algo que no es texto.
# Es un marcador nuestro, no palabras del cliente: `orquestador` lo usa para
# dejar esos mensajes afuera de la agrupación, aunque durante la atención
# humana no se genere la respuesta automática.
PREFIJO_NO_SOPORTADO = "[mensaje de tipo "

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
    if not secreto:
        return False
    digest = hmac.new(secreto.encode("utf-8"), cuerpo or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", firma)


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
    try:
        with transaction.atomic():
            if Mensaje.objects.filter(wa_message_id=wa_message_id).exists():
                return None

            numero = _normalizar_numero(numero_raw)
            contacto = contacto_por_numero(numero)
            if contacto is None:
                contacto = ContactoWhatsapp.objects.create(
                    numero=numero, cliente=None, nombre_perfil=nombre_perfil
                )
            elif nombre_perfil and not contacto.nombre_perfil:
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
    except IntegrityError:
        # Meta puede reenviar en paralelo el mismo evento. La restricción única
        # sobre wa_message_id decide cuál petición lo registra.
        if Mensaje.objects.filter(wa_message_id=wa_message_id).exists():
            return None
        raise


def _avisar_solo_texto(mensaje: Mensaje) -> None:
    """Explica qué formatos se pueden recibir por este canal."""
    from negocio.bot.plantillas import SOLO_TEXTO

    conversacion_id = mensaje.conversacion_id
    with transaction.atomic():
        conversacion = Conversacion.objects.select_for_update().get(
            pk=conversacion_id
        )
        if conversacion.modo == ModoConversacion.HUMANO:
            return
        Mensaje.objects.get_or_create(
            respuesta_a=mensaje,
            defaults={
                "conversacion": conversacion,
                "direccion": Direccion.SALIENTE,
                "emisor": Emisor.BOT,
                "texto": SOLO_TEXTO,
                "estado_envio": EstadoEnvio.PENDIENTE_ENVIO,
                "fecha_hora": timezone.now(),
            },
        )
    enviar_pendientes(conversacion_id)


def _procesar_imagen_siniestro(mensaje_id: int) -> None:
    from negocio.adjuntos_siniestros import procesar_media_entrante
    from negocio.bot.orquestador import ignorar_si_bloqueado
    from negocio.bot.plantillas import (
        FOTO_SINIESTRO_ERROR,
        FOTO_SINIESTRO_EXPEDIENTE,
        FOTO_SINIESTRO_INCORPORADA,
        FOTO_SINIESTRO_INVALIDA,
    )

    mensaje = Mensaje.objects.select_related("conversacion").filter(
        pk=mensaje_id
    ).first()
    if mensaje is None or ignorar_si_bloqueado(mensaje):
        return
    resultado = procesar_media_entrante(mensaje_id)
    respuestas = {
        "falta_expediente": FOTO_SINIESTRO_EXPEDIENTE,
        "sin_vinculacion": FOTO_SINIESTRO_ERROR,
        "expediente_no_verificado": FOTO_SINIESTRO_ERROR,
        "error_descarga": FOTO_SINIESTRO_ERROR,
        "invalido": FOTO_SINIESTRO_INVALIDA,
    }
    if resultado.estado == "incorporado":
        texto = FOTO_SINIESTRO_INCORPORADA.format(
            numero_siniestro=resultado.numero_siniestro
        )
    elif resultado.estado == "ya_procesado":
        texto = FOTO_SINIESTRO_INCORPORADA.format(
            numero_siniestro=resultado.numero_siniestro
        )
    elif resultado.estado in respuestas:
        texto = respuestas[resultado.estado]
    else:
        return

    with transaction.atomic():
        conversacion = Conversacion.objects.select_for_update().filter(
            pk=mensaje.conversacion_id
        ).first()
        if (
            conversacion is None
            or conversacion.modo == ModoConversacion.HUMANO
            or ignorar_si_bloqueado(mensaje)
        ):
            return
        Mensaje.objects.get_or_create(
            respuesta_a=mensaje,
            defaults={
                "conversacion": conversacion,
                "direccion": Direccion.SALIENTE,
                "emisor": Emisor.BOT,
                "texto": texto,
                "estado_envio": EstadoEnvio.PENDIENTE_ENVIO,
                "fecha_hora": timezone.now(),
            },
        )
    enviar_pendientes(mensaje.conversacion_id)


def procesar_webhook(payload: dict) -> None:
    """Persiste mensajes y tareas antes de permitir que el webhook responda 200."""
    if not isinstance(payload, dict):
        logger.warning("Payload de WhatsApp con forma inesperada.")
        return

    entries = payload.get("entry", []) or []
    if not isinstance(entries, list):
        logger.warning("Payload de WhatsApp con entry no válido.")
        return

    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("Entrada de WhatsApp con forma inesperada.")
            continue
        cambios = entry.get("changes", []) or []
        if not isinstance(cambios, list):
            logger.warning("Cambios de WhatsApp con forma inesperada.")
            continue
        for cambio in cambios:
            if not isinstance(cambio, dict):
                logger.warning("Cambio de WhatsApp con forma inesperada.")
                continue
            valor = cambio.get("value", {}) or {}
            if not isinstance(valor, dict):
                logger.warning("Valor de cambio de WhatsApp con forma inesperada.")
                continue

            perfiles = {}
            contactos = valor.get("contacts", []) or []
            if isinstance(contactos, list):
                for contacto in contactos:
                    if not isinstance(contacto, dict) or not contacto.get("wa_id"):
                        continue
                    perfil = contacto.get("profile") or {}
                    if isinstance(perfil, dict):
                        perfiles[str(contacto["wa_id"])] = perfil.get("name")

            mensajes = valor.get("messages", []) or []
            if isinstance(mensajes, list):
                for entrante in mensajes:
                    if not isinstance(entrante, dict):
                        logger.warning("Mensaje de WhatsApp con forma inesperada.")
                        continue
                    wa_message_id = entrante.get("id")
                    numero = entrante.get("from")
                    if not wa_message_id or not numero:
                        logger.warning("Mensaje de WhatsApp sin id o sin número.")
                        continue

                    tipo = entrante.get("type")
                    es_texto = tipo == "text"
                    es_imagen = tipo == "image" and isinstance(
                        entrante.get("image"), dict
                    )
                    cuerpo_texto = entrante.get("text") or {}
                    if not isinstance(cuerpo_texto, dict):
                        cuerpo_texto = {}
                    texto = (
                        cuerpo_texto.get("body", "")
                        if es_texto
                        else f"{PREFIJO_NO_SOPORTADO}{tipo or 'desconocido'} no soportado]"
                    )
                    payload_entrante = entrante
                    if es_imagen:
                        payload_entrante = dict(entrante)
                        payload_entrante["image"] = {
                            clave: dato
                            for clave, dato in entrante["image"].items()
                            if clave != "url"
                        }
                    tipo_trabajo = (
                        TipoTrabajoWhatsApp.TEXTO
                        if es_texto
                        else (
                            TipoTrabajoWhatsApp.IMAGEN
                            if es_imagen
                            else TipoTrabajoWhatsApp.AVISO_FORMATO
                        )
                    )
                    with transaction.atomic():
                        mensaje = registrar_entrante(
                            wa_message_id,
                            numero,
                            texto,
                            payload=payload_entrante,
                            nombre_perfil=perfiles.get(str(numero)),
                        )
                        if mensaje is None:
                            mensaje = Mensaje.objects.filter(
                                wa_message_id=wa_message_id,
                                direccion=Direccion.ENTRANTE,
                            ).first()
                        if mensaje is not None:
                            TrabajoWhatsApp.objects.get_or_create(
                                mensaje=mensaje,
                                defaults={"tipo": tipo_trabajo},
                            )

            estados = valor.get("statuses", []) or []
            if isinstance(estados, list):
                for estado in estados:
                    if not isinstance(estado, dict):
                        logger.warning("Estado de entrega de WhatsApp no válido.")
                        continue
                    wa_message_id = estado.get("id")
                    nombre = estado.get("status")
                    if wa_message_id and nombre:
                        actualizar_estado_entrega(wa_message_id, nombre)


def ejecutar_trabajo_whatsapp(trabajo_id: int) -> None:
    """Ejecuta el trabajo ya reclamado por el comando persistente."""
    trabajo = TrabajoWhatsApp.objects.select_related(
        "mensaje__conversacion"
    ).get(pk=trabajo_id)
    from negocio.bot.orquestador import ignorar_si_bloqueado, procesar_tras_ventana

    mensaje = trabajo.mensaje
    if ignorar_si_bloqueado(mensaje):
        return
    if trabajo.tipo == TipoTrabajoWhatsApp.TEXTO:
        procesar_tras_ventana(mensaje.id)
    elif trabajo.tipo == TipoTrabajoWhatsApp.IMAGEN:
        _procesar_imagen_siniestro(mensaje.id)
    elif trabajo.tipo == TipoTrabajoWhatsApp.AVISO_FORMATO:
        _avisar_solo_texto(mensaje)
    else:
        raise ValueError(f"Tipo de trabajo WhatsApp desconocido: {trabajo.tipo}")


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


def mensaje_permitido_durante_atencion(mensaje: Mensaje) -> bool:
    """Avisos de derivación, respuestas liberadas explícitamente y texto humano."""
    from negocio.bot.plantillas import DERIVACION, DERIVACION_URGENTE, AVISO_NEUTRO, DATOS_REGISTRADOS
    from datos.models import Derivacion

    if mensaje.emisor == Emisor.FUNCIONARIO:
        return True
    if mensaje.emisor != Emisor.BOT:
        return False
    if mensaje.texto in (DERIVACION, DERIVACION_URGENTE):
        return True
    consulta = mensaje.consulta
    if (
        consulta
        and mensaje.texto in (AVISO_NEUTRO, DATOS_REGISTRADOS)
        and (mensaje.payload or {}).get("aviso_derivacion") is True
        and Derivacion.objects.filter(consulta_id=consulta.id).exists()
    ):
        return True
    return bool(
        consulta
        and consulta.revisado_por_id
        and consulta.revisado_en
        and (
            consulta.respuesta_corregida == mensaje.texto
            or (
                consulta.respuesta_corregida is None
                and consulta.respuesta_bot == mensaje.texto
            )
        )
    )


def descartar_automaticos_pendientes(conversacion_id: int) -> None:
    """Cancela respuestas comunes que no deben salir durante una toma humana."""
    pendientes = (
        Mensaje.objects.select_related("consulta")
        .filter(
            conversacion_id=conversacion_id,
            direccion=Direccion.SALIENTE,
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            emisor=Emisor.BOT,
        )
        .order_by("fecha_hora", "id")
    )
    for mensaje in pendientes:
        if mensaje_permitido_durante_atencion(mensaje):
            continue
        mensaje.estado_envio = EstadoEnvio.DESCARTADO
        mensaje.error = "atencion_humana"
        mensaje.save(update_fields=["estado_envio", "error"])


def enviar_pendientes(conversacion_id: int) -> int:
    """Envía salientes pendientes permitidos para el modo de atención actual."""
    with transaction.atomic():
        conversacion = (
            Conversacion.objects.select_for_update().filter(pk=conversacion_id).first()
        )
        if conversacion is None:
            return 0

        ahora = timezone.now()
        Mensaje.objects.filter(
            conversacion_id=conversacion_id,
            direccion=Direccion.SALIENTE,
            estado_envio=EstadoEnvio.FALLIDO,
            proximo_intento_envio__lte=ahora,
            intentos_envio__lt=MAX_INTENTOS_ENVIO,
        ).exclude(error="ventana_24h_cerrada").update(
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            error=None,
            proximo_intento_envio=None,
        )
        pendientes = list(
            Mensaje.objects.select_related("consulta")
            .filter(
                conversacion_id=conversacion_id,
                direccion=Direccion.SALIENTE,
                estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            )
            .order_by("fecha_hora", "id")
        )
        if conversacion.modo == ModoConversacion.HUMANO:
            descartar_automaticos_pendientes(conversacion_id)
            pendientes = [
                mensaje
                for mensaje in pendientes
                if mensaje.estado_envio == EstadoEnvio.PENDIENTE_ENVIO
                and mensaje_permitido_durante_atencion(mensaje)
            ]

        # Mantener el lock de conversación hasta registrar cada intento hace que
        # una toma y un envío concurrentes tengan un orden definido.
        if not ventana_24h_abierta(
            conversacion.ultimo_mensaje_cliente_en, timezone.now()
        ):
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
            mensaje.intentos_envio += 1
            if simulado:
                mensaje.estado_envio = EstadoEnvio.ENVIADO
                mensaje.enviado_en = timezone.now()
                mensaje.proximo_intento_envio = None
                mensaje.save(
                    update_fields=[
                        "intentos_envio",
                        "estado_envio",
                        "enviado_en",
                        "proximo_intento_envio",
                    ]
                )
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
                if mensaje.intentos_envio < MAX_INTENTOS_ENVIO:
                    espera = min(2 ** (mensaje.intentos_envio - 1), 60)
                    mensaje.proximo_intento_envio = timezone.now() + timedelta(
                        minutes=espera
                    )
                else:
                    mensaje.proximo_intento_envio = None
                mensaje.save(
                    update_fields=[
                        "intentos_envio",
                        "estado_envio",
                        "error",
                        "proximo_intento_envio",
                    ]
                )
                logger.warning("Falló el envío del mensaje %s: %s", mensaje.id, error)
                continue
            mensaje.estado_envio = EstadoEnvio.ENVIADO
            mensaje.enviado_en = timezone.now()
            mensaje.error = None
            mensaje.proximo_intento_envio = None
            mensaje.save(
                update_fields=[
                    "wa_message_id",
                    "intentos_envio",
                    "estado_envio",
                    "enviado_en",
                    "error",
                    "proximo_intento_envio",
                ]
            )
            enviados += 1
        return enviados
