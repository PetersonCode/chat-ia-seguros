from pathlib import Path
from unittest import TestCase as TestCaseSimple

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import DO_NOTHING
from django.test import SimpleTestCase, TestCase

from datos import fabricas, models, selectors
from datos.limpieza import normalizar_patente

SQL_13 = Path(settings.BASE_DIR) / "SDD" / "sql" / "13_vehiculos_companias.sql"


class ModeloVehiculosYCompaniasTests(SimpleTestCase):
    # AC-T4-29
    def test_modelos_no_administrados_y_relaciones(self):
        for modelo, tabla in (
            (models.Compania, "companias"),
            (models.Vehiculo, "vehiculos"),
        ):
            with self.subTest(modelo=modelo.__name__):
                self.assertFalse(modelo._meta.managed)
                self.assertEqual(modelo._meta.db_table, tabla)

        relaciones = (
            (models.Vehiculo, "cliente", models.Cliente, "vehiculos", False),
            (models.Poliza, "vehiculo", models.Vehiculo, "polizas", True),
            (models.Poliza, "compania", models.Compania, "polizas", True),
        )
        for modelo, campo, destino, related_name, nulo in relaciones:
            with self.subTest(modelo=modelo.__name__, campo=campo):
                fk = modelo._meta.get_field(campo)
                self.assertIs(fk.remote_field.model, destino)
                self.assertEqual(fk.remote_field.related_name, related_name)
                self.assertIs(fk.remote_field.on_delete, DO_NOTHING)
                self.assertEqual(fk.null, nulo)

        self.assertTrue(models.Poliza._meta.get_field("comision_pct").null)

    # AC-T4-29
    def test_uso_vehiculo_tiene_los_valores_del_check(self):
        self.assertEqual(
            models.UsoVehiculo.values,
            ["particular", "comercial", "remis_taxi", "carga"],
        )


class SqlVehiculosYCompaniasTests(TestCase):
    # AC-T4-29
    def test_el_sql_13_puede_aplicarse_dos_veces_seguidas(self):
        # Ya lo aplicó el test runner una vez. Sin el BEGIN/COMMIT propios (que
        # cerrarían la transacción del test) se aplica dos veces más: todo es
        # IF NOT EXISTS y la transacción del test lo deshace al terminar.
        sql = SQL_13.read_text(encoding="utf-8")
        cuerpo = "\n".join(
            linea for linea in sql.splitlines() if linea.strip() not in ("BEGIN;", "COMMIT;")
        )
        with connection.cursor() as cursor:
            cursor.execute(cuerpo)
            cursor.execute(cuerpo)

    # AC-T4-29
    def test_el_sql_13_esta_en_la_lista_del_test_runner(self):
        fuente = (Path(settings.BASE_DIR) / "config" / "test_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"13_vehiculos_companias.sql"', fuente)

    # AC-T4-29
    def test_la_base_hace_cumplir_patente_anio_uso_y_nombre_unico(self):
        cliente = fabricas.crear_cliente()
        invalidos = (
            {"patente": "ab123cd"},  # minúsculas: la normalización es del código
            {"patente": "AB 123 CD"},
            {"patente": "AB12"},
            {"anio": 1949},
            {"anio": 3000},
            {"uso": "deportivo"},
            {"marca": "  "},
            {"modelo": ""},
            {"valor_asegurado": 0},
        )
        for campos in invalidos:
            with self.subTest(campos=campos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    fabricas.crear_vehiculo(cliente, **campos)

        for patente in ("ABC123", "AB123CD", "123ABC", "A123BCD"):
            with self.subTest(patente=patente):
                fabricas.crear_vehiculo(cliente, patente=patente)

        with self.assertRaises(IntegrityError), transaction.atomic():
            fabricas.crear_vehiculo(cliente, patente="ABC123")

        fabricas.crear_compania(nombre="La Caja")
        for repetido in ("la caja", "LA  CAJA", " lacaja "):
            with self.subTest(nombre=repetido):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    fabricas.crear_compania(nombre=repetido)
        for comision in (-1, 100.01):
            with self.subTest(comision=comision):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    fabricas.crear_compania(comision_pct=comision)

    # AC-T4-29
    def test_poliza_guarda_vehiculo_compania_y_comision_sin_perder_bien_asegurado(self):
        cliente = fabricas.crear_cliente()
        vehiculo = fabricas.crear_vehiculo(cliente)
        compania = fabricas.crear_compania()
        poliza = fabricas.crear_poliza(
            cliente,
            vehiculo=vehiculo,
            compania=compania,
            comision_pct="12.50",
            bien_asegurado="Texto libre viejo",
        )
        poliza.refresh_from_db()
        self.assertEqual(poliza.vehiculo, vehiculo)
        self.assertEqual(poliza.compania, compania)
        self.assertEqual(str(poliza.comision_pct), "12.50")
        self.assertEqual(poliza.bien_asegurado, "Texto libre viejo")
        self.assertEqual(list(vehiculo.polizas.all()), [poliza])
        self.assertEqual(list(compania.polizas.all()), [poliza])
        self.assertEqual(list(cliente.vehiculos.all()), [vehiculo])


class NormalizarPatenteTests(TestCaseSimple):
    # AC-T4-30
    def test_normaliza_mayusculas_espacios_y_guiones(self):
        casos = (
            ("ab 123 cd", "AB123CD"),
            ("AB-123-CD", "AB123CD"),
            (" abc123 ", "ABC123"),
            ("123 abc", "123ABC"),
            ("A123BCD", "A123BCD"),
        )
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_patente(entrada), esperado)

    # AC-T4-30
    def test_rechaza_lo_que_no_es_una_patente(self):
        for entrada in ("AB12", "ABCD123", "", "   ", "12345", "AB123C", "ÁB123CD"):
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValueError):
                    normalizar_patente(entrada)


class ConsultasVehiculosYCompaniasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fabricas.crear_catalogos()

    # AC-T4-31
    def test_vehiculo_por_patente_normaliza_y_devuelve_none(self):
        vehiculo = fabricas.crear_vehiculo(patente="AB123CD")
        self.assertEqual(selectors.vehiculo_por_patente("ab 123 cd"), vehiculo)
        self.assertEqual(selectors.vehiculo_por_patente("AB123CD"), vehiculo)
        self.assertIsNone(selectors.vehiculo_por_patente("ZZ999ZZ"))
        self.assertIsNone(selectors.vehiculo_por_patente("inválida"))
        self.assertIsNone(selectors.vehiculo_por_patente(""))

    # AC-T4-31
    def test_vehiculos_de_filtra_activos_y_ordena_por_patente(self):
        cliente = fabricas.crear_cliente()
        b = fabricas.crear_vehiculo(cliente, patente="BBB222")
        a = fabricas.crear_vehiculo(cliente, patente="AAA111")
        baja = fabricas.crear_vehiculo(cliente, patente="CCC333", activo=False)
        fabricas.crear_vehiculo()  # de otro cliente

        self.assertEqual(list(selectors.vehiculos_de(cliente.pk)), [a, b])
        self.assertEqual(
            list(selectors.vehiculos_de(cliente.pk, solo_activos=False)), [a, b, baja]
        )

    # AC-T4-31
    def test_listar_companias_por_nombre_y_solo_activas(self):
        zeta = fabricas.crear_compania(nombre="Zurich")
        alfa = fabricas.crear_compania(nombre="allianz")
        inactiva = fabricas.crear_compania(nombre="Mapfre", activa=False)

        self.assertEqual(list(selectors.listar_companias()), [alfa, zeta])
        self.assertEqual(
            list(selectors.listar_companias(solo_activas=False)),
            [alfa, inactiva, zeta],
        )

    # AC-T4-31
    def test_buscar_clientes_encuentra_por_patente_antes_que_por_nombre(self):
        dueno = fabricas.crear_cliente(nombre="Laura", apellido="Pérez")
        fabricas.crear_vehiculo(dueno, patente="AB123CD")
        # Un cliente cuyo apellido contiene el texto de la patente no le gana al dueño.
        fabricas.crear_cliente(nombre="Ab", apellido="Ab123cd")

        for q in ("ab123cd", "AB 123 CD", "ab-123-cd"):
            with self.subTest(q=q):
                self.assertEqual(list(selectors.buscar_clientes(q)), [dueno])

        # Una patente que nadie tiene cae a nombre o apellido.
        homonimo = fabricas.crear_cliente(nombre="Zz", apellido="Zz999zz")
        self.assertEqual(list(selectors.buscar_clientes("zz999zz")), [homonimo])
        # Un vehículo dado de baja también ubica al dueño.
        fabricas.crear_vehiculo(homonimo, patente="XY987ZW", activo=False)
        self.assertEqual(list(selectors.buscar_clientes("xy987zw")), [homonimo])
        # Lo anterior sigue funcionando.
        self.assertEqual(list(selectors.buscar_clientes(dueno.dni)), [dueno])
        self.assertIn(dueno, selectors.buscar_clientes("pérez"))

    # AC-T4-31
    def test_detalles_traen_vehiculo_y_compania_en_hasta_cinco_consultas(self):
        cliente = fabricas.crear_cliente()
        vehiculo = fabricas.crear_vehiculo(cliente)
        fabricas.crear_vehiculo(cliente, activo=False)
        compania = fabricas.crear_compania()
        poliza = fabricas.crear_poliza(
            cliente, vehiculo=vehiculo, compania=compania, comision_pct="10.00"
        )
        fabricas.crear_cuota(poliza)

        with self.assertNumQueries(5):
            detalle = selectors.detalle_cliente(cliente.pk)
            polizas = list(detalle.polizas.all())
            vehiculos = list(detalle.vehiculos.all())
            list(detalle.contactos.all())
            for p in polizas:
                list(p.siniestros.all())
            self.assertEqual(polizas[0].vehiculo, vehiculo)
            self.assertEqual(polizas[0].compania, compania)
        self.assertEqual(len(vehiculos), 2)

        # La póliza (con cliente, vehículo y compañía en el mismo JOIN), cuotas,
        # conductores y siniestros.
        with self.assertNumQueries(4):
            detalle = selectors.detalle_poliza(poliza.pk)
            list(detalle.cuotas.all())
            list(detalle.conductores.all())
            list(detalle.siniestros.all())
            self.assertEqual(detalle.vehiculo, vehiculo)
            self.assertEqual(detalle.compania, compania)
            self.assertEqual(detalle.cliente, cliente)

    # AC-T4-31
    def test_fabricas_generan_valores_unicos(self):
        vehiculos = [fabricas.crear_vehiculo() for _ in range(5)]
        self.assertEqual(len({v.patente for v in vehiculos}), 5)
        companias = [fabricas.crear_compania() for _ in range(3)]
        self.assertEqual(len({c.nombre for c in companias}), 3)
        for vehiculo in vehiculos:
            self.assertEqual(normalizar_patente(vehiculo.patente), vehiculo.patente)
