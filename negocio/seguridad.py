"""Límites compartidos entre workers y auditoría sin cuerpos ni credenciales."""
import hashlib
import hmac
import logging
import re
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.utils.cache import patch_vary_headers

logger = logging.getLogger(__name__)


def huella(valor):
    return hmac.new(settings.SECRET_KEY.encode(), str(valor).encode(), hashlib.sha256).hexdigest()


def registrar(evento, recurso, estado=200, usuario_id=None, origen=''):
    with connection.cursor() as c:
        c.execute('INSERT INTO auditoria_seguridad(usuario_id,evento,recurso,estado,origen_hash) VALUES (%s,%s,%s,%s,%s)',
                  [usuario_id, evento[:100], recurso[:300], estado, huella(origen) if origen else ''])


def admitir(clave, limite, segundos=900):
    """UPSERT atómico: una cuota para todos los procesos, sin IPs en claro."""
    with connection.cursor() as c:
        c.execute('''INSERT INTO limites_acceso(clave,inicio,intentos) VALUES (%s,%s,1)
          ON CONFLICT(clave) DO UPDATE SET
          intentos=CASE WHEN limites_acceso.inicio < %s THEN 1 ELSE limites_acceso.intentos+1 END,
          inicio=CASE WHEN limites_acceso.inicio < %s THEN EXCLUDED.inicio ELSE limites_acceso.inicio END
          RETURNING intentos''', [huella(clave), timezone.now(),
          timezone.now()-timedelta(seconds=segundos),
          timezone.now()-timedelta(seconds=segundos)])
        return c.fetchone()[0] <= limite


class ProteccionHTTP:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario_inicial = getattr(request, 'user', None)
        actor_inicial = usuario_inicial.pk if usuario_inicial and usuario_inicial.is_authenticated else None
        try:
            largo = int(request.META.get('CONTENT_LENGTH') or 0)
        except ValueError:
            largo = settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1
        if largo > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            respuesta = JsonResponse({'error': {'codigo': 'demasiado_grande', 'mensaje': 'La solicitud supera el tamaño permitido.'}}, status=413)
        else:
            respuesta = self.get_response(request)
        if request.path.startswith(('/api/', '/panel/')) or request.path == '/':
            respuesta['Cache-Control'] = 'private, no-store'
            respuesta['Pragma'] = 'no-cache'
            patch_vary_headers(respuesta, ['Cookie'])
            respuesta['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: blob:; connect-src 'self'; font-src 'self' https://cdn.jsdelivr.net; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            )
            respuesta['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        # No guarda query strings, textos, DNI, teléfonos ni contraseñas.
        if request.path.startswith('/api/') and (
            request.method not in ('GET', 'HEAD', 'OPTIONS') or
            any(x in request.path for x in ('adjuntos/', 'reportes/', 'clientes/', 'polizas/', 'vencimientos/'))
        ):
            user = getattr(request, 'user', None)
            registrar(request.method, re.sub(r'[^a-zA-Z0-9/_-]', '', request.path),
                      respuesta.status_code, actor_inicial or (user.pk if user and user.is_authenticated else None),
                      request.META.get('REMOTE_ADDR', ''))
        return respuesta
