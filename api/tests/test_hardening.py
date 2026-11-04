from datetime import timedelta
from unittest.mock import patch
from django.conf import settings
from django.db import connection, transaction, DatabaseError
from django.test import override_settings
from django.utils import timezone
from datos import fabricas
from datos.models import ContextoCobertura, AuditoriaSeguridad, DocumentoPoliza
from api.tests.base import ApiTestCase
from negocio.documentos import crear_documento, aprobar_documento, retirar_documento, buscar_fragmentos
from negocio.coberturas import contexto_automatico, responder_cobertura, vincular_documento
from negocio.bot.orquestador import procesar_mensaje
from negocio.seguridad import admitir


@override_settings(BUSQUEDA_SEMANTICA=False)
class CoberturaSeguraTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        hoy = timezone.localdate()
        self.poliza = fabricas.crear_poliza(self.cliente, numero_poliza='POL-00101',
            fecha_inicio=hoy-timedelta(days=5), fecha_vencimiento=hoy+timedelta(days=365))
        self.doc = crear_documento(titulo='Condiciones particulares auto', version='1',
            referencia='Condiciones ficticias académicas', contenido='La cobertura incluye rotura de cristales del automotor. Se excluye el desgaste.',
            funcionario_id=self.aprobadora.id)
        aprobar_documento(self.doc.id, self.aprobadora.id)
        vincular_documento(self.poliza.numero_poliza, self.doc.id, self.aprobadora.id)

    def contexto(self):
        return contexto_automatico(self.conversacion)

    def test_numero_no_vinculado_no_expone_poliza_ni_fuente(self):
        self.contacto.cliente=None
        self.contacto.save()
        self.conversacion.refresh_from_db()
        texto, fuente = responder_cobertura('qué cubre mi póliza', self.conversacion)
        self.assertIn('vinculada a este número', texto)
        self.assertNotIn('POL-', texto)
        self.assertIsNone(fuente)

    def test_contacto_reconocido_cita_solo_condiciones_vinculadas(self):
        self.contexto()
        texto, fuente = responder_cobertura('qué cubre mi póliza', self.conversacion)
        self.assertIn(self.poliza.numero_poliza, texto)
        self.assertIn('rotura de cristales', texto)
        self.assertIsNotNone(fuente)

    def test_parafrasis_parabrisas_encuentra_cristales(self):
        self.contexto()
        texto, fuente = responder_cobertura('mi parabrisas está roto', self.conversacion)
        self.assertIn('rotura de cristales', texto)
        self.assertIsNotNone(fuente)

    def test_fuente_personal_no_se_busca_en_biblioteca_general(self):
        self.assertFalse(buscar_fragmentos('cristales')['respaldo_suficiente'])

    def test_fuentes_retiradas_no_se_usan(self):
        self.contexto()
        retirar_documento(self.doc.id, self.aprobadora.id)
        texto, fuente = responder_cobertura('qué cubre mi póliza', self.conversacion)
        self.assertIsNone(fuente)
        self.assertIn('no tiene condiciones aprobadas', texto)

    def test_contexto_expirado_se_renueva_sin_intervencion_humana(self):
        contexto=self.contexto()
        ContextoCobertura.objects.filter(pk=contexto.pk).update(creado_en=timezone.now()-timedelta(hours=2),expira_en=timezone.now()-timedelta(hours=1))
        texto, fuente=responder_cobertura('qué cubre mi póliza',self.conversacion)
        self.assertIsNotNone(fuente)
        self.assertIn(self.poliza.numero_poliza,texto)

    def test_cambio_de_cliente_no_reutiliza_el_contexto_anterior(self):
        self.contexto()
        otro = fabricas.crear_cliente()
        self.contacto.cliente = otro
        self.contacto.save()
        self.conversacion.refresh_from_db()
        self.assertIsNone(responder_cobertura('mi cobertura', self.conversacion)[1])

    def test_numero_de_poliza_ajena_no_revela_existencia(self):
        self.contexto()
        texto, fuente = responder_cobertura('mi póliza POL-99999', self.conversacion)
        self.assertNotIn('POL-99999', texto)
        self.assertIsNone(fuente)

    def test_dos_polizas_piden_seleccion_y_preservan_pregunta(self):
        from datos.models import TipoSeguro
        fabricas.crear_poliza(self.cliente, numero_poliza='POL-00102', tipo_seguro=TipoSeguro.objects.get(codigo='automotor'),
            fecha_inicio=self.poliza.fecha_inicio, fecha_vencimiento=self.poliza.fecha_vencimiento)
        self.contexto()
        texto, _ = responder_cobertura('qué cubre mi póliza', self.conversacion)
        self.assertIn('varias pólizas automotor', texto)
        texto, fuente = responder_cobertura('POL-00101', self.conversacion)
        self.assertIn('POL-00101', texto)
        self.assertIsNotNone(fuente)

    def test_sin_vinculo_no_usa_fuente_general_como_contrato(self):
        DocumentoPoliza.objects.all().delete()
        self.contexto()
        texto, fuente = responder_cobertura('mi cobertura', self.conversacion)
        self.assertIn('no tiene condiciones aprobadas', texto)
        self.assertIsNone(fuente)

    def test_no_hay_endpoint_de_validacion_manual_obligatoria(self):
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.post(f'/api/conversaciones/{self.conversacion.id}/verificar-identidad/',{}).status_code,404)

    def test_operador_no_vincula_documentos(self):
        self.entrar(self.operador)
        response=self.cliente_api.post(f'/api/polizas/{self.poliza.id}/documentos/', {'documento_id':self.doc.id},format='json')
        self.assertEqual(response.status_code,403)

    def test_flujo_bot_completo_no_retiene_una_cita_real(self):
        self.contexto()
        mensaje=fabricas.crear_mensaje(self.conversacion,texto='qué cubre mi póliza')
        resultado=procesar_mensaje(mensaje.id)
        from datos.models import Mensaje
        respuesta=Mensaje.objects.get(pk=resultado.mensaje_respuesta_id)
        self.assertIn('rotura de cristales',respuesta.texto)
        self.assertNotEqual(respuesta.estado_envio,'retenido')

    def test_modelo_semantico_no_es_fuente_de_afirmaciones(self):
        with patch('negocio.busqueda_semantica.similitud',return_value=0.9):
            resultado=buscar_fragmentos('proteger ventanas del coche',documentos_ids=[self.doc.id])
        self.assertTrue(resultado['respaldo_suficiente'])
        self.assertEqual(resultado['resultados'][0]['pasaje'], self.doc.fragmentos.first().texto)

    def test_cuenta_vinculada_responde_saldo_sin_pedir_un_asesor(self):
        mensaje=fabricas.crear_mensaje(self.conversacion,texto='cuánto debo')
        resultado=procesar_mensaje(mensaje.id)
        from datos.models import Mensaje
        texto=Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).texto
        self.assertNotIn('verificar',texto)
        self.assertTrue('saldo' in texto)

    def test_versiones_duplicadas_no_compiten_como_fuentes(self):
        nuevo=crear_documento(titulo=self.doc.titulo,version='2',referencia='Fuente ficticia',contenido='Otras condiciones',funcionario_id=self.aprobadora.id)
        from negocio.errores import EstadoInvalido
        with self.assertRaises(EstadoInvalido):aprobar_documento(nuevo.id,self.aprobadora.id)

    def test_cliente_inactivo_no_recibe_condiciones_personales(self):
        self.cliente.activo=False
        self.cliente.save()
        self.conversacion.refresh_from_db()
        self.assertIsNone(responder_cobertura('mi cobertura',self.conversacion)[1])

    def test_crear_documento_con_poliza_inexistente_no_deja_datos_parciales(self):
        self.entrar()
        from datos.models import DocumentoGeneral
        antes=DocumentoGeneral.objects.count()
        r=self.cliente_api.post('/api/documentos/',{'titulo':'No debe crearse','version':'1','referencia':'Ficticia','contenido':'Contenido','numero_poliza':'POL-99999'},format='json')
        self.assertEqual(r.status_code,400)
        self.assertEqual(DocumentoGeneral.objects.count(),antes)

    def test_flujo_api_crea_vincula_aprueba(self):
        self.entrar()
        r=self.cliente_api.post('/api/documentos/',{'titulo':'Cobertura extra ficticia','version':'1','referencia':'Ficticia','contenido':'La cobertura excluye desgaste.','numero_poliza':self.poliza.numero_poliza},format='json')
        self.assertEqual(r.status_code,201,r.content)
        self.assertTrue(DocumentoPoliza.objects.filter(documento_id=r.json()['id'],poliza=self.poliza).exists())
        self.assertEqual(self.cliente_api.post(f"/api/documentos/{r.json()['id']}/aprobar/").status_code,200)

    def test_sin_fuente_se_deriva_realmente_al_equipo(self):
        DocumentoPoliza.objects.all().delete()
        mensaje=fabricas.crear_mensaje(self.conversacion,texto='qué cubre mi póliza')
        resultado=procesar_mensaje(mensaje.id)
        from datos.models import Derivacion
        self.assertTrue(Derivacion.objects.filter(consulta__conversacion=self.conversacion).exists())
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'humano')

    def test_solo_se_admiten_altas_automotor(self):
        from negocio.polizas import alta_poliza
        from negocio.errores import DatosInvalidos
        with self.assertRaises(DatosInvalidos):
            alta_poliza(self.cliente.id,tipo_seguro='hogar',cobertura='basica',fecha_inicio=self.poliza.fecha_inicio,fecha_vencimiento=self.poliza.fecha_vencimiento,prima_mensual='1000')

    def test_siniestro_no_urgente_tambien_deriva(self):
        from datos.models import Derivacion
        mensaje=fabricas.crear_mensaje(self.conversacion,texto='Se me rompió el parabrisas, ¿mi seguro lo cubre?')
        resultado=procesar_mensaje(mensaje.id)
        self.assertEqual(resultado.tipo_consulta,'siniestro')
        from negocio.whatsapp import mensaje_permitido_durante_atencion
        from datos.models import Mensaje
        self.assertTrue(mensaje_permitido_durante_atencion(Mensaje.objects.get(pk=resultado.mensaje_respuesta_id)))
        self.assertTrue(Derivacion.objects.filter(consulta__conversacion=self.conversacion).exists())
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'humano')

    def test_pregunta_hipotetica_no_se_confunde_con_hecho_ocurrido(self):
        from negocio.bot.clasificador import clasificar
        for texto in ('¿Qué cubre mi póliza si se me rompe el parabrisas?',
                      '¿Qué pasa si choco?', '¿Qué protección tengo si hay granizo?'):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto),'consulta_cobertura')

    def test_siniestro_no_se_pierde_mientras_el_cliente_elige_poliza(self):
        from datos.models import Derivacion
        contexto=self.contexto()
        contexto.pregunta='qué cubre mi póliza'
        contexto.save(update_fields=['pregunta'])
        mensaje=fabricas.crear_mensaje(self.conversacion,texto='Me rayaron el auto, ¿me cubre?')
        resultado=procesar_mensaje(mensaje.id)
        self.assertEqual(resultado.tipo_consulta,'siniestro')
        self.assertTrue(Derivacion.objects.filter(consulta__conversacion=self.conversacion).exists())

    def test_hechos_relatados_con_distintas_palabras_son_siniestros(self):
        from negocio.bot.clasificador import clasificar
        for texto in ('Mi parabrisas está roto, ¿qué cubre mi póliza?',
                      'Se me astilló el vidrio delantero', 'Me abollaron el coche'):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto),'siniestro')

    def test_pregunta_de_seguimiento_usa_la_poliza_ya_seleccionada(self):
        responder_cobertura('qué cubre mi póliza',self.conversacion)
        texto,fuente=responder_cobertura('¿El parabrisas está cubierto?',self.conversacion)
        self.assertIn(self.poliza.numero_poliza,texto)
        self.assertIsNotNone(fuente)

    def test_cliente_inactivo_tampoco_recibe_saldo(self):
        from datos.models import Mensaje
        self.cliente.activo=False
        self.cliente.save()
        mensaje=fabricas.crear_mensaje(self.conversacion,texto='cuánto debo')
        resultado=procesar_mensaje(mensaje.id)
        texto=Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).texto
        self.assertNotIn('Tu saldo pendiente',texto)
        self.assertIn('asociada a este número',texto)


