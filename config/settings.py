import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def requerida(nombre: str) -> str:
    valor = os.getenv(nombre)
    if valor is None or not valor.strip():
        raise ImproperlyConfigured(
            f"La variable de entorno {nombre} es obligatoria y no está configurada."
        )
    return valor


DJANGO_SECRET_KEY = requerida("DJANGO_SECRET_KEY")
DB_HOST = requerida("DB_HOST")
DB_PORT = requerida("DB_PORT")
DB_NAME = requerida("DB_NAME")
DB_USER = requerida("DB_USER")
DB_PASSWORD = requerida("DB_PASSWORD")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require").strip().lower()

SECRET_KEY = DJANGO_SECRET_KEY
DEBUG = os.getenv("DJANGO_DEBUG", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "datos.apps.DatosConfig",
    "negocio.apps.NegocioConfig",
    "api.apps.ApiConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "negocio.seguridad.ProteccionHTTP",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": DB_NAME,
        "USER": DB_USER,
        "PASSWORD": DB_PASSWORD,
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "TEST": {"NAME": "test_proyecto"},
        "OPTIONS": {"sslmode": DB_SSLMODE},
    }
}
TEST_RUNNER = "config.test_runner.RunnerConEsquema"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "api.permisos.EsFuncionario",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "EXCEPTION_HANDLER": "api.errores.manejar",
}

STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"]
STATIC_URL = "/static/"
PRIVATE_MEDIA_ROOT = Path(
    os.getenv("PRIVATE_MEDIA_ROOT") or str(BASE_DIR / "private_media")
).resolve()
DATA_UPLOAD_MAX_MEMORY_SIZE = 11 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Endurecimiento: producción falla cerrada; desarrollo conserva HTTP local.
if not DEBUG:
    if len(SECRET_KEY) < 50 or 'cambiame' in SECRET_KEY.lower():
        raise ImproperlyConfigured('Producción requiere DJANGO_SECRET_KEY aleatoria de al menos 50 caracteres.')
    if '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured('No se admite ALLOWED_HOSTS=* en producción.')
    if DB_SSLMODE not in {'require', 'verify-ca', 'verify-full'}:
        raise ImproperlyConfigured('Producción requiere TLS para PostgreSQL.')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r'^healthz/$']
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100
DATA_UPLOAD_MAX_NUMBER_FILES = 5
AUTH_PASSWORD_VALIDATORS[1]['OPTIONS'] = {'min_length': 12}
STATIC_ROOT = BASE_DIR / 'staticfiles'
BUSQUEDA_SEMANTICA = os.getenv('BUSQUEDA_SEMANTICA', 'false').lower() in {'true','1'}
MODELO_BUSQUEDA_DIR = Path(os.getenv('MODELO_BUSQUEDA_DIR') or BASE_DIR / '.modelos')

# Perfil académico optativo. Nunca se habilita por defecto ni en producción.
MODO_DEMOSTRACION = os.getenv('MODO_DEMOSTRACION', 'false').lower() in {'true','1'}
if MODO_DEMOSTRACION:
    if not DEBUG or os.getenv('WHATSAPP_MODO','simulado') != 'simulado' or os.getenv('LLM_PROVIDER','none') not in {'none',''}:
        raise ImproperlyConfigured('MODO_DEMOSTRACION requiere DEBUG=true, WhatsApp simulado y LLM desactivado.')
    SESSION_COOKIE_AGE = 8 * 60 * 60
