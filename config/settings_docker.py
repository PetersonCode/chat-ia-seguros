"""Ajustes extra para correr detrás de nginx + Cloudflare (solo Docker).

No cambia config/settings.py: lo importa y agrega lo necesario para HTTPS por proxy.
"""

import os

from .settings import *  # noqa: F401,F403

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = False

_dominios = [d.strip() for d in os.getenv("PUBLIC_DOMAINS", "").split(",") if d.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{d}" for d in _dominios]

# El proxy debe reemplazar X-Forwarded-Proto y ser la única entrada a la app.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
