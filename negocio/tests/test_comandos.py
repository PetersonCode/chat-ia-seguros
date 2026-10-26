"""Etapa F: comandos de desarrollo (AC-T3-45 y AC-T3-46)."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.tests.transacciones import conservar_conexion_del_test
from datos.models import (
    ConsultaBot,
    Direccion,
    Emisor,
    EstadoEnvio,
    EstadoTrabajoWhatsApp,
    Mensaje,
    TipoTrabajoWhatsApp,
    TrabajoWhatsApp,
)
from negocio.tests.datos_prueba import crear_escenario


class SimularWhatsappTests(TestCase):
    def setUp(self):
        self.escenario = crear_escenario()

    # AC-T3-45
    def test_registra_el_mensaje_lo_procesa_sin_hilo_y_muestra_la_respuesta(self):
        salida = StringIO()
        call_command(
            "simular_whatsapp",
            "+5491155551001",
            "cuánto me falta pagar",
            stdout=salida,
        )

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
        # La vigilancia registra el entrante para auditoría, sin responder.
        self.assertFalse(Mensaje.objects.filter(direccion="saliente").exists())


class ReprocesarPendientesTests(TestCase):
    def setUp(self):
        conservar_conexion_del_test(self)
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

        self.assertIn("Trabajos completados: 1", salida.getvalue())
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

        self.assertIn("Trabajos completados: 0", salida.getvalue())
        self.assertEqual(ConsultaBot.objects.count(), 1)

    # AC-T3-46
    def test_no_reintenta_el_aviso_de_adjunto(self):
        """Un adjunto ya tuvo su respuesta y queda afuera de la agrupación, así
        que nunca va a tener consulta: si el worker lo tomara, lo reintentaría
        una vez por minuto para siempre."""
        from negocio.whatsapp import PREFIJO_NO_SOPORTADO

        conversacion = self._conversacion("1001")
        fabricas.crear_mensaje(
            conversacion,
            texto=f"{PREFIJO_NO_SOPORTADO}image no soportado]",
            fecha_hora=timezone.now() - timedelta(minutes=5),
        )

        salida = StringIO()
        call_command("reprocesar_pendientes", stdout=salida)

        self.assertIn("Trabajos completados: 0", salida.getvalue())

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

        self.assertIn("Trabajos completados: 0", salida.getvalue())
        self.assertFalse(ConsultaBot.objects.exists())

    def test_recupera_respuesta_guardada_antes_de_enviarla_sin_duplicar(self):
        conversacion = self._conversacion("1001")
        entrante = fabricas.crear_mensaje(
            conversacion,
            texto="cuánto me falta pagar",
            fecha_hora=timezone.now() - timedelta(minutes=5),
        )
        tarea = TrabajoWhatsApp.objects.create(
            mensaje=entrante, tipo=TipoTrabajoWhatsApp.TEXTO
        )

        from negocio.bot.orquestador import procesar_mensaje

        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            procesar_mensaje(entrante.id)
        self.assertEqual(len(callbacks), 1)
        with patch(
            "negocio.bot.orquestador.enviar_pendientes",
            side_effect=RuntimeError("fallo entre guardar y enviar"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "fallo entre guardar y enviar"
            ):
                callbacks[0]()

        self.assertEqual(ConsultaBot.objects.count(), 1)
        respuesta = Mensaje.objects.get(
            conversacion=conversacion,
            direccion=Direccion.SALIENTE,
            emisor=Emisor.BOT,
        )
        self.assertEqual(respuesta.estado_envio, EstadoEnvio.PENDIENTE_ENVIO)

        call_command("reprocesar_pendientes", stdout=StringIO())

        tarea.refresh_from_db()
        respuesta.refresh_from_db()
        self.assertEqual(tarea.estado, EstadoTrabajoWhatsApp.COMPLETADO)
        self.assertEqual(ConsultaBot.objects.count(), 1)
        self.assertEqual(
            Mensaje.objects.filter(
                conversacion=conversacion,
                direccion=Direccion.SALIENTE,
                emisor=Emisor.BOT,
            ).count(),
            1,
        )
        self.assertEqual(respuesta.estado_envio, EstadoEnvio.ENVIADO)

    def test_reclama_un_trabajo_cuyo_lease_quedo_vencido(self):
        conversacion = self._conversacion("1001")
        entrante = fabricas.crear_mensaje(
            conversacion, texto="hola", fecha_hora=timezone.now()
        )
        tarea = TrabajoWhatsApp.objects.create(
            mensaje=entrante,
            tipo=TipoTrabajoWhatsApp.TEXTO,
            estado=EstadoTrabajoWhatsApp.PROCESANDO,
            intentos=2,
            tomado_en=timezone.now() - timedelta(minutes=30),
        )

        with patch(
            "negocio.management.commands.reprocesar_pendientes.ejecutar_trabajo_whatsapp"
        ):
            call_command("reprocesar_pendientes", stdout=StringIO())

        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, EstadoTrabajoWhatsApp.COMPLETADO)
        self.assertEqual(tarea.intentos, 3)

    def test_un_lease_vencido_en_el_ultimo_intento_pasa_a_fallido(self):
        conversacion = self._conversacion("1001")
        entrante = fabricas.crear_mensaje(conversacion, texto="hola")
        tarea = TrabajoWhatsApp.objects.create(
            mensaje=entrante,
            tipo=TipoTrabajoWhatsApp.TEXTO,
            estado=EstadoTrabajoWhatsApp.PROCESANDO,
            intentos=8,
            tomado_en=timezone.now() - timedelta(minutes=30),
        )

        call_command("reprocesar_pendientes", stdout=StringIO())

        tarea.refresh_from_db()
        self.assertEqual(tarea.estado, EstadoTrabajoWhatsApp.FALLIDO)
        self.assertEqual(tarea.intentos, 8)
        self.assertIsNone(tarea.tomado_en)
