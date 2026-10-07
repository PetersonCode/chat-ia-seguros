"""Base común de los tests de la API.

`WHATSAPP_MODO=simulado` en todos: ninguna prueba toca la red.
"""

from __future__ import annotations

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from datos import fabricas

CLAVE = "clave-de-prueba"


@override_settings(DEBUG=False)
class ApiTestCase(TestCase):
    """Crea un aprobador, un operador y un cliente con conversación abierta."""

    def setUp(self):
        self.cliente_api = APIClient()
        self.aprobadora = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
        self.operador = fabricas.crear_funcionario("Diego", puede_aprobar=False)
        self.cliente = fabricas.crear_cliente(
            dni="27345678", nombre="Laura", apellido="Fernández", email="laura@tests.local"
        )
        self.contacto = fabricas.crear_contacto(
            self.cliente, numero="+5491155551001"
        )
        self.conversacion = fabricas.crear_conversacion(
            self.contacto, ultimo_mensaje_cliente_en=timezone.now()
        )

    def entrar(self, funcionario=None):
        """Abre sesión con ese funcionario (por defecto, la aprobadora)."""
        funcionario = funcionario or self.aprobadora
        self.assertTrue(
            self.cliente_api.login(username=funcionario.email, password=CLAVE)
        )
        return funcionario

    def error_de(self, respuesta) -> dict:
        self.assertIn("error", respuesta.json(), respuesta.content)
        return respuesta.json()["error"]

    def assertError(self, respuesta, http: int, codigo: str):
        self.assertEqual(respuesta.status_code, http, respuesta.content)
        error = self.error_de(respuesta)
        self.assertEqual(error["codigo"], codigo)
        self.assertTrue(error["mensaje"])
