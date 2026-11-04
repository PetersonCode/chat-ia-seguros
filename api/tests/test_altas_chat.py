from datetime import timedelta
from unittest.mock import patch
from django.utils import timezone
from datos import fabricas
from datos.models import AccionPendiente, BorradorPoliza, Cliente, Mensaje, Poliza, Vehiculo
from api.tests.base import ApiTestCase
from negocio.bot.orquestador import procesar_mensaje
from negocio.acciones import aprobar_accion, finalizar_gestion_externa, solicitar_accion
from negocio.errores import EstadoInvalido


class AltasChatTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.compania = fabricas.crear_compania(comision_pct='10')

    def turno(self, texto):
        mensaje = fabricas.crear_mensaje(self.conversacion, texto=texto)
        with self.captureOnCommitCallbacks(execute=True):
            resultado = procesar_mensaje(mensaje.id)
        self.assertFalse(resultado.retenido)
        return resultado

    def datos(self, **extra):
        hoy = timezone.localdate()
        campos = {'Patente': 'AB123CD', 'Marca': 'Toyota', 'Modelo': 'Hilux', 'Año': '2022',
            'Clase': 'camioneta', 'Uso': 'particular', 'Chasis': 'VIN-NUEVA-904',
            'Valor asegurado': '25000000', 'Compañía': str(self.compania.id), 'Cobertura': 'total',
            'Inicio': hoy.isoformat(), 'Fin': (hoy+timedelta(days=180)).isoformat()}
        campos.update(extra)
        return '\n'.join(f'{k}: {v}' for k,v in campos.items())

    def preparar(self, **extra):
        self.turno('Quiero contratar un seguro para mi auto')
        self.turno(self.datos(**extra))
        self.assertTrue(AccionPendiente.objects.filter(tipo_accion='alta_poliza').exists(),
                        list(BorradorPoliza.objects.values('campo','respuesta')))
        return AccionPendiente.objects.get(tipo_accion='alta_poliza')

    def test_bot_prepara_sin_emitir_y_humano_ingresa_prima_y_confirma_con_aviso(self):
        accion = self.preparar(Prima='1', Comision='100')
        self.assertNotIn('prima_mensual', accion.parametros)
        self.assertNotIn('comision_pct', accion.parametros)
        self.assertFalse(Poliza.objects.exists())
        self.assertFalse(Vehiculo.objects.exists())
        self.entrar()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta = self.cliente_api.post(f'/api/acciones/{accion.id}/aprobar/',
                {'prima_mensual': '48000'}, format='json')
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        accion.refresh_from_db()
        self.assertEqual(accion.estado, 'ejecutada')
        self.assertEqual(accion.poliza.prima_mensual, 48000)
        self.assertEqual(accion.poliza.comision_pct, 10)
        self.assertEqual(accion.poliza.cuotas.count(), 6)
        aviso = Mensaje.objects.get(payload__accion_id=accion.id)
        self.assertEqual(aviso.estado_envio, 'enviado')
        self.assertIn(accion.poliza.numero_poliza, aviso.texto)
        self.assertIn('aprobada y procesada', aviso.texto)
        with self.assertRaises(EstadoInvalido):
            aprobar_accion(accion.id, self.aprobadora.id, prima_mensual='48000')
        self.assertEqual(Mensaje.objects.filter(payload__accion_id=accion.id).count(), 1)

    def test_faltan_prima_y_permiso_no_se_crea_nada_y_todo_sigue_pendiente(self):
        accion = self.preparar()
        self.entrar(self.operador)
        ruta=f'/api/acciones/{accion.id}/aprobar/'
        self.assertError(self.cliente_api.post(ruta, {'prima_mensual':'1'}, format='json'),403,'permiso_denegado')
        self.entrar()
        self.assertError(self.cliente_api.post(ruta, {}, format='json'),400,'parametros_incompletos')
        for importe in ['NaN','-1','10.123']:
            self.assertError(self.cliente_api.post(ruta, {'prima_mensual':importe}, format='json'),400,'datos_invalidos')
        self.assertFalse(Poliza.objects.exists())
        accion.refresh_from_db()
        self.assertEqual(accion.estado,'pendiente')

    def test_cliente_nuevo_y_poliza_se_crean_juntos_solo_al_confirmar(self):
        self.contacto.cliente=None
        self.contacto.save(update_fields=['cliente'])
        self.conversacion.refresh_from_db()
        accion = self.preparar(**{'Nombre y apellido':'Ana Pérez','DNI':'31444777'})
        self.assertFalse(Cliente.objects.filter(dni='31444777').exists())
        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id,self.aprobadora.id,prima_mensual='50000')
        cliente=Cliente.objects.get(dni='31444777')
        self.contacto.refresh_from_db()
        self.assertEqual(self.contacto.cliente_id,cliente.id)
        self.assertEqual(Poliza.objects.get().cliente_id,cliente.id)

    def test_error_de_poliza_revierte_cliente_y_vehiculo_y_no_envia_confirmacion(self):
        self.contacto.cliente=None
        self.contacto.save(update_fields=['cliente'])
        self.conversacion.refresh_from_db()
        accion=self.preparar(**{'Nombre y apellido':'Ana Pérez','DNI':'31444777'})
        self.compania.activa=False
        self.compania.save(update_fields=['activa'])
        self.entrar()
        respuesta=self.cliente_api.post(f'/api/acciones/{accion.id}/aprobar/',{'prima_mensual':'50000'},format='json')
        self.assertEqual(respuesta.status_code,400,respuesta.content)
        self.assertFalse(Cliente.objects.filter(dni='31444777').exists())
        self.assertFalse(Vehiculo.objects.exists())
        self.assertFalse(Mensaje.objects.filter(payload__accion_id=accion.id).exists())

    def test_recopila_turnos_valida_y_siniestro_interrumpe_la_recoleccion(self):
        self.turno('Quiero asegurar mi camioneta')
        self.turno('patente mal')
        borrador=BorradorPoliza.objects.get()
        self.assertNotIn('patente',borrador.datos)
        self.turno('AB123CD')
        self.turno('Toyota')
        borrador.refresh_from_db()
        self.assertEqual(borrador.datos['marca'],'Toyota')
        resultado=self.turno('me chocaron en la autopista')
        self.assertEqual(resultado.tipo_consulta,'siniestro_urgente')
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'humano')
        self.assertFalse(AccionPendiente.objects.exists())

    def test_vehiculo_propio_ya_cargado_no_pide_otra_vez_sus_datos(self):
        v=fabricas.crear_vehiculo(self.cliente,patente='AB123CD')
        self.turno('Quiero contratar un seguro')
        self.turno('AB123CD')
        borrador=BorradorPoliza.objects.get()
        self.assertEqual(borrador.campo,'compania_id')
        self.assertEqual(borrador.datos['modelo'],v.modelo)

    def test_otra_consulta_no_se_guarda_como_marca_y_una_repeticion_no_duplica(self):
        fabricas.crear_poliza(self.cliente)
        self.turno('Quiero asegurar mi camioneta')
        self.turno('AB123CD')
        self.turno('cuanto debo')
        borrador=BorradorPoliza.objects.get()
        self.assertNotIn('marca',borrador.datos)
        resultado=self.turno(self.datos())
        accion=AccionPendiente.objects.get(tipo_accion='alta_poliza')
        entrada=Mensaje.objects.filter(direccion='entrante').latest('id')
        self.assertTrue(procesar_mensaje(entrada.id).ignorado)
        self.assertEqual(AccionPendiente.objects.filter(tipo_accion='alta_poliza').count(),1)

    def test_rechazo_no_crea_la_poliza_y_notifica_una_sola_vez(self):
        accion=self.preparar()
        self.entrar()
        with self.captureOnCommitCallbacks(execute=True):
            respuesta=self.cliente_api.post(f'/api/acciones/{accion.id}/rechazar/',
                {'motivo':'Solicitud ficticia rechazada'},format='json')
        self.assertEqual(respuesta.status_code,200,respuesta.content)
        self.assertFalse(Poliza.objects.exists())
        aviso=Mensaje.objects.get(payload__accion_id=accion.id)
        self.assertEqual(aviso.estado_envio,'enviado')
        self.assertEqual(aviso.payload['resolucion_accion'],'rechazada')

    def test_la_falla_de_envio_no_pierde_el_aviso_ni_la_accion(self):
        accion=self.preparar()
        with patch('negocio.acciones.enviar_pendientes',side_effect=OSError('sin red')):
            with self.captureOnCommitCallbacks(execute=True):
                aprobar_accion(accion.id,self.aprobadora.id,prima_mensual='48000')
        accion.refresh_from_db()
        self.assertEqual(accion.estado,'ejecutada')
        self.assertEqual(Mensaje.objects.get(payload__accion_id=accion.id).estado_envio,'pendiente_envio')

    def test_si_la_ventana_cierra_aviso_queda_pendiente_sin_afirmar_entrega(self):
        accion=self.preparar()
        self.conversacion.ultimo_mensaje_cliente_en=timezone.now()-timedelta(days=2)
        self.conversacion.save(update_fields=['ultimo_mensaje_cliente_en'])
        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id,self.aprobadora.id,prima_mensual='48000')
        aviso=Mensaje.objects.get(payload__accion_id=accion.id)
        self.assertEqual(aviso.estado_envio,'fallido')
        self.assertEqual(aviso.error,'ventana_24h_cerrada')
        self.conversacion.ultimo_mensaje_cliente_en=timezone.now()
        self.conversacion.save(update_fields=['ultimo_mensaje_cliente_en'])
        from negocio.whatsapp import enviar_pendientes
        self.assertEqual(enviar_pendientes(self.conversacion.id),1)
        aviso.refresh_from_db()
        self.assertEqual(aviso.estado_envio,'enviado')

    def test_una_gestion_externa_avisa_al_finalizar_sin_dar_por_hecho_un_pago(self):
        consulta=fabricas.crear_consulta(self.conversacion)
        accion=solicitar_accion(consulta.id,'reembolso',parametros={'importe':'1000'})
        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id,self.aprobadora.id)
        with self.captureOnCommitCallbacks(execute=True):
            finalizar_gestion_externa(accion.id,self.aprobadora.id,referencia='DEMO-904',motivo='Gestión externa ficticia realizada')
        self.assertEqual(Mensaje.objects.filter(payload__accion_id=accion.id).count(),2)
        self.assertTrue(Mensaje.objects.filter(payload__accion_id=accion.id,payload__resolucion_accion='ejecutada').exists())
