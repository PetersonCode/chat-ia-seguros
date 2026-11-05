from datetime import date, timedelta

from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import AuditoriaSeguridad
from negocio.polizas import alta_poliza


class CarteraApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.vehiculo = fabricas.crear_vehiculo(self.cliente, patente='AA777ZZ',
            marca='Toyota', modelo='Hilux', clase='camioneta')
        self.compania = fabricas.crear_compania(nombre='Aseguradora prueba', comision_pct='15')
        hoy = timezone.localdate()
        self.poliza = alta_poliza(self.cliente.id, tipo_seguro='automotor', cobertura='basica',
            fecha_inicio=hoy, fecha_vencimiento=hoy+timedelta(days=180), prima_mensual='1000')

    @property
    def ruta(self):
        return f'/api/polizas/{self.poliza.id}/cartera/'

    def test_aprobador_completa_historica_y_api_devuelve_comision_en_pesos(self):
        self.entrar()
        respuesta = self.cliente_api.patch(self.ruta, {'vehiculo_id': self.vehiculo.id,
            'compania_id': self.compania.id}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()['comision_mensual_estimada'], '150.00')
        self.assertEqual(respuesta.json()['vehiculo']['clase'], 'camioneta')
        self.poliza.refresh_from_db()
        self.assertEqual(self.poliza.vehiculo_id, self.vehiculo.id)
        self.assertEqual(self.poliza.cuotas.first().importe, 1000)
        self.assertTrue(AuditoriaSeguridad.objects.filter(recurso=self.ruta, estado=200).exists())

    def test_no_expone_comisiones_ni_permite_modificarlas_a_operador(self):
        self.entrar(self.operador)
        self.assertError(self.cliente_api.patch(self.ruta, {'comision_pct': '100'}, format='json'),
                         403, 'permiso_denegado')
        respuesta = self.cliente_api.get(f'/api/polizas/{self.poliza.id}/')
        self.assertIsNone(respuesta.json()['comision_mensual_estimada'])
        self.assertError(self.cliente_api.get('/api/reportes/comisiones/?desde=2026-01-01&hasta=2026-12-31'),
                         403, 'permiso_denegado')

    def test_reporte_requiere_sesion_y_valida_fechas(self):
        ruta = '/api/reportes/comisiones/'
        self.assertError(self.cliente_api.get(ruta), 401, 'no_autenticado')
        self.entrar()
        for query in ['', '?desde=2026-12-01&hasta=2026-01-01', '?desde=ayer&hasta=2026-01-01']:
            self.assertError(self.cliente_api.get(ruta+query), 400, 'datos_invalidos')

    def test_reporte_agrupa_y_usa_fecha_de_cuota_no_fecha_de_alta(self):
        self.entrar()
        self.cliente_api.patch(self.ruta, {'compania_id': self.compania.id}, format='json')
        mes = timezone.localdate().replace(day=1)
        respuesta = self.cliente_api.get(f'/api/reportes/comisiones/?desde={mes}&hasta={mes.replace(day=28)}')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        reporte = respuesta.json()
        self.assertEqual(reporte['totales']['estimada'], '150.00')
        self.assertEqual(reporte['totales']['sobre_cobros'], '0.00')
        self.assertEqual(reporte['por_compania'][0]['nombre'], self.compania.nombre)
        self.assertIn('no-store', respuesta.get('Cache-Control', ''))

    def test_no_permite_vehiculo_ajeno_ni_comisiones_fuera_de_rango(self):
        self.entrar()
        ajeno = fabricas.crear_vehiculo()
        for campos in [{'vehiculo_id': ajeno.id}, {'vehiculo_id': 999999},
                       {'comision_pct': '101'}, {'comision_pct': 'NaN'}]:
            respuesta = self.cliente_api.patch(self.ruta, campos, format='json')
            self.assertError(respuesta, 400, 'datos_invalidos')
        self.poliza.refresh_from_db()
        self.assertIsNone(self.poliza.vehiculo_id)

    def test_vencimientos_busca_patente_actualizada_y_no_pierde_saldo_ni_compania(self):
        self.entrar()
        self.cliente_api.patch(self.ruta, {'vehiculo_id': self.vehiculo.id,
            'compania_id': self.compania.id}, format='json')
        self.vehiculo.patente = 'BB888ZZ'
        self.vehiculo.save(update_fields=['patente'])
        respuesta = self.cliente_api.get('/api/vencimientos/?q=BB888ZZ')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        fila = respuesta.json()['resultados'][0]
        self.assertIn('BB888ZZ', fila['vehiculo'])
        self.assertEqual(fila['compania'], self.compania.nombre)
        self.assertEqual(float(fila['saldo_total']), 6000)

    def test_clase_valida_en_alta_y_edicion(self):
        self.entrar()
        ruta = f'/api/vehiculos/{self.vehiculo.id}/'
        respuesta = self.cliente_api.patch(ruta, {'clase': 'utilitario'}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()['clase'], 'utilitario')
        self.assertError(self.cliente_api.patch(ruta, {'clase': 'espacial'}, format='json'),
                         400, 'datos_invalidos')

    def test_csv_no_ejecuta_formulas_y_restringe_comisiones(self):
        self.entrar()
        self.compania.nombre = '=1+1'
        self.compania.save(update_fields=['nombre'])
        self.cliente_api.patch(self.ruta, {'compania_id': self.compania.id}, format='json')
        ruta = '/api/reportes/comisiones/?desde=2026-01-01&hasta=2099-12-31&formato=csv'
        respuesta = self.cliente_api.get(ruta)
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertIn("'=1+1", respuesta.content.decode())
        self.assertIn('text/csv', respuesta['Content-Type'])
        self.entrar(self.operador)
        self.assertError(self.cliente_api.get(ruta), 403, 'permiso_denegado')
