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
