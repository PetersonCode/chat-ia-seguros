from datetime import timedelta
from django.utils import timezone
from datos import fabricas
from datos.models import Mensaje,CondicionesPoliza
from datos.gestion_models import PerfilCliente,Referido,Renovacion,Encuesta,AvisoGestion
from api.tests.base import ApiTestCase
from negocio.bot.orquestador import procesar_mensaje
from negocio.fidelizacion import programar_encuestas
from negocio.gestion_diaria import procesar

class FidelizacionTests(ApiTestCase):
    def setUp(self):
        super().setUp();self.entrar();self.hoy=timezone.localdate()
        self.poliza=fabricas.crear_poliza(self.cliente,vehiculo=fabricas.crear_vehiculo(self.cliente),compania=fabricas.crear_compania(),fecha_vencimiento=self.hoy+timedelta(days=7))
        self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/',{'cubre':'Responsabilidad civil.','asistencia':'0800-123-4567'},format='json')

    def test_renovacion_humana_no_duplica_y_copia_fuente_sin_compartir_version(self):
        ruta=f'/api/gestion/polizas/{self.poliza.id}/renovar/'
        d={'prima_mensual':'1500','fecha_vencimiento':str(self.hoy+timedelta(days=372)),'conservar_condiciones':True}
        r=self.cliente_api.post(ruta,d,format='json');self.assertEqual(r.status_code,201,r.content)
        n=Renovacion.objects.get().nueva
        self.assertEqual(n.prima_mensual,1500)
        self.assertNotEqual(CondicionesPoliza.objects.get(poliza=n).documento_id,CondicionesPoliza.objects.get(poliza=self.poliza).documento_id)
        self.assertEqual(self.cliente_api.post(ruta,d,format='json').status_code,409)
        self.assertTrue(AvisoGestion.objects.filter(tipo='renovacion_confirmada').exists())

    def test_operador_no_confirma_renovacion_ni_beneficio(self):
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.post(f'/api/gestion/polizas/{self.poliza.id}/renovar/',{},format='json').status_code,403)
        self.assertEqual(self.cliente_api.post(f'/api/gestion/clientes/{self.cliente.id}/referidos/',{},format='json').status_code,403)

    def test_perfil_no_exige_cumpleanos_y_rechaza_fecha_futura(self):
        ruta=f'/api/gestion/clientes/{self.cliente.id}/perfil/'
        self.assertIsNone(self.cliente_api.get(ruta).json()['nacimiento'])
        self.assertEqual(self.cliente_api.patch(ruta,{'nacimiento':str(self.hoy+timedelta(days=1))},format='json').status_code,400)

    def test_cumpleanos_solo_con_aceptacion_y_sin_duplicados(self):
        procesar(dry_run=False)
        self.assertFalse(AvisoGestion.objects.filter(tipo='cumpleanos').exists())
        PerfilCliente.objects.create(cliente=self.cliente,nacimiento=self.hoy.replace(year=2000),comerciales=True)
        procesar();procesar()
        self.assertEqual(AvisoGestion.objects.filter(tipo='cumpleanos').count(),1)

    def test_referidos_exigen_personas_distintas_y_una_sola_recompensa(self):
        ruta=f'/api/gestion/clientes/{self.cliente.id}/referidos/'
        self.assertEqual(self.cliente_api.post(ruta,{'referido':self.cliente.id},format='json').status_code,400)
        otro=fabricas.crear_cliente()
        r=self.cliente_api.post(ruta,{'referido':otro.id},format='json');self.assertEqual(r.status_code,201)
        self.assertEqual(self.cliente_api.post(ruta,{'referido':otro.id},format='json').status_code,409)
        r=self.cliente_api.patch(f'/api/gestion/referidos/{r.json()["id"]}/',{'estado':'otorgado','beneficio':'Regalo entregado en la agencia'},format='json')
        self.assertEqual(r.status_code,200)
        self.poliza.refresh_from_db();self.assertEqual(self.poliza.prima_mensual,1000)

    def test_credencial_privada_sin_dni_ni_saldo_y_bot_no_deriva(self):
        ruta=f'/api/gestion/polizas/{self.poliza.id}/credencial/'
        r=self.cliente_api.get(ruta);self.assertEqual(r.status_code,200)
        self.assertNotIn(self.cliente.dni,r.content.decode())
        self.assertNotIn('Saldo',r.content.decode())
        m=fabricas.crear_mensaje(self.conversacion,texto='Pasame mi credencial')
        with self.captureOnCommitCallbacks(execute=True):resultado=procesar_mensaje(m.id)
        self.assertFalse(resultado.retenido,resultado.alertas)
        self.assertIn(self.poliza.vehiculo.patente,Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).texto)
        self.cliente_api.logout();self.assertEqual(self.cliente_api.get(ruta).status_code,401)

    def test_encuesta_por_chat_no_confunde_seleccion_de_poliza(self):
        e=Encuesta.objects.create(contacto=self.contacto,referencia='consulta/prueba')
        m=fabricas.crear_mensaje(self.conversacion,texto='Encuesta 5')
        with self.captureOnCommitCallbacks(execute=True):r=procesar_mensaje(m.id)
        self.assertEqual(r.tipo_consulta,'encuesta_respuesta')
        e.refresh_from_db();self.assertEqual(e.puntaje,5)

    def test_credencial_png_es_descargable_para_el_celular(self):
        from PIL import Image
        from io import BytesIO
        r=self.cliente_api.get(f'/api/gestion/polizas/{self.poliza.id}/credencial/?formato=png')
        self.assertEqual(r.status_code,200)
        self.assertEqual(r['Content-Type'],'image/png')
        self.assertEqual(Image.open(BytesIO(r.content)).size,(1080,1240))

    def test_reporte_no_confunde_altas_con_renovaciones_y_oculta_comision(self):
        ruta='/api/gestion/reporte/?mes='+self.hoy.strftime('%Y-%m')
        self.assertEqual(self.cliente_api.get(ruta).json()['nuevas'],1)
        self.entrar(self.operador);self.assertIsNone(self.cliente_api.get(ruta).json()['comision'])

    def test_no_se_encuesta_cada_mensaje_del_mismo_cliente(self):
        fabricas.crear_catalogos()
        for pregunta in ('¿Qué cubre mi póliza?','¿Qué cobertura tengo?'):
            m=fabricas.crear_mensaje(self.conversacion,texto=pregunta)
            with self.captureOnCommitCallbacks(execute=True):procesar_mensaje(m.id)
        programar_encuestas();programar_encuestas()
        self.assertEqual(Encuesta.objects.count(),1)
