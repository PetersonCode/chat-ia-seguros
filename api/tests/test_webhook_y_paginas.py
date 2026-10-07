"""Etapa F: webhook de WhatsApp y páginas del front (AC-T2-19 a AC-T2-21)."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase

SECRETO = "secreto-de-prueba"
TOKEN = "token-de-prueba"

PAYLOAD = {
    "entry": [
        {
            "changes": [
                {
                    "value": {
                        "messages": [
                            {
                                "id": "wamid.test",
                                "from": "5491155551001",
                                "type": "text",
                                "text": {"body": "hola"},
                            }
                        ]
                    }
                }
            ]
        }
    ]
}


def _firma(cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()


class WebhookVerificacionTests(TestCase):
    # AC-T2-19
    def test_el_get_de_verificacion_devuelve_el_challenge_como_texto(self):
        with patch.dict("os.environ", {"WHATSAPP_VERIFY_TOKEN": TOKEN}):
            respuesta = self.client.get(
                "/webhook/whatsapp/",
                {
                    "hub.mode": "subscribe",
                    "hub.verify_token": TOKEN,
                    "hub.challenge": "1234567890",
                },
            )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.content, b"1234567890")
        self.assertTrue(respuesta["Content-Type"].startswith("text/plain"))

    # AC-T2-19
    def test_un_token_incorrecto_o_un_modo_raro_es_403(self):
        with patch.dict("os.environ", {"WHATSAPP_VERIFY_TOKEN": TOKEN}):
            malos = (
                {"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "1"},
                {"hub.mode": "unsubscribe", "hub.verify_token": TOKEN, "hub.challenge": "1"},
                {},
            )
            for parametros in malos:
                with self.subTest(parametros=parametros):
                    respuesta = self.client.get("/webhook/whatsapp/", parametros)
                    self.assertEqual(respuesta.status_code, 403)


class WebhookEntranteTests(TestCase):
    def setUp(self):
        # Sin sesión y sin CSRF: el webhook lo llama Meta, no el front.
        self.anonimo = Client(enforce_csrf_checks=True)

    # AC-T2-20
    def test_una_firma_invalida_es_403_y_no_se_procesa_nada(self):
        cuerpo = json.dumps(PAYLOAD).encode()
        with patch.dict("os.environ", {"WHATSAPP_APP_SECRET": SECRETO}):
            with patch("api.webhook.procesar_webhook") as procesar:
                respuesta = self.anonimo.post(
                    "/webhook/whatsapp/",
                    data=cuerpo,
                    content_type="application/json",
                    HTTP_X_HUB_SIGNATURE_256="sha256=00deadbeef",
                )
        self.assertEqual(respuesta.status_code, 403)
        procesar.assert_not_called()

    # AC-T2-20
    def test_sin_firma_tambien_es_403(self):
        cuerpo = json.dumps(PAYLOAD).encode()
        with patch.dict("os.environ", {"WHATSAPP_APP_SECRET": SECRETO}):
            with patch("api.webhook.procesar_webhook") as procesar:
                respuesta = self.anonimo.post(
                    "/webhook/whatsapp/", data=cuerpo, content_type="application/json"
                )
        self.assertEqual(respuesta.status_code, 403)
        procesar.assert_not_called()

    # AC-T2-20
    def test_un_json_invalido_con_firma_valida_es_400(self):
        cuerpo = b"{esto no es json"
        with patch.dict("os.environ", {"WHATSAPP_APP_SECRET": SECRETO}):
            with patch("api.webhook.procesar_webhook") as procesar:
                respuesta = self.anonimo.post(
                    "/webhook/whatsapp/",
                    data=cuerpo,
                    content_type="application/json",
                    HTTP_X_HUB_SIGNATURE_256=_firma(cuerpo),
                )
        self.assertEqual(respuesta.status_code, 400)
        procesar.assert_not_called()

    # AC-T2-20
    def test_un_payload_valido_llama_a_procesar_webhook_y_responde_200(self):
        cuerpo = json.dumps(PAYLOAD).encode()
        with patch.dict(
            "os.environ", {"WHATSAPP_APP_SECRET": SECRETO, "WHATSAPP_MODO": "simulado"}
        ):
            with patch("api.webhook.procesar_webhook") as procesar:
                respuesta = self.anonimo.post(
                    "/webhook/whatsapp/",
                    data=cuerpo,
                    content_type="application/json",
                    HTTP_X_HUB_SIGNATURE_256=_firma(cuerpo),
                )
        self.assertEqual(respuesta.status_code, 200)
        procesar.assert_called_once_with(PAYLOAD)

    # AC-T2-20
    def test_un_payload_sin_mensajes_tambien_responde_200(self):
        cuerpo = json.dumps({"entry": []}).encode()
        with patch.dict("os.environ", {"WHATSAPP_APP_SECRET": SECRETO}):
            respuesta = self.anonimo.post(
                "/webhook/whatsapp/",
                data=cuerpo,
                content_type="application/json",
                HTTP_X_HUB_SIGNATURE_256=_firma(cuerpo),
            )
        self.assertEqual(respuesta.status_code, 200)

    # AC-T2-20
    def test_el_webhook_de_punta_a_punta_registra_el_mensaje(self):
        from datos.models import ContactoWhatsapp, Mensaje

        cuerpo = json.dumps(PAYLOAD).encode()
        entorno = {"WHATSAPP_APP_SECRET": SECRETO, "WHATSAPP_MODO": "simulado"}
        with patch.dict("os.environ", entorno):
            with patch("negocio.whatsapp.en_segundo_plano") as fondo:
                respuesta = self.anonimo.post(
                    "/webhook/whatsapp/",
                    data=cuerpo,
                    content_type="application/json",
                    HTTP_X_HUB_SIGNATURE_256=_firma(cuerpo),
                )

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(ContactoWhatsapp.objects.filter(numero="+5491155551001").exists())
        self.assertTrue(Mensaje.objects.filter(wa_message_id="wamid.test").exists())
        fondo.assert_called_once()


class PaginasTests(TestCase):
    RUTAS = {
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

    # AC-T2-21
    def test_cada_ruta_del_panel_sirve_su_archivo_sin_pedir_sesion(self):
        for ruta, archivo in self.RUTAS.items():
            with self.subTest(ruta=ruta):
                esperado = settings.BASE_DIR / "frontend" / "pages" / archivo
                self.assertTrue(esperado.exists(), f"falta {archivo}")

                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200, ruta)
                contenido = b"".join(respuesta.streaming_content)
                self.assertEqual(contenido, esperado.read_bytes())

    # AC-T2-21
    def test_una_ruta_que_no_esta_en_la_lista_blanca_es_404(self):
        for ruta in ("/panel/inventada/", "/panel/../etc/passwd", "/otra/"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.get(ruta).status_code, 404)

    # AC-T2-21
    def test_si_el_archivo_no_existe_todavia_la_ruta_da_404(self):
        with patch("api.paginas.Path.exists", return_value=False):
            self.assertEqual(self.client.get("/panel/").status_code, 404)

    # AC-T2-21
    def test_los_estaticos_del_front_se_sirven_bajo_static(self):
        from django.contrib.staticfiles import finders

        for estatico in ("js/api.js", "css/app.css", "js/nav.js"):
            with self.subTest(estatico=estatico):
                self.assertIsNotNone(finders.find(estatico), estatico)
