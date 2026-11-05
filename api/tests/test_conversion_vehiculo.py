from api.tests.test_interesados import BaseInteresadosApi
from datos.models import Vehiculo
from datos import fabricas
from negocio.interesados import convertir_en_cliente
from negocio.errores import DatosInvalidos

class ConversionVehiculoTests(BaseInteresadosApi):
    def test_convertir_guarda_vehiculo_y_reintentar_no_duplica(self):
        i=self.en_documentacion(telefono='1155550881',datos={'patente':'AE433ZZ','marca':'Toyota','modelo':'Corolla','anio':2020,'uso':'particular'})
        i=convertir_en_cliente(i.id,self.aprobadora.id,'49999881','Mateo','Prueba')
        self.assertEqual(Vehiculo.objects.get(patente='AE433ZZ').cliente_id,i.cliente_id)
        convertir_en_cliente(i.id,self.aprobadora.id,'49999881','Mateo','Prueba')
        self.assertEqual(Vehiculo.objects.filter(patente='AE433ZZ').count(),1)

    def test_patente_ajena_impide_conversion_sin_reasignar(self):
        from negocio.vehiculos import alta_vehiculo
        otro=fabricas.crear_cliente()
        v=alta_vehiculo(otro.id,'AE433ZZ','Toyota','Corolla',2020,funcionario_id=self.aprobadora.id)
        i=self.en_documentacion(telefono='1155550882',datos={'patente':'AE433ZZ','marca':'Toyota','modelo':'Corolla','anio':2020,'uso':'particular'})
        with self.assertRaises(DatosInvalidos):convertir_en_cliente(i.id,self.aprobadora.id,'49999882','Mateo','Prueba')
        i.refresh_from_db();v.refresh_from_db()
        self.assertIsNone(i.cliente_id)
        self.assertEqual(v.cliente_id,otro.id)


