"""Pone un mismo token de versión en todas las URLs de estáticos del panel.

    python manage.py versionar_estaticos            # usa la fecha de hoy
    python manage.py versionar_estaticos --token b3

Los estáticos se sirven con `max-age` de horas, así que un archivo que cambia
pero conserva su URL se sigue leyendo viejo hasta que vence la caché. Versionar
a mano archivo por archivo es frágil: hay que acordarse de la cadena entera —la
página pide su script, el script importa `nav.js`, `nav.js` no cambió de URL—
y basta olvidar un eslabón para que quede media página vieja y media nueva, o
un `import` que no encuentra lo que busca.

Con un token único eso no puede pasar: se corre esto antes de desplegar y todas
las URLs cambian juntas.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand

from config.settings import BASE_DIR

# `href`/`src` a /static/ en el HTML, e imports relativos entre módulos ES.
PATRONES = (
    re.compile(r'((?:href|src)="/static/[^"?]+)(?:\?v=[^"]*)?"'),
    re.compile(r'(from "\.{1,2}/[^"?]+\.js)(?:\?v=[^"]*)?"'),
)


class Command(BaseCommand):
    help = "Versiona las URLs de los estáticos del panel con un token común."

    def add_arguments(self, parser):
        parser.add_argument(
            "--token",
            default=date.today().strftime("%Y%m%d"),
            help="Token a usar. Por defecto, la fecha de hoy (aaaammdd).",
        )

    def handle(self, *args, **opciones):
        token = opciones["token"].strip()
        frontend = Path(BASE_DIR) / "frontend"
        archivos = [
            *sorted((frontend / "pages").glob("*.html")),
            *sorted((frontend / "static" / "js").rglob("*.js")),
        ]

        tocados = 0
        for archivo in archivos:
            texto = archivo.read_text(encoding="utf-8")
            nuevo = texto
            for patron in PATRONES:
                nuevo = patron.sub(rf'\1?v={token}"', nuevo)
            if nuevo != texto:
                archivo.write_text(nuevo, encoding="utf-8", newline="")
                tocados += 1
                self.stdout.write(f"  {archivo.relative_to(BASE_DIR).as_posix()}")

        self.stdout.write(
            self.style.SUCCESS(f"Archivos actualizados: {tocados} (token ?v={token})")
        )
