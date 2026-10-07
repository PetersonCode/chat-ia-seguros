"""Etapa B: el canal WhatsApp (AC-T3-05 a AC-T3-15).

La red nunca se toca de verdad: `WHATSAPP_MODO=simulado` o un `patch` de
`urllib.request.urlopen`. El bot tampoco corre: se parchea `en_segundo_plano`.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from datetime import timedelta
from unittest.mock import patch
from urllib.error import HTTPError

from django.test import TestCase, override_settings
from django.utils import timezone

from datos import fabricas
from datos.models import (
    ContactoWhatsapp,
    Conversacion,
    EstadoConversacion,
    EstadoEnvio,
    Mensaje,
)
from negocio import whatsapp
from negocio.bot.plantillas import SOLO_TEXTO

SECRETO = "secreto-de-prueba"
TOKEN = "token-de-prueba"


def _payload_texto(
    wa_id: str, numero: str, texto: str, perfil: str | None = None
) -> dict:
    valor_contactos = (
        [{"wa_id": numero, "profile": {"name": perfil}}] if perfil else []
    )
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": valor_contactos,
                            "messages": [
                                {
                                    "id": wa_id,
                                    "from": numero,
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _payload_estado(wa_id: str, estado: str) -> dict:
    return {
        "entry": [
            {"changes": [{"value": {"statuses": [{"id": wa_id, "status": estado}]}}]}
        ]
    }


class VerificacionTests(TestCase):
    # AC-T3-05
    def test_verificar_suscripcion(self):
        with patch.dict("os.environ", {"WHATSAPP_VERIFY_TOKEN": TOKEN}):
            self.assertEqual(
                whatsapp.verificar_suscripcion("subscribe", TOKEN, "desafio"), "desafio"
            )
            self.assertIsNone(whatsapp.verificar_suscripcion("subscribe", "otro", "d"))
            self.assertIsNone(whatsapp.verificar_suscripcion("unsubscribe", TOKEN, "d"))
            self.assertIsNone(whatsapp.verificar_suscripcion("subscribe", TOKEN, None))

    # AC-T3-05
    def test_verificar_firma(self):
        cuerpo = b'{"hola": "mundo"}'
        correcta = hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()
        with patch.dict("os.environ", {"WHATSAPP_APP_SECRET": SECRETO}):
            self.assertTrue(whatsapp.verificar_firma(cuerpo, f"sha256={correcta}"))
            self.assertFalse(whatsapp.verificar_firma(cuerpo, None))
            self.assertFalse(whatsapp.verificar_firma(cuerpo, correcta))
            self.assertFalse(whatsapp.verificar_firma(cuerpo, "sha256=00deadbeef"))
            self.assertFalse(whatsapp.verificar_firma(b"otro cuerpo", f"sha256={correcta}"))


class EntrantesTests(TestCase):
    # AC-T3-06
    def test_se_guarda_el_nombre_de_perfil_que_manda_meta(self):
        """Lo único que se sabe de un desconocido: prellena su alta como cliente."""
        payload = _payload_texto(
            "wamid.perfil", "5491155551001", "hola", perfil="Daniel Peterson"
        )
        with patch.object(whatsapp, "en_segundo_plano"):
            whatsapp.procesar_webhook(payload)

        contacto = ContactoWhatsapp.objects.get(numero="+5491155551001")
        self.assertEqual(contacto.nombre_perfil, "Daniel Peterson")

    # AC-T3-06
    def test_el_perfil_completa_un_contacto_viejo_pero_no_pisa_el_guardado(self):
        sin_perfil = fabricas.crear_contacto(None, numero="+5491155551001")
        self.assertIsNone(sin_perfil.nombre_perfil)

        with patch.object(whatsapp, "en_segundo_plano"):
            whatsapp.procesar_webhook(
                _payload_texto("wamid.p1", "5491155551001", "hola", perfil="Daniel")
            )
            sin_perfil.refresh_from_db()
            self.assertEqual(sin_perfil.nombre_perfil, "Daniel")

            # Un segundo mensaje con otro nombre no lo reescribe.
            whatsapp.procesar_webhook(
                _payload_texto("wamid.p2", "5491155551001", "hola", perfil="Otro")
            )
        sin_perfil.refresh_from_db()
        self.assertEqual(sin_perfil.nombre_perfil, "Daniel")

    # AC-T3-06
    def test_un_numero_nuevo_crea_contacto_conversacion_y_mensaje(self):
        payload = _payload_texto("wamid.nuevo", "5491155551001", "hola")
        with patch.object(whatsapp, "en_segundo_plano") as fondo:
            whatsapp.procesar_webhook(payload)

        contacto = ContactoWhatsapp.objects.get(numero="+5491155551001")
        self.assertIsNone(contacto.cliente)
        conversacion = Conversacion.objects.get(contacto=contacto)
        self.assertEqual(conversacion.estado, EstadoConversacion.ABIERTA)

        mensaje = Mensaje.objects.get(wa_message_id="wamid.nuevo")
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.RECIBIDO)
        self.assertEqual(mensaje.direccion, "entrante")
        self.assertEqual(mensaje.emisor, "cliente")
        self.assertEqual(mensaje.payload["id"], "wamid.nuevo")
        self.assertEqual(conversacion.ultimo_mensaje_cliente_en, mensaje.fecha_hora)

        from negocio.bot.orquestador import procesar_mensaje

        fondo.assert_called_once_with(procesar_mensaje, mensaje.id)

    # AC-T3-07
    def test_reutiliza_contacto_y_conversacion_abierta_en_cualquier_formato(self):
        contacto = fabricas.crear_contacto(None, numero="+5491155551001")
        conversacion = fabricas.crear_conversacion(contacto)

        with patch.object(whatsapp, "en_segundo_plano"):
            whatsapp.procesar_webhook(_payload_texto("wamid.a", "5411 5555-1001", "uno"))
            whatsapp.procesar_webhook(_payload_texto("wamid.b", "54911 5555 1001", "dos"))

        self.assertEqual(ContactoWhatsapp.objects.count(), 1)
        self.assertEqual(Conversacion.objects.count(), 1)
        self.assertEqual(Mensaje.objects.filter(conversacion=conversacion).count(), 2)

    # AC-T3-07
    def test_si_la_conversacion_estaba_cerrada_se_abre_una_nueva(self):
        contacto = fabricas.crear_contacto(None, numero="+5491155551002")
        # La base exige `cerrada_en` cuando el estado es `cerrada`.
        cerrada = fabricas.crear_conversacion(
            contacto,
            estado=EstadoConversacion.CERRADA,
            cerrada_en=timezone.now(),
        )

        with patch.object(whatsapp, "en_segundo_plano"):
            whatsapp.procesar_webhook(_payload_texto("wamid.c", "+5491155551002", "hola"))

        self.assertEqual(Conversacion.objects.filter(contacto=contacto).count(), 2)
        cerrada.refresh_from_db()
        self.assertEqual(cerrada.estado, EstadoConversacion.CERRADA)

    # AC-T3-07
    def test_no_devuelve_al_bot_una_conversacion_que_tomo_un_humano(self):
        contacto = fabricas.crear_contacto(None, numero="+5491155551005")
        # La base exige un funcionario cuando el modo es `humano`.
        conversacion = fabricas.crear_conversacion(
            contacto, modo="humano", funcionario=fabricas.crear_funcionario("Graciela")
        )

        with patch.object(whatsapp, "en_segundo_plano"):
            whatsapp.procesar_webhook(_payload_texto("wamid.h", "+5491155551005", "hola"))

        conversacion.refresh_from_db()
        self.assertEqual(conversacion.modo, "humano")

    # AC-T3-08
    def test_el_mismo_wa_message_id_dos_veces_no_duplica_ni_redispara(self):
        payload = _payload_texto("wamid.repetido", "+5491155551001", "hola")
        with patch.object(whatsapp, "en_segundo_plano") as fondo:
            whatsapp.procesar_webhook(payload)
            whatsapp.procesar_webhook(payload)

        self.assertEqual(Mensaje.objects.filter(wa_message_id="wamid.repetido").count(), 1)
        self.assertEqual(fondo.call_count, 1)

    # AC-T3-09
    def test_un_adjunto_se_guarda_no_dispara_el_bot_y_avisa_que_solo_hay_texto(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.img",
                                        "from": "+5491155551001",
                                        "type": "image",
                                        "image": {"id": "media-1"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        with patch.object(whatsapp, "en_segundo_plano") as fondo:
            whatsapp.procesar_webhook(payload)

        entrante = Mensaje.objects.get(wa_message_id="wamid.img")
        self.assertEqual(entrante.texto, "[mensaje de tipo image no soportado]")
        fondo.assert_not_called()

        aviso = Mensaje.objects.get(direccion="saliente", texto=SOLO_TEXTO)
        self.assertEqual(aviso.conversacion_id, entrante.conversacion_id)
        self.assertEqual(aviso.estado_envio, EstadoEnvio.ENVIADO)

    # AC-T3-10
    def test_una_excepcion_en_segundo_plano_se_loguea_y_no_se_propaga(self):
        def explotar():
            raise RuntimeError("boom")

        with self.assertLogs("negocio.whatsapp", level="ERROR") as registro:
            whatsapp.en_segundo_plano(explotar)
            # El hilo es daemon; esperamos a que termine para leer el log.
            for hilo in __import__("threading").enumerate():
                if hilo is not __import__("threading").current_thread():
                    hilo.join(timeout=5)
        self.assertTrue(any("segundo plano" in linea for linea in registro.output))

    # AC-T3-10
    def test_un_payload_con_forma_inesperada_se_loguea_y_no_lanza(self):
        with self.assertLogs("negocio.whatsapp", level="WARNING"):
            whatsapp.procesar_webhook({"entry": [{"changes": [{"value": {"messages": [{}]}}]}]})
        whatsapp.procesar_webhook({})
        whatsapp.procesar_webhook({"entry": "no es una lista"})
        self.assertEqual(Mensaje.objects.count(), 0)


class EstadoEntregaTests(TestCase):
    def setUp(self):
        self.conversacion = fabricas.crear_conversacion()
        self.mensaje = fabricas.crear_mensaje(
            self.conversacion,
            direccion="saliente",
            emisor="bot",
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            wa_message_id="wamid.saliente",
        )

    def _estado_tras(self, *statuses: str) -> str:
        for status in statuses:
            whatsapp.actualizar_estado_entrega("wamid.saliente", status)
        self.mensaje.refresh_from_db()
        return self.mensaje.estado_envio

    # AC-T3-11
    def test_el_estado_avanza_en_orden(self):
        self.assertEqual(self._estado_tras("sent"), EstadoEnvio.ENVIADO)
        self.assertEqual(self._estado_tras("delivered"), EstadoEnvio.ENTREGADO)
        self.assertEqual(self._estado_tras("read"), EstadoEnvio.LEIDO)

    # AC-T3-11
    def test_leido_no_vuelve_a_entregado(self):
        self.assertEqual(
            self._estado_tras("sent", "delivered", "read", "delivered", "sent"),
            EstadoEnvio.LEIDO,
        )

    # AC-T3-11
    def test_failed_no_aplica_sobre_entregado_ni_leido(self):
        self.assertEqual(self._estado_tras("sent", "delivered", "failed"), EstadoEnvio.ENTREGADO)
        self.assertEqual(self._estado_tras("read", "failed"), EstadoEnvio.LEIDO)

    # AC-T3-11
    def test_failed_si_aplica_sobre_enviado(self):
        self.assertEqual(self._estado_tras("sent", "failed"), EstadoEnvio.FALLIDO)

    # AC-T3-11
    def test_un_id_desconocido_o_un_status_raro_se_ignoran(self):
        whatsapp.actualizar_estado_entrega("wamid.no-existe", "read")
        self.assertEqual(self._estado_tras("inventado"), EstadoEnvio.PENDIENTE_ENVIO)
        whatsapp.procesar_webhook(_payload_estado("wamid.no-existe", "read"))


class EnvioTests(TestCase):
    def setUp(self):
        self.conversacion = fabricas.crear_conversacion(
            ultimo_mensaje_cliente_en=timezone.now()
        )

    def _saliente(self, estado: str = EstadoEnvio.PENDIENTE_ENVIO) -> Mensaje:
        return fabricas.crear_mensaje(
            self.conversacion,
            direccion="saliente",
            emisor="bot",
            estado_envio=estado,
            wa_message_id=None,
        )

    # AC-T3-12
    def test_en_modo_simulado_marca_enviado_y_no_toca_la_red(self):
        mensaje = self._saliente()
        with patch.dict("os.environ", {"WHATSAPP_MODO": "simulado"}):
            with patch("negocio.whatsapp.request.urlopen") as red:
                self.assertEqual(whatsapp.enviar_pendientes(self.conversacion.id), 1)
        red.assert_not_called()
        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.ENVIADO)
        self.assertIsNotNone(mensaje.enviado_en)

    # AC-T3-13
    def test_en_modo_real_guarda_el_wa_message_id_que_devuelve_la_api(self):
        mensaje = self._saliente()
        respuesta = json.dumps({"messages": [{"id": "wamid.meta.1"}]}).encode()

        class _Respuesta:
            def read(self):
                return respuesta

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        entorno = {
            "WHATSAPP_MODO": "real",
            "WHATSAPP_ACCESS_TOKEN": "token",
            "WHATSAPP_PHONE_NUMBER_ID": "123",
            "WHATSAPP_API_VERSION": "v21.0",
        }
        with patch.dict("os.environ", entorno):
            with patch("negocio.whatsapp.request.urlopen", return_value=_Respuesta()) as red:
                self.assertEqual(whatsapp.enviar_pendientes(self.conversacion.id), 1)

        peticion = red.call_args.args[0]
        self.assertEqual(red.call_args.kwargs["timeout"], 10)
        self.assertEqual(peticion.headers["Authorization"], "Bearer token")
        self.assertIn("/v21.0/123/messages", peticion.full_url)
        cuerpo = json.loads(peticion.data.decode())
        self.assertEqual(cuerpo["messaging_product"], "whatsapp")
        self.assertFalse(cuerpo["to"].startswith("+"))

        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.ENVIADO)
        self.assertEqual(mensaje.wa_message_id, "wamid.meta.1")

    # AC-T3-13
    def test_si_la_api_falla_el_mensaje_queda_fallido_con_el_detalle(self):
        mensaje = self._saliente()
        entorno = {"WHATSAPP_MODO": "real", "WHATSAPP_PHONE_NUMBER_ID": "123"}
        with patch.dict("os.environ", entorno):
            with patch(
                "negocio.whatsapp.request.urlopen", side_effect=OSError("sin red")
            ):
                self.assertEqual(whatsapp.enviar_pendientes(self.conversacion.id), 0)

        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.FALLIDO)
        self.assertIn("sin red", mensaje.error)

    # AC-T3-13
    def test_a_un_movil_argentino_se_le_envia_sin_el_9(self):
        """El `wa_id` argentino lleva un 9 que la API de envío rechaza."""
        contacto = self.conversacion.contacto
        contacto.numero = "+5491126914442"
        contacto.save(update_fields=["numero"])
        self._saliente()

        class _RespuestaOk:
            def read(self):
                return json.dumps({"messages": [{"id": "wamid.ok"}]}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        entorno = {"WHATSAPP_MODO": "real", "WHATSAPP_PHONE_NUMBER_ID": "123"}
        with patch.dict("os.environ", entorno):
            with patch(
                "negocio.whatsapp.request.urlopen", return_value=_RespuestaOk()
            ) as red:
                whatsapp.enviar_pendientes(self.conversacion.id)

        cuerpo = json.loads(red.call_args.args[0].data.decode())
        self.assertEqual(cuerpo["to"], "541126914442")
        # El número de la base no se toca: el 9 es parte de su identidad en WhatsApp.
        contacto.refresh_from_db()
        self.assertEqual(str(contacto.numero), "+5491126914442")

    # AC-T3-13
    def test_si_la_api_rechaza_el_envio_se_guarda_el_motivo_de_meta(self):
        """Un 400 de Meta trae el motivo en el cuerpo, no en el status."""
        mensaje = self._saliente()
        cuerpo = json.dumps(
            {
                "error": {
                    "message": "(#131030) Recipient phone number not in allowed list",
                    "code": 131030,
                }
            }
        ).encode("utf-8")
        fallo = HTTPError(
            "https://graph.facebook.com", 400, "Bad Request", {}, io.BytesIO(cuerpo)
        )
        entorno = {"WHATSAPP_MODO": "real", "WHATSAPP_PHONE_NUMBER_ID": "123"}
        with patch.dict("os.environ", entorno):
            with patch("negocio.whatsapp.request.urlopen", side_effect=fallo):
                self.assertEqual(whatsapp.enviar_pendientes(self.conversacion.id), 0)

        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.FALLIDO)
        self.assertIn("131030", mensaje.error)
        self.assertIn("not in allowed list", mensaje.error)

    # AC-T3-14
    def test_nunca_envia_retenidos_descartados_enviados_ni_fallidos(self):
        intocables = {
            estado: self._saliente(estado)
            for estado in (
                EstadoEnvio.RETENIDO,
                EstadoEnvio.DESCARTADO,
                EstadoEnvio.ENVIADO,
                EstadoEnvio.FALLIDO,
            )
        }
        with patch.dict("os.environ", {"WHATSAPP_MODO": "simulado"}):
            self.assertEqual(whatsapp.enviar_pendientes(self.conversacion.id), 0)

        for estado, mensaje in intocables.items():
            with self.subTest(estado=estado):
                mensaje.refresh_from_db()
                self.assertEqual(mensaje.estado_envio, estado)
                self.assertIsNone(mensaje.enviado_en)

    # AC-T3-15
    def test_con_la_ventana_de_24h_cerrada_quedan_fallidos_sin_llamar_a_la_api(self):
        self.conversacion.ultimo_mensaje_cliente_en = timezone.now() - timedelta(hours=25)
        self.conversacion.save(update_fields=["ultimo_mensaje_cliente_en"])
        mensaje = self._saliente()

        with patch.dict("os.environ", {"WHATSAPP_MODO": "real"}):
            with patch("negocio.whatsapp.request.urlopen") as red:
                self.assertEqual(whatsapp.enviar_pendientes(self.conversacion.id), 0)
        red.assert_not_called()

        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.FALLIDO)
        self.assertEqual(mensaje.error, "ventana_24h_cerrada")
