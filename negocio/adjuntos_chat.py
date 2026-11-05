"""Imágenes y videos del chat: se guardan en privado para poder descargarlos."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.db import DatabaseError, transaction
from django.utils import timezone

from datos.models import Mensaje, MensajeAdjunto
from negocio.adjuntos_siniestros import AdjuntoInvalido, descargar_media_whatsapp
from negocio.errores import NoEncontrado

logger = logging.getLogger(__name__)

TAMANO_MAXIMO_VIDEO = 16 * 1024 * 1024  # el tope de WhatsApp para video
# mime declarado por el webhook -> (extensión, tipo de archivo en el nombre)
TIPOS = {
    "image/jpeg": ("jpg", "imagen"),
    "image/png": ("png", "imagen"),
    "image/webp": ("webp", "imagen"),
    "video/mp4": ("mp4", "video"),
    "video/3gpp": ("3gp", "video"),
}
CAMPOS_MEDIA = ("image", "video")


@dataclass(frozen=True)
class ResultadoGuardado:
    estado: str  # guardado | ya_guardado | no_es_media


def _storage() -> FileSystemStorage:
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def _validar_contenido(contenido: bytes, mime: str) -> None:
    """El contenido tiene que ser lo que el webhook dijo que era."""
    if mime.startswith("video/"):
        # MP4 y 3GP son contenedores ISO: la caja `ftyp` va al principio.
        if len(contenido) < 12 or contenido[4:8] != b"ftyp":
            raise AdjuntoInvalido("El contenido no es un video válido.")
        return
    firmas = {
        "image/jpeg": b"\xff\xd8\xff",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "image/webp": b"RIFF",
    }
    if not contenido.startswith(firmas[mime]):
        raise AdjuntoInvalido("El contenido no coincide con el tipo de imagen declarado.")
    if mime == "image/webp" and contenido[8:12] != b"WEBP":
        raise AdjuntoInvalido("El contenido no coincide con el tipo de imagen declarado.")


def _nombre_archivo(tipo: str, extension: str) -> str:
    ahora = timezone.localtime(timezone.now())
    return f"{tipo}-{ahora:%Y%m%d-%H%M%S}.{extension}"


def guardar_media_de_chat(mensaje_id: int) -> ResultadoGuardado:
    """Descarga de Meta la imagen o el video del mensaje y lo deja disponible en el chat.

    Lanza `DescargaMediaInvalida` si Meta no lo entrega (el trabajo se reintenta)
    y `AdjuntoInvalido` si lo que llegó no es lo que se declaró.
    """
    mensaje = Mensaje.objects.filter(pk=mensaje_id).first()
    if mensaje is None or not isinstance(mensaje.payload, dict):
        return ResultadoGuardado("no_es_media")
    media = next(
        (mensaje.payload[c] for c in CAMPOS_MEDIA if isinstance(mensaje.payload.get(c), dict)),
        None,
    )
    if media is None:
        return ResultadoGuardado("no_es_media")
    if MensajeAdjunto.objects.filter(mensaje_id=mensaje.id).exists():
        return ResultadoGuardado("ya_guardado")

    mime = str(media.get("mime_type") or "").lower().split(";")[0].strip()
    if mime not in TIPOS:
        raise AdjuntoInvalido("WhatsApp mandó un formato que no se puede guardar.")
    extension, tipo = TIPOS[mime]
    contenido = descargar_media_whatsapp(
        media.get("id"),
        mime_esperado=mime,
        sha256_esperado=media.get("sha256"),
        mimes_permitidos=frozenset(TIPOS),
        tamano_maximo=TAMANO_MAXIMO_VIDEO,
        accept="*/*",
    )
    _validar_contenido(contenido, mime)

    storage = _storage()
    clave = storage.save(
        f"chat/{mensaje.conversacion_id}/{uuid.uuid4().hex}.{extension}",
        ContentFile(contenido),
    )
    try:
        with transaction.atomic():
            MensajeAdjunto.objects.create(
                mensaje_id=mensaje.id,
                clave_almacenamiento=clave,
                nombre_archivo=_nombre_archivo(tipo, extension),
                content_type=mime,
                tamano=len(contenido),
                sha256=hashlib.sha256(contenido).hexdigest(),
                creado_en=timezone.now(),
            )
    except DatabaseError:
        storage.delete(clave)
        if MensajeAdjunto.objects.filter(mensaje_id=mensaje.id).exists():
            return ResultadoGuardado("ya_guardado")  # otro proceso llegó primero
        raise
    return ResultadoGuardado("guardado")


def abrir_adjunto_de_mensaje(mensaje_id: int):
    adjunto = MensajeAdjunto.objects.filter(mensaje_id=mensaje_id).first()
    if adjunto is None:
        raise NoEncontrado("Este mensaje no tiene un archivo para descargar.")
    storage = _storage()
    try:
        archivo = storage.open(adjunto.clave_almacenamiento, "rb")
    except FileNotFoundError as error:
        raise NoEncontrado("El archivo ya no está disponible.") from error
    return adjunto, archivo


def borrar_archivos_de_mensajes(mensaje_ids) -> int:
    """Quita del disco los archivos de esos mensajes (antes de borrar sus filas)."""
    storage = _storage()
    borrados = 0
    for clave in MensajeAdjunto.objects.filter(mensaje_id__in=list(mensaje_ids)).values_list(
        "clave_almacenamiento", flat=True
    ):
        try:
            storage.delete(clave)
            borrados += 1
        except OSError:
            logger.warning("No se pudo borrar el archivo %s.", clave)
    return borrados
