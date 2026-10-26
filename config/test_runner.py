import os
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


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
        from unittest.mock import patch
        self._entorno_test = patch.dict(os.environ, {
            "WHATSAPP_MODO": "simulado", "LLM_PROVIDER": "none",
            "BOT_VENTANA_AGRUPACION_SEGUNDOS": "0",
        })
        self._entorno_test.start()
        # Acelera fixtures; settings.py y la aplicación normal siguen usando
        # PBKDF2. Hay una prueba explícita de login con PBKDF2.
        self._hashers_test = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
        self._hashers_test.enable()
        return super().setup_test_environment(**kwargs)

    def teardown_test_environment(self, **kwargs):
        try:
            return super().teardown_test_environment(**kwargs)
        finally:
            self._hashers_test.disable()
            self._entorno_test.stop()

    def setup_databases(self, **kwargs):
        configuracion_anterior = super().setup_databases(**kwargs)
        if not configuracion_anterior:
            return configuracion_anterior

        archivos_sql = (
            "01_schema.sql",
            "03_whatsapp.sql",
            "04_mensaje_descartado.sql",
            "05_acciones_del_bot.sql",
            "06_pagos_con_referencia.sql",
            "07_expediente_siniestros.sql",
            "08_adjuntos_siniestros.sql",
            "09_documentos_generales.sql",
            "10_trabajos_whatsapp.sql",
            "11_finalizaciones_acciones.sql",
        )
        with connection.cursor() as cursor:
            for nombre in archivos_sql:
                ruta = Path(settings.BASE_DIR) / "SDD" / "sql" / nombre
                cursor.execute(ruta.read_text(encoding="utf-8"))
        return configuracion_anterior
