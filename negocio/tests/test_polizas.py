"""Alta de pólizas desde el panel: validaciones, numeración y plan de cuotas.

Lo que más se cuida acá es el plan de cuotas, porque de ahí sale el saldo que
el bot le contesta a un cliente: `v_polizas_resumen` suma cuotas, así que una
póliza sin cuotas o con cuotas de más se convierte en una respuesta equivocada.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import Cuota, EstadoCuota, EstadoPoliza, Poliza
from datos.selectors import resumen_polizas
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado
from negocio.polizas import (
    alta_poliza,
    meses_de_cobertura,
    proximo_numero_poliza,
    registrar_pago,
)


class MesesDeCoberturaTests(TestCase):
    def test_un_ano_son_doce_cuotas_y_no_trece(self):
        self.assertEqual(meses_de_cobertura(date(2026, 1, 10), date(2027, 1, 10)), 12)

    def test_medio_ano_son_seis(self):
        self.assertEqual(meses_de_cobertura(date(2026, 1, 10), date(2026, 7, 10)), 6)

    def test_el_mes_empezado_no_cuenta(self):
        # Del 20/01 al 10/03 hay un mes entero y pico, no dos.
        self.assertEqual(meses_de_cobertura(date(2026, 1, 20), date(2026, 3, 10)), 1)

    def test_una_poliza_de_quince_dias_igual_lleva_una_cuota(self):
        self.assertEqual(meses_de_cobertura(date(2026, 1, 10), date(2026, 1, 25)), 1)


class AltaPolizaTests(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        self.cliente = fabricas.crear_cliente(
            dni="28111222", nombre="Juan", apellido="García"
        )

    def _alta(self, **campos):
        datos = {
            "tipo_seguro": "automotor",
            "cobertura": "intermedia",
            "fecha_inicio": date(2026, 1, 10),
            "fecha_vencimiento": date(2027, 1, 10),
            "prima_mensual": "18000",
        }
        datos.update(campos)
        return alta_poliza(self.cliente.id, **datos)

    # --- numeración -------------------------------------------------------

    def test_sin_numero_toma_el_proximo_libre(self):
        poliza = self._alta()

        self.assertRegex(poliza.numero_poliza, r"^POL-\d{5}$")
        self.assertEqual(Poliza.objects.count(), 1)

    def test_el_correlativo_sigue_al_mayor_que_exista(self):
        self._alta(numero_poliza="POL-00108")

        self.assertEqual(proximo_numero_poliza(), "POL-00109")
        self.assertEqual(self._alta().numero_poliza, "POL-00109")

    def test_el_numero_lo_puede_elegir_el_funcionario(self):
        self.assertEqual(self._alta(numero_poliza="POL-04242").numero_poliza, "POL-04242")

    def test_un_numero_repetido_o_mal_formado_no_pasa(self):
        self._alta(numero_poliza="POL-04242")
        for numero in ("POL-04242", "4242", "POL-123", "POL-123456", "ABC-00001"):
            with self.subTest(numero=numero):
                with self.assertRaises(DatosInvalidos):
                    self._alta(numero_poliza=numero)

    def test_el_numero_en_minusculas_se_normaliza(self):
        # Lo escribe una persona a mano: que importe la caja sería una molestia.
        self.assertEqual(self._alta(numero_poliza="pol-00001").numero_poliza, "POL-00001")

    # --- plan de cuotas ---------------------------------------------------

    def test_genera_una_cuota_por_mes_pendiente_y_con_vencimiento_el_15(self):
        poliza = self._alta()

        cuotas = list(Cuota.objects.filter(poliza=poliza).order_by("periodo"))
        self.assertEqual(len(cuotas), 12)
        self.assertEqual(cuotas[0].periodo, date(2026, 1, 1))
        self.assertEqual(cuotas[0].vencimiento, date(2026, 1, 15))
        self.assertEqual(cuotas[-1].periodo, date(2026, 12, 1))
        self.assertEqual({cuota.estado for cuota in cuotas}, {EstadoCuota.PENDIENTE})
        self.assertEqual({cuota.importe for cuota in cuotas}, {Decimal("18000.00")})
        # La base exige que solo una cuota pagada tenga pago cargado.
        self.assertTrue(all(cuota.fecha_pago is None for cuota in cuotas))
        self.assertTrue(all(cuota.importe_pagado is None for cuota in cuotas))

    def test_la_primera_cuota_no_vence_antes_de_que_empiece_la_poliza(self):
        poliza = self._alta(
            fecha_inicio=date(2026, 1, 20), fecha_vencimiento=date(2027, 1, 20)
        )

        primera = Cuota.objects.filter(poliza=poliza).order_by("periodo").first()
        self.assertEqual(primera.periodo, date(2026, 1, 1))
        self.assertEqual(primera.vencimiento, date(2026, 1, 20))

    def test_el_saldo_que_ve_el_bot_sale_de_las_cuotas_nuevas(self):
        poliza = self._alta()

        fila = next(
            f for f in resumen_polizas(self.cliente.id)
            if f.numero_poliza == poliza.numero_poliza
        )
        self.assertEqual(fila.saldo_pendiente, Decimal("216000.00"))
        self.assertEqual(fila.proximo_vencimiento_pago, date(2026, 1, 15))

    # --- validaciones -----------------------------------------------------

    def test_las_fechas_al_reves_o_iguales_no_pasan(self):
        for vencimiento in (date(2026, 1, 10), date(2025, 1, 10)):
            with self.subTest(vencimiento=vencimiento):
                with self.assertRaises(DatosInvalidos):
                    self._alta(fecha_vencimiento=vencimiento)

    def test_el_tipo_y_la_cobertura_tienen_que_existir(self):
        with self.assertRaises(DatosInvalidos):
            self._alta(tipo_seguro="submarino")
        with self.assertRaises(DatosInvalidos):
            self._alta(cobertura="premium")

    def test_la_prima_tiene_que_ser_un_numero_no_negativo(self):
        for prima in ("-1", "mucha plata", ""):
            with self.subTest(prima=prima):
                with self.assertRaises(DatosInvalidos):
                    self._alta(prima_mensual=prima)

    def test_la_prima_acepta_coma_decimal(self):
        poliza = self._alta(prima_mensual="18000,50")

        self.assertEqual(poliza.prima_mensual, Decimal("18000.50"))

    def test_una_poliza_que_nace_con_el_vencimiento_pasado_nace_vencida(self):
        poliza = self._alta(
            fecha_inicio=date(2020, 1, 10), fecha_vencimiento=date(2021, 1, 10)
        )

        self.assertEqual(poliza.estado, EstadoPoliza.VENCIDA)

    def test_una_poliza_con_vencimiento_futuro_nace_vigente(self):
        hoy = timezone.localdate()

        poliza = self._alta(fecha_inicio=hoy, fecha_vencimiento=hoy + timedelta(days=365))

        self.assertEqual(poliza.estado, EstadoPoliza.VIGENTE)

    def test_a_un_cliente_dado_de_baja_no_se_le_agregan_polizas(self):
        self.cliente.activo = False
        self.cliente.save(update_fields=["activo"])

        with self.assertRaises(EstadoInvalido):
            self._alta()

    def test_el_cliente_tiene_que_existir(self):
        with self.assertRaises(NoEncontrado):
            alta_poliza(
                999999,
                tipo_seguro="automotor",
                cobertura="basica",
                fecha_inicio=date(2026, 1, 1),
                fecha_vencimiento=date(2027, 1, 1),
                prima_mensual="1000",
            )

    def test_si_algo_falla_no_queda_una_poliza_a_medias(self):
        with self.assertRaises(DatosInvalidos):
            self._alta(cobertura="premium")

        self.assertEqual(Poliza.objects.count(), 0)
        self.assertEqual(Cuota.objects.count(), 0)

    def test_el_bien_asegurado_es_opcional_y_vacio_queda_en_null(self):
        self.assertIsNone(self._alta(bien_asegurado="   ").bien_asegurado)
        self.assertEqual(
            self._alta(bien_asegurado=" Ford Fiesta ").bien_asegurado, "Ford Fiesta"
        )


class RegistrarPagoTests(TestCase):
    """Cobrar una cuota: siempre la impaga más vieja, de a una."""

    def setUp(self):
        fabricas.crear_catalogos()
        self.cliente = fabricas.crear_cliente(
            dni="28111222", nombre="Juan", apellido="García"
        )
        self.poliza = alta_poliza(
            self.cliente.id,
            tipo_seguro="automotor",
            cobertura="intermedia",
            fecha_inicio=date(2026, 1, 10),
            fecha_vencimiento=date(2027, 1, 10),
            prima_mensual="18000",
        )

    def test_cobra_la_cuota_mas_vieja_con_fecha_e_importe(self):
        cuota = registrar_pago(self.poliza.id)

        self.assertEqual(cuota.periodo, date(2026, 1, 1))
        self.assertEqual(cuota.estado, EstadoCuota.PAGADA)
        self.assertEqual(cuota.fecha_pago, timezone.localdate())
        # La base exige los dos campos juntos cuando la cuota queda pagada.
        self.assertEqual(cuota.importe_pagado, Decimal("18000.00"))

    def test_el_saldo_que_ve_el_bot_baja_un_mes_por_pago(self):
        registrar_pago(self.poliza.id)

        fila = next(
            f for f in resumen_polizas(self.cliente.id)
            if f.numero_poliza == self.poliza.numero_poliza
        )
        self.assertEqual(fila.saldo_pendiente, Decimal("198000.00"))
        self.assertEqual(fila.proximo_vencimiento_pago, date(2026, 2, 15))

    def test_dos_pagos_seguidos_cobran_dos_meses_distintos(self):
        primera = registrar_pago(self.poliza.id)
        segunda = registrar_pago(self.poliza.id)

        self.assertEqual(primera.periodo, date(2026, 1, 1))
        self.assertEqual(segunda.periodo, date(2026, 2, 1))
        self.assertEqual(
            Cuota.objects.filter(
                poliza=self.poliza, estado=EstadoCuota.PAGADA
            ).count(),
            2,
        )

    def test_una_cuota_vencida_tambien_se_cobra(self):
        vieja = Cuota.objects.filter(poliza=self.poliza).order_by("periodo").first()
        vieja.estado = EstadoCuota.VENCIDA
        vieja.save(update_fields=["estado"])

        self.assertEqual(registrar_pago(self.poliza.id).id, vieja.id)

    def test_sin_cuotas_pendientes_es_estado_invalido(self):
        for _ in range(12):
            registrar_pago(self.poliza.id)

        with self.assertRaises(EstadoInvalido):
            registrar_pago(self.poliza.id)

    def test_una_poliza_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            registrar_pago(999999)
