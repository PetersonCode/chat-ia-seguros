"""Alta de pólizas por la API, desde la ficha del cliente.

Mismo criterio de permisos que el ABM de clientes: leer necesita sesión, crear
exige permiso de aprobación. El contenido se valida en `negocio.polizas`; acá
se comprueba que cada error salga con el HTTP que pide el contrato.
"""

from __future__ import annotations

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import Cuota, EstadoCuota, Poliza


class AltaDePolizaPorApiTests(ApiTestCase):
    ALTA = {
        "tipo_seguro": "automotor",
        "cobertura": "intermedia",
        "fecha_inicio": "2026-01-10",
        "fecha_vencimiento": "2027-01-10",
        "prima_mensual": "18000",
        "bien_asegurado": "Ford Fiesta 2019",
    }

    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()

    @property
    def ruta(self) -> str:
        return f"/api/clientes/{self.cliente.id}/polizas/"

    def test_el_alta_devuelve_201_con_el_detalle_y_sus_cuotas(self):
        self.entrar()

        respuesta = self.cliente_api.post(self.ruta, self.ALTA, format="json")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        cuerpo = respuesta.json()
        self.assertRegex(cuerpo["numero_poliza"], r"^POL-\d{5}$")
        self.assertEqual(cuerpo["cobertura"], "intermedia")
        self.assertEqual(cuerpo["bien_asegurado"], "Ford Fiesta 2019")
        self.assertEqual(len(cuerpo["cuotas"]), 12)
        self.assertEqual(Poliza.objects.count(), 1)

    def test_la_poliza_nueva_aparece_en_la_ficha_del_cliente(self):
        self.entrar()
        self.cliente_api.post(self.ruta, self.ALTA, format="json")

        respuesta = self.cliente_api.get(f"/api/clientes/{self.cliente.id}/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(len(respuesta.json()["polizas"]), 1)

    def test_el_detalle_trae_el_saldo_y_el_proximo_pago_de_las_cuotas(self):
        """Venían siempre en null: `detalle_poliza` devuelve una `Poliza`, que
        no tiene esas columnas —las calcula `v_polizas_resumen`—, así que
        la ficha mostraba "—" en el saldo de todas las pólizas."""
        self.entrar()
        creada = self.cliente_api.post(self.ruta, self.ALTA, format="json").json()

        cuerpo = self.cliente_api.get(f"/api/polizas/{creada['id']}/").json()

        # 12 cuotas de 18.000, todas pendientes.
        self.assertEqual(cuerpo["saldo_pendiente"], "216000.00")
        self.assertEqual(cuerpo["proximo_vencimiento_pago"], "2026-01-15")

    def test_las_opciones_traen_tipos_coberturas_y_el_proximo_numero(self):
        self.entrar()

        respuesta = self.cliente_api.get("/api/polizas/opciones/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertRegex(cuerpo["numero_sugerido"], r"^POL-\d{5}$")
        self.assertIn("automotor", [tipo["codigo"] for tipo in cuerpo["tipos_seguro"]])
        self.assertEqual(cuerpo["coberturas"], ["basica", "intermedia", "total"])

    def test_el_numero_sugerido_avanza_despues_de_un_alta(self):
        self.entrar()
        primero = self.cliente_api.get("/api/polizas/opciones/").json()["numero_sugerido"]

        self.cliente_api.post(self.ruta, {**self.ALTA, "numero_poliza": primero}, format="json")

        segundo = self.cliente_api.get("/api/polizas/opciones/").json()["numero_sugerido"]
        self.assertNotEqual(segundo, primero)

    def test_los_datos_invalidos_son_400_y_no_crean_nada(self):
        self.entrar()
        casos = {
            "cobertura inexistente": {**self.ALTA, "cobertura": "premium"},
            "tipo inexistente": {**self.ALTA, "tipo_seguro": "submarino"},
            "fechas al revés": {**self.ALTA, "fecha_vencimiento": "2025-01-10"},
            "prima negativa": {**self.ALTA, "prima_mensual": "-5"},
            "número mal formado": {**self.ALTA, "numero_poliza": "12345"},
            "falta la fecha de inicio": {
                campo: valor for campo, valor in self.ALTA.items() if campo != "fecha_inicio"
            },
        }

        for nombre, cuerpo in casos.items():
            with self.subTest(caso=nombre):
                respuesta = self.cliente_api.post(self.ruta, cuerpo, format="json")
                self.assertError(respuesta, 400, "datos_invalidos")

        self.assertEqual(Poliza.objects.count(), 0)
        self.assertEqual(Cuota.objects.count(), 0)

    def test_un_numero_repetido_es_400(self):
        self.entrar()
        self.cliente_api.post(self.ruta, {**self.ALTA, "numero_poliza": "POL-04242"}, format="json")

        respuesta = self.cliente_api.post(
            self.ruta, {**self.ALTA, "numero_poliza": "POL-04242"}, format="json"
        )

        self.assertError(respuesta, 400, "datos_invalidos")
        self.assertEqual(Poliza.objects.count(), 1)

    def test_un_operador_sin_permiso_de_aprobacion_no_puede_crear(self):
        self.entrar(self.operador)

        respuesta = self.cliente_api.post(self.ruta, self.ALTA, format="json")

        self.assertError(respuesta, 403, "permiso_denegado")
        self.assertEqual(Poliza.objects.count(), 0)

    def test_un_operador_si_puede_ver_las_opciones(self):
        self.entrar(self.operador)

        respuesta = self.cliente_api.get("/api/polizas/opciones/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)

    def test_sin_sesion_el_alta_es_401(self):
        respuesta = self.cliente_api.post(self.ruta, self.ALTA, format="json")

        self.assertError(respuesta, 401, "no_autenticado")

    def test_a_un_cliente_dado_de_baja_es_409(self):
        self.entrar()
        self.cliente.activo = False
        self.cliente.save(update_fields=["activo"])

        respuesta = self.cliente_api.post(self.ruta, self.ALTA, format="json")

        self.assertError(respuesta, 409, "estado_invalido")
        self.assertEqual(Poliza.objects.count(), 0)

    def test_un_cliente_inexistente_es_404(self):
        self.entrar()

        respuesta = self.cliente_api.post(
            "/api/clientes/999999/polizas/", self.ALTA, format="json"
        )

        self.assertError(respuesta, 404, "no_encontrado")


class RegistrarPagoPorApiTests(ApiTestCase):
    """`POST /api/polizas/<id>/pagos/`: cobra la cuota impaga más vieja."""

    ALTA = {
        "tipo_seguro": "automotor",
        "cobertura": "intermedia",
        "fecha_inicio": "2026-01-10",
        "fecha_vencimiento": "2027-01-10",
        "prima_mensual": "18000",
    }

    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.entrar()
        self.poliza = self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/polizas/", self.ALTA, format="json"
        ).json()

    @property
    def ruta(self) -> str:
        return f"/api/polizas/{self.poliza['id']}/pagos/"

    def test_el_pago_devuelve_la_poliza_con_el_saldo_ya_bajado(self):
        respuesta = self.cliente_api.post(self.ruta, {}, format="json")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        # Eran 12 × 18.000; queda un mes menos.
        self.assertEqual(cuerpo["saldo_pendiente"], "198000.00")
        self.assertEqual(cuerpo["proximo_vencimiento_pago"], "2026-02-15")
        self.assertEqual(
            Cuota.objects.filter(
                poliza_id=self.poliza["id"], estado=EstadoCuota.PAGADA
            ).count(),
            1,
        )

    def test_un_operador_sin_permiso_de_aprobacion_no_puede_cobrar(self):
        self.cliente_api.logout()
        self.entrar(self.operador)

        respuesta = self.cliente_api.post(self.ruta, {}, format="json")

        self.assertError(respuesta, 403, "permiso_denegado")
        self.assertFalse(
            Cuota.objects.filter(
                poliza_id=self.poliza["id"], estado=EstadoCuota.PAGADA
            ).exists()
        )

    def test_sin_cuotas_pendientes_es_409(self):
        for _ in range(12):
            self.cliente_api.post(self.ruta, {}, format="json")

        respuesta = self.cliente_api.post(self.ruta, {}, format="json")

        self.assertError(respuesta, 409, "estado_invalido")

    def test_una_poliza_inexistente_es_404(self):
        respuesta = self.cliente_api.post("/api/polizas/999999/pagos/", {}, format="json")

        self.assertError(respuesta, 404, "no_encontrado")

    def test_sin_sesion_es_401(self):
        self.cliente_api.logout()

        self.assertError(self.cliente_api.post(self.ruta, {}, format="json"), 401, "no_autenticado")
