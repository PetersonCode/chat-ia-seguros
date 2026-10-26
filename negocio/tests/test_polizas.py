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
from datos.models import Cuota, EstadoCuota, EstadoPoliza, Pago, Poliza
from datos.selectors import polizas_vigentes, resumen_polizas
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)
from negocio.polizas import (
    alta_poliza,
    meses_de_cobertura,
    plan_de_cuotas,
    proximo_numero_poliza,
    registrar_pago,
)


class MesesDeCoberturaTests(TestCase):
    def test_casos_limite_de_ciclos_mensuales(self):
        casos = (
            (date(2026, 1, 1), date(2026, 12, 31), 12),
            (date(2026, 1, 1), date(2027, 1, 1), 12),
            (date(2026, 1, 31), date(2026, 2, 28), 1),
            (date(2026, 1, 31), date(2026, 5, 1), 4),
            (date(2024, 2, 29), date(2025, 2, 28), 12),
        )
        for inicio, vencimiento, esperado in casos:
            with self.subTest(inicio=inicio, vencimiento=vencimiento):
                self.assertEqual(
                    meses_de_cobertura(inicio, vencimiento),
                    esperado,
                )

    def test_un_ano_son_doce_cuotas_y_no_trece(self):
        self.assertEqual(meses_de_cobertura(date(2026, 1, 10), date(2027, 1, 10)), 12)

    def test_medio_ano_son_seis(self):
        self.assertEqual(meses_de_cobertura(date(2026, 1, 10), date(2026, 7, 10)), 6)

    def test_cobra_completo_el_ciclo_final_parcial(self):
        self.assertEqual(meses_de_cobertura(date(2026, 1, 20), date(2026, 3, 10)), 2)

    def test_del_primero_de_enero_al_ultimo_de_diciembre_genera_doce(self):
        poliza = fabricas.crear_poliza(
            fecha_inicio=date(2026, 1, 1),
            fecha_vencimiento=date(2026, 12, 31),
        )

        self.assertEqual(len(plan_de_cuotas(poliza)), 12)

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

    def test_genera_una_cuota_por_ciclo_y_vence_en_su_inicio(self):
        poliza = self._alta()

        cuotas = list(Cuota.objects.filter(poliza=poliza).order_by("periodo"))
        self.assertEqual(len(cuotas), 12)
        self.assertEqual(cuotas[0].periodo, date(2026, 1, 1))
        self.assertEqual(cuotas[0].vencimiento, date(2026, 1, 10))
        self.assertEqual(cuotas[-1].periodo, date(2026, 12, 1))
        self.assertEqual(cuotas[-1].vencimiento, date(2026, 12, 10))
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

    def test_los_aniversarios_de_31_vuelven_al_31_despues_de_febrero(self):
        poliza = self._alta(
            fecha_inicio=date(2026, 1, 31),
            fecha_vencimiento=date(2026, 5, 1),
        )
        cuotas = list(Cuota.objects.filter(poliza=poliza).order_by("periodo"))

        self.assertEqual(
            [cuota.vencimiento for cuota in cuotas],
            [
                date(2026, 1, 31),
                date(2026, 2, 28),
                date(2026, 3, 31),
                date(2026, 4, 30),
            ],
        )
        self.assertEqual(
            [cuota.periodo for cuota in cuotas],
            [
                date(2026, 1, 1),
                date(2026, 2, 1),
                date(2026, 3, 1),
                date(2026, 4, 1),
            ],
        )

    def test_el_saldo_que_ve_el_bot_sale_de_las_cuotas_nuevas(self):
        poliza = self._alta()

        fila = next(
            f for f in resumen_polizas(self.cliente.id)
            if f.numero_poliza == poliza.numero_poliza
        )
        self.assertEqual(fila.saldo_pendiente, Decimal("216000.00"))
        self.assertEqual(fila.proximo_vencimiento_pago, date(2026, 1, 10))

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

    def test_una_poliza_con_inicio_futuro_no_es_cobertura_actual(self):
        hoy = timezone.localdate()
        poliza = self._alta(
            fecha_inicio=hoy + timedelta(days=1),
            fecha_vencimiento=hoy + timedelta(days=365),
        )

        self.assertEqual(poliza.estado, EstadoPoliza.VIGENTE)
        self.assertNotIn(poliza, polizas_vigentes(self.cliente.id))

    def test_una_poliza_que_vence_hoy_sigue_vigente_hasta_esa_fecha(self):
        hoy = timezone.localdate()

        poliza = self._alta(fecha_inicio=hoy - timedelta(days=30), fecha_vencimiento=hoy)

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
    """Registrar cobros completos, trazables e idempotentes."""

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
        self.funcionario = fabricas.crear_funcionario(
            "Graciela", puede_aprobar=True
        )

    def _registrar(self, referencia="COMP-001", importe="18000"):
        return registrar_pago(
            self.poliza.id,
            referencia=referencia,
            importe=importe,
            funcionario_id=self.funcionario.id,
        )

    def test_cobra_la_cuota_mas_vieja_con_fecha_e_importe(self):
        pago = self._registrar()
        cuota = pago.cuota

        self.assertEqual(cuota.periodo, date(2026, 1, 1))
        self.assertEqual(cuota.estado, EstadoCuota.PAGADA)
        self.assertEqual(cuota.fecha_pago, timezone.localdate())
        self.assertEqual(cuota.importe_pagado, Decimal("18000.00"))
        self.assertEqual(pago.referencia, "COMP-001")
        self.assertEqual(pago.importe, Decimal("18000.00"))
        self.assertEqual(pago.fecha_pago, timezone.localdate())
        self.assertEqual(pago.responsable_id, self.funcionario.id)

    def test_el_saldo_que_ve_el_bot_baja_un_mes_por_pago(self):
        self._registrar()

        fila = next(
            f for f in resumen_polizas(self.cliente.id)
            if f.numero_poliza == self.poliza.numero_poliza
        )
        self.assertEqual(fila.saldo_pendiente, Decimal("198000.00"))
        self.assertEqual(fila.proximo_vencimiento_pago, date(2026, 2, 10))

    def test_dos_pagos_seguidos_cobran_dos_meses_distintos(self):
        primera = self._registrar("COMP-001")
        segunda = self._registrar("COMP-002")

        self.assertEqual(primera.cuota.periodo, date(2026, 1, 1))
        self.assertEqual(segunda.cuota.periodo, date(2026, 2, 1))
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

        self.assertEqual(self._registrar().cuota_id, vieja.id)

    def test_sin_cuotas_pendientes_es_estado_invalido(self):
        for indice in range(12):
            self._registrar(f"COMP-{indice:03}", "18000")

        with self.assertRaises(EstadoInvalido):
            self._registrar("COMP-ULTIMO")

    def test_una_poliza_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            registrar_pago(
                999999,
                referencia="COMP-001",
                importe="18000",
                funcionario_id=self.funcionario.id,
            )

    def test_reintentar_el_mismo_comprobante_devuelve_el_movimiento_y_no_cobra_otra_cuota(self):
        primero = self._registrar()

        reintentado = self._registrar()

        self.assertEqual(reintentado.id, primero.id)
        self.assertEqual(reintentado.cuota_id, primero.cuota_id)
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(
            Cuota.objects.filter(
                poliza=self.poliza, estado=EstadoCuota.PAGADA
            ).count(),
            1,
        )

    def test_reutilizar_referencia_con_importe_o_poliza_distintos_se_rechaza(self):
        self._registrar()
        with self.assertRaises(EstadoInvalido):
            self._registrar(importe="18001")

        otra_poliza = alta_poliza(
            self.cliente.id,
            tipo_seguro="hogar",
            cobertura="basica",
            fecha_inicio=date(2026, 1, 10),
            fecha_vencimiento=date(2026, 2, 10),
            prima_mensual="18000",
        )
        with self.assertRaises(EstadoInvalido):
            registrar_pago(
                otra_poliza.id,
                referencia="COMP-001",
                importe="18000",
                funcionario_id=self.funcionario.id,
            )

    def test_un_importe_parcial_o_invalido_no_cambia_la_cuota(self):
        for importe in ("9000", "0", "-1", "no es un importe"):
            with self.subTest(importe=importe):
                with self.assertRaises(DatosInvalidos):
                    self._registrar("COMP-PARCIAL", importe)
                self.assertFalse(Pago.objects.exists())
                self.assertFalse(
                    Cuota.objects.filter(
                        poliza=self.poliza, estado=EstadoCuota.PAGADA
                    ).exists()
                )

    def test_funcionario_sin_permiso_no_puede_registrar_pago(self):
        operador = fabricas.crear_funcionario("Diego", puede_aprobar=False)
        with self.assertRaises(PermisoDenegado):
            registrar_pago(
                self.poliza.id,
                referencia="COMP-OPERADOR",
                importe="18000",
                funcionario_id=operador.id,
            )
        self.assertFalse(Pago.objects.exists())

    def test_funcionario_inactivo_no_puede_registrar_pago(self):
        self.funcionario.activo = False
        self.funcionario.save(update_fields=["activo"])
        with self.assertRaises(PermisoDenegado):
            self._registrar()
        self.assertFalse(Pago.objects.exists())
