"""El cliente avisa por el chat que pagó: el bot pide la referencia del comprobante.

Con la referencia queda la acción `registrar_pago`; el pago se registra recién
cuando un aprobador la confirma, con la misma regla que desde el panel.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import (
    AccionPendiente,
    ConsultaBot,
    Cuota,
    Derivacion,
    EstadoAccion,
    EstadoCuota,
    Mensaje,
    Pago,
    TipoAccion,
)
from negocio.acciones import aprobar_accion
from negocio.bot import plantillas
from negocio.bot.guardrails import evaluar_salida
from negocio.bot.orquestador import procesar_mensaje
from negocio.bot.pago_informado import declara_pago, extraer_referencia
from negocio.tests.datos_prueba import crear_escenario


class LecturaDelAvisoTests(SimpleTestCase):
    def test_reconoce_las_formas_de_decir_que_pago(self):
        for texto in (
            "Pagué el seguro", "Realicé el pago", "aboné", "Transferí", "ya pagué la cuota",
            "hice la transferencia", "te mando el comprobante", "Comprobante 1111222",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(declara_pago(texto))

    def test_preguntar_como_o_cuanto_pagar_no_es_avisar_un_pago(self):
        for texto in (
            "¿cómo pago?", "quiero pagar", "cuánto me falta pagar", "¿pagué la cuota de marzo?",
            "¿puedo pagar por transferencia?",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(declara_pago(texto))

    def test_la_referencia_puede_tener_letras_y_o_numeros(self):
        casos = {
            "Comprobante 1111222": "1111222",
            "transferí, nro de operación: AB12": "AB12",
            "el número es MP-998877": "MP-998877",
            "pagué, comprobante PAGOFACIL": "PAGOFACIL",
        }
        for texto, esperada in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(extraer_referencia(texto, en_pedido=False), esperada)

    def test_con_el_pedido_delante_acepta_un_numero_corto_o_solo_letras(self):
        for texto, esperada in (("4455", "4455"), ("abcdef", "abcdef"), ("es la 4455", "4455")):
            with self.subTest(texto=texto):
                self.assertEqual(extraer_referencia(texto, en_pedido=True), esperada)

    def test_en_rafaga_el_codigo_solo_en_su_renglon_es_la_referencia(self):
        """«Ya pagué» y enseguida «1111222»: la ráfaga llega unida por líneas."""
        texto = "Ya pagué\n1111222"
        self.assertTrue(declara_pago(texto))
        self.assertEqual(extraer_referencia(texto, en_pedido=False), "1111222")

    def test_las_reglas_clasifican_el_aviso_de_pago_como_pago(self):
        from negocio.bot.clasificador import clasificar

        for texto in ("ya pagué la cuota", "Realice el pago", "aboné", "te transferí", "deposité ayer"):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "pago")

    def test_pagar_y_quejarse_es_un_reclamo_no_un_aviso_de_pago(self):
        for texto in (
            "pague y me sigue figurando deuda, que onda",
            "ya pagué y no se acreditó",
            "pagué y me cobraron dos veces",
        ):
            with self.subTest(texto=texto):
                self.assertFalse(declara_pago(texto))

    def test_no_toma_por_comprobante_un_importe_una_poliza_ni_una_palabra_comun(self):
        self.assertIsNone(extraer_referencia("pagué 45000", en_pedido=False))
        for texto in ("dale", "no lo tengo", "POL-00037", "05-11-2026", "te mando foto"):
            with self.subTest(texto=texto):
                self.assertIsNone(extraer_referencia(texto, en_pedido=True))


class PagoInformadoPorChatTests(TestCase):
    def setUp(self):
        self.escenario = crear_escenario()

    def _conversacion(self, etiqueta: str):
        return fabricas.crear_conversacion(
            self.escenario.contacto(etiqueta), ultimo_mensaje_cliente_en=timezone.now()
        )

    def _turno(self, conversacion, texto: str):
        mensaje = fabricas.crear_mensaje(conversacion, texto=texto)
        with self.captureOnCommitCallbacks(execute=True):
            return procesar_mensaje(mensaje.id)

    def _texto(self, resultado) -> str:
        return Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).texto

    def test_avisar_que_pago_pide_la_referencia_sin_derivar(self):
        for numero, texto in enumerate(("Pague el seguro", "Realice el pago", "Aboné", "Transferí")):
            with self.subTest(texto=texto):
                conversacion = self._conversacion("1001") if numero == 0 else fabricas.crear_conversacion(
                    fabricas.crear_contacto(self.escenario.laura), ultimo_mensaje_cliente_en=timezone.now()
                )
                resultado = self._turno(conversacion, texto)

                self.assertEqual(resultado.tipo_consulta, "pago")
                self.assertEqual(self._texto(resultado), plantillas.PEDIDO_COMPROBANTE)
                conversacion.refresh_from_db()
                self.assertEqual(conversacion.modo, "bot")
        self.assertFalse(Derivacion.objects.exists())
        self.assertFalse(AccionPendiente.objects.exists())

    def test_con_la_referencia_queda_el_pago_para_aprobar_en_la_cuota_mas_vieja(self):
        conversacion = self._conversacion("1001")
        self._turno(conversacion, "Pagué el seguro")

        resultado = self._turno(conversacion, "1111222")

        self.assertEqual(
            self._texto(resultado), plantillas.PAGO_INFORMADO.format(referencia="1111222")
        )
        accion = AccionPendiente.objects.get()
        self.assertEqual(accion.tipo_accion, TipoAccion.REGISTRAR_PAGO)
        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)
        self.assertEqual(accion.poliza.numero_poliza, "POL-00101")
        self.assertEqual(accion.parametros["referencia"], "1111222")
        self.assertEqual(accion.parametros["importe"], "8000.00")
        self.assertIn("POL-00102", accion.parametros["aclaracion"])
        # Todavía no hay pago: lo registra quien aprueba.
        self.assertFalse(Pago.objects.exists())
        self.assertFalse(Derivacion.objects.exists())
        # Aviso y referencia son el mismo caso.
        self.assertEqual(ConsultaBot.objects.filter(conversacion=conversacion).count(), 1)
        self.assertFalse(resultado.retenido)

    def test_si_la_referencia_viene_en_el_mismo_mensaje_no_la_vuelve_a_pedir(self):
        conversacion = self._conversacion("1001")

        resultado = self._turno(conversacion, "Pagué la cuota, comprobante AB-12345")

        self.assertEqual(
            self._texto(resultado), plantillas.PAGO_INFORMADO.format(referencia="AB-12345")
        )
        self.assertEqual(AccionPendiente.objects.get().parametros["referencia"], "AB-12345")

    def test_una_referencia_de_solo_letras_tambien_vale(self):
        conversacion = self._conversacion("1001")
        self._turno(conversacion, "transferí")

        self._turno(conversacion, "abcdef")

        self.assertEqual(AccionPendiente.objects.get().parametros["referencia"], "abcdef")

    def test_sin_referencia_la_vuelve_a_pedir_y_despues_deriva(self):
        conversacion = self._conversacion("1001")
        self._turno(conversacion, "ya pagué")

        segundo = self._turno(conversacion, "no lo tengo a mano")
        self.assertEqual(self._texto(segundo), plantillas.PEDIDO_COMPROBANTE_REVISAR)
        self.assertFalse(Derivacion.objects.exists())

        tercero = self._turno(conversacion, "no lo encuentro")

        self.assertEqual(self._texto(tercero), plantillas.PAGO_SIN_REFERENCIA)
        self.assertIn("deriv", self._texto(tercero))
        self.assertTrue(Derivacion.objects.exists())
        self.assertFalse(AccionPendiente.objects.exists())

    def test_si_cambia_de_tema_el_pedido_no_lo_atrapa(self):
        conversacion = self._conversacion("1001")
        self._turno(conversacion, "pagué")

        resultado = self._turno(conversacion, "cuánto me falta pagar")

        self.assertEqual(resultado.tipo_consulta, "saldo")
        self.assertFalse(AccionPendiente.objects.exists())

    def test_el_mismo_comprobante_dos_veces_no_abre_otra_solicitud(self):
        conversacion = self._conversacion("1001")
        self._turno(conversacion, "pagué, comprobante 99887766")

        resultado = self._turno(conversacion, "pagué, comprobante 99887766")

        self.assertEqual(
            self._texto(resultado), plantillas.PAGO_YA_INFORMADO.format(referencia="99887766")
        )
        self.assertEqual(AccionPendiente.objects.count(), 1)

    def test_sin_cuotas_pendientes_deriva_con_el_comprobante_en_el_motivo(self):
        conversacion = self._conversacion("1009")  # Nora: póliza sin cuotas.
        self._turno(conversacion, "realicé el pago")

        resultado = self._turno(conversacion, "ZX-4455")

        self.assertEqual(
            self._texto(resultado), plantillas.PAGO_SIN_CUOTAS.format(referencia="ZX-4455")
        )
        self.assertIn("ZX-4455", Derivacion.objects.get().motivo)
        self.assertFalse(AccionPendiente.objects.exists())

    def test_quien_no_es_cliente_sigue_el_camino_de_siempre(self):
        conversacion = self._conversacion("1004")

        resultado = self._turno(conversacion, "pagué el seguro")

        self.assertNotIn(plantillas.MARCA_PEDIDO_COMPROBANTE, self._texto(resultado))
        self.assertFalse(
            AccionPendiente.objects.filter(tipo_accion=TipoAccion.REGISTRAR_PAGO).exists()
        )

    def test_al_aprobar_se_registra_el_pago_y_se_le_avisa(self):
        conversacion = self._conversacion("1001")
        self._turno(conversacion, "pagué, comprobante 1111222")
        accion = AccionPendiente.objects.get()

        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id, self.escenario.graciela.id)

        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.EJECUTADA)
        pago = Pago.objects.get(referencia="1111222")
        self.assertEqual(pago.cuota.poliza.numero_poliza, "POL-00101")
        self.assertEqual(str(pago.importe), "8000.00")
        self.assertEqual(Cuota.objects.get(pk=pago.cuota_id).estado, EstadoCuota.PAGADA)
        aviso = Mensaje.objects.filter(conversacion=conversacion, emisor="funcionario").latest("id")
        self.assertIn("1111222", aviso.texto)

    def test_los_textos_fijos_no_disparan_alertas_de_salida(self):
        for texto in (
            plantillas.PEDIDO_COMPROBANTE,
            plantillas.PEDIDO_COMPROBANTE_REVISAR,
            plantillas.PAGO_SIN_REFERENCIA,
        ):
            with self.subTest(texto=texto[:30]):
                self.assertEqual(evaluar_salida(texto, cliente_id=None), [])
