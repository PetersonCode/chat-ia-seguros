"""Etapas D y E: acciones, derivaciones, clientes y pólizas.

AC-T2-15 a AC-T2-18.
"""

from __future__ import annotations

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import EstadoAccion, TipoAccion


class AccionesTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.consulta = fabricas.crear_consulta(self.conversacion)
        self.poliza = fabricas.crear_poliza(self.cliente)

    def _accion(self, **campos):
        return fabricas.crear_accion(self.consulta, poliza=self.poliza, **campos)

    # AC-T2-15
    def test_el_listado_trae_el_objeto_accion_completo(self):
        self.entrar()
        accion = self._accion()

        payload = self.cliente_api.get("/api/acciones/").json()
        self.assertEqual(payload["total"], 1)
        fila = payload["resultados"][0]
        self.assertEqual(fila["id"], accion.id)
        self.assertEqual(fila["tipo_accion"], TipoAccion.BAJA_POLIZA)
        self.assertEqual(fila["estado"], "pendiente")
        self.assertEqual(fila["consulta_id"], self.consulta.id)
        self.assertEqual(fila["conversacion_id"], self.conversacion.id)
        self.assertEqual(fila["cliente"]["apellido"], "Fernández")
        self.assertEqual(fila["poliza"]["numero_poliza"], self.poliza.numero_poliza)
        self.assertEqual(fila["parametros"], {})
        self.assertIsNone(fila["resuelta_por"])
        self.assertIsNone(fila["resuelta_en"])

    # AC-T2-15
    def test_el_listado_filtra_por_estado_y_por_defecto_trae_pendientes(self):
        self.entrar()
        pendiente = self._accion()
        self.cliente_api.post(
            f"/api/acciones/{self._accion(tipo_accion=TipoAccion.MODIFICAR_POLIZA).id}/rechazar/",
            {"motivo": "No corresponde."},
            format="json",
        )

        por_defecto = self.cliente_api.get("/api/acciones/").json()
        self.assertEqual([a["id"] for a in por_defecto["resultados"]], [pendiente.id])

        rechazadas = self.cliente_api.get("/api/acciones/?estado=rechazada").json()
        self.assertEqual(len(rechazadas["resultados"]), 1)

        todas = self.cliente_api.get("/api/acciones/?estado=").json()
        self.assertEqual(todas["total"], 2)

    # AC-T2-15
    def test_el_detalle_de_una_accion_y_el_404(self):
        self.entrar()
        accion = self._accion()
        self.assertEqual(
            self.cliente_api.get(f"/api/acciones/{accion.id}/").json()["id"], accion.id
        )
        self.assertError(
            self.cliente_api.get("/api/acciones/999999/"), 404, "no_encontrado"
        )

    # AC-T2-16
    def test_aprobar_ejecuta_la_accion_y_devuelve_la_accion(self):
        self.entrar()
        accion = self._accion()

        payload = self.cliente_api.post(
            f"/api/acciones/{accion.id}/aprobar/", {}, format="json"
        ).json()

        self.assertEqual(payload["estado"], EstadoAccion.EJECUTADA)
        self.assertEqual(payload["resuelta_por"]["id"], self.aprobadora.id)
        self.poliza.refresh_from_db()
        self.assertEqual(self.poliza.estado, "dada_de_baja")

    # AC-T2-16
    def test_rechazar_pide_motivo_y_devuelve_la_accion(self):
        self.entrar()
        accion = self._accion()

        self.assertError(
            self.cliente_api.post(
                f"/api/acciones/{accion.id}/rechazar/", {}, format="json"
            ),
            400,
            "datos_invalidos",
        )

        payload = self.cliente_api.post(
            f"/api/acciones/{accion.id}/rechazar/",
            {"motivo": "El titular no confirmó."},
            format="json",
        ).json()
        self.assertEqual(payload["estado"], EstadoAccion.RECHAZADA)
        self.assertEqual(payload["motivo"], "El titular no confirmó.")

    # AC-T2-16
    def test_completar_parametros_con_patch(self):
        self.entrar()
        accion = self._accion(tipo_accion=TipoAccion.AGREGAR_CONDUCTOR)

        payload = self.cliente_api.patch(
            f"/api/acciones/{accion.id}/parametros/",
            {"parametros": {"nombre": "Hijo", "dni": "28.111.222"}},
            format="json",
        ).json()
        self.assertEqual(payload["parametros"], {"nombre": "Hijo", "dni": "28111222"})

    # AC-T2-16
    def test_faltan_parametros_es_400_parametros_incompletos(self):
        self.entrar()
        accion = self._accion(tipo_accion=TipoAccion.AGREGAR_CONDUCTOR)

        self.assertError(
            self.cliente_api.post(
                f"/api/acciones/{accion.id}/aprobar/", {}, format="json"
            ),
            400,
            "parametros_incompletos",
        )

    # AC-T2-16
    def test_una_accion_ya_resuelta_es_409(self):
        self.entrar()
        accion = self._accion()
        self.cliente_api.post(f"/api/acciones/{accion.id}/aprobar/", {}, format="json")

        self.assertError(
            self.cliente_api.post(
                f"/api/acciones/{accion.id}/aprobar/", {}, format="json"
            ),
            409,
            "estado_invalido",
        )

    # AC-T2-16
    def test_las_tres_operaciones_exigen_aprobador(self):
        self.entrar(self.operador)
        accion = self._accion()
        casos = (
            ("post", f"/api/acciones/{accion.id}/aprobar/", {}),
            ("post", f"/api/acciones/{accion.id}/rechazar/", {"motivo": "porque si"}),
            ("patch", f"/api/acciones/{accion.id}/parametros/", {"parametros": {}}),
        )
        for metodo, ruta, cuerpo in casos:
            with self.subTest(ruta=ruta):
                respuesta = getattr(self.cliente_api, metodo)(ruta, cuerpo, format="json")
                self.assertError(respuesta, 403, "permiso_denegado")


class DerivacionesTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.consulta = fabricas.crear_consulta(self.conversacion)

    # AC-T2-17
    def test_el_listado_solo_trae_las_del_usuario_y_sin_atender(self):
        self.entrar()
        mia = fabricas.crear_derivacion(self.consulta, self.aprobadora, prioridad="urgente")
        fabricas.crear_derivacion(self.consulta, self.operador)

        payload = self.cliente_api.get("/api/derivaciones/").json()
        self.assertEqual([d["id"] for d in payload["resultados"]], [mia.id])
        fila = payload["resultados"][0]
        self.assertEqual(fila["prioridad"], "urgente")
        self.assertEqual(fila["consulta_id"], self.consulta.id)
        self.assertEqual(fila["conversacion_id"], self.conversacion.id)
        self.assertIsNone(fila["atendida_en"])

    # AC-T2-17
    def test_atender_marca_la_derivacion_y_el_filtro_atendidas_la_muestra(self):
        self.entrar()
        mia = fabricas.crear_derivacion(self.consulta, self.aprobadora)

        payload = self.cliente_api.post(f"/api/derivaciones/{mia.id}/atender/").json()
        self.assertIsNotNone(payload["atendida_en"])

        self.assertEqual(self.cliente_api.get("/api/derivaciones/").json()["total"], 0)
        self.assertEqual(
            self.cliente_api.get("/api/derivaciones/?atendidas=1").json()["total"], 1
        )

    # AC-T2-17
    def test_atender_una_derivacion_ajena_es_403(self):
        self.entrar()
        ajena = fabricas.crear_derivacion(self.consulta, self.operador)
        self.assertError(
            self.cliente_api.post(f"/api/derivaciones/{ajena.id}/atender/"),
            403,
            "permiso_denegado",
        )


class LecturaTests(ApiTestCase):
    # AC-T2-18
    def test_clientes_busca_por_dni_y_por_apellido(self):
        self.entrar()
        fabricas.crear_poliza(self.cliente)

        por_dni = self.cliente_api.get("/api/clientes/?q=27.345.678").json()
        self.assertEqual([c["id"] for c in por_dni["resultados"]], [self.cliente.id])
        self.assertEqual(por_dni["resultados"][0]["polizas_vigentes"], 1)

        por_apellido = self.cliente_api.get("/api/clientes/?q=fernández").json()
        self.assertEqual([c["id"] for c in por_apellido["resultados"]], [self.cliente.id])

    # AC-T2-18
    def test_el_detalle_de_cliente_trae_contactos_polizas_y_siniestros(self):
        self.entrar()
        poliza = fabricas.crear_poliza(self.cliente)
        from datos.models import Siniestro

        Siniestro.objects.create(
            numero_siniestro="SIN-2025-00001",
            poliza=poliza,
            fecha_ocurrencia="2025-03-31",
            descripcion="Granizo",
            estado="denunciado",
        )

        payload = self.cliente_api.get(f"/api/clientes/{self.cliente.id}/").json()
        self.assertEqual(payload["dni"], "27345678")
        self.assertEqual(payload["contactos"], ["+5491155551001"])
        self.assertEqual(
            [p["numero_poliza"] for p in payload["polizas"]], [poliza.numero_poliza]
        )
        self.assertEqual(
            payload["siniestros"][0],
            {
                "numero_siniestro": "SIN-2025-00001",
                "fecha_ocurrencia": "2025-03-31",
                "descripcion": "Granizo",
                "estado": "denunciado",
            },
        )

    # AC-T2-18
    def test_el_detalle_de_poliza_trae_conductores_y_cuotas(self):
        self.entrar()
        poliza = fabricas.crear_poliza(self.cliente, bien_asegurado="Fiat Cronos")
        fabricas.crear_cuota(poliza, importe="8000.00")
        from datos.models import ConductorPoliza

        ConductorPoliza.objects.create(
            poliza=poliza, nombre="Laura Fernández", dni="27345678", relacion="titular"
        )

        payload = self.cliente_api.get(f"/api/polizas/{poliza.id}/").json()
        self.assertEqual(payload["cliente"]["apellido"], "Fernández")
        self.assertEqual(payload["bien_asegurado"], "Fiat Cronos")
        self.assertEqual(payload["conductores"][0]["relacion"], "titular")
        self.assertEqual(payload["cuotas"][0]["importe"], "8000.00")
        self.assertEqual(payload["cuotas"][0]["estado"], "pendiente")

    # AC-T2-18
    def test_los_metodos_no_contemplados_sobre_clientes_o_polizas_son_405(self):
        """El ABM habilita POST en la colección y PATCH en el detalle; nada más."""
        self.entrar()
        poliza = fabricas.crear_poliza(self.cliente)
        casos = (
            ("/api/clientes/", ("put", "patch", "delete")),
            (f"/api/clientes/{self.cliente.id}/", ("post", "put", "delete")),
            (f"/api/polizas/{poliza.id}/", ("post", "put", "patch", "delete")),
        )
        for ruta, metodos in casos:
            for metodo in metodos:
                with self.subTest(ruta=ruta, metodo=metodo):
                    respuesta = getattr(self.cliente_api, metodo)(ruta, {}, format="json")
                    self.assertError(respuesta, 405, "metodo_no_permitido")
