"""Etapa F: comandos de desarrollo (AC-T3-45 y AC-T3-46)."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import ConsultaBot, EstadoEnvio, Mensaje
from negocio.tests.datos_prueba import crear_escenario


class SimularWhatsappTests(TestCase):
    def setUp(self):
        self.escenario = crear_escenario()

    # AC-T3-45
    def test_registra_el_mensaje_lo_procesa_sin_hilo_y_muestra_la_respuesta(self):
        salida = StringIO()
        with patch("negocio.whatsapp.en_segundo_plano") as fondo:
            call_command(
                "simular_whatsapp",
                "+5491155551001",
                "cuánto me falta pagar",
                stdout=salida,
            )

        # "sin hilo": el comando no delega en `en_segundo_plano`.
        fondo.assert_not_called()

        entrante = Mensaje.objects.get(direccion="entrante")
        self.assertTrue(entrante.wa_message_id.startswith("sim-"))
        self.assertEqual(entrante.estado_envio, EstadoEnvio.RECIBIDO)

        texto = salida.getvalue()
        self.assertIn("saldo", texto)
        self.assertIn("$12.500", texto)
        self.assertIn("Sin alertas", texto)

    # AC-T3-45
    def test_muestra_el_estado_y_las_alertas_cuando_la_respuesta_queda_retenida(self):
        from negocio.bot.llm import FakeLLM

        llm = FakeLLM(clasificacion="saludo", charla="Tu póliza POL-99999 está al día.")
        salida = StringIO()
        with patch("negocio.bot.orquestador.cliente_llm", return_value=llm):
            call_command("simular_whatsapp", "+5491155551001", "hola", stdout=salida)

        texto = salida.getvalue()
        self.assertIn("retenido", texto)
        self.assertIn("dato_inventado", texto)

    # AC-T3-45
    def test_avisa_cuando_la_conversacion_esta_en_modo_humano(self):
        contacto = self.escenario.contacto("1001")
        fabricas.crear_conversacion(
            contacto,
            modo="humano",
            funcionario=self.escenario.graciela,
            ultimo_mensaje_cliente_en=timezone.now(),
        )

        salida = StringIO()
        call_command("simular_whatsapp", "+5491155551001", "hola", stdout=salida)
        self.assertIn("no intervino", salida.getvalue())
        self.assertFalse(ConsultaBot.objects.exists())


class ReprocesarPendientesTests(TestCase):
    def setUp(self):
        self.escenario = crear_escenario()

    def _conversacion(self, etiqueta: str, **campos):
        return fabricas.crear_conversacion(
            self.escenario.contacto(etiqueta),
            ultimo_mensaje_cliente_en=timezone.now(),
            **campos,
        )

    # AC-T3-46
    def test_procesa_el_ultimo_mensaje_del_cliente_que_quedo_sin_consulta(self):
        conversacion = self._conversacion("1001")
        fabricas.crear_mensaje(
            conversacion,
            texto="cuánto me falta pagar",
            fecha_hora=timezone.now() - timedelta(minutes=5),
        )

        salida = StringIO()
        call_command("reprocesar_pendientes", stdout=salida)

        self.assertIn("Conversaciones procesadas: 1", salida.getvalue())
        self.assertEqual(ConsultaBot.objects.count(), 1)

    # AC-T3-46
    def test_no_procesa_dos_veces_la_misma_conversacion(self):
        conversacion = self._conversacion("1001")
        fabricas.crear_mensaje(
            conversacion,
            texto="cuánto me falta pagar",
            fecha_hora=timezone.now() - timedelta(minutes=5),
        )

        call_command("reprocesar_pendientes", stdout=StringIO())
        salida = StringIO()
        call_command("reprocesar_pendientes", stdout=salida)

        self.assertIn("Conversaciones procesadas: 0", salida.getvalue())
        self.assertEqual(ConsultaBot.objects.count(), 1)

    # AC-T3-46
    def test_saltea_lo_reciente_lo_de_modo_humano_y_lo_que_no_es_del_cliente(self):
        reciente = self._conversacion("1001")
        fabricas.crear_mensaje(reciente, texto="recién llegó", fecha_hora=timezone.now())

        humana = self._conversacion(
            "1003", modo="humano", funcionario=self.escenario.graciela
        )
        fabricas.crear_mensaje(
            humana, texto="cuánto debo", fecha_hora=timezone.now() - timedelta(hours=1)
        )

        del_bot = self._conversacion("1009")
        fabricas.crear_mensaje(
            del_bot,
            direccion="saliente",
            emisor="bot",
            texto="ya te respondí",
            estado_envio=EstadoEnvio.ENVIADO,
            fecha_hora=timezone.now() - timedelta(hours=1),
        )

        salida = StringIO()
        call_command("reprocesar_pendientes", stdout=salida)

        self.assertIn("Conversaciones procesadas: 0", salida.getvalue())
        self.assertFalse(ConsultaBot.objects.exists())
