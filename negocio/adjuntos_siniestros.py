"""Validación y almacenamiento privado de imágenes de expedientes."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import DatabaseError, transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from datos.models import (
    AdjuntoSiniestro,
    Conversacion,
    Mensaje,
    OrigenAdjuntoSiniestro,
    Siniestro,
)
from negocio.errores import NoEncontrado

logger = logging.getLogger(__name__)

TAMANO_MAXIMO = 10 * 1024 * 1024
TAMANO_MAXIMO_WHATSAPP = 5 * 1024 * 1024
PIXELES_MAXIMOS = 20_000_000
MIMES = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
PATRON_EXPEDIENTE = re.compile(r"(?<![A-Z0-9])SIN-\d{4}-\d{5}(?![A-Z0-9])")
PATRON_MEDIA_ID = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
PATRON_SHA256 = re.compile(r"^[A-Za-z0-9+/]{43}=$")
Image.MAX_IMAGE_PIXELS = PIXELES_MAXIMOS


class AdjuntoInvalido(ValueError):
    pass


class DescargaMediaInvalida(ValueError):
    pass


@dataclass(frozen=True)
class ResultadoMedia:
    estado: str
    numero_siniestro: str | None = None


def _storage() -> FileSystemStorage:
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def _leer_limitado(archivo) -> bytes:
    partes = []
    total = 0
    for parte in archivo.chunks():
        total += len(parte)
        if total > TAMANO_MAXIMO:
            raise AdjuntoInvalido("La imagen supera el límite de 10 MB.")
        partes.append(parte)
    if total == 0:
        raise AdjuntoInvalido("El archivo está vacío.")
    return b"".join(partes)


def _normalizar_imagen(contenido: bytes) -> tuple[bytes, str, str]:
    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            imagen_format = imagen.format
            if imagen_format not in MIMES:
                raise AdjuntoInvalido("Solo se admiten imágenes JPEG, PNG o WebP.")
            if imagen.width * imagen.height > PIXELES_MAXIMOS:
                raise AdjuntoInvalido("La resolución de la imagen supera el límite permitido.")
            if getattr(imagen, "n_frames", 1) != 1:
                raise AdjuntoInvalido("No se admiten imágenes animadas.")
            imagen.load()
            imagen = ImageOps.exif_transpose(imagen)
            if imagen_format == "JPEG" and imagen.mode not in ("RGB", "L"):
                imagen = imagen.convert("RGB")

            salida = io.BytesIO()
            opciones = {"optimize": True} if imagen_format in ("JPEG", "PNG") else {
                "quality": 90,
                "method": 4,
            }
            imagen.save(salida, format=imagen_format, **opciones)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise AdjuntoInvalido("La resolución de la imagen supera el límite permitido.") from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        if isinstance(error, AdjuntoInvalido):
            raise
        raise AdjuntoInvalido("El contenido no es una imagen válida.") from error

    mime, extension = MIMES[imagen_format]
    normalizada = salida.getvalue()
    if len(normalizada) > TAMANO_MAXIMO:
        raise AdjuntoInvalido("La imagen normalizada supera el límite de 10 MB.")
    return normalizada, mime, extension


def _guardar_validado(
    siniestro: Siniestro,
    contenido: bytes,
    *,
    origen: str,
    creado_por_id: int | None = None,
    mensaje_origen: Mensaje | None = None,
    mime_esperado: str | None = None,
) -> AdjuntoSiniestro:
    imagen, mime, extension = _normalizar_imagen(contenido)
    if mime_esperado and mime != mime_esperado.lower():
        raise AdjuntoInvalido("El contenido no coincide con el tipo de imagen declarado.")
    clave = f"siniestros/{siniestro.id}/{uuid.uuid4().hex}.{extension}"
    storage = _storage()
    clave_guardada = storage.save(clave, ContentFile(imagen))
    try:
        with transaction.atomic():
            return AdjuntoSiniestro.objects.create(
                siniestro=siniestro,
                clave_almacenamiento=clave_guardada,
                content_type=mime,
                tamano=len(imagen),
                sha256=hashlib.sha256(imagen).hexdigest(),
                origen=origen,
                mensaje_origen=mensaje_origen,
                creado_por_id=creado_por_id,
                creado_en=timezone.now(),
            )
    except DatabaseError:
        storage.delete(clave_guardada)
        raise


def guardar_adjunto_panel(
    siniestro: Siniestro, archivo, funcionario_id: int
) -> AdjuntoSiniestro:
    contenido = _leer_limitado(archivo)
    with transaction.atomic():
        siniestro = Siniestro.objects.select_for_update().get(pk=siniestro.pk)
        return _guardar_validado(
            siniestro,
            contenido,
            origen=OrigenAdjuntoSiniestro.PANEL,
            creado_por_id=funcionario_id,
        )


class _RedireccionMeta(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validar_url_meta(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validar_url_meta(url: str) -> None:
    try:
        partes = urlsplit(url)
    except ValueError as error:
        raise DescargaMediaInvalida("Meta devolvió una URL de descarga no permitida.") from error
    host = (partes.hostname or "").lower()
    host_permitido = (
        host == "graph.facebook.com"
        or host.endswith(".fbsbx.com")
        or host.endswith(".fbcdn.net")
    )
    try:
        puerto = partes.port
    except ValueError as error:
        raise DescargaMediaInvalida("Meta devolvió una URL de descarga no permitida.") from error
    if (
        partes.scheme != "https"
        or not host_permitido
        or partes.username
        or partes.password
        or puerto not in (None, 443)
    ):
        raise DescargaMediaInvalida("Meta devolvió una URL de descarga no permitida.")


def _abrir_media(opener, solicitud):
    try:
        return opener.open(solicitud, timeout=10)
    except (URLError, TimeoutError, OSError) as error:
        raise DescargaMediaInvalida("No se pudo descargar la imagen desde Meta.") from error


def descargar_media_whatsapp(
    media_id: str, *, mime_esperado: str | None, sha256_esperado: str | None
) -> bytes:
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    version = os.getenv("WHATSAPP_API_VERSION", "")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    if not token or not phone_number_id or not re.fullmatch(r"v\d+\.\d+", version):
        raise DescargaMediaInvalida("Falta la configuración de WhatsApp Cloud.")
    if not re.fullmatch(r"\d+", phone_number_id):
        raise DescargaMediaInvalida("El ID del número de WhatsApp no es válido.")
    if not PATRON_MEDIA_ID.fullmatch(media_id or ""):
        raise DescargaMediaInvalida("El ID de media no es válido.")
    if not isinstance(mime_esperado, str) or mime_esperado.lower() not in {
        "image/jpeg",
        "image/png",
    }:
        raise DescargaMediaInvalida("WhatsApp no indicó una imagen JPEG o PNG.")
    if not isinstance(sha256_esperado, str) or not PATRON_SHA256.fullmatch(
        sha256_esperado
    ):
        raise DescargaMediaInvalida("El hash recibido no es válido.")

    base = f"https://graph.facebook.com/{version}/{quote(media_id, safe='')}"
    metadata_url = f"{base}?phone_number_id={quote(phone_number_id, safe='')}"
    opener = build_opener(_RedireccionMeta())
    request_metadata = Request(
        metadata_url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with _abrir_media(opener, request_metadata) as respuesta:
        metadata_contenido = respuesta.read(1024 * 1024 + 1)
    if len(metadata_contenido) > 1024 * 1024:
        raise DescargaMediaInvalida("La respuesta de metadatos es demasiado grande.")
    try:
        metadata = json.loads(metadata_contenido)
        url = metadata["url"]
        mime_meta = metadata["mime_type"]
        tamano_meta = int(metadata["file_size"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise DescargaMediaInvalida("Meta devolvió metadatos incompletos.") from error
    hash_meta = metadata.get("sha256")
    if (
        not isinstance(url, str)
        or not isinstance(mime_meta, str)
        or not isinstance(hash_meta, str)
        or not PATRON_SHA256.fullmatch(hash_meta)
    ):
        raise DescargaMediaInvalida("Meta devolvió metadatos incompletos.")
    if metadata.get("id") != media_id:
        raise DescargaMediaInvalida("El ID de media devuelto no coincide.")
    if hash_meta != sha256_esperado:
        raise DescargaMediaInvalida("El hash de Meta no coincide con el webhook.")
    _validar_url_meta(url)
    if not 1 <= tamano_meta <= TAMANO_MAXIMO_WHATSAPP:
        raise DescargaMediaInvalida("La imagen supera el límite de 5 MB de WhatsApp.")
    if mime_esperado and mime_meta.lower() != mime_esperado.lower():
        raise DescargaMediaInvalida("El tipo de imagen no coincide con el webhook.")

    request_archivo = Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "image/*"},
    )
    with _abrir_media(opener, request_archivo) as respuesta:
        contenido = respuesta.read(TAMANO_MAXIMO_WHATSAPP + 1)
    if (
        len(contenido) > TAMANO_MAXIMO_WHATSAPP
        or len(contenido) != tamano_meta
    ):
        raise DescargaMediaInvalida("El tamaño descargado no coincide con Meta.")
    hash_real = hashlib.sha256(contenido).hexdigest()
    hash_base64 = base64.b64encode(bytes.fromhex(hash_real)).decode("ascii")
    if sha256_esperado and hash_base64 != sha256_esperado:
        raise DescargaMediaInvalida("El hash descargado no coincide con Meta.")
    return contenido


def procesar_media_entrante(mensaje_id: int) -> ResultadoMedia:
    mensaje = Mensaje.objects.select_related("conversacion__contacto").filter(
        pk=mensaje_id
    ).first()
    if mensaje is None or mensaje.payload is None:
        return ResultadoMedia("no_encontrado")
    from negocio.bot.orquestador import ignorar_si_bloqueado

    if ignorar_si_bloqueado(mensaje):
        return ResultadoMedia("bloqueado")
    imagen = mensaje.payload.get("image")
    if not isinstance(imagen, dict):
        return ResultadoMedia("no_es_imagen")

    media_id = imagen.get("id")
    caption = imagen.get("caption") or ""
    match = PATRON_EXPEDIENTE.search(caption.upper())
    if not match:
        return ResultadoMedia("falta_expediente")

    contacto = mensaje.conversacion.contacto
    if contacto.cliente_id is None:
        return ResultadoMedia("sin_vinculacion")
    siniestro = (
        Siniestro.objects.select_related("poliza")
        .filter(
            numero_siniestro=match.group(0),
            poliza__cliente_id=contacto.cliente_id,
        )
        .first()
    )
    if siniestro is None:
        return ResultadoMedia("expediente_no_verificado")
    if AdjuntoSiniestro.objects.filter(mensaje_origen=mensaje).exists():
        return ResultadoMedia("ya_procesado", siniestro.numero_siniestro)

    try:
        contenido = descargar_media_whatsapp(
            media_id,
            mime_esperado=imagen.get("mime_type"),
            sha256_esperado=imagen.get("sha256"),
        )
        with transaction.atomic():
            conversacion = Conversacion.objects.select_for_update().get(
                pk=mensaje.conversacion_id
            )
            if ignorar_si_bloqueado(mensaje):
                return ResultadoMedia("bloqueado")
            if AdjuntoSiniestro.objects.filter(mensaje_origen=mensaje).exists():
                return ResultadoMedia("ya_procesado", siniestro.numero_siniestro)
            _guardar_validado(
                siniestro,
                contenido,
                origen=OrigenAdjuntoSiniestro.WHATSAPP,
                mensaje_origen=mensaje,
                mime_esperado=imagen.get("mime_type"),
            )
    except (AdjuntoInvalido, DescargaMediaInvalida) as error:
        logger.warning("No se pudo incorporar una imagen de WhatsApp: %s", error)
        return ResultadoMedia(
            "error_descarga"
            if isinstance(error, DescargaMediaInvalida)
            else "invalido"
        )
    return ResultadoMedia("incorporado", siniestro.numero_siniestro)


def abrir_adjunto(siniestro_id: int, adjunto_id: int):
    adjunto = (
        AdjuntoSiniestro.objects.select_related("siniestro")
        .filter(pk=adjunto_id, siniestro_id=siniestro_id)
        .first()
    )
    if adjunto is None:
        raise NoEncontrado("No encontramos ese adjunto en el expediente.")
    storage = _storage()
    if not storage.exists(adjunto.clave_almacenamiento):
        raise NoEncontrado("El archivo del expediente no está disponible.")
    try:
        archivo = storage.open(adjunto.clave_almacenamiento, "rb")
    except FileNotFoundError as error:
        raise NoEncontrado("El archivo del expediente no está disponible.") from error
    return adjunto, archivo
