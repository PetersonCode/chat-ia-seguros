"""Etapa A: configuración, permisos, errores, CSRF y paginación.

AC-T2-01 a AC-T2-05.
"""

from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.tests.base import CLAVE, ApiTestCase
from datos import fabricas
from datos.models import EstadoEnvio


class ConfiguracionTests(SimpleTestCase):
    # AC-T2-01
    def test_rest_framework_usa_sesion_json_y_el_manejador_propio(self):
        config = settings.REST_FRAMEWORK
        self.assertEqual(
            config["DEFAULT_AUTHENTICATION_CLASSES"],
            ["rest_framework.authentication.SessionAuthentication"],
        )
        self.assertEqual(
            config["DEFAULT_PERMISSION_CLASSES"], ["api.permisos.EsFuncionario"]
        )
        self.assertEqual(
            config["DEFAULT_RENDERER_CLASSES"],
            ["rest_framework.renderers.JSONRenderer"],
        )
        self.assertEqual(config["EXCEPTION_HANDLER"], "api.errores.manejar")

    # AC-T2-04
    def test_las_cookies_estan_configuradas_para_el_front(self):
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)

    # AC-T2-01
    def test_los_estaticos_del_front_se_sirven_desde_frontend_static(self):
        self.assertEqual(settings.STATIC_URL, "/static/")
        self.assertIn(
            settings.BASE_DIR / "frontend" / "static", settings.STATICFILES_DIRS
        )


