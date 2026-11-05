from api.tests.base import ApiTestCase
from datos import fabricas
from django.utils import timezone

class BandejaContactosTests(ApiTestCase):
    def lista(self, vista='atencion'):
        self.entrar()
        r=self.cliente_api.get('/api/conversaciones/',{'agrupada':'1','vista':vista})
        self.assertEqual(r.status_code,200,r.content)
        return r.json()

    def test_bot_no_infla_pendientes_y_una_tarjeta_por_contacto(self):
        c=self.conversacion
        c.estado='cerrada';c.cerrada_en=timezone.now();c.save()
        actual=fabricas.crear_conversacion(self.contacto)
        for _ in range(4):fabricas.crear_consulta(actual)
        fabricas.crear_mensaje(actual,texto='Hola')
        self.assertEqual(self.lista()['clientes']['atencion'],0)
        d=self.lista('todas');self.assertEqual(d['total'],1)
        self.assertEqual(d['resultados'][0]['id'],actual.id)

    def test_humano_sale_de_pendientes_al_responder(self):
        c=self.conversacion;c.modo='humano';c.funcionario=self.operador;c.save()
        fabricas.crear_mensaje(c,emisor='cliente')
        self.assertEqual(self.lista()['total'],1)
        fabricas.crear_mensaje(c,emisor='funcionario',funcionario=self.operador,direccion='saliente',estado_envio='enviado')
        self.assertEqual(self.lista()['total'],0)
        self.assertEqual(self.lista('esperando')['total'],1)

    def test_derivaciones_repetidas_cuentan_un_cliente(self):
        c=self.conversacion
        for _ in range(3):fabricas.crear_derivacion(fabricas.crear_consulta(c),self.operador)
        fabricas.crear_mensaje(c,emisor='cliente')
        self.assertEqual(self.lista()['clientes']['atencion'],1)
        self.assertEqual(self.lista()['total'],1)

    def test_cerradas_no_se_cuentan_como_trabajo_pendiente(self):
        c=self.conversacion;c.estado='cerrada';c.cerrada_en=timezone.now();c.save()
        fabricas.crear_derivacion(fabricas.crear_consulta(c),self.operador)
        fabricas.crear_mensaje(c,emisor='cliente')
        self.assertEqual(self.lista()['total'],0)
        self.assertEqual(self.lista('resueltas')['total'],1)

    def test_acuse_del_bot_no_oculta_una_derivacion_sin_atender(self):
        c=self.conversacion
        fabricas.crear_derivacion(fabricas.crear_consulta(c),self.operador)
        fabricas.crear_mensaje(c,emisor='bot',direccion='saliente',estado_envio='enviado')
        self.assertEqual(self.lista()['total'],1)

    def test_recordatorio_y_envio_fallido_no_ocultan_al_cliente_pendiente(self):
        c=self.conversacion;c.modo='humano';c.funcionario=self.operador;c.save()
        fabricas.crear_mensaje(c,emisor='cliente')
        recordatorio=fabricas.crear_mensaje(c,emisor='funcionario',funcionario=self.operador,
            direccion='saliente',estado_envio='enviado')
        recordatorio.payload={'recordatorio_poliza_id':1};recordatorio.save(update_fields=['payload'])
        self.assertEqual(self.lista()['total'],1)
        fabricas.crear_mensaje(c,emisor='funcionario',funcionario=self.operador,
            direccion='saliente',estado_envio='fallido')
        self.assertEqual(self.lista()['total'],1)
        aviso=fabricas.crear_mensaje(c,emisor='bot',direccion='saliente',estado_envio='enviado')
        aviso.payload={'aviso_gestion_id':1};aviso.save(update_fields=['payload'])
        self.assertEqual(self.lista()['total'],1)
