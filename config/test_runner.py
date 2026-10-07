import os
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test.runner import DiscoverRunner


class RunnerConEsquema(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        """Ningún test puede mandar un WhatsApp de verdad.

        Varios tests comprueban que un saliente queda `enviado`, cosa que solo
        pasa en modo simulado. Si el `.env` del equipo está en `real` —como
        corresponde en producción— esos tests saldrían a la API de Meta.
        Fijarlo acá los hace deterministas y, sobre todo, evita que correr la
        suite le mande mensajes a un cliente. Un test que necesite otro modo lo
        parchea con `patch.dict`, que tiene prioridad sobre esto.
        """
        os.environ["WHATSAPP_MODO"] = "simulado"
        return super().setup_test_environment(**kwargs)

    def setup_databases(self, **kwargs):
        configuracion_anterior = super().setup_databases(**kwargs)
        if not configuracion_anterior:
            return configuracion_anterior

        archivos_sql = (
            "01_schema.sql",
            "03_whatsapp.sql",
            "04_mensaje_descartado.sql",
        )
        with connection.cursor() as cursor:
            for nombre in archivos_sql:
                ruta = Path(settings.BASE_DIR) / "SDD" / "sql" / nombre
                cursor.execute(ruta.read_text(encoding="utf-8"))
        return configuracion_anterior