class SeguridadHTTPTests(ApiTestCase):
    def test_cabeceras_y_no_cache_de_datos(self):
        self.entrar()
        r=self.cliente_api.get('/api/auth/me/')
        self.assertIn('no-store',r['Cache-Control'])
        self.assertIn("frame-ancestors 'none'",r['Content-Security-Policy'])

    def test_login_tiene_limite_por_cuenta(self):
        for _ in range(10):
            r=self.cliente_api.post('/api/auth/login/',{'email':self.aprobadora.email,'password':'erronea'},format='json')
            self.assertEqual(r.status_code,401)
        self.assertEqual(self.cliente_api.post('/api/auth/login/',{'email':self.aprobadora.email,'password':'erronea'},format='json').status_code,429)

    def test_auditoria_no_guarda_contrasenas_ni_consultas(self):
        self.cliente_api.post('/api/auth/login/',{'email':self.aprobadora.email,'password':'secreto-no-registrable'},format='json')
        eventos=list(AuditoriaSeguridad.objects.values())
        self.assertTrue(eventos)
        self.assertNotIn('secreto-no-registrable',str(eventos))
        self.assertNotIn(self.aprobadora.email,str(eventos))

    def test_auditoria_es_inmutable(self):
        self.entrar()
        self.cliente_api.post('/api/auth/logout/')
        with self.assertRaises(DatabaseError),transaction.atomic():
            AuditoriaSeguridad.objects.all().update(evento='borrado')

    def test_logout_conserva_al_usuario_que_cerro_la_sesion(self):
        from django.contrib.auth import get_user_model
        self.entrar()
        usuario=get_user_model().objects.get(username=self.aprobadora.email)
        self.cliente_api.post('/api/auth/logout/')
        evento=AuditoriaSeguridad.objects.filter(recurso='/api/auth/logout/').latest('id')
        self.assertEqual(evento.usuario_id,usuario.pk)

    def test_limite_compartido_rechaza_y_expira(self):
        self.assertTrue(admitir('prueba',1))
        self.assertFalse(admitir('prueba',1))
        with connection.cursor() as c:c.execute("UPDATE limites_acceso SET inicio = now()-interval '1 hour'")
        self.assertTrue(admitir('prueba',1))

    def test_payload_excesivo_es_rechazado_antes_del_parser(self):
        r=self.cliente_api.post('/api/auth/login/',data='{}',content_type='application/json',CONTENT_LENGTH=str(settings.DATA_UPLOAD_MAX_MEMORY_SIZE+1))
        self.assertEqual(r.status_code,413)

    def test_webhook_json_no_objeto_no_rompe_el_worker(self):
        import os,hmac,hashlib
        with patch.dict(os.environ,{'WHATSAPP_APP_SECRET':'prueba'}):
            firma=hmac.new(b'prueba',b'[]',hashlib.sha256).hexdigest()
            r=self.cliente_api.post('/webhook/whatsapp/',data='[]',content_type='application/json',HTTP_X_HUB_SIGNATURE_256='sha256='+firma)
        self.assertEqual(r.status_code,400)


@override_settings(MODO_DEMOSTRACION=True, DEBUG=True)
class ModoDemostracionTests(ApiTestCase):
    def test_demo_tampoco_pide_una_validacion_manual(self):
        contexto=contexto_automatico(self.conversacion)
        self.assertEqual(contexto.expira_en-contexto.creado_en,timedelta(hours=4))

    def test_demo_no_omite_roles(self):
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.post('/api/documentos/',{},format='json').status_code,403)

    def test_no_se_puede_habilitar_demo_en_produccion(self):
        import os,runpy
        from django.core.exceptions import ImproperlyConfigured
        with patch.dict(os.environ,{'MODO_DEMOSTRACION':'true','DJANGO_DEBUG':'false','DB_SSLMODE':'require','DJANGO_SECRET_KEY':'a1B2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0U1v2W3x4Y5z6'}):
            with self.assertRaisesMessage(ImproperlyConfigured,'MODO_DEMOSTRACION'):
                runpy.run_path(str(settings.BASE_DIR/'config/settings.py'))
