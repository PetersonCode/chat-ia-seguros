from __future__ import annotations

from pathlib import Path

from django.http import FileResponse, Http404

from config.settings import BASE_DIR

_PAGINAS = {
    "/": "login.html",
    "/panel/": "bandeja.html",
    "/panel/conversacion/": "conversacion.html",
    "/panel/alertas/": "alertas.html",
    "/panel/cerrados/": "cerrados.html",
    "/panel/acciones/": "acciones.html",
    "/panel/derivaciones/": "derivaciones.html",
    "/panel/clientes/": "clientes.html",
    "/panel/cliente/": "cliente.html",
}


def servir_pagina(request, path: str | None = None):
    ruta = request.path
    nombre = _PAGINAS.get(ruta)
    if nombre is None:
        raise Http404()
    archivo = BASE_DIR / "frontend" / "pages" / nombre
    if not archivo.exists():
        raise Http404()
    return FileResponse(archivo.open("rb"), content_type="text/html")
