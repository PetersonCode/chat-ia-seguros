import base64
import hashlib
import io
import json
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from negocio.adjuntos_siniestros import (
    TAMANO_MAXIMO,
    TAMANO_MAXIMO_WHATSAPP,
    AdjuntoInvalido,
    DescargaMediaInvalida,
    _leer_limitado,
    _normalizar_imagen,
    descargar_media_whatsapp,
)


class RespuestaMedia:
    def __init__(self, contenido):
        self.contenido = contenido

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limite=-1):
        return self.contenido[:limite]


def crear_imagen(formato="PNG"):
    salida = io.BytesIO()
    Image.new("RGB", (3, 2), "blue").save(salida, format=formato)
    return salida.getvalue()


class ValidacionImagenTests(SimpleTestCase):
    def test_acepta_y_reencoda_jpeg_png_y_webp(self):
        tipos = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }
        for formato, mime in tipos.items():
            with self.subTest(formato=formato):
                imagen, mime_real, _ = _normalizar_imagen(crear_imagen(formato))
                self.assertGreater(len(imagen), 0)
                self.assertEqual(mime_real, mime)

    def test_rechaza_contenido_falso_y_archivos_mayores_a_10_mib(self):
        with self.assertRaises(AdjuntoInvalido):
            _normalizar_imagen(b"esto no es una imagen")
        with self.assertRaises(AdjuntoInvalido):
            _leer_limitado(
                SimpleUploadedFile("grande.png", b"x" * (TAMANO_MAXIMO + 1))
            )


class DescargaWhatsAppTests(SimpleTestCase):
    def _datos_descarga(self, contenido):
        digest = base64.b64encode(hashlib.sha256(contenido).digest()).decode("ascii")
        metadata = {
            "id": "1234567890",
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/test",
            "mime_type": "image/png",
            "file_size": len(contenido),
            "sha256": digest,
        }
        opener = MagicMock()
        opener.open.side_effect = [
            RespuestaMedia(json.dumps(metadata).encode()),
            RespuestaMedia(contenido),
        ]
        variables = {
            "WHATSAPP_ACCESS_TOKEN": "token-de-prueba",
            "WHATSAPP_PHONE_NUMBER_ID": "12345",
            "WHATSAPP_API_VERSION": "v26.0",
        }
        return digest, opener, variables, metadata

    def test_descarga_con_bearer_y_verifica_el_hash_oficial_en_base64(self):
        contenido = crear_imagen()
        digest, opener, variables, _ = self._datos_descarga(contenido)
        with patch.dict("os.environ", variables), patch(
            "negocio.adjuntos_siniestros.build_opener", return_value=opener
        ):
            descargado = descargar_media_whatsapp(
                "1234567890",
                mime_esperado="image/png",
                sha256_esperado=digest,
            )

        self.assertEqual(descargado, contenido)
        self.assertEqual(opener.open.call_count, 2)
        self.assertTrue(
            opener.open.call_args_list[0].args[0].get_header("Authorization")
        )
        self.assertTrue(
            opener.open.call_args_list[1].args[0].get_header("Authorization")
        )

    def test_rechaza_url_no_meta_y_checksum_incorrecto(self):
        contenido = crear_imagen()
        digest, opener, variables, metadata = self._datos_descarga(contenido)
        metadata["url"] = "https://example.invalid/file"
        opener.open.side_effect = [RespuestaMedia(json.dumps(metadata).encode())]
        with patch.dict("os.environ", variables), patch(
            "negocio.adjuntos_siniestros.build_opener", return_value=opener
        ):
            with self.assertRaises(DescargaMediaInvalida):
                descargar_media_whatsapp(
                    "1234567890",
                    mime_esperado="image/png",
                    sha256_esperado=digest,
                )
        self.assertEqual(opener.open.call_count, 1)

        digest, opener, variables, metadata = self._datos_descarga(contenido)
        opener.open.side_effect = [
            RespuestaMedia(json.dumps(metadata).encode()),
            RespuestaMedia(b"x" * len(contenido)),
        ]
        with patch.dict("os.environ", variables), patch(
            "negocio.adjuntos_siniestros.build_opener", return_value=opener
        ):
            with self.assertRaises(DescargaMediaInvalida):
                descargar_media_whatsapp(
                    "1234567890",
                    mime_esperado="image/png",
                    sha256_esperado=digest,
                )

    def test_whatsapp_rechaza_webp_y_tamano_superior_a_5_mib(self):
        contenido = crear_imagen()
        digest, opener, variables, metadata = self._datos_descarga(contenido)
        with patch.dict("os.environ", variables), patch(
            "negocio.adjuntos_siniestros.build_opener", return_value=opener
        ) as construir:
            with self.assertRaises(DescargaMediaInvalida):
                descargar_media_whatsapp(
                    "1234567890",
                    mime_esperado="image/webp",
                    sha256_esperado=digest,
                )
        construir.assert_not_called()

        metadata["file_size"] = TAMANO_MAXIMO_WHATSAPP + 1
        opener.open.side_effect = [
            RespuestaMedia(json.dumps(metadata).encode())
        ]
        with patch.dict("os.environ", variables), patch(
            "negocio.adjuntos_siniestros.build_opener", return_value=opener
        ):
            with self.assertRaises(DescargaMediaInvalida):
                descargar_media_whatsapp(
                    "1234567890",
                    mime_esperado="image/png",
                    sha256_esperado=digest,
                )
        self.assertEqual(opener.open.call_count, 1)
