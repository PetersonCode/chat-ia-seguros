"""ABM de clientes por la API (AC-T2-22 y AC-T2-23).

Leer la cartera sigue necesitando solo sesión; tocarla exige permiso de
aprobación, igual que aprobar una baja de póliza.
"""

from __future__ import annotations

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import Cliente, ContactoWhatsapp, EstadoPoliza


class AltaPorApiTests(ApiTestCase):
    ALTA = {
        "dni": "28111222",
        "nombre": "Juan",
        "apellido": "García",
        "telefono": "11 2691-4442",
        "email": "juan@tests.local",
    }

    # AC-T2-22
    def test_el_alta_devuelve_201_con_el_detalle_del_cliente(self):
        self.entrar()

        respuesta = self.cliente_api.post("/api/clientes/", self.ALTA, format="json")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["dni"], "28111222")
        self.assertTrue(cuerpo["activo"])
        self.assertEqual(cuerpo["contactos"], ["+5491126914442"])
        self.assertEqual(cuerpo["polizas"], [])

    # AC-T2-22
    def test_los_datos_sucios_o_repetidos_son_400(self):
        self.entrar()
        casos = {
            "dni repetido": {**self.ALTA, "dni": "27345678"},
            "dni corto": {**self.ALTA, "dni": "123"},
            "telefono repetido": {**self.ALTA, "telefono": "11 5555-1001"},
            "telefono invalido": {**self.ALTA, "telefono": "no tengo"},
            "nombre con numeros": {**self.ALTA, "nombre": "Juan 2"},
            "email invalido": {**self.ALTA, "email": "arroba-no"},
        }
        for nombre, cuerpo in casos.items():
            with self.subTest(caso=nombre):
                respuesta = self.cliente_api.post("/api/clientes/", cuerpo, format="json")
                self.assertError(respuesta, 400, "datos_invalidos")
        self.assertEqual(Cliente.objects.filter(dni="28111222").count(), 0)

    # AC-T2-22
    def test_falta_un_campo_obligatorio_y_es_400(self):
        self.entrar()
        for campo in ("dni", "nombre", "apellido", "telefono"):
            with self.subTest(campo=campo):
                cuerpo = {k: v for k, v in self.ALTA.items() if k != campo}
                respuesta = self.cliente_api.post("/api/clientes/", cuerpo, format="json")
                self.assertError(respuesta, 400, "datos_invalidos")

    # AC-T2-22
    def test_un_operador_sin_permiso_de_aprobacion_no_puede_dar_de_alta(self):
        self.entrar(self.operador)

        respuesta = self.cliente_api.post("/api/clientes/", self.ALTA, format="json")

        self.assertError(respuesta, 403, "permiso_denegado")
        self.assertFalse(Cliente.objects.filter(dni="28111222").exists())

    # AC-T2-22
    def test_un_operador_si_puede_seguir_leyendo_la_cartera(self):
        self.entrar(self.operador)

        self.assertEqual(self.cliente_api.get("/api/clientes/").status_code, 200)
        self.assertEqual(
            self.cliente_api.get(f"/api/clientes/{self.cliente.id}/").status_code, 200
        )

    # AC-T2-22
    def test_sin_sesion_el_alta_es_401(self):
        respuesta = self.cliente_api.post("/api/clientes/", self.ALTA, format="json")
        self.assertError(respuesta, 401, "no_autenticado")


class ModificacionYBajaPorApiTests(ApiTestCase):
    # AC-T2-23
    def test_el_patch_actualiza_y_devuelve_el_detalle(self):
        self.entrar()

        respuesta = self.cliente_api.patch(
            f"/api/clientes/{self.cliente.id}/",
            {"nombre": "Laura Beatriz", "telefono": "11 2691-4442"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()["nombre"], "Laura Beatriz")
        self.assertEqual(respuesta.json()["contactos"], ["+5491126914442"])
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.apellido, "Fernández")

    # AC-T2-23
    def test_el_patch_con_datos_invalidos_es_400_y_no_cambia_nada(self):
        self.entrar()

        respuesta = self.cliente_api.patch(
            f"/api/clientes/{self.cliente.id}/", {"dni": "1"}, format="json"
        )

        self.assertError(respuesta, 400, "datos_invalidos")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.dni, "27345678")

    # AC-T2-23
    def test_un_operador_no_puede_modificar(self):
        self.entrar(self.operador)

        respuesta = self.cliente_api.patch(
            f"/api/clientes/{self.cliente.id}/", {"nombre": "Otra"}, format="json"
        )

        self.assertError(respuesta, 403, "permiso_denegado")

    # AC-T2-23
    def test_la_baja_deja_el_cliente_inactivo_sin_borrar_nada(self):
        self.entrar()

        respuesta = self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/baja/", {}, format="json"
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertFalse(respuesta.json()["activo"])
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.activo)
        self.assertTrue(
            ContactoWhatsapp.objects.filter(cliente=self.cliente).exists()
        )

    # AC-T2-23
    def test_la_baja_con_polizas_vigentes_es_409(self):
        self.entrar()
        fabricas.crear_poliza(self.cliente, estado=EstadoPoliza.VIGENTE)

        respuesta = self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/baja/", {}, format="json"
        )

        self.assertError(respuesta, 409, "estado_invalido")
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.activo)

    # AC-T2-23
    def test_reactivar_vuelve_a_dejarlo_activo_y_repetirlo_es_409(self):
        self.entrar()
        self.cliente_api.post(f"/api/clientes/{self.cliente.id}/baja/", {}, format="json")

        respuesta = self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/reactivar/", {}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertTrue(respuesta.json()["activo"])

        repetida = self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/reactivar/", {}, format="json"
        )
        self.assertError(repetida, 409, "estado_invalido")

    # AC-T2-23
    def test_un_operador_no_puede_dar_de_baja_ni_reactivar(self):
        self.entrar(self.operador)

        for ruta in ("baja", "reactivar"):
            with self.subTest(ruta=ruta):
                respuesta = self.cliente_api.post(
                    f"/api/clientes/{self.cliente.id}/{ruta}/", {}, format="json"
                )
                self.assertError(respuesta, 403, "permiso_denegado")

    # AC-T2-23
    def test_sobre_un_cliente_inexistente_es_404(self):
        self.entrar()

        for ruta in ("baja", "reactivar"):
            with self.subTest(ruta=ruta):
                respuesta = self.cliente_api.post(
                    f"/api/clientes/999999/{ruta}/", {}, format="json"
                )
                self.assertError(respuesta, 404, "no_encontrado")