class RegistrarCotizacionElegidaTests(BaseInteresadosApi):
    def preparar(self):
        from negocio.cotizaciones import cargar_cotizacion,elegir_cotizacion
        i=self.en_documentacion(telefono='1155550883',datos={'patente':'AF512ZZ','marca':'Toyota','modelo':'Etios','anio':2021,'uso':'particular'})
        i=convertir_en_cliente(i.id,self.aprobadora.id,'49999883','Valentina','Prueba')
        c=cargar_cotizacion(self.aprobadora.id,fabricas.crear_compania().id,'intermedia','142000.00',interesado_id=i.id)
        elegir_cotizacion(c.id,self.aprobadora.id)
        return i,c

    def test_registra_opcion_elegida_y_no_duplica(self):
        from datos.models import Poliza
        from django.utils import timezone
        from datetime import timedelta
        i,c=self.preparar();self.entrar()
        d={'fecha_inicio':str(timezone.localdate()),'fecha_vencimiento':str(timezone.localdate()+timedelta(days=365))}
        ruta=f'/api/interesados/{i.id}/registrar-poliza/'
        r=self.cliente_api.post(ruta,d,format='json');self.assertEqual(r.status_code,201,r.content)
        i.refresh_from_db();self.assertEqual(i.estado,'emitida')
        p=Poliza.objects.get(cliente=i.cliente)
        self.assertEqual(p.compania_id,c.compania_id);self.assertEqual(p.prima_mensual,c.prima_mensual)
        self.assertEqual(p.vehiculo.patente,'AF512ZZ')
        self.assertEqual(self.cliente_api.post(ruta,d,format='json').status_code,409)
        self.assertEqual(Poliza.objects.filter(cliente=i.cliente).count(),1)

    def test_operador_no_confirma_y_fechas_invalidas_no_crean_poliza(self):
        from datos.models import Poliza
        i,c=self.preparar();ruta=f'/api/interesados/{i.id}/registrar-poliza/'
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.post(ruta,{},format='json').status_code,403)
        self.entrar();self.assertEqual(self.cliente_api.post(ruta,{},format='json').status_code,400)
        self.assertFalse(Poliza.objects.filter(cliente=i.cliente).exists())

    def test_registro_desde_interesado_copia_plan_y_lo_hace_consultable(self):
        from datos.models import Poliza, CondicionesPoliza
        from django.utils import timezone
        from datetime import timedelta
        i,c=self.preparar();self.entrar()
        plan=self.cliente_api.post('/api/planes-cobertura/', {'compania_id':c.compania_id,
            'nombre':'Terceros completo', 'nivel':'intermedia', 'cubre':'Cristales y robo total.',
            'asistencia':'0800-123-4567'},format='json').json()
        ruta=f'/api/interesados/{i.id}/registrar-poliza/'
        d={'fecha_inicio':str(timezone.localdate()),'fecha_vencimiento':str(timezone.localdate()+timedelta(days=365))}
        self.assertEqual(self.cliente_api.post(ruta,d,format='json').status_code,400)
        self.assertFalse(Poliza.objects.filter(cliente=i.cliente).exists())
        d.update(plan_id=plan['id'],plan_version=plan['version'])
        r=self.cliente_api.post(ruta,d,format='json');self.assertEqual(r.status_code,201,r.content)
        p=Poliza.objects.get(cliente=i.cliente);info=CondicionesPoliza.objects.get(poliza=p)
        self.assertEqual(info.plan_id,plan['id']);self.assertEqual(info.cubre,'Cristales y robo total.')
        self.assertEqual(info.documento.estado,'aprobado');self.assertGreater(p.cuotas.count(),0)
        i.refresh_from_db();self.assertEqual(i.estado,'emitida')

    def test_plan_incompatible_revierte_poliza_cuotas_y_etapa(self):
        from datos.models import Poliza
        from django.utils import timezone
        from datetime import timedelta
        i,c=self.preparar();self.entrar()
        plan=self.cliente_api.post('/api/planes-cobertura/', {'compania_id':c.compania_id,
            'nombre':'Total', 'nivel':'total', 'cubre':'Todo riesgo.'},format='json').json()
        d={'fecha_inicio':str(timezone.localdate()),'fecha_vencimiento':str(timezone.localdate()+timedelta(days=365)),
           'plan_id':plan['id'],'plan_version':plan['version']}
        r=self.cliente_api.post(f'/api/interesados/{i.id}/registrar-poliza/',d,format='json')
        self.assertEqual(r.status_code,400,r.content)
        self.assertFalse(Poliza.objects.filter(cliente=i.cliente).exists())
        i.refresh_from_db();self.assertEqual(i.estado,'documentacion')

    def test_editar_vehiculo_en_cartera_se_reutiliza_al_emitir_sin_duplicarlo(self):
        from negocio.vehiculos import modificar_vehiculo
        from datos.models import Poliza
        from django.utils import timezone
        from datetime import timedelta
        i,c=self.preparar();self.entrar()
        vehiculo_id=i.vehiculo_id
        modificar_vehiculo(vehiculo_id,funcionario_id=self.aprobadora.id,
            patente='AF513ZZ',modelo='Etios actualizado',clase='moto',chasis='DEMO1234')
        d=self.cliente_api.get(f'/api/interesados/{i.id}/').json()
        self.assertEqual(d['datos']['patente'],'AF513ZZ')
        self.assertEqual(d['datos']['clase'],'moto')
        r=self.cliente_api.patch(f'/api/interesados/{i.id}/',{'datos':{'modelo':'Etios definitivo'}},format='json')
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(Vehiculo.objects.get(pk=vehiculo_id).modelo,'Etios definitivo')
        r=self.cliente_api.post(f'/api/interesados/{i.id}/registrar-poliza/',{
            'fecha_inicio':str(timezone.localdate()),'fecha_vencimiento':str(timezone.localdate()+timedelta(days=180))},format='json')
        self.assertEqual(r.status_code,201,r.content)
        i.refresh_from_db();p=Poliza.objects.get(pk=i.poliza_registrada_id)
        self.assertEqual(p.vehiculo_id,vehiculo_id)
        self.assertEqual(Vehiculo.objects.filter(cliente=i.cliente).count(),1)
        self.assertEqual(self.cliente_api.patch(f'/api/interesados/{i.id}/',{'datos':{'marca':'Otra'}},format='json').status_code,409)
        self.assertEqual(self.cliente_api.post('/api/cotizaciones/',{'interesado_id':i.id,
            'compania_id':c.compania_id,'cobertura':'basica','prima_mensual':'10000'},format='json').status_code,409)

    def test_vincular_contrato_existente_exige_titular_vehiculo_y_aprobador(self):
        from datos.models import Poliza
        i,c=self.preparar();ruta=f'/api/interesados/{i.id}/vincular-poliza/'
        propio=fabricas.crear_poliza(i.cliente,vehiculo=i.vehiculo,compania=c.compania)
        ajeno=fabricas.crear_poliza(fabricas.crear_cliente())
        otro_vehiculo=fabricas.crear_poliza(i.cliente,vehiculo=fabricas.crear_vehiculo(i.cliente),compania=c.compania)
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.post(ruta,{'poliza_id':propio.id},format='json').status_code,403)
        self.entrar()
        for p in (ajeno,otro_vehiculo):
            self.assertEqual(self.cliente_api.post(ruta,{'poliza_id':p.id},format='json').status_code,400)
        cantidad=Poliza.objects.count()
        r=self.cliente_api.post(ruta,{'poliza_id':propio.id},format='json')
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(r.json()['poliza_registrada_id'],propio.id)
        self.assertEqual(r.json()['estado'],'emitida')
        self.assertEqual(Poliza.objects.count(),cantidad)
        self.assertEqual(self.cliente_api.post(ruta,{'poliza_id':propio.id},format='json').status_code,409)
