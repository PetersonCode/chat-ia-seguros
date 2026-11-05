from datetime import timedelta,datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from django.utils import timezone
from datos import fabricas
from datos.models import Mensaje,ContactoWhatsapp
from datos.gestion_models import ConfigGestion,Tarea,NotaInterna,AvisoGestion
from api.tests.base import ApiTestCase
from negocio.gestion_diaria import procesar,texto
from negocio.bot.orquestador import procesar_mensaje

class GestionDiariaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.entrar()
        self.hoy=timezone.localdate()
        self.poliza=fabricas.crear_poliza(self.cliente,fecha_vencimiento=self.hoy+timedelta(days=7))
        self.ahora=datetime.combine(self.hoy,datetime.min.time(),tzinfo=ZoneInfo('America/Argentina/Buenos_Aires')).replace(hour=12)
        self.conversacion.ultimo_mensaje_cliente_en=self.ahora-timedelta(hours=1)
        self.conversacion.save()

    def test_panel_prioriza_atrasos_y_usa_embudo_existente(self):
        fabricas.crear_cuota(self.poliza,vencimiento=self.hoy-timedelta(days=4))
        fabricas.crear_interesado(contacto=self.contacto,proximo_contacto=self.hoy)
        d=self.cliente_api.get('/api/gestion/inicio/').json()
        self.assertEqual(d['cantidades']['renovaciones'],1)
        self.assertEqual(d['cantidades']['morosos'],1)
        self.assertEqual(d['cantidades']['interesados'],1)

    def test_aviso_automatico_no_borra_cliente_que_lleva_horas_sin_respuesta(self):
        m=fabricas.crear_mensaje(self.conversacion,emisor='cliente')
        Mensaje.objects.filter(pk=m.pk).update(fecha_hora=timezone.now()-timedelta(hours=3))
        aviso=fabricas.crear_mensaje(self.conversacion,emisor='bot',direccion='saliente',estado_envio='enviado')
        aviso.payload={'aviso_gestion_id':1};aviso.save(update_fields=['payload'])
        self.assertEqual(self.cliente_api.get('/api/gestion/inicio/').json()['cantidades']['sin_respuesta'],1)

    def test_asignar_completar_y_no_duplicar_resolucion(self):
        r=self.cliente_api.post('/api/gestion/tareas/',{'titulo':'Llamar por descuento','vence':str(self.hoy),'cliente':self.cliente.id,'asignada_a':self.operador.id},format='json')
        self.assertEqual(r.status_code,201,r.content)
        self.entrar(self.operador)
        ruta=f'/api/gestion/tareas/{r.json()["id"]}/'
        self.assertEqual(self.cliente_api.patch(ruta,{'accion':'hecha'},format='json').status_code,200)
        self.assertEqual(self.cliente_api.patch(ruta,{'accion':'hecha'},format='json').status_code,409)

    def test_no_permite_completar_tarea_ajena_ni_asignar_a_inactivo(self):
        otro=fabricas.crear_funcionario('Otro',puede_aprobar=False)
        t=Tarea.objects.create(titulo='Consultar póliza',asignada_a=otro,creada_por=otro,vence=self.hoy)
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.patch(f'/api/gestion/tareas/{t.id}/',{'accion':'hecha'},format='json').status_code,403)
        otro.activo=False;otro.save()
        self.assertEqual(self.cliente_api.post('/api/gestion/tareas/',{'titulo':'Consultar póliza','vence':str(self.hoy),'asignada_a':otro.id},format='json').status_code,400)

    def test_notas_son_internas_y_exigen_sesion(self):
        ruta=f'/api/gestion/clientes/{self.cliente.id}/notas/'
        r=self.cliente_api.post(ruta,{'texto':'Pidió descuento, llamar en marzo.'},format='json')
        self.assertEqual(r.status_code,200)
        self.assertEqual(NotaInterna.objects.get().autor_id,self.aprobadora.id)
        self.cliente_api.logout()
        self.assertEqual(self.cliente_api.get(ruta).status_code,401)

    def test_dry_run_no_escribe_y_config_apagada_no_envia(self):
        self.assertEqual(procesar(self.ahora,dry_run=True)['escrituras'],0)
        self.assertFalse(AvisoGestion.objects.exists())
        procesar(self.ahora)
        self.assertEqual(AvisoGestion.objects.count(),1)
        self.assertFalse(Mensaje.objects.filter(direccion='saliente').exists())

    def test_auto_abierto_envia_una_vez_y_reintento_no_duplica(self):
        ConfigGestion.objects.filter(pk=1).update(automaticos=True)
        with patch('django.utils.timezone.now',return_value=self.ahora), self.captureOnCommitCallbacks(execute=True):
            procesar(self.ahora);procesar(self.ahora)
        a=AvisoGestion.objects.get()
        self.assertEqual(a.estado,'preparado')
        self.assertEqual(a.mensaje.estado_envio,'enviado')
        self.assertEqual(Mensaje.objects.filter(direccion='saliente').count(),1)

    def test_ventana_cerrada_humano_y_fuera_horario_no_envian(self):
        ConfigGestion.objects.filter(pk=1).update(automaticos=True)
        self.conversacion.modo='humano';self.conversacion.funcionario=self.aprobadora;self.conversacion.save()
        procesar(self.ahora)
        self.assertFalse(Mensaje.objects.filter(direccion='saliente').exists())

    def test_pago_entre_programacion_y_envio_cancela_cuota(self):
        q=fabricas.crear_cuota(self.poliza,vencimiento=self.hoy)
        procesar(self.ahora)
        a=AvisoGestion.objects.get(tipo='cuota')
        from negocio.polizas import registrar_pago
        registrar_pago(self.poliza.id,referencia='PRUEBA-GESTION-01',importe=q.importe,funcionario_id=self.aprobadora.id)
        a.refresh_from_db()
        self.assertIsNone(texto(a))
        procesar(self.ahora)
        a.refresh_from_db();self.assertEqual(a.estado,'cancelado')

    def test_maximo_un_aviso_al_dia_por_contacto(self):
        ConfigGestion.objects.filter(pk=1).update(automaticos=True)
        fabricas.crear_cuota(self.poliza,vencimiento=self.hoy)
        with patch('django.utils.timezone.now',return_value=self.ahora), self.captureOnCommitCallbacks(execute=True):procesar(self.ahora)
        self.assertEqual(Mensaje.objects.filter(direccion='saliente').count(),1)

    def test_stop_no_da_de_baja_poliza_y_cancela_avisos(self):
        procesar(self.ahora)
        m=fabricas.crear_mensaje(self.conversacion,texto='No quiero recibir avisos')
        with self.captureOnCommitCallbacks(execute=True):r=procesar_mensaje(m.id)
        self.assertEqual(r.tipo_consulta,'baja_avisos')
        self.contacto.refresh_from_db();self.assertFalse(self.contacto.acepta_avisos)
        self.poliza.refresh_from_db();self.assertEqual(self.poliza.estado,'vigente')
        self.assertFalse(AvisoGestion.objects.filter(estado='pendiente').exists())

    def test_operador_no_activa_envios_automaticos(self):
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.patch('/api/gestion/config/',{'automaticos':True},format='json').status_code,403)

    def test_stop_se_respeta_tambien_durante_atencion_humana(self):
        procesar(self.ahora)
        self.conversacion.modo='humano';self.conversacion.funcionario=self.aprobadora;self.conversacion.save()
        m=fabricas.crear_mensaje(self.conversacion,texto='STOP')
        r=procesar_mensaje(m.id)
        self.assertTrue(r.ignorado)
        self.contacto.refresh_from_db();self.assertFalse(self.contacto.acepta_avisos)

    def test_recordatorio_fuera_de_horario_y_con_ventana_cerrada_no_envia(self):
        ConfigGestion.objects.filter(pk=1).update(automaticos=True)
        procesar(self.ahora.replace(hour=22))
        self.assertFalse(Mensaje.objects.filter(direccion='saliente').exists())
        self.conversacion.ultimo_mensaje_cliente_en=self.ahora-timedelta(hours=25);self.conversacion.save()
        procesar(self.ahora)
        self.assertFalse(Mensaje.objects.filter(direccion='saliente').exists())

    def test_pago_despues_de_encolar_evitar_enviar_recordatorio_viejo(self):
        from negocio.polizas import registrar_pago
        self.poliza.fecha_vencimiento=self.hoy+timedelta(days=90);self.poliza.save()
        q=fabricas.crear_cuota(self.poliza,vencimiento=self.hoy)
        ConfigGestion.objects.filter(pk=1).update(automaticos=True)
        with patch('django.utils.timezone.now',return_value=self.ahora):
            with self.captureOnCommitCallbacks(execute=False) as callbacks:procesar(self.ahora)
            registrar_pago(self.poliza.id,referencia='GESTION-PAGO-ANTES-DE-ENVIO',importe=q.importe,funcionario_id=self.aprobadora.id)
            for callback in callbacks:callback()
        self.assertFalse(Mensaje.objects.filter(estado_envio='enviado').exists())
        self.assertTrue(Mensaje.objects.filter(estado_envio='descartado').exists())
