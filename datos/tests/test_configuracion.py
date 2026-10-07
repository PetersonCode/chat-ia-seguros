import os
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import SimpleTestCase

from config import settings


class ConfiguracionTests(SimpleTestCase):
    # AC-T4-01
    def test_apps_requeridas_instaladas_y_check_sin_errores(self):
        for app in ("rest_framework", "datos", "negocio", "api"):
            with self.subTest(app=app):
                self.assertTrue(apps.is_installed(app))

        call_command("check", verbosity=0)

    # AC-T4-02
    def test_variable_obligatoria_faltante_falla_en_espanol_y_la_nombra(self):
        obligatorias = (
            "DJANGO_SECRET_KEY",
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
        )
        entorno_valido = {
            "DJANGO_SECRET_KEY": "clave-de-prueba",
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_NAME": "proyecto",
            "DB_USER": "usuario",
            "DB_PASSWORD": "clave",
        }

        for variable in obligatorias:
            with self.subTest(variable=variable):
                entorno = entorno_valido.copy()
                entorno.pop(variable)
                with patch.dict(os.environ, entorno, clear=True):
                    with self.assertRaises(ImproperlyConfigured) as error:
                        settings.requerida(variable)
                self.assertIn(variable, str(error.exception))
                self.assertIn("obligatoria", str(error.exception).lower())

    # AC-T4-03
    def test_configuracion_de_base_y_localizacion(self):
        base = settings.DATABASES["default"]
        self.assertEqual(base["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(
            {key: base[key] for key in ("HOST", "PORT", "USER", "PASSWORD")},
            {
                "HOST": settings.DB_HOST,
                "PORT": settings.DB_PORT,
                "USER": settings.DB_USER,
                "PASSWORD": settings.DB_PASSWORD,
            },
        )
        # Mientras corren los tests Django reemplaza NAME por el de la base de
        # prueba (AC-T4-10), asi que vale cualquiera de los dos.
        self.assertIn(base["NAME"], {settings.DB_NAME, base["TEST"]["NAME"]})
        self.assertEqual(base["OPTIONS"], {"sslmode": "require"})
        self.assertEqual(settings.TIME_ZONE, "America/Argentina/Buenos_Aires")
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(settings.LANGUAGE_CODE, "es-ar")

    # AC-T4-04
    def test_archivos_y_dependencias_fijadas(self):
        raiz = Path(settings.BASE_DIR)
        self.assertEqual(
            (raiz / ".env.example").read_bytes(),
            (raiz / "SDD" / "plantillas" / "env.example").read_bytes(),
        )

        gitignore = (raiz / ".gitignore").read_text(encoding="utf-8")
        for patron in (".env", "__pycache__/", ".venv/", "node_modules/"):
            with self.subTest(patron=patron):
                self.assertIn(patron, gitignore.splitlines())

        requisitos = [
            linea.strip()
            for linea in (raiz / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.lstrip().startswith("#")
        ]
        self.assertCountEqual(
            requisitos,
            [
                "Django==5.2.4",
                "djangorestframework==3.16.0",
                "psycopg[binary]==3.2.9",
                "python-dotenv==1.1.1",
            ],
        )
