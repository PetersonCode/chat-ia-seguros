from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.utils import timezone
from django.db import connection
from datos import fabricas
from datos.models import Cuota, Mensaje, RecordatorioPoliza
from api.tests.base import ApiTestCase
from negocio.recordatorios import polizas_por_vencer, enviar_recordatorio, texto_recordatorio
from negocio.errores import DatosInvalidos, EstadoInvalido


class VencimientosTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.hoy=timezone.localdate()
        self.poliza=fabricas.crear_poliza(self.cliente,numero_poliza='POL-90100',
            fecha_inicio=self.hoy-timedelta(days=60),fecha_vencimiento=self.hoy+timedelta(days=7))
        self.cuota=fabricas.crear_cuota(self.poliza,importe=Decimal('12500.50'),
            vencimiento=self.hoy+timedelta(days=2))
        self.ruta=f'/api/polizas/{self.poliza.pk}/recordatorio/'

    def test_listado_ordena_por_vencimiento_no_por_saldo(self):
        segunda=fabricas.crear_poliza(self.cliente,numero_poliza='POL-90101',fecha_vencimiento=self.hoy+timedelta(days=1))
        fabricas.crear_poliza(self.cliente,numero_poliza='POL-90102',estado='dada_de_baja')
        self.entrar(self.operador)
        datos=self.cliente_api.get('/api/vencimientos/').json()['resultados']
        self.assertEqual([d['id'] for d in datos],[segunda.pk,self.poliza.pk])
        self.assertEqual(datos[1]['saldo_pendiente'],'12500.50')

    def test_listado_carga_cliente_saldo_y_ultimo_aviso_sin_consultas_por_fila(self):
        for i in range(4):
            fabricas.crear_poliza(self.cliente,numero_poliza=f'POL-9030{i}')
        with self.assertNumQueries(1):
            filas=list(polizas_por_vencer())
            self.assertTrue(all(p.cliente.nombre for p in filas))
            self.assertEqual(filas[0].saldo,Decimal('12500.50'))

    def test_lectura_del_listado_deja_auditoria_sin_texto_de_busqueda(self):
        from datos.models import AuditoriaSeguridad
        self.entrar()
        self.cliente_api.get('/api/vencimientos/',{'q':'consulta-privada'})
        evento=AuditoriaSeguridad.objects.filter(recurso='/api/vencimientos/').latest('id')
        self.assertEqual(evento.evento,'GET')
        self.assertNotIn('consulta-privada',str(evento.__dict__))

    def test_filtra_plazo_busqueda_y_vencidas(self):
        vencida=fabricas.crear_poliza(self.cliente,numero_poliza='POL-90103',estado='vencida',fecha_inicio=self.hoy-timedelta(days=60),fecha_vencimiento=self.hoy-timedelta(days=3))
        self.assertEqual(list(polizas_por_vencer(dias=7).values_list('id',flat=True)),[self.poliza.pk])
        self.assertEqual(list(polizas_por_vencer(incluir_vencidas=True,q='90103').values_list('id',flat=True)),[vencida.pk])

    def test_dias_invalidos_son_400(self):
        self.entrar()
        for dias in ('-1','abc','4000'):
            self.assertEqual(self.cliente_api.get('/api/vencimientos/',{'dias':dias}).status_code,400)

    def test_atrasos_primero_por_cuota_mas_antigua_aunque_poliza_venza_despues(self):
        antigua=fabricas.crear_poliza(self.cliente,fecha_vencimiento=self.hoy+timedelta(days=90))
        reciente=fabricas.crear_poliza(self.cliente,fecha_vencimiento=self.hoy+timedelta(days=30))
        fabricas.crear_cuota(antigua,importe='5000',vencimiento=self.hoy-timedelta(days=15),estado='pendiente')
        fabricas.crear_cuota(reciente,importe='20000',vencimiento=self.hoy-timedelta(days=3),estado='vencida')
        filas=list(polizas_por_vencer())
        self.assertEqual([p.pk for p in filas],[antigua.pk,reciente.pk,self.poliza.pk])
        self.assertEqual(filas[0].saldo_vencido,Decimal('5000'))
        self.assertEqual(filas[0].primera_cuota_vencida,self.hoy-timedelta(days=15))
        self.assertEqual(filas[2].saldo_vencido,Decimal('0'))

    def test_una_cuota_pagada_o_que_vence_hoy_no_es_pago_atrasado(self):
        self.cuota.vencimiento=self.hoy;self.cuota.save()
        fabricas.crear_cuota(self.poliza,importe='3000',vencimiento=self.hoy-timedelta(days=20),
            estado='pagada',fecha_pago=self.hoy,importe_pagado='3000')
        self.assertEqual(polizas_por_vencer().get(pk=self.poliza.pk).saldo_vencido,Decimal('0'))
        self.assertNotIn('cuotas vencidas',texto_recordatorio(self.poliza)[0])

    def test_aviso_distingue_deuda_vencida_del_total_y_actualiza_al_pagar(self):
        atrasada=fabricas.crear_cuota(self.poliza,importe='5000',vencimiento=self.hoy-timedelta(days=2))
        texto,total=texto_recordatorio(self.poliza)
        self.assertEqual(total,Decimal('17500.50'))
        self.assertIn('De ese total, $5.000 corresponde a cuotas vencidas.',texto)
        self.entrar()
        fila=self.cliente_api.get('/api/vencimientos/').json()['resultados'][0]
        self.assertEqual(fila['saldo_vencido'],'5000.00')
        atrasada.estado='pagada';atrasada.importe_pagado='5000';atrasada.fecha_pago=self.hoy;atrasada.save()
        self.assertEqual(polizas_por_vencer().get(pk=self.poliza.pk).saldo_vencido,Decimal('0'))

    def test_sin_sesion_no_se_ven_datos_ni_envia(self):
        self.assertIn(self.cliente_api.get('/api/vencimientos/').status_code,(401,403))
        self.assertIn(self.cliente_api.post(self.ruta,{'contacto_id':self.contacto.pk}).status_code,(401,403))

    def test_texto_usa_saldo_de_la_poliza_y_plazo_real(self):
        ajena=fabricas.crear_poliza(fabricas.crear_cliente())
        fabricas.crear_cuota(ajena,importe='99999')
        texto,saldo=texto_recordatorio(self.poliza)
        self.assertIn('vence en 7 días',texto)
        self.assertIn('$12.500,50',texto)
        self.assertNotIn('99.999',texto)
        self.assertEqual(saldo,Decimal('12500.50'))

    def test_hoy_manana_vencida_y_saldo_cero_no_mienten(self):
        self.cuota.estado='pagada';self.cuota.importe_pagado=self.cuota.importe;self.cuota.fecha_pago=self.hoy;self.cuota.save()
        for dias,esperado in [(0,'vence hoy'),(1,'vence mañana'),(-1,'venció hace 1 día')]:
            self.poliza.fecha_vencimiento=self.hoy+timedelta(days=dias)
            texto,saldo=texto_recordatorio(self.poliza)
            self.assertIn(esperado,texto)
            self.assertIn('Saldo pendiente de esta póliza: $0',texto)

    def test_numero_ajeno_no_recibe_datos_ni_crea_aviso(self):
        otro=fabricas.crear_contacto(fabricas.crear_cliente())
        self.entrar()
        self.assertEqual(self.cliente_api.get(self.ruta,{'contacto_id':otro.pk}).status_code,400)
        self.assertEqual(self.cliente_api.post(self.ruta,{'contacto_id':otro.pk},format='json').status_code,400)
        self.assertFalse(RecordatorioPoliza.objects.exists())

    def test_previsualizar_no_envia_y_refleja_pago_posterior(self):
        self.entrar()
        self.assertIn('$12.500,50',self.cliente_api.get(self.ruta).json()['texto'])
        self.assertFalse(RecordatorioPoliza.objects.exists())
        self.cuota.estado='pagada';self.cuota.importe_pagado=self.cuota.importe;self.cuota.fecha_pago=self.hoy;self.cuota.save()
        with self.captureOnCommitCallbacks(execute=True):
            r=self.cliente_api.post(self.ruta,{'contacto_id':self.contacto.pk},format='json')
        self.assertEqual(r.status_code,201,r.content)
        self.assertIn('Saldo pendiente de esta póliza: $0',RecordatorioPoliza.objects.get().texto)

    def test_envio_se_registra_en_chat_sin_tomar_el_control(self):
        self.entrar(self.operador)
        with self.captureOnCommitCallbacks(execute=True):
            r=self.cliente_api.post(self.ruta,{'contacto_id':self.contacto.pk},format='json')
        self.assertEqual(r.status_code,201,r.content)
        aviso=RecordatorioPoliza.objects.get()
        self.assertEqual(aviso.mensaje.estado_envio,'enviado')
        self.assertEqual(aviso.mensaje.emisor,'funcionario')
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'bot')

    def test_doble_click_es_idempotente_y_no_reenvia(self):
        with self.captureOnCommitCallbacks(execute=True):
            primero,nuevo=enviar_recordatorio(self.poliza.pk,self.contacto.pk,self.operador.pk)
            segundo,nuevo2=enviar_recordatorio(self.poliza.pk,self.contacto.pk,self.operador.pk)
        self.assertEqual(primero.pk,segundo.pk)
        self.assertTrue(nuevo);self.assertFalse(nuevo2)
        self.assertEqual(Mensaje.objects.filter(emisor='funcionario').count(),1)

    def test_ventana_cerrada_no_simula_envio_y_permite_registro_manual(self):
        self.conversacion.ultimo_mensaje_cliente_en=timezone.now()-timedelta(days=2);self.conversacion.save()
        self.entrar()
        self.assertFalse(self.cliente_api.get(self.ruta).json()['puede_enviar'])
        r=self.cliente_api.post(self.ruta,{'contacto_id':self.contacto.pk},format='json')
        self.assertEqual(r.status_code,409,r.content)
        self.assertFalse(RecordatorioPoliza.objects.exists())
        r=self.cliente_api.post(self.ruta,{'contacto_id':self.contacto.pk,'canal':'manual'},format='json')
        self.assertEqual(r.status_code,201)
        self.assertEqual(r.json()['recordatorio']['estado'],'enviado_manual')
        self.assertIsNone(RecordatorioPoliza.objects.get().mensaje)

    def test_fallo_de_meta_se_conserva_como_fallido_no_enviado(self):
        with patch.dict('os.environ',{'WHATSAPP_MODO':'real'}),patch('negocio.whatsapp._enviar_por_api',side_effect=RuntimeError('fallo de prueba')):
            with self.captureOnCommitCallbacks(execute=True):
                aviso,_=enviar_recordatorio(self.poliza.pk,self.contacto.pk,self.operador.pk)
        aviso.mensaje.refresh_from_db()
        self.assertEqual(aviso.mensaje.estado_envio,'fallido')

    def test_cliente_inactivo_o_poliza_baja_no_admiten_envio(self):
        self.cliente.activo=False;self.cliente.save()
        with self.assertRaises(EstadoInvalido):enviar_recordatorio(self.poliza.pk,self.contacto.pk,self.operador.pk)
        self.assertFalse(polizas_por_vencer().exists())

    def test_varios_numeros_exigen_elegir_y_se_validan(self):
        fabricas.crear_contacto(self.cliente)
        self.entrar()
        datos=self.cliente_api.get(self.ruta).json()
        self.assertIsNone(datos['contacto_id'])
        self.assertFalse(datos['puede_enviar'])

    def test_sql_23_se_puede_aplicar_otra_vez_sin_borrar_avisos(self):
        from django.conf import settings
        enviar_recordatorio(self.poliza.pk,self.contacto.pk,self.operador.pk,canal='manual')
        with connection.cursor() as c:c.execute((settings.BASE_DIR/'SDD/sql/23_recordatorios_polizas.sql').read_text().replace('BEGIN;','').replace('COMMIT;',''))
        self.assertEqual(RecordatorioPoliza.objects.count(),1)