class PermisosTests(ApiTestCase):
    # AC-T2-02
    def test_un_anonimo_recibe_401_no_autenticado(self):
        self.assertError(self.cliente_api.get("/api/auth/me/"), 401, "no_autenticado")

    # AC-T2-02
    def test_un_usuario_sin_funcionario_activo_recibe_403(self):
        from django.contrib.auth import get_user_model

        get_user_model().objects.create_user(
            username="ajeno@tests.local", email="ajeno@tests.local", password=CLAVE
        )
        self.cliente_api.login(username="ajeno@tests.local", password=CLAVE)
        self.assertError(
            self.cliente_api.get("/api/auth/me/"), 403, "permiso_denegado"
        )

    # AC-T2-02
    def test_un_operador_no_pasa_donde_se_exige_aprobador(self):
        self.entrar(self.operador)
        self.assertError(
            self.cliente_api.post("/api/consultas/1/reabrir/"), 403, "permiso_denegado"
        )

    # AC-T2-02
    def test_el_funcionario_queda_en_request_funcionario(self):
        self.entrar()
        respuesta = self.cliente_api.get("/api/auth/me/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["id"], self.aprobadora.id)


class ErroresTests(ApiTestCase):
    # AC-T2-03
    def test_los_errores_de_negocio_viajan_con_su_codigo_y_su_http(self):
        self.entrar()
        consulta = fabricas.crear_consulta(self.conversacion)
        retenido = fabricas.crear_mensaje(
            self.conversacion,
            consulta=consulta,
            direccion="saliente",
            emisor="bot",
            estado_envio=EstadoEnvio.RETENIDO,
            wa_message_id=None,
        )

        # 400 datos_invalidos: motivo demasiado corto.
        self.assertError(
            self.cliente_api.post(
                f"/api/mensajes/{retenido.id}/descartar/", {"motivo": "no"}, format="json"
            ),
            400,
            "datos_invalidos",
        )
        # 404 no_encontrado.
        self.assertError(
            self.cliente_api.post("/api/mensajes/999999/liberar/", {}, format="json"),
            404,
            "no_encontrado",
        )
        # 409 estado_invalido: ya no está retenido.
        self.cliente_api.post(f"/api/mensajes/{retenido.id}/liberar/", {}, format="json")
        self.assertError(
            self.cliente_api.post(
                f"/api/mensajes/{retenido.id}/liberar/", {}, format="json"
            ),
            409,
            "estado_invalido",
        )

    # AC-T2-03
    def test_la_ventana_de_24h_cerrada_llega_con_su_codigo_especifico(self):
        from datetime import timedelta

        self.entrar()
        self.conversacion.ultimo_mensaje_cliente_en = timezone.now() - timedelta(hours=25)
        self.conversacion.save(update_fields=["ultimo_mensaje_cliente_en"])

        self.assertError(
            self.cliente_api.post(
                f"/api/conversaciones/{self.conversacion.id}/responder/",
                {"texto": "hola"},
                format="json",
            ),
            409,
            "ventana_24h_cerrada",
        )

    # AC-T2-03
    def test_un_serializer_invalido_es_400_datos_invalidos(self):
        self.entrar()
        self.assertError(
            self.cliente_api.post(
                f"/api/conversaciones/{self.conversacion.id}/responder/", {}, format="json"
            ),
            400,
            "datos_invalidos",
        )

    # AC-T2-03
    def test_un_metodo_no_permitido_es_405(self):
        self.entrar()
        self.assertError(
            self.cliente_api.delete("/api/auth/me/"), 405, "metodo_no_permitido"
        )

    # AC-T2-03
    def test_un_error_inesperado_es_500_sin_detalles_internos(self):
        self.entrar()
        with patch(
            "api.views.selectors.contar_pendientes",
            side_effect=RuntimeError("se cayó la base en la tabla secreta"),
        ):
            respuesta = self.cliente_api.get("/api/pendientes/")

        self.assertEqual(respuesta.status_code, 500)
        error = self.error_de(respuesta)
        self.assertEqual(error["codigo"], "error_interno")
        self.assertNotIn("secreta", error["mensaje"])
        self.assertNotIn("RuntimeError", error["mensaje"])

    # AC-T2-03
    def test_un_doesnotexist_de_un_selector_es_404(self):
        self.entrar()
        self.assertError(
            self.cliente_api.get("/api/clientes/999999/"), 404, "no_encontrado"
        )
        self.assertError(
            self.cliente_api.get("/api/polizas/999999/"), 404, "no_encontrado"
        )


class CsrfTests(ApiTestCase):
    # AC-T2-04
    def test_csrf_responde_204_y_entrega_la_cookie(self):
        respuesta = self.cliente_api.get("/api/auth/csrf/")
        self.assertEqual(respuesta.status_code, 204)
        self.assertIn("csrftoken", respuesta.cookies)

    # AC-T2-04
    def test_un_post_sin_el_header_x_csrftoken_es_403(self):
        estricto = APIClient(enforce_csrf_checks=True)
        self.assertTrue(estricto.login(username=self.aprobadora.email, password=CLAVE))

        sin_header = estricto.post(
            f"/api/conversaciones/{self.conversacion.id}/responder/",
            {"texto": "hola"},
            format="json",
        )
        self.assertError(sin_header, 403, "permiso_denegado")

        token = estricto.get("/api/auth/csrf/").cookies["csrftoken"].value
        con_header = estricto.post(
            f"/api/conversaciones/{self.conversacion.id}/responder/",
            {"texto": "hola"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(con_header.status_code, 201, con_header.content)


class PaginacionTests(ApiTestCase):
    # AC-T2-05
    def test_los_listados_vienen_paginados_de_25(self):
        self.entrar()
        for numero in range(27):
            fabricas.crear_cliente(dni=f"3{numero:07d}")

        primera = self.cliente_api.get("/api/clientes/").json()
        self.assertEqual(primera["total"], 28)
        self.assertEqual(primera["pagina"], 1)
        self.assertEqual(primera["por_pagina"], 25)
        self.assertEqual(len(primera["resultados"]), 25)

        segunda = self.cliente_api.get("/api/clientes/?pagina=2").json()
        self.assertEqual(segunda["pagina"], 2)
        self.assertEqual(len(segunda["resultados"]), 3)

    # AC-T2-05
    def test_una_pagina_fuera_de_rango_es_404(self):
        self.entrar()
        self.assertError(
            self.cliente_api.get("/api/clientes/?pagina=99"), 404, "no_encontrado"
        )

    # AC-T2-05
    def test_el_dinero_es_string_con_dos_decimales_y_las_fechas_son_iso(self):
        self.entrar()
        poliza = fabricas.crear_poliza(self.cliente, prima_mensual="8000.00")
        fabricas.crear_cuota(poliza, importe="4500.5")

        payload = self.cliente_api.get(f"/api/polizas/{poliza.id}/").json()
        self.assertEqual(payload["prima_mensual"], "8000.00")
        self.assertEqual(payload["cuotas"][0]["importe"], "4500.50")
        self.assertEqual(payload["fecha_vencimiento"], "2026-01-01")
        self.assertEqual(payload["fecha_inicio"], "2025-01-01")

    # AC-T2-05
    def test_las_horas_son_iso_en_utc_con_z(self):
        self.entrar()
        fabricas.crear_mensaje(self.conversacion)
        mensajes = self.cliente_api.get(
            f"/api/conversaciones/{self.conversacion.id}/mensajes/"
        ).json()["mensajes"]
        self.assertRegex(
            mensajes[0]["fecha_hora"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
        )
