"""P5 · cotizaciones de las compañías (AC-T3-87 y AC-T3-88)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from datos import fabricas
from datos.models import Cotizacion
from negocio import cotizaciones, reglas
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado, PermisoDenegado


class BaseCotizacionesTests(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        self.diego = fabricas.crear_funcionario("Diego", puede_aprobar=False)
        self.compania = fabricas.crear_compania(nombre="La Caja")
        self.otra = fabricas.crear_compania(nombre="Sancor")
        self.interesado = fabricas.crear_interesado()
        self.poliza = fabricas.crear_poliza()

    def _cargar(self, **campos):
        argumentos = {
            "funcionario_id": self.diego.id,
            "compania_id": self.compania.id,
            "cobertura": "intermedia",
            "prima_mensual": "15000.00",
            "interesado_id": self.interesado.pk,
        }
        argumentos.update(campos)
        return cotizaciones.cargar_cotizacion(**argumentos)


class CargarCotizacionTests(BaseCotizacionesTests):
    # AC-T3-87
    def test_carga_una_cotizacion_de_un_interesado(self):
        cotizacion = self._cargar(
            prima_mensual="12500.75",
            vigencia_hasta="2026-12-31",
            notas="  Incluye granizo  ",
        )

        cotizacion.refresh_from_db()
        self.assertEqual(cotizacion.interesado_id, self.interesado.pk)
        self.assertIsNone(cotizacion.poliza_id)
        self.assertEqual(cotizacion.compania_id, self.compania.id)
        self.assertEqual(cotizacion.cobertura, "intermedia")
        self.assertEqual(cotizacion.prima_mensual, Decimal("12500.75"))
        self.assertEqual(cotizacion.vigencia_hasta, date(2026, 12, 31))
        self.assertEqual(cotizacion.notas, "Incluye granizo")
        self.assertFalse(cotizacion.elegida)
        self.assertEqual(cotizacion.creada_por_id, self.diego.id)

    # AC-T3-87
    def test_carga_una_cotizacion_de_una_poliza_y_acepta_coma_decimal(self):
        cotizacion = self._cargar(
            interesado_id=None, poliza_id=self.poliza.pk, prima_mensual="9000,5"
        )
        cotizacion.refresh_from_db()
        self.assertEqual(cotizacion.poliza_id, self.poliza.pk)
        self.assertIsNone(cotizacion.interesado_id)
        self.assertEqual(cotizacion.prima_mensual, Decimal("9000.50"))

    # AC-T3-87
    def test_exige_exactamente_uno_de_interesado_o_poliza(self):
        for destino in (
            {"interesado_id": None, "poliza_id": None},
            {"interesado_id": self.interesado.pk, "poliza_id": self.poliza.pk},
        ):
            with self.subTest(destino=destino):
                with self.assertRaises(DatosInvalidos):
                    self._cargar(**destino)
        self.assertFalse(Cotizacion.objects.exists())

        with self.assertRaises(NoEncontrado):
            self._cargar(interesado_id=0)
        with self.assertRaises(NoEncontrado):
            self._cargar(interesado_id=None, poliza_id=0)

    # AC-T3-87
    def test_exige_una_compania_activa(self):
        inactiva = fabricas.crear_compania(activa=False)
        with self.assertRaises(DatosInvalidos):
            self._cargar(compania_id=inactiva.id)
        with self.assertRaises(NoEncontrado):
            self._cargar(compania_id=0)
        self.assertFalse(Cotizacion.objects.exists())

    # AC-T3-87
    def test_la_prima_tiene_que_ser_mayor_que_cero_con_dos_decimales(self):
        for prima in (0, "0", "-100", "abc", "", None, True, "1.234", "nan", "inf", "99999999999"):
            with self.subTest(prima=prima):
                with self.assertRaises(DatosInvalidos):
                    self._cargar(prima_mensual=prima)
        self.assertFalse(Cotizacion.objects.exists())
        self.assertEqual(self._cargar(prima_mensual="0.01").prima_mensual, Decimal("0.01"))
        self.assertEqual(self._cargar(prima_mensual=1500).prima_mensual, Decimal("1500.00"))

    # AC-T3-87
    def test_cobertura_vigencia_y_notas_se_validan(self):
        for campos in (
            {"cobertura": "premium"},
            {"cobertura": ""},
            {"vigencia_hasta": "pronto"},
            {"notas": "x" * 1001},
        ):
            with self.subTest(campos=campos):
                with self.assertRaises(DatosInvalidos):
                    self._cargar(**campos)
        cotizacion = self._cargar(vigencia_hasta="", notas="   ")
        self.assertIsNone(cotizacion.vigencia_hasta)
        self.assertIsNone(cotizacion.notas)

    # AC-T3-87
    def test_cualquier_funcionario_activo_puede_cargar_y_uno_inactivo_no(self):
        self._cargar()  # Diego es operador
        inactivo = fabricas.crear_funcionario("Baja", activo=False)
        with self.assertRaises(PermisoDenegado):
            self._cargar(funcionario_id=inactivo.id)
        with self.assertRaises(PermisoDenegado):
            self._cargar(funcionario_id=0)


class ElegirYQuitarTests(BaseCotizacionesTests):
    # AC-T3-87
    def test_elegir_marca_la_elegida_y_desmarca_la_anterior_del_mismo_destino(self):
        barata = self._cargar(prima_mensual="1000")
        cara = self._cargar(prima_mensual="2000", compania_id=self.otra.id)
        de_poliza = self._cargar(interesado_id=None, poliza_id=self.poliza.pk, prima_mensual="900")
        ajena = fabricas.crear_cotizacion(elegida=True)  # de otro interesado

        cotizaciones.elegir_cotizacion(barata.pk, self.diego.id)
        elegida = cotizaciones.elegir_cotizacion(de_poliza.pk, self.diego.id)
        self.assertTrue(elegida.elegida)

        def elegidas():
            return set(Cotizacion.objects.filter(elegida=True).values_list("pk", flat=True))

        self.assertEqual(elegidas(), {barata.pk, de_poliza.pk, ajena.pk})

        cotizaciones.elegir_cotizacion(cara.pk, self.diego.id)

        # Cambió la del interesado; la de la póliza y la ajena siguen igual.
        self.assertEqual(elegidas(), {cara.pk, de_poliza.pk, ajena.pk})

    # AC-T3-87
    def test_elegir_la_que_ya_esta_elegida_no_cambia_nada(self):
        cotizacion = self._cargar()
        cotizaciones.elegir_cotizacion(cotizacion.pk, self.diego.id)
        cotizaciones.elegir_cotizacion(cotizacion.pk, self.diego.id)
        self.assertEqual(Cotizacion.objects.filter(elegida=True).count(), 1)

    # AC-T3-87
    def test_elegir_una_cotizacion_inexistente_o_sin_funcionario(self):
        cotizacion = self._cargar()
        with self.assertRaises(NoEncontrado):
            cotizaciones.elegir_cotizacion(0, self.diego.id)
        with self.assertRaises(PermisoDenegado):
            cotizaciones.elegir_cotizacion(cotizacion.pk, 0)
        cotizacion.refresh_from_db()
        self.assertFalse(cotizacion.elegida)

    # AC-T3-87
    def test_quitar_borra_una_no_elegida(self):
        sobra = self._cargar(prima_mensual="3000")
        queda = self._cargar(prima_mensual="1000")
        cotizaciones.elegir_cotizacion(queda.pk, self.diego.id)

        cotizaciones.quitar_cotizacion(sobra.pk, self.diego.id)

        self.assertEqual(list(Cotizacion.objects.values_list("pk", flat=True)), [queda.pk])

    # AC-T3-87
    def test_quitar_la_elegida_es_estado_invalido(self):
        elegida = self._cargar()
        cotizaciones.elegir_cotizacion(elegida.pk, self.diego.id)

        with self.assertRaises(EstadoInvalido):
            cotizaciones.quitar_cotizacion(elegida.pk, self.diego.id)

        self.assertTrue(Cotizacion.objects.filter(pk=elegida.pk).exists())
        with self.assertRaises(NoEncontrado):
            cotizaciones.quitar_cotizacion(0, self.diego.id)
        with self.assertRaises(PermisoDenegado):
            cotizaciones.quitar_cotizacion(elegida.pk, 0)


class AumentoSignificativoTests(SimpleTestCase):
    # AC-T3-88
    def test_es_verdadero_desde_el_quince_por_ciento(self):
        casos = (
            ("1000", "1150", True),   # justo 15 %: cuenta
            ("1000", "1149.99", False),
            ("1000", "1200", True),
            ("1000", "1000", False),
            ("1000", "900", False),   # una baja no es un aumento
            ("1000", "5000", True),
        )
        for actual, nueva, esperado in casos:
            with self.subTest(actual=actual, nueva=nueva):
                self.assertIs(
                    reglas.aumento_significativo(Decimal(actual), Decimal(nueva)), esperado
                )

    # AC-T3-88
    def test_usa_decimal_sin_redondeos_binarios(self):
        # Con floats 1.15 * 3000 = 3449.9999999999995 y el borde fallaría.
        self.assertTrue(reglas.aumento_significativo(Decimal("3000"), Decimal("3450")))
        self.assertTrue(reglas.aumento_significativo("3000", "3450"))
        self.assertTrue(reglas.aumento_significativo(3000, 3450))
        self.assertFalse(reglas.aumento_significativo(Decimal("3000"), Decimal("3449.99")))
        self.assertTrue(reglas.aumento_significativo(Decimal("0.10"), Decimal("0.115")))

    # AC-T3-88
    def test_el_umbral_es_configurable(self):
        self.assertTrue(reglas.aumento_significativo(Decimal("1000"), Decimal("1100"), umbral=Decimal("10")))
        self.assertFalse(reglas.aumento_significativo(Decimal("1000"), Decimal("1099"), umbral=Decimal("10")))
        self.assertTrue(reglas.aumento_significativo(Decimal("1000"), Decimal("1001"), umbral=Decimal("0")))
        self.assertEqual(reglas.UMBRAL_AUMENTO_SIGNIFICATIVO, Decimal("15"))

    # AC-T3-88
    def test_sin_una_prima_actual_positiva_no_hay_con_que_comparar(self):
        self.assertFalse(reglas.aumento_significativo(Decimal("0"), Decimal("1000")))
        self.assertFalse(reglas.aumento_significativo(Decimal("-5"), Decimal("1000")))


class VariacionDeRenovacionTests(BaseCotizacionesTests):
    # AC-T3-88
    def test_variacion_es_el_porcentaje_entre_la_poliza_y_la_cotizacion_elegida(self):
        poliza = fabricas.crear_poliza(prima_mensual="10000.00")
        mas_cara = cotizaciones.cargar_cotizacion(
            self.diego.id, self.compania.id, "total", "11850", poliza_id=poliza.pk
        )
        mas_barata = cotizaciones.cargar_cotizacion(
            self.diego.id, self.otra.id, "total", "9000", poliza_id=poliza.pk
        )

        cotizaciones.elegir_cotizacion(mas_cara.pk, self.diego.id)
        self.assertEqual(cotizaciones.variacion_renovacion(poliza.pk), Decimal("18.50"))

        cotizaciones.elegir_cotizacion(mas_barata.pk, self.diego.id)
        self.assertEqual(cotizaciones.variacion_renovacion(poliza.pk), Decimal("-10.00"))

    # AC-T3-88
    def test_sin_cotizacion_elegida_es_none(self):
        poliza = fabricas.crear_poliza(prima_mensual="10000.00")
        self.assertIsNone(cotizaciones.variacion_renovacion(poliza.pk))

        cotizaciones.cargar_cotizacion(
            self.diego.id, self.compania.id, "total", "12000", poliza_id=poliza.pk
        )
        self.assertIsNone(cotizaciones.variacion_renovacion(poliza.pk))

        with self.assertRaises(NoEncontrado):
            cotizaciones.variacion_renovacion(0)

    # AC-T3-88
    def test_la_variacion_y_la_regla_se_complementan(self):
        poliza = fabricas.crear_poliza(prima_mensual="10000.00")
        elegida = cotizaciones.cargar_cotizacion(
            self.diego.id, self.compania.id, "total", "11500", poliza_id=poliza.pk
        )
        cotizaciones.elegir_cotizacion(elegida.pk, self.diego.id)

        variacion = cotizaciones.variacion_renovacion(poliza.pk)

        self.assertEqual(variacion, Decimal("15.00"))
        self.assertTrue(reglas.aumento_significativo(poliza.prima_mensual, elegida.prima_mensual))
