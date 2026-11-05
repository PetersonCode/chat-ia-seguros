"""Simulación de cinco clientes: recordatorio, pago, aviso, cuota paga y cobertura.

Cada cliente escribe a su manera. El recorrido es el de un día real:

1. La gestión diaria le manda el recordatorio de la cuota que vence.
2. El cliente avisa que pagó («ya pagué», «aboné», «transferí»…).
3. El bot le pide la referencia del comprobante y el cliente la pasa (ficticia).
4. Un aprobador confirma la acción «Registro de pago»: la cuota queda paga.
5. El cliente pregunta qué le cubre la póliza y el bot cita sus condiciones.

Todo en modo WhatsApp simulado: no sale ningún mensaje real.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import override_settings
from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.gestion_models import AvisoGestion, ConfigGestion
from datos.models import AccionPendiente, Cuota, Derivacion, Mensaje, Pago, TipoAccion
from negocio.bot import plantillas
from negocio.bot.orquestador import procesar_mensaje
from negocio.gestion_diaria import procesar

# (estilo, aviso de pago, referencia que manda, referencia que se lee, pregunta de cobertura)
CLIENTES = (
    ("formal", "Buenas tardes, ya pagué la cuota de este mes.", "1111222", "1111222",
     "¿Qué me cubre mi póliza?"),
    ("apurado", "realice el pago recien", "Comprobante MP-77881", "MP-77881",
     "y que cubre?"),
    ("home banking", "aboné por home banking", "nro de operacion: 0099887766", "0099887766",
     "mi seguro cubre granizo?"),
    ("transferencia", "te transferí hace un rato", "abcxyz", "abcxyz",
     "que cobertura tengo"),
    ("con faltas", "hice la transferencia, te paso el comprobante", "es el TRX4455", "TRX4455",
     "kiero saver q me cubre"),
)


@override_settings(BUSQUEDA_SEMANTICA=False)
class SimulacionCobroYCoberturaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.hoy = timezone.localdate()
        self.ahora = datetime.combine(
            self.hoy, datetime.min.time(), tzinfo=ZoneInfo("America/Argentina/Buenos_Aires")
        ).replace(hour=12)
        ConfigGestion.objects.filter(pk=1).update(automaticos=True)
        self.entrar()
        self.casos = [self._cliente(numero) for numero in range(len(CLIENTES))]

    def _cliente(self, numero: int):
        cliente = fabricas.crear_cliente(nombre=f"Cliente{numero}", apellido="Simulado")
        contacto = fabricas.crear_contacto(cliente, numero=f"+54911000077{numero:02d}")
        poliza = fabricas.crear_poliza(cliente, compania=fabricas.crear_compania())
        cuota = fabricas.crear_cuota(
            poliza, importe=f"{15000 + numero * 1000}.00", vencimiento=self.hoy + timedelta(days=3)
        )
        respuesta = self.cliente_api.patch(
            f"/api/polizas/{poliza.id}/condiciones/",
            {
                "cubre": "Responsabilidad civil por daños a terceros y robo total.",
                "no_cubre": "Granizo ni cristales.",
                "limites": "Hasta $100.000.000.",
                "asistencia": "0800-555-0100",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        conversacion = fabricas.crear_conversacion(
            contacto, ultimo_mensaje_cliente_en=self.ahora - timedelta(hours=1)
        )
        return {"cliente": cliente, "poliza": poliza, "cuota": cuota, "conversacion": conversacion}

    def _turno(self, conversacion, texto: str):
        mensaje = fabricas.crear_mensaje(conversacion, texto=texto)
        with self.captureOnCommitCallbacks(execute=True):
            resultado = procesar_mensaje(mensaje.id)
        return resultado, Mensaje.objects.get(pk=resultado.mensaje_respuesta_id)

    def test_cinco_clientes_reciben_el_recordatorio_pagan_y_preguntan_la_cobertura(self):
        # 1. Recordatorio de la cuota que vence en tres días, a los cinco.
        with patch("django.utils.timezone.now", return_value=self.ahora), \
                self.captureOnCommitCallbacks(execute=True):
            procesar(self.ahora)
        for caso in self.casos:
            recordatorio = Mensaje.objects.get(
                conversacion=caso["conversacion"], payload__has_key="aviso_gestion_id"
            )
            self.assertIn(caso["poliza"].numero_poliza, recordatorio.texto)
            self.assertIn("Si ya pagaste", recordatorio.texto)

        for caso, (estilo, aviso, enviada, leida, pregunta) in zip(self.casos, CLIENTES):
            with self.subTest(cliente=estilo):
                conversacion = caso["conversacion"]

                # 2. Avisa que pagó: el bot pide la referencia, no deriva.
                resultado, respuesta = self._turno(conversacion, aviso)
                self.assertEqual(resultado.tipo_consulta, "pago")
                self.assertEqual(respuesta.texto, plantillas.PEDIDO_COMPROBANTE)
                self.assertEqual(respuesta.estado_envio, "enviado")

                # 3. Pasa la referencia ficticia: queda el pago para aprobar.
                resultado, respuesta = self._turno(conversacion, enviada)
                self.assertFalse(resultado.retenido, resultado.alertas)
                self.assertEqual(respuesta.texto, plantillas.PAGO_INFORMADO.format(referencia=leida))
                accion = AccionPendiente.objects.get(
                    consulta__conversacion=conversacion, tipo_accion=TipoAccion.REGISTRAR_PAGO
                )
                self.assertEqual(accion.poliza_id, caso["poliza"].id)
                self.assertEqual(accion.parametros["referencia"], leida)

                # 4. El aprobador confirma desde el panel: la cuota queda paga.
                with self.captureOnCommitCallbacks(execute=True):
                    aprobada = self.cliente_api.post(
                        f"/api/acciones/{accion.id}/aprobar/", {}, format="json"
                    )
                self.assertEqual(aprobada.status_code, 200, aprobada.content)
                caso["cuota"].refresh_from_db()
                self.assertEqual(caso["cuota"].estado, "pagada")
                self.assertEqual(Pago.objects.get(cuota=caso["cuota"]).referencia, leida)
                aviso_cliente = Mensaje.objects.filter(
                    conversacion=conversacion, emisor="funcionario"
                ).latest("id")
                self.assertIn(leida, aviso_cliente.texto)

                # 5. Pregunta qué le cubre: cita sus condiciones, sin derivar.
                resultado, respuesta = self._turno(conversacion, pregunta)
                self.assertEqual(resultado.tipo_consulta, "consulta_cobertura", respuesta.texto)
                self.assertFalse(resultado.retenido, resultado.alertas)
                self.assertIn(caso["poliza"].numero_poliza, respuesta.texto)
                self.assertIn("Granizo ni cristales", respuesta.texto)
                conversacion.refresh_from_db()
                self.assertEqual(conversacion.modo, "bot")

        self.assertFalse(Derivacion.objects.exists())
        self.assertEqual(Pago.objects.count(), len(CLIENTES))
        self.assertFalse(Cuota.objects.filter(estado__in=["pendiente", "vencida"]).exists())

        # Con la cuota paga, el recordatorio pendiente no se vuelve a mandar.
        with patch("django.utils.timezone.now", return_value=self.ahora):
            procesar(self.ahora)
        self.assertFalse(
            AvisoGestion.objects.filter(tipo="cuota", estado="pendiente").exists()
        )
