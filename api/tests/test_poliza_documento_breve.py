from django.test import override_settings
from datos import fabricas
from api.tests.base import ApiTestCase
from negocio.documentos import crear_documento, aprobar_documento
from negocio.coberturas import vincular_documento, responder_cobertura


@override_settings(BUSQUEDA_SEMANTICA=False)
class DocumentoBreveTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.poliza=fabricas.crear_poliza(self.cliente)
        self.doc=crear_documento(titulo='Plan básico',version='1',referencia='Ejemplo académico',
            contenido='Responsabilidad civil por daños ocasionados a terceros. No ampara robo ni incendio.',
            funcionario_id=self.aprobadora.id)
        aprobar_documento(self.doc.id,self.aprobadora.id)
        vincular_documento(self.poliza.numero_poliza,self.doc.id,self.aprobadora.id)

    def test_resumen_personal_lee_la_descripcion_breve_sin_modelo_ni_palabra_cobertura(self):
        for pregunta in ('¿Qué cubre mi póliza?', '¿Qué cobertura tengo?', '¿Cuál es mi cobertura?'):
            with self.subTest(pregunta=pregunta):
                texto,fuente=responder_cobertura(pregunta,self.conversacion)
                self.assertIsNotNone(fuente)
                self.assertIn('Responsabilidad civil',texto)
                self.assertIn('No ampara robo ni incendio',texto)

    def test_un_tema_ausente_sigue_sin_inventar_cobertura(self):
        texto,fuente=responder_cobertura('¿Mi póliza cubre daños por inundación?',self.conversacion)
        self.assertIsNone(fuente)

    def test_otro_cliente_no_usa_la_descripcion(self):
        self.contacto.cliente=fabricas.crear_cliente()
        self.contacto.save()
        self.conversacion.refresh_from_db()
        texto,fuente=responder_cobertura('¿Qué cubre mi póliza?',self.conversacion)
        self.assertIsNone(fuente)
        self.assertNotIn('Responsabilidad civil',texto)

    def test_descripcion_real_de_la_prueba_vinculada_contesta_y_no_inventa_granizo(self):
        from datos.models import FragmentoDocumento
        FragmentoDocumento.objects.filter(documento=self.doc).update(texto='La poliza basica solamente cubre responsabilidad civil. asegura hasta 100 millones de pesos ($100.000.000). no cubre granizo ni hurto')
        texto,fuente=responder_cobertura('que cubre mi póliza??',self.conversacion)
        self.assertIsNotNone(fuente)
        self.assertIn('no cubre granizo ni hurto',texto)
        texto,fuente=responder_cobertura('mi póliza cubre granizo?',self.conversacion)
        self.assertIsNotNone(fuente)
        self.assertIn('no cubre granizo ni hurto',texto)

    def test_diagnostico_distingue_documento_aprobado_de_documento_vinculado(self):
        from datos.models import DocumentoPoliza
        self.entrar()
        ruta=f'/api/polizas/{self.poliza.id}/diagnostico-bot/'
        self.assertTrue(self.cliente_api.get(ruta).json()['listo'])
        DocumentoPoliza.objects.filter(poliza=self.poliza).delete()
        resultado=self.cliente_api.get(ruta).json()
        self.assertFalse(resultado['listo'])
        self.assertIn('Falta vincular',resultado['problemas'][0])
        self.assertEqual(resultado['disponibles'][0]['id'],self.doc.id)
        respuesta=self.cliente_api.post(f'/api/polizas/{self.poliza.id}/documentos/',{'documento_id':self.doc.id},format='json')
        self.assertEqual(respuesta.status_code,200,respuesta.content)
        self.assertTrue(self.cliente_api.get(ruta).json()['listo'])

    def test_diagnostico_exige_sesion(self):
        self.assertError(self.cliente_api.get(f'/api/polizas/{self.poliza.id}/diagnostico-bot/'),401,'no_autenticado')

    def test_cargar_condiciones_en_poliza_alcanza_sin_vincular_documentos_a_mano(self):
        self.entrar()
        ruta=f'/api/polizas/{self.poliza.id}/condiciones/'
        r=self.cliente_api.patch(ruta,{'cubre':'Responsabilidad civil por daños a terceros.',
            'no_cubre':'Granizo ni hurto.','limites':'Hasta $100.000.000.','asistencia':'0800-000-0000'},format='json')
        self.assertEqual(r.status_code,200,r.content)
        for pregunta in ('¿Qué cubre mi póliza?', '¿Mi póliza cubre granizo?'):
            texto,fuente=responder_cobertura(pregunta,self.conversacion)
            self.assertIsNotNone(fuente)
            self.assertIn('Granizo ni hurto',texto)
        self.entrar(self.operador)
        self.assertError(self.cliente_api.patch(ruta,{'cubre':'Todo'},format='json'),403,'permiso_denegado')

    def guardar(self, **campos):
        self.entrar()
        datos={'cubre':'Responsabilidad civil por daños a terceros.',
               'no_cubre':'Granizo ni hurto.', 'limites':'Hasta $100.000.000.'}
        datos.update(campos)
        r=self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/',datos,format='json')
        self.assertEqual(r.status_code,200,r.content)
        return r

    def turno(self,pregunta):
        from negocio.bot.orquestador import procesar_mensaje
        from datos.models import Mensaje
        mensaje=fabricas.crear_mensaje(self.conversacion,texto=pregunta)
        with self.captureOnCommitCallbacks(execute=True):
            resultado=procesar_mensaje(mensaje.id)
        return resultado,Mensaje.objects.get(pk=resultado.mensaje_respuesta_id)

    def test_recorrido_whatsapp_simulado_contesta_cobertura_y_exclusion_sin_derivar(self):
        from datos.models import Derivacion
        self.guardar()
        for pregunta in ('¿Cubre granizo?', 'que cubre mi póliza??','qué póliza tengo y qué cubre',
                         '¿Mi seguro incluye daños por pedrisco?'):
            with self.subTest(pregunta=pregunta):
                r,m=self.turno(pregunta)
                self.assertFalse(r.retenido,r.alertas)
                self.assertEqual(r.tipo_consulta,'consulta_cobertura')
                self.assertEqual(m.estado_envio,'enviado')
                self.assertIn('Responsabilidad civil',m.texto)
                self.assertIn('Granizo ni hurto',m.texto)
                self.conversacion.refresh_from_db()
                self.assertEqual(self.conversacion.modo,'bot')
        self.assertFalse(Derivacion.objects.exists())

    def test_actualizar_reemplaza_solo_sus_condiciones_y_preserva_la_fuente_anterior(self):
        from datos.models import CondicionesPoliza,DocumentoGeneral
        self.guardar()
        anterior=CondicionesPoliza.objects.get(poliza=self.poliza).documento_id
        self.guardar(cubre='Responsabilidad civil y daños por incendio.',no_cubre='No cubre inundación.')
        actual=CondicionesPoliza.objects.get(poliza=self.poliza).documento_id
        self.assertNotEqual(anterior,actual)
        self.assertEqual(DocumentoGeneral.objects.get(pk=anterior).estado,'retirado')
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.estado,'aprobado')
        texto,fuente=responder_cobertura('¿Qué cubre mi póliza?',self.conversacion)
        self.assertIn('daños por incendio',texto)
        self.assertNotIn('No ampara robo ni incendio',texto)

    def test_condiciones_invalidas_no_retiran_la_version_vigente(self):
        from datos.models import CondicionesPoliza
        self.guardar()
        anterior=CondicionesPoliza.objects.get(poliza=self.poliza).documento
        r=self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/',{'cubre':' '},format='json')
        self.assertEqual(r.status_code,400)
        anterior.refresh_from_db()
        self.assertEqual(anterior.estado,'aprobado')
        self.assertEqual(CondicionesPoliza.objects.get(poliza=self.poliza).documento_id,anterior.id)

    def test_condiciones_de_otro_titular_no_se_filtran_al_chat(self):
        self.guardar()
        self.contacto.cliente=fabricas.crear_cliente()
        self.contacto.save()
        self.conversacion.refresh_from_db()
        r,m=self.turno(f'¿Qué cubre mi póliza {self.poliza.numero_poliza}?')
        self.assertNotIn('Responsabilidad civil',m.texto)
        self.assertEqual(m.estado_envio,'enviado')
        self.assertIn('No encuentro',m.texto)

    def test_siniestro_ocurrido_se_deriva_aunque_existan_condiciones(self):
        from datos.models import Derivacion
        self.guardar()
        r,m=self.turno('Me chocaron en la autopista, ¿me cubre mi póliza?')
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'humano')
        self.assertTrue(Derivacion.objects.exists())

    def test_listado_permite_buscar_compania_y_patente_y_exige_sesion(self):
        compania=fabricas.crear_compania(nombre='Compañía Ficticia del Sur')
        self.poliza.compania=compania
        self.poliza.vehiculo=fabricas.crear_vehiculo(self.cliente,patente='AB123CD')
        self.poliza.save()
        self.assertEqual(self.cliente_api.get('/api/polizas/').status_code,401)
        self.entrar(self.operador)
        for q in ('Ficticia','ab 123 cd'):
            r=self.cliente_api.get('/api/polizas/',{'q':q})
            self.assertEqual(r.status_code,200)
            self.assertEqual([p['id'] for p in r.json()['resultados']],[self.poliza.id])

    def test_asistencia_usa_telefono_de_esta_poliza_y_no_un_numero_generico(self):
        self.guardar(asistencia='0800-123-4567')
        r,m=self.turno('Necesito el número de la grúa')
        self.assertFalse(r.retenido,r.alertas)
        self.assertEqual(m.estado_envio,'enviado')
        self.assertIn('0800-123-4567',m.texto)

    def test_patch_parcial_no_borra_exclusiones_ni_telefono(self):
        from datos.models import CondicionesPoliza
        self.guardar(asistencia='0800-123-4567')
        r=self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/',{'limites':'Hasta $200.000.000.'},format='json')
        self.assertEqual(r.status_code,200,r.content)
        info=CondicionesPoliza.objects.get(poliza=self.poliza)
        self.assertEqual(info.asistencia,'0800-123-4567')
        self.assertEqual(info.no_cubre,'Granizo ni hurto.')

    def crear_plan(self, **campos):
        self.entrar()
        if not self.poliza.compania_id:
            self.poliza.compania=fabricas.crear_compania()
            self.poliza.save()
        datos={'compania_id':self.poliza.compania_id,'nombre':'Terceros completo','nivel':'intermedia',
            'cubre':'Responsabilidad civil y rotura de cristales.', 'no_cubre':'No cubre granizo.',
            'limites':'Hasta $100.000.000.', 'asistencia':'0800-123-4567'}
        datos.update(campos)
        r=self.cliente_api.post('/api/planes-cobertura/',datos,format='json')
        self.assertEqual(r.status_code,201,r.content)
        return r.json()

    def aplicar_plan(self, plan, poliza=None, **particulares):
        poliza=poliza or self.poliza
        r=self.cliente_api.patch(f'/api/polizas/{poliza.id}/condiciones/',
            {'plan_id':plan['id'],'plan_version':plan['version'],**particulares},format='json')
        self.assertEqual(r.status_code,200,r.content)
        return r.json()

    def test_plan_se_carga_una_vez_y_se_reutiliza_en_dos_vehiculos(self):
        from datos.models import CondicionesPoliza
        plan=self.crear_plan()
        self.aplicar_plan(plan,limites='Límite particular de $90.000.000.')
        otra=fabricas.crear_poliza(self.cliente,compania=self.poliza.compania)
        self.aplicar_plan(plan,otra)
        self.assertEqual(CondicionesPoliza.objects.filter(plan_id=plan['id']).count(),2)
        self.assertEqual(CondicionesPoliza.objects.get(poliza=otra).limites,plan['limites'])
        texto,fuente=responder_cobertura(f'¿Qué cubre mi póliza {self.poliza.numero_poliza}?',self.conversacion)
        self.assertIsNotNone(fuente)
        self.assertIn('$90.000.000',texto)
        self.assertNotIn('$100.000.000',texto)

    def test_actualizar_plan_no_cambia_la_copia_confirmada_de_un_cliente(self):
        from datos.models import CondicionesPoliza
        plan=self.crear_plan()
        self.aplicar_plan(plan)
        r=self.cliente_api.patch(f'/api/planes-cobertura/{plan["id"]}/',
            {'cubre':'Responsabilidad civil, cristales y granizo.','no_cubre':'No cubre inundación.'},format='json')
        self.assertEqual(r.status_code,200,r.content)
        nuevo=r.json()
        self.assertEqual(nuevo['version'],2)
        self.assertEqual(CondicionesPoliza.objects.get(poliza=self.poliza).plan_version,1)
        texto,fuente=responder_cobertura('¿Qué cubre mi póliza?',self.conversacion)
        self.assertIn('No cubre granizo',texto)
        self.aplicar_plan(nuevo)
        texto,fuente=responder_cobertura('¿Qué cubre mi póliza?',self.conversacion)
        self.assertIn('cristales y granizo',texto)
        self.assertNotIn('No cubre granizo',texto)

    def test_no_se_aplica_un_plan_de_otra_compania_ni_un_plan_inactivo(self):
        plan=self.crear_plan()
        otra=fabricas.crear_poliza(self.cliente,compania=fabricas.crear_compania())
        r=self.cliente_api.patch(f'/api/polizas/{otra.id}/condiciones/',{'plan_id':plan['id']},format='json')
        self.assertEqual(r.status_code,400,r.content)
        self.cliente_api.patch(f'/api/planes-cobertura/{plan["id"]}/',{'activo':False},format='json')
        r=self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/',{'plan_id':plan['id']},format='json')
        self.assertEqual(r.status_code,400,r.content)

    def test_plan_editado_mientras_se_lo_elegia_exige_revisar_version(self):
        plan=self.crear_plan()
        self.cliente_api.patch(f'/api/planes-cobertura/{plan["id"]}/',{'limites':'Hasta $200.000.000.'},format='json')
        r=self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/',
            {'plan_id':plan['id'],'plan_version':plan['version']},format='json')
        self.assertEqual(r.status_code,400,r.content)

    def test_operador_consulta_planes_pero_no_los_crea_ni_modifica(self):
        plan=self.crear_plan()
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.get('/api/planes-cobertura/').status_code,200)
        self.assertEqual(self.cliente_api.post('/api/planes-cobertura/',plan,format='json').status_code,403)
        self.assertEqual(self.cliente_api.patch(f'/api/planes-cobertura/{plan["id"]}/',{'cubre':'Todo'},format='json').status_code,403)

    def test_consulta_de_cobertura_puede_interrumpir_una_cotizacion_sin_derivar(self):
        self.guardar()
        r,m=self.turno('Cuánto sale asegurar otro auto')
        r,m=self.turno('¿Qué cubre mi póliza?')
        self.assertEqual(r.tipo_consulta,'consulta_cobertura')
        self.assertIn('Responsabilidad civil',m.texto)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'bot')

    def test_selecciona_moto_por_patente_entre_varios_vehiculos(self):
        self.guardar()
        self.poliza.vehiculo=fabricas.crear_vehiculo(self.cliente,clase='moto',patente='A123BCD')
        self.poliza.save()
        fabricas.crear_poliza(self.cliente,vehiculo=fabricas.crear_vehiculo(self.cliente,clase='auto'))
        r,m=self.turno('¿Qué cubre mi póliza?')
        self.assertIn('varias pólizas',m.texto)
        r,m=self.turno('A123BCD')
        self.assertIn(self.poliza.numero_poliza,m.texto)
        self.assertIn('Responsabilidad civil',m.texto)
        self.assertFalse(r.retenido,r.alertas)
