from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt

from negocio.whatsapp import procesar_webhook, verificar_firma, verificar_suscripcion


@csrf_exempt
def webhook_whatsapp(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        resultado = verificar_suscripcion(mode, token, challenge)
        if resultado is None:
            return HttpResponseForbidden()
        return HttpResponse(resultado, content_type="text/plain")

    if request.method == "POST":
        firma = request.META.get("HTTP_X_HUB_SIGNATURE_256")
        if not verificar_firma(request.body, firma):
            return HttpResponseForbidden()
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError):
            return HttpResponseBadRequest("JSON inválido")
        procesar_webhook(payload)
        return HttpResponse(status=200)

    return HttpResponse(status=405)
