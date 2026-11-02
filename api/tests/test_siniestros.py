import base64
import hashlib
import io
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import (
    AdjuntoSiniestro,
    EstadoEnvio,
    EstadoSiniestro,
    HistorialSiniestro,
    Mensaje,
    ModoConversacion,
    Siniestro,
    EstadoTrabajoWhatsApp,
    TrabajoWhatsApp,
)
from negocio import whatsapp
from negocio.adjuntos_siniestros import TAMANO_MAXIMO


def _imagen_png() -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(salida, format="PNG")
    return salida.getvalue()


class RespuestaMedia:
    def __init__(self, contenido):
        self.contenido = contenido

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limite=-1):
        return self.contenido[:limite]


class ExpedienteSiniestrosApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        self.poliza = fabricas.crear_poliza(
            self.cliente,
            fecha_inicio=hoy - timedelta(days=90),
            fecha_vencimiento=hoy + timedelta(days=180),
            bien_asegurado="Auto de prueba",
        )

    def _denunciar(self, **campos):
        cuerpo = {
            "cliente_id": self.cliente.id,
            "poliza_id": self.poliza.id,
            "fecha_ocurrencia": timezone.localdate().isoformat(),
            "descripcion": "Daño por granizo en el vehículo.",
        }
        cuerpo.update(campos)
        return self.cliente_api.post(
            "/api/siniestros/", cuerpo, format="json"
        )

    # AC-T2-25
    def test_aprobador_registra_y_consulta_el_expediente(self):
        self.entrar()

        respuesta = self._denunciar()

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        cuerpo = respuesta.json()
        self.assertRegex(cuerpo["numero_siniestro"], r"^SIN-\d{4}-\d{5}$")
        self.assertEqual(cuerpo["estado"], EstadoSiniestro.DENUNCIADO)
        self.assertEqual(cuerpo["cliente"]["id"], self.cliente.id)
        self.assertEqual(cuerpo["poliza"]["id"], self.poliza.id)
        self.assertEqual(len(cuerpo["historial"]), 1)
        self.assertEqual(
            cuerpo["historial"][0]["responsable"]["id"], self.aprobadora.id
        )
        self.assertTrue(cuerpo["historial"][0]["fecha"])
        self.assertIn("no confirma", cuerpo["aclaracion_decision"])

        listado = self.cliente_api.get("/api/siniestros/?estado=denunciado")
        self.assertEqual(listado.status_code, 200)
        self.assertEqual(listado.json()["total"], 1)
        detalle = self.cliente_api.get(f"/api/siniestros/{cuerpo['id']}/")
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(detalle.json()["id"], cuerpo["id"])

    # AC-T2-25
    def test_rechaza_poliza_ajena_fecha_futura_y_fecha_fuera_de_cobertura(self):
        self.entrar()
        poliza_ajena = fabricas.crear_poliza(fabricas.crear_cliente())

        self.assertError(
            self._denunciar(poliza_id=poliza_ajena.id),
            400,
            "datos_invalidos",
        )
        self.assertError(
            self._denunciar(
                fecha_ocurrencia=(timezone.localdate() + timedelta(days=1)).isoformat()
            ),
            400,
            "datos_invalidos",
        )
        self.assertError(
            self._denunciar(
                fecha_ocurrencia=(self.poliza.fecha_inicio - timedelta(days=1)).isoformat()
            ),
            400,
            "datos_invalidos",
        )
        self.assertFalse(Siniestro.objects.exists())

    # AC-T2-25
    def test_funcionario_registra_denuncia_y_solo_aprobador_decide(self):
        self.entrar(self.operador)

        siniestro = self._denunciar().json()
        self.assertEqual(siniestro["estado"], EstadoSiniestro.DENUNCIADO)
        self.assertError(
            self.cliente_api.post(
                f"/api/siniestros/{siniestro['id']}/transiciones/",
                {
                    "estado": EstadoSiniestro.EN_EVALUACION,
                    "motivo": "Inicia la revisión documental.",
                },
                format="json",
            ),
            403,
            "permiso_denegado",
        )

    # AC-T2-25
    def test_transicion_pide_motivo_y_no_admite_saltar_estados(self):
        self.entrar()
        siniestro = self._denunciar().json()
        ruta = f"/api/siniestros/{siniestro['id']}/transiciones/"

        self.assertError(
            self.cliente_api.post(
                ruta,
                {"estado": EstadoSiniestro.EN_EVALUACION},
                format="json",
            ),
            400,
            "datos_invalidos",
        )
        self.assertError(
            self.cliente_api.post(
                ruta,
                {"estado": EstadoSiniestro.APROBADO, "motivo": "Aprobado."},
                format="json",
            ),
            409,
            "estado_invalido",
        )
        self.assertEqual(
            Siniestro.objects.get(pk=siniestro["id"]).estado,
            EstadoSiniestro.DENUNCIADO,
        )

    # AC-T2-25
    def test_recorrido_completo_a_cierre_audita_cada_decision(self):
        self.entrar()
        siniestro = self._denunciar().json()
        ruta = f"/api/siniestros/{siniestro['id']}/transiciones/"
        decisiones = (
            (EstadoSiniestro.EN_EVALUACION, "Se inicia la revisión documental."),
            (EstadoSiniestro.APROBADO, "Aprobación operativa interna."),
            (EstadoSiniestro.CERRADO, "Se cierra la gestión interna."),
        )
        for estado, motivo in decisiones:
            with self.subTest(estado=estado):
                respuesta = self.cliente_api.post(
                    ruta,
                    {"estado": estado, "motivo": motivo},
                    format="json",
                )
                self.assertEqual(respuesta.status_code, 200, respuesta.content)
                self.assertEqual(respuesta.json()["estado"], estado)

        expediente = self.cliente_api.get(f"/api/siniestros/{siniestro['id']}/").json()
        self.assertEqual(expediente["estado"], EstadoSiniestro.CERRADO)
        self.assertEqual(len(expediente["historial"]), 4)
        self.assertEqual(
            HistorialSiniestro.objects.filter(
                siniestro_id=siniestro["id"],
                responsable=self.aprobadora,
            ).count(),
            4,
        )
        self.assertEqual(
            self.cliente_api.get("/api/siniestros/?estado=inventado").status_code,
            400,
        )


class AdjuntoSiniestroApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.poliza = fabricas.crear_poliza(
            self.cliente,
            fecha_inicio=timezone.localdate() - timedelta(days=90),
            fecha_vencimiento=timezone.localdate() + timedelta(days=180),
            bien_asegurado="Auto de prueba",
        )

    def _crear_expediente(self):
        self.entrar()
        respuesta = self.cliente_api.post(
            "/api/siniestros/",
            {
                "cliente_id": self.cliente.id,
                "poliza_id": self.poliza.id,
                "fecha_ocurrencia": timezone.localdate().isoformat(),
                "descripcion": "Daño en el vehículo.",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return respuesta.json()

    def test_panel_valida_guarda_y_descarga_privadamente(self):
        expediente = self._crear_expediente()
        with tempfile.TemporaryDirectory() as directorio, override_settings(
            PRIVATE_MEDIA_ROOT=directorio
        ):
            respuesta = self.cliente_api.post(
                f"/api/siniestros/{expediente['id']}/adjuntos/",
                {
                    "archivo": SimpleUploadedFile(
                        "../../nombre-original.png",
                        _imagen_png(),
                        content_type="image/png",
                    )
                },
                format="multipart",
            )
            self.assertEqual(respuesta.status_code, 201, respuesta.content)
            adjunto = AdjuntoSiniestro.objects.get(siniestro_id=expediente["id"])
            self.assertRegex(
                adjunto.clave_almacenamiento,
                rf"^siniestros/{expediente['id']}/[0-9a-f]{{32}}\.png$",
            )
            self.assertTrue((Path(directorio) / adjunto.clave_almacenamiento).is_file())
            self.assertEqual(respuesta.json()["adjuntos"][0]["id"], adjunto.id)

            descarga = self.cliente_api.get(
                respuesta.json()["adjuntos"][0]["descarga_url"]
            )
            self.assertEqual(descarga.status_code, 200)
            self.assertEqual(descarga["Content-Type"], "image/png")
            self.assertIn("private, no-store", descarga["Cache-Control"])
            self.assertEqual(descarga["X-Content-Type-Options"], "nosniff")
            # Consumir el streaming usa el cierre del cliente Django, que
            # libera el archivo sin cerrar la transacción envolvente del test.
            self.assertTrue(b"".join(descarga.streaming_content).startswith(b"\x89PNG"))

            anonimo = APIClient().get(
                respuesta.json()["adjuntos"][0]["descarga_url"]
            )
            self.assertNotEqual(anonimo.status_code, 200)
            self.assertEqual(
                self.cliente_api.get(
                    f"/api/siniestros/{expediente['id'] + 999}/"
                    f"adjuntos/{adjunto.id}/"
                ).status_code,
                404,
            )
            self.assertEqual(
                self.cliente_api.get(
                    f"/{adjunto.clave_almacenamiento}"
                ).status_code,
                404,
            )

    def test_rechaza_archivos_invalidos_y_mayores_a_10_mib(self):
        expediente = self._crear_expediente()
        ruta = f"/api/siniestros/{expediente['id']}/adjuntos/"
        respuesta = self.cliente_api.post(
            ruta,
            {
                "archivo": SimpleUploadedFile(
                    "falsa.jpg", b"no es una imagen", content_type="image/jpeg"
                )
            },
            format="multipart",
        )
        self.assertEqual(respuesta.status_code, 400, respuesta.content)
        self.assertFalse(AdjuntoSiniestro.objects.exists())

        respuesta = self.cliente_api.post(
            ruta,
            {
                "archivo": SimpleUploadedFile(
                    "demasiado.png",
                    b"x" * (TAMANO_MAXIMO + 1),
                    content_type="image/png",
                )
            },
            format="multipart",
        )
        self.assertEqual(respuesta.status_code, 400, respuesta.content)
        self.assertFalse(AdjuntoSiniestro.objects.exists())

    def _payload_imagen(self, numero_siniestro, *, sha256=None):
        contenido = _imagen_png()
        digest = base64.b64encode(hashlib.sha256(contenido).digest()).decode("ascii")
        return contenido, {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "id": "wamid.test-imagen",
                                        "from": "5491155551001",
                                        "type": "image",
                                        "image": {
                                            "id": "1234567890",
                                            "caption": f"Documentación {numero_siniestro}",
                                            "mime_type": "image/png",
                                            "sha256": sha256 or digest,
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }, digest

    def _configurar_descarga(self, contenido, digest):
        meta = {
            "id": "1234567890",
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/test",
            "mime_type": "image/png",
            "file_size": len(contenido),
            "sha256": digest,
        }
        opener = MagicMock()
        opener.open.side_effect = [
            RespuestaMedia(json.dumps(meta).encode()),
            RespuestaMedia(contenido),
        ]
        return patch(
            "negocio.adjuntos_siniestros.build_opener", return_value=opener
        ), opener

    def _procesar_webhook_imagen(self, payload):
        whatsapp.procesar_webhook(payload)
        tarea = TrabajoWhatsApp.objects.get(
            mensaje__wa_message_id=payload["entry"][0]["changes"][0]["value"][
                "messages"
            ][0]["id"]
        )
        self.assertEqual(tarea.estado, EstadoTrabajoWhatsApp.PENDIENTE)
        call_command("reprocesar_pendientes")
        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, EstadoTrabajoWhatsApp.COMPLETADO)

    def test_whatsapp_descarga_verifica_y_adjunta_a_expediente_del_titular(self):
        expediente = self._crear_expediente()
        contenido, payload, digest = self._payload_imagen(
            expediente["numero_siniestro"]
        )
        descargar, opener = self._configurar_descarga(contenido, digest)
        with tempfile.TemporaryDirectory() as directorio, override_settings(
            PRIVATE_MEDIA_ROOT=directorio
        ), patch.dict(
            "os.environ",
            {
                "WHATSAPP_ACCESS_TOKEN": "token-de-prueba",
                "WHATSAPP_PHONE_NUMBER_ID": "12345",
                "WHATSAPP_API_VERSION": "v26.0",
            },
        ), descargar:
            self._procesar_webhook_imagen(payload)
            adjunto = AdjuntoSiniestro.objects.get()
            self.assertEqual(adjunto.origen, "whatsapp")
            self.assertEqual(adjunto.siniestro_id, expediente["id"])
            self.assertEqual(adjunto.mensaje_origen.wa_message_id, "wamid.test-imagen")
            self.assertTrue((Path(directorio) / adjunto.clave_almacenamiento).is_file())
            self.assertEqual(opener.open.call_count, 2)
            respuesta_bot = Mensaje.objects.filter(
                conversacion=self.conversacion,
                direccion="saliente",
                emisor="bot",
            ).latest("id")
            self.assertEqual(respuesta_bot.estado_envio, EstadoEnvio.ENVIADO)
            self.assertIn(expediente["numero_siniestro"], respuesta_bot.texto)

    def test_whatsapp_no_descarga_sin_referencia(self):
        expediente = self._crear_expediente()
        contenido, payload, digest = self._payload_imagen(
            expediente["numero_siniestro"]
        )
        payload["entry"][0]["changes"][0]["value"]["messages"][0]["image"][
            "caption"
        ] = "Foto del auto"
        descargar, opener = self._configurar_descarga(contenido, digest)
        with patch.dict(
            "os.environ",
            {
                "WHATSAPP_ACCESS_TOKEN": "token-de-prueba",
                "WHATSAPP_PHONE_NUMBER_ID": "12345",
                "WHATSAPP_API_VERSION": "v26.0",
            },
        ), descargar:
            self._procesar_webhook_imagen(payload)
        opener.open.assert_not_called()
        self.assertFalse(AdjuntoSiniestro.objects.exists())

    def test_whatsapp_no_descarga_un_expediente_de_otro_cliente(self):
        self._crear_expediente()
        otro_cliente = fabricas.crear_cliente()
        otra_poliza = fabricas.crear_poliza(
            otro_cliente,
            fecha_inicio=timezone.localdate() - timedelta(days=90),
            fecha_vencimiento=timezone.localdate() + timedelta(days=180),
        )
        respuesta = self.cliente_api.post(
            "/api/siniestros/",
            {
                "cliente_id": otro_cliente.id,
                "poliza_id": otra_poliza.id,
                "fecha_ocurrencia": timezone.localdate().isoformat(),
                "descripcion": "Siniestro de otro titular.",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        contenido, payload, digest = self._payload_imagen(
            respuesta.json()["numero_siniestro"]
        )
        descargar, opener = self._configurar_descarga(contenido, digest)
        with patch.dict(
            "os.environ",
            {
                "WHATSAPP_ACCESS_TOKEN": "token-de-prueba",
                "WHATSAPP_PHONE_NUMBER_ID": "12345",
                "WHATSAPP_API_VERSION": "v26.0",
            },
        ), descargar:
            self._procesar_webhook_imagen(payload)
        opener.open.assert_not_called()
        self.assertFalse(AdjuntoSiniestro.objects.exists())

    def test_whatsapp_adjunta_en_atencion_humana_sin_responder(self):
        expediente = self._crear_expediente()
        self.conversacion.modo = ModoConversacion.HUMANO
        self.conversacion.funcionario = self.aprobadora
        self.conversacion.save(update_fields=["modo", "funcionario"])
        contenido, payload, digest = self._payload_imagen(
            expediente["numero_siniestro"]
        )
        payload["entry"][0]["changes"][0]["value"]["messages"][0][
            "id"
        ] = "wamid.test-imagen-humano"
        descargar, opener = self._configurar_descarga(contenido, digest)
        with tempfile.TemporaryDirectory() as directorio, override_settings(
            PRIVATE_MEDIA_ROOT=directorio
        ), patch.dict(
            "os.environ",
            {
                "WHATSAPP_ACCESS_TOKEN": "token-de-prueba",
                "WHATSAPP_PHONE_NUMBER_ID": "12345",
                "WHATSAPP_API_VERSION": "v26.0",
            },
        ), descargar:
            self._procesar_webhook_imagen(payload)
        self.assertTrue(AdjuntoSiniestro.objects.filter().exists())
        self.assertFalse(
            Mensaje.objects.filter(
                conversacion=self.conversacion,
                direccion="saliente",
                emisor="bot",
            ).exists()
        )
        self.assertEqual(opener.open.call_count, 2)
