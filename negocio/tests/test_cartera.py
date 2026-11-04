from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase
from django.utils import timezone

from datos import fabricas, selectors
from datos.models import Poliza, Cuota
from datos.tests.transacciones import PruebaConTransacciones
from negocio.cartera import completar_cartera
from negocio.comisiones import reporte_comisiones, importe_comision
from negocio.errores import DatosInvalidos, PermisoDenegado
from negocio.polizas import alta_poliza, registrar_pago


class CarteraTests(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        self.cliente = fabricas.crear_cliente(nombre='Ana', apellido='Pérez')
        self.funcionario = fabricas.crear_funcionario(puede_aprobar=True)
        self.vehiculo = fabricas.crear_vehiculo(self.cliente, marca='Toyota', modelo='Hilux',
            clase='camioneta', patente='AB123CD', chasis='VIN1234')
        self.compania = fabricas.crear_compania(comision_pct='12.50')

    def alta(self, **datos):
        campos = dict(tipo_seguro='automotor', cobertura='intermedia', fecha_inicio=date(2026, 1, 1),
                      fecha_vencimiento=date(2026, 12, 31), prima_mensual='1000',
                      vehiculo_id=self.vehiculo.id, compania_id=self.compania.id)
        return alta_poliza(self.cliente.id, **(campos | datos))

    def test_busca_frase_patente_chasis_nombre_completo_y_sin_tildes(self):
        for texto in ['la camioneta de Perez', 'Hilux Pérez', 'Ana Perez', 'AB-123-CD',
                      'vin1234', 'pickup de Pérez', 'TOYOTA HILUX']:
            with self.subTest(texto=texto):
                self.assertEqual(list(selectors.buscar_clientes(texto)), [self.cliente])
        self.assertFalse(selectors.buscar_clientes('Hilux Gonzalez').exists())

    def test_no_mezcla_datos_de_dos_vehiculos_del_mismo_cliente(self):
        fabricas.crear_vehiculo(self.cliente, marca='Ford', modelo='Focus', clase='auto')
        self.assertFalse(selectors.buscar_clientes('Ford Hilux').exists())

    def test_chasis_se_normaliza_y_no_admite_el_mismo_con_otra_patente(self):
        from negocio.vehiculos import alta_vehiculo, modificar_vehiculo
        modificar_vehiculo(self.vehiculo.id, funcionario_id=self.funcionario.id, chasis=' vi n-1234 ')
        self.vehiculo.refresh_from_db()
        self.assertEqual(self.vehiculo.chasis, 'VIN1234')
        for texto in ['VIN1234', 'vin 1234', 'VIN-1234']:
            self.assertEqual(list(selectors.buscar_clientes(texto)), [self.cliente])
        with self.assertRaises(DatosInvalidos):
            alta_vehiculo(self.cliente.id, patente='XY123ZZ', marca='Toyota', modelo='Hilux',
                          anio=2022, chasis='vin-1234', funcionario_id=self.funcionario.id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            fabricas.crear_vehiculo(chasis='V I N-1234')

    def test_no_duplica_cliente_con_varios_vehiculos_que_coinciden(self):
        fabricas.crear_vehiculo(self.cliente, marca='Toyota', modelo='Corolla')
        self.assertEqual(list(selectors.buscar_clientes('Toyota')), [self.cliente])

    def test_chasis_numerico_no_se_confunde_exclusivamente_con_dni(self):
        self.vehiculo.chasis = '12345678'
        self.vehiculo.save(update_fields=['chasis'])
        self.assertEqual(list(selectors.buscar_clientes('12345678')), [self.cliente])

    def test_rechaza_solapamiento_aun_cambiando_de_compania(self):
        primera = self.alta()
        for inicio, fin in [(date(2026, 2, 1), date(2026, 3, 1)),
                            (date(2025, 1, 1), date(2027, 1, 1)),
                            (date(2026, 12, 31), date(2027, 12, 31))]:
            with self.subTest(inicio=inicio):
                with self.assertRaises(DatosInvalidos):
                    self.alta(fecha_inicio=inicio, fecha_vencimiento=fin,
                              compania_id=fabricas.crear_compania().id)
        self.assertEqual(Poliza.objects.count(), 1)
        self.assertEqual(Cuota.objects.filter(poliza=primera).count(), 12)

    def test_permite_renovacion_desde_el_dia_siguiente_y_reemplazo_tras_baja(self):
        primera = self.alta()
        renovada = self.alta(fecha_inicio=date(2027, 1, 1), fecha_vencimiento=date(2027, 12, 31))
        self.assertIsNotNone(renovada.id)
        primera.estado = 'dada_de_baja'
        primera.save(update_fields=['estado'])
        self.assertIsNotNone(self.alta().id)

    def test_trigger_impide_solapamiento_y_titular_ajeno_incluso_fuera_del_servicio(self):
        primera = self.alta()
        with self.assertRaises(IntegrityError), transaction.atomic():
            fabricas.crear_poliza(self.cliente, vehiculo=self.vehiculo,
                fecha_inicio=primera.fecha_inicio, fecha_vencimiento=primera.fecha_vencimiento)
        with self.assertRaises(IntegrityError), transaction.atomic():
            fabricas.crear_poliza(vehiculo=self.vehiculo)

    def test_completar_historica_conserva_cuotas_y_saldo_y_no_cambia_pct_al_guardar(self):
        poliza = self.alta(vehiculo_id=None, compania_id=None)
        cuotas = list(poliza.cuotas.values())
        completar_cartera(poliza.id, funcionario_id=self.funcionario.id,
                         vehiculo_id=self.vehiculo.id, compania_id=self.compania.id)
        self.compania.comision_pct = 20
        self.compania.save(update_fields=['comision_pct'])
        completar_cartera(poliza.id, funcionario_id=self.funcionario.id, compania_id=self.compania.id)
        poliza.refresh_from_db()
        self.assertEqual(poliza.comision_pct, Decimal('12.50'))
        self.assertEqual(list(poliza.cuotas.values()), cuotas)

    def test_completar_rechaza_solapamiento_y_no_guarda_cambios_parciales(self):
        self.alta()
        historica = self.alta(vehiculo_id=None, compania_id=None)
        with self.assertRaises(DatosInvalidos):
            completar_cartera(historica.id, funcionario_id=self.funcionario.id,
                             vehiculo_id=self.vehiculo.id, compania_id=self.compania.id)
        historica.refresh_from_db()
        self.assertIsNone(historica.compania_id)
        operador = fabricas.crear_funcionario(puede_aprobar=False)
        with self.assertRaises(PermisoDenegado):
            completar_cartera(historica.id, funcionario_id=operador.id, comision_pct='99')

    def test_comision_congelada_y_bases_diferentes_sin_multiplicar_importes(self):
        poliza = self.alta()
        with patch('negocio.polizas.timezone.localdate', return_value=date(2026, 11, 4)):
            registrar_pago(poliza.id, funcionario_id=self.funcionario.id, importe='1000', referencia='COBRO-CARTERA-1')
        self.compania.comision_pct = 40
        self.compania.save(update_fields=['comision_pct'])
        hoy = date(2026, 11, 4)
        reporte = reporte_comisiones(hoy.replace(day=1), hoy.replace(day=28))
        self.assertEqual(reporte['totales']['estimada'], '125.00')
        self.assertEqual(reporte['totales']['sobre_cobros'], '125.00')
        self.assertEqual(reporte['por_compania'][0]['estimada'], '125.00')
        self.assertEqual(reporte['por_cliente'][0]['nombre'], 'Pérez, Ana')
        self.assertEqual(reporte['sin_porcentaje'], 0)

    def test_cero_es_conocido_y_sin_porcentaje_se_advierte_redondeo_por_cuota(self):
        self.alta(comision_pct='0')
        otra = fabricas.crear_poliza(self.cliente, numero_poliza='POL-97000')
        fabricas.crear_cuota(otra, periodo=date(2026, 2, 1), vencimiento=date(2026, 2, 10))
        reporte = reporte_comisiones(date(2026, 2, 1), date(2026, 2, 28))
        self.assertEqual(reporte['totales']['estimada'], '0.00')
        self.assertEqual(reporte['sin_porcentaje'], 1)
        self.assertEqual(importe_comision(Decimal('0.05'), Decimal('10')), Decimal('0.01'))

    def test_sql_es_reaplicable_y_preserva_el_historico(self):
        poliza = self.alta()
        sql = (Path(settings.BASE_DIR)/'SDD/sql/24_cartera_vehiculos.sql').read_text(encoding='utf-8')
        sql = sql.replace('BEGIN;', '').replace('COMMIT;', '')
        with connection.cursor() as cursor:
            cursor.execute(sql)
            cursor.execute(sql)
        self.assertTrue(Poliza.objects.filter(id=poliza.id).exists())

    def test_bot_elige_la_patente_o_la_camioneta_sin_ver_polizas_ajenas(self):
        from datos.models import ContextoCobertura
        from negocio.coberturas import contexto_automatico, responder_cobertura, es_seleccion
        contacto = fabricas.crear_contacto(self.cliente)
        conversacion = fabricas.crear_conversacion(contacto)
        hoy = timezone.localdate()
        camioneta = self.alta(fecha_inicio=hoy, fecha_vencimiento=hoy+timedelta(days=180))
        auto = fabricas.crear_vehiculo(self.cliente, modelo='Focus', clase='auto')
        fabricas.crear_poliza(self.cliente, numero_poliza='POL-96000', vehiculo=auto)
        contexto_automatico(conversacion)
        listado, _ = responder_cobertura('qué cubre mi póliza', conversacion)
        self.assertIn('AB123CD', listado)
        self.assertIn('Focus', listado)
        self.assertTrue(es_seleccion('AB 123 CD', conversacion))
        responder_cobertura('AB 123 CD', conversacion)
        contexto = ContextoCobertura.objects.get(conversacion=conversacion)
        self.assertEqual(contexto.poliza_id, camioneta.id)
        responder_cobertura('qué cubre mi camioneta', conversacion)
        contexto.refresh_from_db()
        self.assertEqual(contexto.poliza_id, camioneta.id)
        mensaje, _ = responder_cobertura('mi patente XY987ZZ', conversacion)
        self.assertIn('No encuentro', mensaje)


class ConcurrenciaCarteraTests(PruebaConTransacciones):
    def test_dos_altas_directas_concurrentes_solo_dejan_una_poliza(self):
        fabricas.crear_catalogos()
        cliente = fabricas.crear_cliente()
        vehiculo = fabricas.crear_vehiculo(cliente)
        tipo_id = fabricas.crear_poliza(cliente).tipo_seguro_id
        barrera = Barrier(2)

        def insertar(numero):
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                with transaction.atomic():
                    Poliza.objects.create(numero_poliza=f'POL-{numero:05d}', cliente_id=cliente.id,
                        vehiculo_id=vehiculo.id, tipo_seguro_id=tipo_id, cobertura='basica', estado='vigente',
                        fecha_inicio=date(2030, 1, 1), fecha_vencimiento=date(2030, 12, 31), prima_mensual=1000)
                return 'creada'
            except IntegrityError:
                return 'rechazada'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as equipo:
            futuros = [equipo.submit(insertar, n) for n in (98001, 98002)]
            self.assertCountEqual([f.result(timeout=20) for f in futuros], ['creada', 'rechazada'])
        self.assertEqual(Poliza.objects.filter(vehiculo=vehiculo).count(), 1)
