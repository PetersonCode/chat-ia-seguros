"""Imágenes y videos del chat: se guardan y se descargan como archivo adjunto."""

import shutil
import tempfile
from unittest.mock import patch

from django.test import override_settings

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import Mensaje, MensajeAdjunto, TipoTrabajoWhatsApp, TrabajoWhatsApp
from negocio import whatsapp
from negocio.adjuntos_chat import AdjuntoInvalido, guardar_media_de_chat
from negocio.adjuntos_siniestros import DescargaMediaInvalida

VIDEO_MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x01" * 200
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100


class AdjuntosChatTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.carpeta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.carpeta, True)
        configuracion = override_settings(PRIVATE_MEDIA_ROOT=self.carpeta)
        configuracion.enable()
        self.addCleanup(configuracion.disable)

    def _entrante(self, campo, mime, **extra):
        return fabricas.crear_mensaje(
            self.conversacion,
            texto=f"[mensaje de tipo {campo} no soportado]",
            payload={"type": campo, campo: {"id": "media-1", "mime_type": mime, "sha256": "x" * 43 + "=", **extra}},
        )

    def _guardar(self, mensaje, contenido):
        with patch("negocio.adjuntos_chat.descargar_media_whatsapp", return_value=contenido):
            return guardar_media_de_chat(mensaje.id)

    def test_un_video_se_guarda_y_aparece_como_adjunto_en_el_chat(self):
        mensaje = self._entrante("video", "video/mp4")

        self.assertEqual(self._guardar(mensaje, VIDEO_MP4).estado, "guardado")

        adjunto = MensajeAdjunto.objects.get(mensaje=mensaje)
        self.assertEqual(adjunto.content_type, "video/mp4")
        self.assertEqual(adjunto.tamano, len(VIDEO_MP4))
        self.assertRegex(adjunto.nombre_archivo, r"^video-\d{8}-\d{6}\.mp4$")
        self.entrar()
        cuerpo = self.cliente_api.get(f"/api/conversaciones/{self.conversacion.id}/mensajes/").json()
        fila = next(m for m in cuerpo["mensajes"] if m["id"] == mensaje.id)
        self.assertEqual(fila["adjunto"]["tipo"], "video")
        self.assertEqual(fila["adjunto"]["nombre"], adjunto.nombre_archivo)
        self.assertEqual(fila["adjunto"]["descarga_url"], f"/api/mensajes/{mensaje.id}/adjunto/")

    def test_un_mensaje_con_imagen_aun_sin_guardar_ya_se_ve_como_adjunto(self):
        mensaje = self._entrante("image", "image/jpeg", caption="Así quedó el paragolpes")
        self.entrar()

        cuerpo = self.cliente_api.get(f"/api/conversaciones/{self.conversacion.id}/mensajes/").json()

        fila = next(m for m in cuerpo["mensajes"] if m["id"] == mensaje.id)
        self.assertEqual(fila["adjunto"]["tipo"], "imagen")
        self.assertFalse(fila["adjunto"]["guardado"])
        self.assertRegex(fila["adjunto"]["nombre"], r"^imagen-\d{8}-\d{6}\.jpg$")
        self.assertEqual(fila["adjunto"]["texto"], "Así quedó el paragolpes")
        self.assertEqual(fila["adjunto"]["descarga_url"], f"/api/mensajes/{mensaje.id}/adjunto/")

    def test_al_pedirlo_se_baja_de_meta_y_se_entrega_como_adjunto(self):
        mensaje = self._entrante("video", "video/mp4")
        self.entrar()

        with patch("negocio.adjuntos_chat.descargar_media_whatsapp", return_value=VIDEO_MP4):
            respuesta = self.cliente_api.get(f"/api/mensajes/{mensaje.id}/adjunto/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("attachment", respuesta["Content-Disposition"])
        self.assertEqual(b"".join(respuesta.streaming_content), VIDEO_MP4)
        adjunto = MensajeAdjunto.objects.get(mensaje=mensaje)
        self.assertIn(adjunto.nombre_archivo, respuesta["Content-Disposition"])
        cuerpo = self.cliente_api.get(f"/api/conversaciones/{self.conversacion.id}/mensajes/").json()
        self.assertTrue(next(m for m in cuerpo["mensajes"] if m["id"] == mensaje.id)["adjunto"]["guardado"])

    def test_si_meta_no_entrega_el_archivo_el_error_es_claro(self):
        mensaje = self._entrante("image", "image/jpeg")
        self.entrar()

        with patch("negocio.adjuntos_chat.descargar_media_whatsapp", side_effect=DescargaMediaInvalida("caído")):
            respuesta = self.cliente_api.get(f"/api/mensajes/{mensaje.id}/adjunto/")

        self.assertEqual(respuesta.status_code, 409)
        self.assertIn("No se pudo descargar", respuesta.json()["error"]["mensaje"])
        self.assertFalse(MensajeAdjunto.objects.exists())

    def test_la_descarga_es_un_adjunto_sin_vista_previa(self):
        mensaje = self._entrante("image", "image/jpeg")
        self._guardar(mensaje, JPEG)
        self.entrar()

        respuesta = self.cliente_api.get(f"/api/mensajes/{mensaje.id}/adjunto/")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("attachment", respuesta["Content-Disposition"])
        self.assertIn(MensajeAdjunto.objects.get(mensaje=mensaje).nombre_archivo, respuesta["Content-Disposition"])
        self.assertEqual(respuesta["Content-Type"], "image/jpeg")
        self.assertEqual(respuesta["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(respuesta.streaming_content), JPEG)

    def test_sin_sesion_no_se_puede_descargar(self):
        mensaje = self._entrante("image", "image/jpeg")
        self._guardar(mensaje, JPEG)

        respuesta = self.cliente_api.get(f"/api/mensajes/{mensaje.id}/adjunto/")

        self.assertIn(respuesta.status_code, (401, 403))

    def test_un_mensaje_sin_archivo_da_404(self):
        mensaje = fabricas.crear_mensaje(self.conversacion)
        self.entrar()

        self.assertEqual(self.cliente_api.get(f"/api/mensajes/{mensaje.id}/adjunto/").status_code, 404)

    def test_un_contenido_que_no_es_lo_declarado_no_se_guarda(self):
        video_falso = self._entrante("video", "video/mp4")
        imagen_falsa = self._entrante("image", "image/png")

        with self.assertRaises(AdjuntoInvalido):
            self._guardar(video_falso, b"esto no es un video" * 5)
        with self.assertRaises(AdjuntoInvalido):
            self._guardar(imagen_falsa, JPEG)

        self.assertFalse(MensajeAdjunto.objects.exists())

    def test_guardar_dos_veces_no_duplica(self):
        mensaje = self._entrante("video", "video/mp4")
        self._guardar(mensaje, VIDEO_MP4)

        self.assertEqual(self._guardar(mensaje, VIDEO_MP4).estado, "ya_guardado")
        self.assertEqual(MensajeAdjunto.objects.filter(mensaje=mensaje).count(), 1)

    def test_un_mensaje_de_texto_no_es_media(self):
        mensaje = fabricas.crear_mensaje(self.conversacion)

        self.assertEqual(guardar_media_de_chat(mensaje.id).estado, "no_es_media")

    def test_el_webhook_encola_el_video_y_no_guarda_la_url_de_meta(self):
        payload = {"entry": [{"changes": [{"value": {"messages": [{
            "id": "wamid.video.1", "from": self.contacto.numero, "type": "video",
            "video": {"id": "media-v", "mime_type": "video/mp4", "sha256": "x" * 43 + "=", "url": "https://secreto"},
        }]}}]}]}

        whatsapp.procesar_webhook(payload)

        entrante = Mensaje.objects.get(wa_message_id="wamid.video.1")
        self.assertEqual(TrabajoWhatsApp.objects.get(mensaje=entrante).tipo, TipoTrabajoWhatsApp.VIDEO)
        self.assertNotIn("url", entrante.payload["video"])

    def test_el_trabajo_de_video_se_reintenta_si_meta_no_entrega_el_archivo(self):
        mensaje = self._entrante("video", "video/mp4")
        trabajo = TrabajoWhatsApp.objects.create(mensaje=mensaje, tipo=TipoTrabajoWhatsApp.VIDEO)

        with patch("negocio.adjuntos_chat.descargar_media_whatsapp", side_effect=DescargaMediaInvalida("caído")):
            with self.assertRaises(DescargaMediaInvalida):
                whatsapp.ejecutar_trabajo_whatsapp(trabajo.id)
        self.assertFalse(MensajeAdjunto.objects.exists())

        with patch("negocio.adjuntos_chat.descargar_media_whatsapp", return_value=VIDEO_MP4):
            whatsapp.ejecutar_trabajo_whatsapp(trabajo.id)
        self.assertTrue(MensajeAdjunto.objects.filter(mensaje=mensaje).exists())
