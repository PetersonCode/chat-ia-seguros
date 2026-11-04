"""P1 · Vehículos y compañías: lógica (AC-T3-57 a AC-T3-61).

Lo que se cuida: que solo un aprobador escriba (la comisión es del dueño), que
la patente sea única y esté normalizada, y que una póliza nunca quede apuntando
al vehículo de otro cliente ni a una compañía desactivada.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import Compania, EstadoPoliza, Vehiculo
from negocio.bot import orquestador, plantillas
from negocio.companias import alta_compania, desactivar_compania, modificar_compania
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)
from negocio.polizas import alta_poliza
from negocio.vehiculos import alta_vehiculo, dar_de_baja_vehiculo, modificar_vehiculo


class _Base(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        self.aprobador = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
        self.operador = fabricas.crear_funcionario("Diego", puede_aprobar=False)
        self.cliente = fabricas.crear_cliente(nombre="Laura", apellido="Pérez")


class AltaVehiculoTests(_Base):
    def _alta(self, **campos):
        datos = {
            "cliente_id": self.cliente.id,
            "patente": "ab 123 cd",
            "marca": "Toyota",
            "modelo": "Corolla",
            "anio": 2020,
            "funcionario_id": self.aprobador.id,
        }
        datos.update(campos)
        return alta_vehiculo(**datos)

    # AC-T3-57
    def test_crea_el_vehiculo_con_la_patente_normalizada(self):
        vehiculo = self._alta(chasis=" 8AB123 ", valor_asegurado="15000000,50")

        vehiculo.refresh_from_db()
        self.assertEqual(vehiculo.patente, "AB123CD")
        self.assertEqual(vehiculo.cliente, self.cliente)
        self.assertEqual(vehiculo.uso, "particular")
        self.assertEqual(vehiculo.chasis, "8AB123")
        self.assertEqual(vehiculo.valor_asegurado, Decimal("15000000.50"))
        self.assertTrue(vehiculo.activo)

    # AC-T3-57
    def test_datos_invalidos(self):
        self._alta()
        anio_siguiente = timezone.localdate().year + 1
        casos = {
            "patente repetida": {"patente": "AB-123-CD"},
            "patente invalida": {"patente": "AB12"},
            "patente vacia": {"patente": ""},
            "anio muy viejo": {"anio": 1949},
            "anio del futuro lejano": {"anio": anio_siguiente + 1},
            "anio no numerico": {"anio": "dos mil"},
            "marca vacia": {"patente": "ZZ111ZZ", "marca": "   "},
            "modelo vacio": {"patente": "ZZ111ZZ", "modelo": ""},
            "valor cero": {"patente": "ZZ111ZZ", "valor_asegurado": 0},
            "valor negativo": {"patente": "ZZ111ZZ", "valor_asegurado": "-5"},
            "valor no numerico": {"patente": "ZZ111ZZ", "valor_asegurado": "mucho"},
            "uso desconocido": {"patente": "ZZ111ZZ", "uso": "deportivo"},
        }
        for nombre, campos in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(DatosInvalidos):
                    self._alta(**campos)
        self.assertEqual(Vehiculo.objects.count(), 1)

    # AC-T3-57
    def test_el_anio_siguiente_es_el_ultimo_valido(self):
        vehiculo = self._alta(patente="ZZ111ZZ", anio=timezone.localdate().year + 1)
        self.assertEqual(vehiculo.anio, timezone.localdate().year + 1)

    # AC-T3-57
    def test_un_cliente_inactivo_no_recibe_vehiculos(self):
        self.cliente.activo = False
        self.cliente.save(update_fields=["activo"])
        with self.assertRaises(DatosInvalidos):
            self._alta()

    # AC-T3-57
    def test_un_operador_no_puede_y_un_cliente_inexistente_no_se_encuentra(self):
        with self.assertRaises(PermisoDenegado):
            self._alta(funcionario_id=self.operador.id)
        with self.assertRaises(NoEncontrado):
            self._alta(cliente_id=999_999)
        with self.assertRaises(NoEncontrado):
            self._alta(funcionario_id=999_999)
        self.assertEqual(Vehiculo.objects.count(), 0)


class ModificarYBajaVehiculoTests(_Base):
    def setUp(self):
        super().setUp()
        self.vehiculo = fabricas.crear_vehiculo(
            self.cliente, patente="AB123CD", marca="Ford", modelo="Fiesta", anio=2018
        )

    # AC-T3-58
    def test_modificar_actualiza_solo_lo_recibido(self):
        modificar_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id, modelo="Focus")

        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.modelo, "Focus")
        self.assertEqual(self.vehiculo.marca, "Ford")
        self.assertEqual(self.vehiculo.patente, "AB123CD")
        self.assertEqual(self.vehiculo.anio, 2018)

    # AC-T3-58
    def test_la_patente_propia_no_cuenta_como_repetida_pero_la_ajena_si(self):
        modificar_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id, patente="ab 123 cd")
        fabricas.crear_vehiculo(patente="XY987ZW")
        with self.assertRaises(DatosInvalidos):
            modificar_vehiculo(
                self.vehiculo.id, funcionario_id=self.aprobador.id, patente="xy-987-zw"
            )
        modificar_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id, patente="ABC123")
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.patente, "ABC123")

    # AC-T3-58
    def test_chasis_y_valor_se_pueden_borrar_y_los_demas_se_validan(self):
        modificar_vehiculo(
            self.vehiculo.id, funcionario_id=self.aprobador.id, chasis="X1", valor_asegurado="100"
        )
        modificar_vehiculo(
            self.vehiculo.id, funcionario_id=self.aprobador.id, chasis=None, valor_asegurado=None
        )
        self.vehiculo.refresh_from_db()
        self.assertIsNone(self.vehiculo.chasis)
        self.assertIsNone(self.vehiculo.valor_asegurado)

        for campos in ({"anio": 1900}, {"marca": " "}, {"uso": "x"}, {"valor_asegurado": 0}):
            with self.subTest(campos=campos):
                with self.assertRaises(DatosInvalidos):
                    modificar_vehiculo(
                        self.vehiculo.id, funcionario_id=self.aprobador.id, **campos
                    )

    # AC-T3-58
    def test_la_baja_es_logica(self):
        dar_de_baja_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id)

        self.vehiculo.refresh_from_db()
        self.assertFalse(self.vehiculo.activo)
        self.assertTrue(Vehiculo.objects.filter(pk=self.vehiculo.id).exists())
        with self.assertRaises(EstadoInvalido):
            dar_de_baja_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id)

    # AC-T3-58
    def test_no_se_da_de_baja_con_una_poliza_vigente(self):
        fabricas.crear_poliza(self.cliente, vehiculo=self.vehiculo)

        with self.assertRaises(EstadoInvalido):
            dar_de_baja_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id)
        self.vehiculo.refresh_from_db()
        self.assertTrue(self.vehiculo.activo)

    # AC-T3-58
    def test_una_poliza_vencida_o_dada_de_baja_no_impide_la_baja(self):
        fabricas.crear_poliza(
            self.cliente,
            vehiculo=self.vehiculo,
            estado=EstadoPoliza.DADA_DE_BAJA,
        )
        hoy = timezone.localdate()
        fabricas.crear_poliza(
            self.cliente,
            vehiculo=self.vehiculo,
            estado=EstadoPoliza.VENCIDA,
            fecha_inicio=hoy - timedelta(days=400),
            fecha_vencimiento=hoy - timedelta(days=35),
        )
        dar_de_baja_vehiculo(self.vehiculo.id, funcionario_id=self.aprobador.id)

    # AC-T3-58
    def test_ambos_exigen_aprobador_y_vehiculo_existente(self):
        with self.assertRaises(PermisoDenegado):
            modificar_vehiculo(self.vehiculo.id, funcionario_id=self.operador.id, marca="X")
        with self.assertRaises(PermisoDenegado):
            dar_de_baja_vehiculo(self.vehiculo.id, funcionario_id=self.operador.id)
        with self.assertRaises(NoEncontrado):
            modificar_vehiculo(999_999, funcionario_id=self.aprobador.id, marca="X")
        with self.assertRaises(NoEncontrado):
            dar_de_baja_vehiculo(999_999, funcionario_id=self.aprobador.id)


class CompaniasTests(_Base):
    # AC-T3-59
    def test_alta_crea_la_compania_activa(self):
        compania = alta_compania("  La   Caja ", "12,5", funcionario_id=self.aprobador.id)

        compania.refresh_from_db()
        self.assertEqual(compania.nombre, "La Caja")
        self.assertEqual(compania.comision_pct, Decimal("12.50"))
        self.assertTrue(compania.activa)

    # AC-T3-59
    def test_el_nombre_es_unico_sin_distinguir_mayusculas_ni_espacios(self):
        alta_compania("La Caja", 10, funcionario_id=self.aprobador.id)
        otra = alta_compania("Sancor", 8, funcionario_id=self.aprobador.id)
        for repetido in ("la caja", "LA  CAJA", "lacaja", " La Caja "):
            with self.subTest(nombre=repetido):
                with self.assertRaises(DatosInvalidos):
                    alta_compania(repetido, 5, funcionario_id=self.aprobador.id)
        with self.assertRaises(DatosInvalidos):
            modificar_compania(otra.id, funcionario_id=self.aprobador.id, nombre="LA CAJA")
        # Su propio nombre, escrito distinto, sí se puede.
        modificar_compania(otra.id, funcionario_id=self.aprobador.id, nombre="SANCOR")
        otra.refresh_from_db()
        self.assertEqual(otra.nombre, "SANCOR")

    # AC-T3-59
    def test_la_comision_va_de_0_a_100(self):
        for indice, valida in enumerate((0, "0", 100, "100.00", "33.33")):
            with self.subTest(comision=valida):
                alta_compania(f"Válida {indice}", valida, funcionario_id=self.aprobador.id)
        for invalida in (-1, "100.01", 101, "abc", None, "", "1.234", True):
            with self.subTest(comision=invalida):
                with self.assertRaises(DatosInvalidos):
                    alta_compania(f"X {invalida}", invalida, funcionario_id=self.aprobador.id)
        with self.assertRaises(DatosInvalidos):
            alta_compania("   ", 5, funcionario_id=self.aprobador.id)

    # AC-T3-59
    def test_modificar_actualiza_solo_lo_recibido_y_permite_reactivar(self):
        compania = alta_compania("Zurich", 10, funcionario_id=self.aprobador.id)
        modificar_compania(compania.id, funcionario_id=self.aprobador.id, comision_pct=15)
        compania.refresh_from_db()
        self.assertEqual((compania.nombre, compania.comision_pct), ("Zurich", Decimal("15.00")))

        desactivar_compania(compania.id, funcionario_id=self.aprobador.id)
        compania.refresh_from_db()
        self.assertFalse(compania.activa)
        modificar_compania(compania.id, funcionario_id=self.aprobador.id, activa=True)
        compania.refresh_from_db()
        self.assertTrue(compania.activa)

    # AC-T3-59
    def test_desactivar_no_toca_las_polizas_que_ya_la_usan(self):
        compania = alta_compania("Zurich", 10, funcionario_id=self.aprobador.id)
        poliza = fabricas.crear_poliza(self.cliente, compania=compania, comision_pct="10.00")

        desactivar_compania(compania.id, funcionario_id=self.aprobador.id)
        modificar_compania(compania.id, funcionario_id=self.aprobador.id, comision_pct=20)

        poliza.refresh_from_db()
        self.assertEqual(poliza.compania_id, compania.id)
        self.assertEqual(poliza.comision_pct, Decimal("10.00"))
        self.assertEqual(poliza.estado, EstadoPoliza.VIGENTE)

    # AC-T3-59
    def test_las_tres_exigen_aprobador(self):
        compania = fabricas.crear_compania()
        with self.assertRaises(PermisoDenegado):
            alta_compania("Nueva", 5, funcionario_id=self.operador.id)
        with self.assertRaises(PermisoDenegado):
            modificar_compania(compania.id, funcionario_id=self.operador.id, comision_pct=1)
        with self.assertRaises(PermisoDenegado):
            desactivar_compania(compania.id, funcionario_id=self.operador.id)
        with self.assertRaises(NoEncontrado):
            modificar_compania(999_999, funcionario_id=self.aprobador.id, comision_pct=1)
        compania.refresh_from_db()
        self.assertTrue(compania.activa)
        self.assertEqual(Compania.objects.count(), 1)


class AltaPolizaConVehiculoTests(_Base):
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

    # AC-T3-60
    def test_vehiculo_y_compania_quedan_en_la_poliza_y_completan_el_bien(self):
        vehiculo = fabricas.crear_vehiculo(
            self.cliente, patente="AB123CD", marca="Toyota", modelo="Corolla", anio=2020
        )
        compania = fabricas.crear_compania(comision_pct="12.50")

        poliza = self._alta(vehiculo_id=vehiculo.id, compania_id=compania.id)

        poliza.refresh_from_db()
        self.assertEqual(poliza.vehiculo, vehiculo)
        self.assertEqual(poliza.compania, compania)
        self.assertEqual(poliza.comision_pct, Decimal("12.50"))
        self.assertEqual(poliza.bien_asegurado, "Toyota Corolla 2020 (AB123CD)")

    # AC-T3-60
    def test_la_comision_se_congela_al_emitir_y_se_puede_pasar_otra(self):
        compania = fabricas.crear_compania(comision_pct="10.00")
        primera = self._alta(compania_id=compania.id)
        compania.comision_pct = Decimal("20.00")
        compania.save(update_fields=["comision_pct"])
        segunda = self._alta(compania_id=compania.id)
        tercera = self._alta(compania_id=compania.id, comision_pct="7,5")

        primera.refresh_from_db()
        segunda.refresh_from_db()
        tercera.refresh_from_db()
        self.assertEqual(primera.comision_pct, Decimal("10.00"))
        self.assertEqual(segunda.comision_pct, Decimal("20.00"))
        self.assertEqual(tercera.comision_pct, Decimal("7.50"))

    # AC-T3-60
    def test_un_bien_asegurado_escrito_se_respeta(self):
        vehiculo = fabricas.crear_vehiculo(self.cliente)
        poliza = self._alta(vehiculo_id=vehiculo.id, bien_asegurado="Camioneta de reparto")
        self.assertEqual(poliza.bien_asegurado, "Camioneta de reparto")

    # AC-T3-60
    def test_el_vehiculo_tiene_que_ser_del_cliente(self):
        ajeno = fabricas.crear_vehiculo()
        with self.assertRaises(DatosInvalidos):
            self._alta(vehiculo_id=ajeno.id)
        with self.assertRaises(DatosInvalidos):
            self._alta(vehiculo_id=999_999)
        propio_de_baja = fabricas.crear_vehiculo(self.cliente, activo=False)
        with self.assertRaises(DatosInvalidos):
            self._alta(vehiculo_id=propio_de_baja.id)

    # AC-T3-60
    def test_la_compania_tiene_que_estar_activa(self):
        inactiva = fabricas.crear_compania(activa=False)
        with self.assertRaises(DatosInvalidos):
            self._alta(compania_id=inactiva.id)
        with self.assertRaises(DatosInvalidos):
            self._alta(compania_id=999_999)
        with self.assertRaises(DatosInvalidos):
            self._alta(compania_id=fabricas.crear_compania().id, comision_pct=101)

    # AC-T3-60
    def test_una_alta_rechazada_no_deja_poliza_a_medias(self):
        from datos.models import Poliza

        with self.assertRaises(DatosInvalidos):
            self._alta(vehiculo_id=fabricas.crear_vehiculo().id)
        self.assertEqual(Poliza.objects.count(), 0)

    # AC-T3-60
    def test_sin_vehiculo_ni_compania_se_comporta_como_antes(self):
        poliza = self._alta(bien_asegurado="  Ford Ka  ")

        poliza.refresh_from_db()
        self.assertIsNone(poliza.vehiculo)
        self.assertIsNone(poliza.compania)
        self.assertIsNone(poliza.comision_pct)
        self.assertEqual(poliza.bien_asegurado, "Ford Ka")
        self.assertIsNone(self._alta().bien_asegurado)


class PlantillaVencimientoConPatenteTests(_Base):
    # AC-T3-61
    def test_la_linea_lleva_la_patente_solo_si_la_poliza_tiene_vehiculo(self):
        vehiculo = fabricas.crear_vehiculo(self.cliente, patente="AB123CD")
        con = fabricas.crear_poliza(self.cliente, vehiculo=vehiculo)
        sin = fabricas.crear_poliza(self.cliente)

        respuesta = orquestador._respuesta_vencimiento(self.cliente.id)

        lineas = {
            linea.split(" ")[1]: linea
            for linea in respuesta.texto.splitlines()
            if linea.startswith("•")
        }
        fecha_con = con.fecha_vencimiento.strftime("%d/%m/%Y")
        fecha_sin = sin.fecha_vencimiento.strftime("%d/%m/%Y")
        self.assertTrue(lineas[con.numero_poliza].endswith(f"vence el {fecha_con}"))
        self.assertEqual(lineas[con.numero_poliza].count("AB123CD"), 1)
        self.assertTrue(lineas[sin.numero_poliza].endswith(f"vence el {fecha_sin}"))
        self.assertNotIn("·", lineas[sin.numero_poliza])
        # La patente sale de la base: va en lo verificado para que el guardrail no la objete.
        self.assertIn("AB123CD", respuesta.datos_verificados)

    # AC-T3-61
    def test_la_plantilla_sin_patente_queda_igual_que_antes(self):
        linea = plantillas.LINEA_VENCIMIENTO.format(
            numero_poliza="POL-00001",
            tipo_seguro="Automotor",
            bien="",
            fecha="15/04/2024",
            marca="",
            patente="",
        )
        self.assertEqual(linea, "• POL-00001 (Automotor): vence el 15/04/2024")
