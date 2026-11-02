from api.tests.base import ApiTestCase
from datos.models import DocumentoGeneral, EstadoDocumento, FragmentoDocumento


class DocumentosApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.entrar()

    def _crear_borrador(self, **cambios):
        datos = {
            "titulo": "Guía de cobertura automotor",
            "version": "1.0",
            "referencia": "Manual interno autorizado, sección 3",
            "contenido": (
                "La cobertura contra robo depende del plan contratado. "
                "La cobertura básica incluye responsabilidad civil."
            ),
        }
        datos.update(cambios)
        return self.cliente_api.post("/api/documentos/", datos, format="json")

    def test_solo_documentos_aprobados_entran_en_la_busqueda_y_se_citan(self):
        borrador = self._crear_borrador()
        self.assertEqual(borrador.status_code, 201, borrador.content)
        self.assertEqual(borrador.json()["estado"], EstadoDocumento.BORRADOR)

        busqueda = self.cliente_api.get(
            "/api/documentos/buscar/?q=cobertura+robo"
        )
        self.assertEqual(busqueda.status_code, 200, busqueda.content)
        self.assertFalse(busqueda.json()["respaldo_suficiente"])
        self.assertEqual(busqueda.json()["resultados"], [])

        aprobado = self.cliente_api.post(
            f"/api/documentos/{borrador.json()['id']}/aprobar/",
            {},
            format="json",
        )
        self.assertEqual(aprobado.status_code, 200, aprobado.content)
        self.assertEqual(aprobado.json()["estado"], EstadoDocumento.APROBADO)
        registro = DocumentoGeneral.objects.get(pk=borrador.json()["id"])
        self.assertEqual(registro.aprobado_por_id, self.aprobadora.id)
        self.assertIsNotNone(registro.aprobado_en)

        busqueda = self.cliente_api.get(
            "/api/documentos/buscar/?q=cobertura+robo"
        )
        self.assertTrue(busqueda.json()["respaldo_suficiente"])
        self.assertEqual(len(busqueda.json()["resultados"]), 1)
        resultado = busqueda.json()["resultados"][0]
        self.assertEqual(resultado["titulo"], "Guía de cobertura automotor")
        self.assertEqual(resultado["version"], "1.0")
        self.assertEqual(resultado["referencia"], "Manual interno autorizado, sección 3")
        self.assertIn("cobertura contra robo", resultado["pasaje"])
        self.assertNotIn("respuesta_generada", busqueda.json())

        retirado = self.cliente_api.post(
            f"/api/documentos/{borrador.json()['id']}/retirar/",
            {},
            format="json",
        )
        self.assertEqual(retirado.status_code, 200, retirado.content)
        self.assertEqual(retirado.json()["estado"], EstadoDocumento.RETIRADO)
        registro.refresh_from_db()
        self.assertEqual(registro.retirado_por_id, self.aprobadora.id)
        self.assertIsNotNone(registro.retirado_en)
        sin_respaldo = self.cliente_api.get(
            "/api/documentos/buscar/?q=cobertura+robo"
        )
        self.assertFalse(sin_respaldo.json()["respaldo_suficiente"])

    def test_busqueda_y_gestion_exigen_funcionario_aprobador_para_escrituras(self):
        self.cliente_api.logout()
        self.assertEqual(
            self.cliente_api.get("/api/documentos/buscar/?q=cobertura").status_code,
            401,
        )
        self.entrar(self.operador)
        self.assertEqual(
            self.cliente_api.post(
                "/api/documentos/",
                {
                    "titulo": "Documento",
                    "version": "1",
                    "referencia": "Fuente permitida",
                    "contenido": "Texto autorizado.",
                },
                format="json",
            ).status_code,
            403,
        )
        abstencion = self.cliente_api.get("/api/documentos/buscar/?q=de+el")
        self.assertEqual(abstencion.status_code, 200)
        self.assertFalse(abstencion.json()["respaldo_suficiente"])
        self.assertEqual(abstencion.json()["resultados"], [])

    def test_no_repite_titulo_version_ni_aprueba_documento_retirado(self):
        borrador = self._crear_borrador()
        self.assertEqual(self._crear_borrador().status_code, 400)

        documento_id = borrador.json()["id"]
        self.cliente_api.post(f"/api/documentos/{documento_id}/aprobar/", {}, format="json")
        self.cliente_api.post(f"/api/documentos/{documento_id}/retirar/", {}, format="json")
        respuesta = self.cliente_api.post(
            f"/api/documentos/{documento_id}/aprobar/", {}, format="json"
        )
        self.assertEqual(respuesta.status_code, 409, respuesta.content)
        self.assertEqual(
            DocumentoGeneral.objects.get(pk=documento_id).estado,
            EstadoDocumento.RETIRADO,
        )
        self.assertTrue(FragmentoDocumento.objects.filter(documento_id=documento_id).exists())
