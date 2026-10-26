"""Administración de usuarios: solo el propietario (Roberto)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from api.tests.base import CLAVE, ApiTestCase
from datos import fabricas
from datos.models import Funcionario

CLAVE_NUEVA = "Castano-2026!"


class UsuariosTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.roberto = fabricas.crear_funcionario(
            "Roberto", puede_aprobar=True, rol="propietario"
        )

    def _alta(self, **campos):
        datos = {
            "nombre": "Sofía",
            "email": "sofia@tests.local",
            "rol": "operador",
            "clave": CLAVE_NUEVA,
        }
        datos.update(campos)
        return self.cliente_api.post("/api/usuarios/", datos, format="json")

    # --- acceso ------------------------------------------------------------

    def test_solo_el_propietario_ve_la_lista(self):
        for funcionario in (self.aprobadora, self.operador):
            with self.subTest(funcionario=funcionario.nombre):
                self.cliente_api.logout()
                self.entrar(funcionario)
                self.assertError(
                    self.cliente_api.get("/api/usuarios/"), 403, "permiso_denegado"
                )

        self.cliente_api.logout()
        self.entrar(self.roberto)
        respuesta = self.cliente_api.get("/api/usuarios/")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        emails = {u["email"] for u in respuesta.json()["resultados"]}
        self.assertIn(self.aprobadora.email, emails)

    def test_una_aprobadora_no_puede_crear_ni_modificar(self):
        self.entrar(self.aprobadora)
        self.assertError(self._alta(), 403, "permiso_denegado")
        self.assertError(
            self.cliente_api.patch(
                f"/api/usuarios/{self.operador.id}/", {"activo": False}, format="json"
            ),
            403,
            "permiso_denegado",
        )

    def test_sin_sesion_es_401(self):
        self.assertEqual(self.cliente_api.get("/api/usuarios/").status_code, 401)

    # --- alta ----------------------------------------------------------------

    def test_crear_un_usuario_que_despues_puede_iniciar_sesion(self):
        self.entrar(self.roberto)

        respuesta = self._alta(puede_aprobar=True, rol="administracion")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        sofia = Funcionario.objects.get(email="sofia@tests.local")
        self.assertEqual(sofia.rol, "administracion")
        self.assertTrue(sofia.puede_aprobar)
        otro = APIClient()
        self.assertTrue(otro.login(username="sofia@tests.local", password=CLAVE_NUEVA))

    def test_no_se_puede_crear_otro_propietario(self):
        self.entrar(self.roberto)
        self.assertError(self._alta(rol="propietario"), 400, "datos_invalidos")
        self.assertFalse(Funcionario.objects.filter(email="sofia@tests.local").exists())

    def test_el_correo_repetido_o_invalido_se_rechaza(self):
        self.entrar(self.roberto)
        self.assertError(self._alta(email=self.operador.email), 400, "datos_invalidos")
        self.assertError(self._alta(email="no-es-un-correo"), 400, "datos_invalidos")

    def test_una_contrasena_debil_se_rechaza(self):
        self.entrar(self.roberto)
        self.assertError(self._alta(clave="12345678"), 400, "datos_invalidos")
        self.assertFalse(
            get_user_model().objects.filter(username="sofia@tests.local").exists()
        )

    # --- modificación ----------------------------------------------------------

    def test_desactivar_impide_iniciar_sesion(self):
        self.entrar(self.roberto)

        respuesta = self.cliente_api.patch(
            f"/api/usuarios/{self.operador.id}/", {"activo": False}, format="json"
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertFalse(respuesta.json()["activo"])
        self.assertFalse(
            APIClient().login(username=self.operador.email, password=CLAVE)
        )

    def test_cambiar_rol_y_permiso_de_aprobacion(self):
        self.entrar(self.roberto)

        self.cliente_api.patch(
            f"/api/usuarios/{self.operador.id}/",
            {"rol": "administracion", "puede_aprobar": True},
            format="json",
        )

        self.operador.refresh_from_db()
        self.assertEqual(self.operador.rol, "administracion")
        self.assertTrue(self.operador.puede_aprobar)

    def test_no_se_puede_ascender_a_propietario(self):
        self.entrar(self.roberto)
        self.assertError(
            self.cliente_api.patch(
                f"/api/usuarios/{self.operador.id}/", {"rol": "propietario"}, format="json"
            ),
            400,
            "datos_invalidos",
        )

    def test_el_propietario_no_se_puede_tocar_desde_aca(self):
        self.entrar(self.roberto)
        self.assertError(
            self.cliente_api.patch(
                f"/api/usuarios/{self.roberto.id}/", {"activo": False}, format="json"
            ),
            409,
            "estado_invalido",
        )
        self.roberto.refresh_from_db()
        self.assertTrue(self.roberto.activo)

    def test_cambiar_la_contrasena(self):
        self.entrar(self.roberto)

        respuesta = self.cliente_api.post(
            f"/api/usuarios/{self.operador.id}/clave/",
            {"clave": CLAVE_NUEVA},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertTrue(
            APIClient().login(username=self.operador.email, password=CLAVE_NUEVA)
        )

    def test_un_usuario_inexistente_es_404(self):
        self.entrar(self.roberto)
        self.assertError(
            self.cliente_api.patch("/api/usuarios/999999/", {"activo": False}, format="json"),
            404,
            "no_encontrado",
        )

    def test_la_pagina_existe(self):
        self.assertEqual(self.cliente_api.get("/panel/usuarios/").status_code, 200)
