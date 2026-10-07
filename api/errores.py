"""El único lugar donde se decide qué HTTP le corresponde a cada error.

Formato de respuesta, siempre: `{"error": {"codigo", "mensaje"}}`.

Las vistas no atrapan errores: lanzan las excepciones de `negocio.errores` y
este manejador (`EXCEPTION_HANDLER`) las traduce. Un error inesperado sale como
500 con un mensaje genérico, sin filtrar detalles internos.
"""

from __future__ import annotations

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as PermisoDjango
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

from negocio.errores import ErrorNegocio

logger = logging.getLogger(__name__)

# Código de negocio -> HTTP (contrato, sección "Errores").
HTTP_POR_CODIGO = {
    "datos_invalidos": status.HTTP_400_BAD_REQUEST,
    "parametros_incompletos": status.HTTP_400_BAD_REQUEST,
    "no_autenticado": status.HTTP_401_UNAUTHORIZED,
    "permiso_denegado": status.HTTP_403_FORBIDDEN,
    "no_encontrado": status.HTTP_404_NOT_FOUND,
    "metodo_no_permitido": status.HTTP_405_METHOD_NOT_ALLOWED,
    "estado_invalido": status.HTTP_409_CONFLICT,
    "ventana_24h_cerrada": status.HTTP_409_CONFLICT,
}
# HTTP -> código, para los errores que levanta DRF por su cuenta.
CODIGO_POR_HTTP = {
    status.HTTP_400_BAD_REQUEST: "datos_invalidos",
    status.HTTP_401_UNAUTHORIZED: "no_autenticado",
    status.HTTP_403_FORBIDDEN: "permiso_denegado",
    status.HTTP_404_NOT_FOUND: "no_encontrado",
    status.HTTP_405_METHOD_NOT_ALLOWED: "metodo_no_permitido",
    status.HTTP_409_CONFLICT: "estado_invalido",
}
MENSAJE_POR_HTTP = {
    status.HTTP_400_BAD_REQUEST: "Los datos enviados no son válidos.",
    status.HTTP_401_UNAUTHORIZED: "Tenés que iniciar sesión.",
    status.HTTP_403_FORBIDDEN: "No tenés permiso para hacer esto.",
    status.HTTP_404_NOT_FOUND: "No se encontró lo que buscabas.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Método no permitido.",
    status.HTTP_409_CONFLICT: "El estado actual no permite esta operación.",
}


def _error(codigo: str, mensaje: str, http: int) -> Response:
    return Response({"error": {"codigo": codigo, "mensaje": mensaje}}, status=http)


def _texto(exc, por_defecto: str) -> str:
    detalle = getattr(exc, "detail", None)
    if isinstance(detalle, str):
        return detalle
    return por_defecto


def manejar(exc, context):
    """`EXCEPTION_HANDLER` de DRF."""
    if isinstance(exc, ErrorNegocio):
        codigo = exc.codigo
        return _error(
            codigo,
            exc.mensaje,
            HTTP_POR_CODIGO.get(codigo, status.HTTP_500_INTERNAL_SERVER_ERROR),
        )

    # Un `Modelo.DoesNotExist` que se escapó de un selector es un 404.
    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return _error(
            "no_encontrado",
            "No se encontró lo que buscabas.",
            status.HTTP_404_NOT_FOUND,
        )

    # DRF convierte esto a 403 cuando no hay cabecera de autenticación
    # (SessionAuthentication no la tiene), pero el contrato pide 401.
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return _error(
            "no_autenticado",
            _texto(exc, "Tenés que iniciar sesión."),
            status.HTTP_401_UNAUTHORIZED,
        )

    if isinstance(exc, (PermissionDenied, PermisoDjango)):
        return _error(
            "permiso_denegado",
            _texto(exc, "No tenés permiso para hacer esto."),
            status.HTTP_403_FORBIDDEN,
        )

    respuesta = exception_handler(exc, context)
    if respuesta is not None:
        http = respuesta.status_code
        return _error(
            CODIGO_POR_HTTP.get(http, "error_interno"),
            MENSAJE_POR_HTTP.get(http, "Ocurrió un error inesperado."),
            http,
        )

    # Nada de lo anterior: no se filtra el detalle, se registra y se avisa.
    logger.exception("Error no manejado en la API", exc_info=exc)
    return _error(
        "error_interno",
        "Ocurrió un error inesperado.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
