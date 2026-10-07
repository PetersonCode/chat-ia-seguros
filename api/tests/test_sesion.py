"""Etapa B: sesión y utilidades (AC-T2-06 a AC-T2-09)."""

from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from api.tests.base import CLAVE, ApiTestCase
from datos import fabricas


class LoginTests(ApiTestCase):
    # AC-T2-06
    def test_login_correcto_devuelve_me_y_abre_sesion(self):
        respuesta = self.cliente_api.post(
            "/api/auth/login/",
            {"email": self.aprobadora.email, "password": CLAVE},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(
            respuesta.json(),
            {
                "id": self.aprobadora.id,
                "nombre": "Graciela",
                "email": self.aprobadora.email,
                "rol": "administracion",
                "puede_aprobar": True,
            },
        )
        # La sesión quedó abierta: `me` ya responde sin volver a autenticarse.
        self.assertEqual(self.cliente_api.get("/api/auth/me/").status_code, 200)

    # AC-T2-06
    def test_una_clave_incorrecta_es_401(self):
        self.assertError(
            self.cliente_api.post(
                "/api/auth/login/",
                {"email": self.aprobadora.email, "password": "otra"},
                format="json",
            ),
            401,
            "no_autenticado",
        )

    # AC-T2-06
    def test_un_usuario_sin_funcionario_activo_es_403(self):
        get_user_model().objects.create_user(
            username="ajeno@tests.local", email="ajeno@tests.local", password=CLAVE
        )
        self.assertError(
            self.cliente_api.post(
                "/api/auth/login/",
                {"email": "ajeno@tests.local", "password": CLAVE},
                format="json",
            ),
            403,
            "permiso_denegado",
        )

    # AC-T2-06
    def test_un_funcionario_dado_de_baja_no_puede_entrar(self):
        self.aprobadora.activo = False
        self.aprobadora.save(update_fields=["activo"])
        self.assertError(
            self.cliente_api.post(
                "/api/auth/login/",
                {"email": self.aprobadora.email, "password": CLAVE},
                format="json",
            ),
            403,
            "permiso_denegado",
        )


class MeYLogoutTests(ApiTestCase):
    # AC-T2-07
    def test_me_con_sesion_responde_200_y_sin_sesion_401(self):
        self.assertError(self.cliente_api.get("/api/auth/me/"), 401, "no_autenticado")
        self.entrar()
        self.assertEqual(self.cliente_api.get("/api/auth/me/").status_code, 200)

    # AC-T2-07
    def test_logout_responde_204_y_cierra_la_sesion(self):
        self.entrar()
        respuesta = self.cliente_api.post("/api/auth/logout/")
        self.assertEqual(respuesta.status_code, 204)
        self.assertError(self.cliente_api.get("/api/auth/me/"), 401, "no_autenticado")


class PendientesTests(ApiTestCase):
    # AC-T2-08
    def test_pendientes_devuelve_los_contadores_del_funcionario(self):
        self.entrar()
        consulta = fabricas.crear_consulta(self.conversacion)
        fabricas.crear_accion(consulta)
        fabricas.crear_accion(consulta, tipo_accion="modificar_poliza")
        fabricas.crear_derivacion(consulta, self.aprobadora)
        fabricas.crear_derivacion(consulta, self.operador)
        fabricas.crear_alerta(consulta, severidad="critica")

        self.assertEqual(
            self.cliente_api.get("/api/pendientes/").json(),
            {"acciones": 2, "derivaciones": 1, "alertas_criticas": 1},
        )

    # AC-T2-08
    def test_pendientes_sin_sesion_es_401(self):
        self.assertError(self.cliente_api.get("/api/pendientes/"), 401, "no_autenticado")


class CrearUsuariosTests(ApiTestCase):
    # AC-T2-09
    def test_crea_o_actualiza_un_usuario_por_funcionario_activo(self):
        User = get_user_model()
        inactivo = fabricas.crear_funcionario("Inactivo", activo=False)
        User.objects.filter(email=inactivo.email).delete()

        salida = StringIO()
        call_command("crear_usuarios_funcionarios", "--clave", "nueva-clave", stdout=salida)

        for funcionario in (self.aprobadora, self.operador):
            with self.subTest(funcionario=funcionario.nombre):
                usuario = User.objects.get(username=funcionario.email)
                self.assertTrue(usuario.check_password("nueva-clave"))
                self.assertTrue(usuario.is_active)

        self.assertFalse(User.objects.filter(username=inactivo.email).exists())
        self.assertNotIn("nueva-clave", salida.getvalue())

    # AC-T2-09
    def test_sin_clave_falla_con_un_mensaje_claro(self):
        with self.assertRaises(CommandError) as error:
            call_command("crear_usuarios_funcionarios", stdout=StringIO())
        self.assertIn("clave", str(error.exception).lower())
