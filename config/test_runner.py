from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test.runner import DiscoverRunner


class RunnerConEsquema(DiscoverRunner):
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
