"""Alta de póliza por chat escribiendo como escribe la gente (simulación de 20 interesados).

La meta: la IA junta todos los datos y deja una acción lista, para que el
asesor solo ingrese la prima y confirme o rechace.
"""
from datetime import date

from django.test import override_settings
from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import AccionPendiente, BorradorPoliza, CondicionesPoliza, Mensaje, PlanCobertura
from negocio.acciones import aprobar_accion
from negocio.bot.orquestador import procesar_mensaje


@override_settings(BUSQUEDA_SEMANTICA=False)
class AltaPorChatNaturalTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.compania = fabricas.crear_compania(nombre="Pampa Protección Seguros", comision_pct="12")
        for nivel, nombre in (("basica", "Responsabilidad Civil"), ("intermedia", "Terceros Completo"),
                              ("total", "Todo Riesgo con franquicia")):
            PlanCobertura.objects.create(compania=self.compania, nombre=nombre, nivel=nivel,
                                         cubre=f"Cobertura {nombre}.", asistencia="0800-555-0303",
                                         actualizado_por=self.aprobadora)
        # Un interesado: el número todavía no es de ningún cliente.
        self.contacto.cliente = None
        self.contacto.save(update_fields=["cliente"])
        self.conversacion.refresh_from_db()

    def turno(self, texto):
        mensaje = fabricas.crear_mensaje(self.conversacion, texto=texto)
        with self.captureOnCommitCallbacks(execute=True):
            resultado = procesar_mensaje(mensaje.id)
        return Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).texto

    def charla_completa(self):
        for texto in ("QUIERO SACAR SEGURO PARA MI AUTO", "carla ibañez 38999310", "ab 345 cd",
                      "chevrolet onix", "es del 2020", "particular", "no lo tengo", "ni idea",
                      "Pampa", "todo riesgo"):
            self.turno(texto)
        return self.turno("hoy")

    def test_una_charla_natural_deja_la_accion_lista_y_prolija(self):
        cierre = self.charla_completa()

        self.assertIn("Preparé tu solicitud (Todo Riesgo con franquicia)", cierre)
        p = AccionPendiente.objects.get(tipo_accion="alta_poliza").parametros
        hoy = timezone.localdate()
        self.assertEqual((p["nombre"], p["apellido"], p["dni"]), ("Carla", "Ibañez", "38999310"))
        self.assertEqual((p["patente"], p["marca"], p["modelo"], p["anio"]), ("AB345CD", "Chevrolet", "Onix", 2020))
        self.assertEqual((p["clase"], p["uso"]), ("auto", "particular"))  # la clase salió del primer mensaje
        self.assertIsNone(p["chasis"])
        self.assertIsNone(p["valor_asegurado"])
        self.assertEqual(p["compania_id"], self.compania.id)
        self.assertEqual((p["plan_nombre"], p["cobertura"]), ("Todo Riesgo con franquicia", "total"))
        self.assertEqual(p["fecha_inicio"], hoy.isoformat())
        self.assertEqual(p["fecha_vencimiento"], date(hoy.year + 1, hoy.month, hoy.day).isoformat())
        self.assertFalse(any(k.startswith("_") for k in p))

    def test_al_aprobar_la_poliza_queda_con_las_condiciones_del_plan(self):
        self.charla_completa()
        accion = AccionPendiente.objects.get(tipo_accion="alta_poliza")

        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id, self.aprobadora.id, prima_mensual="95000")

        accion.refresh_from_db()
        condiciones = CondicionesPoliza.objects.get(poliza=accion.poliza)
        self.assertEqual(condiciones.plan.nombre, "Todo Riesgo con franquicia")
        self.assertEqual(accion.poliza.cobertura, "total")
        self.assertEqual(condiciones.documento.estado, "aprobado")

    def test_plan_cambiado_no_reemplaza_la_oferta_pendiente_del_chat(self):
        self.charla_completa()
        accion = AccionPendiente.objects.get(tipo_accion='alta_poliza')
        plan = PlanCobertura.objects.get(pk=accion.parametros['plan_id'])
        nombre, cubre, version = plan.nombre, plan.cubre, plan.version
        plan.nombre='Catálogo nuevo'; plan.cubre='Otras condiciones'; plan.nivel='basica'; plan.version += 1
        plan.save()
        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id, self.aprobadora.id, prima_mensual='95000')
        accion.refresh_from_db()
        condiciones = CondicionesPoliza.objects.get(poliza=accion.poliza)
        self.assertEqual((condiciones.nombre_plan_confirmado, condiciones.cubre, condiciones.plan_version), (nombre,cubre,version))
        self.assertEqual(accion.poliza.cobertura, 'total')

    def test_duda_durante_el_alta_no_inventa_granizo_para_todo_terceros(self):
        from negocio.bot.alta_poliza import _respuesta_a_una_duda, _elegir_plan
        borrador = BorradorPoliza(conversacion=self.conversacion, campo='fecha_inicio',datos={'compania_id':self.compania.id})
        plan = PlanCobertura.objects.get(compania=self.compania,nivel='intermedia')
        plan.no_cubre='Granizo excluido.';plan.save()
        _elegir_plan('terceros completo',borrador.datos)
        texto = _respuesta_a_una_duda('¿Qué cubre este plan?',borrador)
        self.assertIn('Granizo excluido.', texto)
        self.assertNotIn('suma robo, incendio, granizo',texto)

    def test_limites_del_catalogo_no_provocan_derivacion_por_monto_inventado(self):
        plan=PlanCobertura.objects.get(compania=self.compania,nivel='total')
        plan.limites='Cristales hasta $300.000.';plan.save()
        for texto in ('Quiero asegurar mi auto','Carla Ibáñez 38999310','AB345CD','Chevrolet Onix','2020',
                      'particular','no sé','no sé','Pampa','todo riesgo'):
            self.turno(texto)
        respuesta=self.turno('¿Qué cubre el plan?')
        self.assertIn('$300.000',respuesta)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo,'bot')
        self.assertFalse(Mensaje.objects.filter(estado_envio='retenido').exists())

    def test_aprobar_el_alta_cierra_la_propuesta_del_mismo_vehiculo(self):
        from datos.models import Interesado
        interesado=fabricas.crear_interesado(contacto=self.contacto,datos={'patente':'AB345CD'},estado='cotizando')
        self.charla_completa()
        accion=AccionPendiente.objects.get(tipo_accion='alta_poliza')
        with self.captureOnCommitCallbacks(execute=True):
            aprobar_accion(accion.id,self.aprobadora.id,prima_mensual='95000')
        accion.refresh_from_db();interesado.refresh_from_db()
        self.assertEqual(interesado.estado,'emitida')
        self.assertEqual(interesado.poliza_registrada_id,accion.poliza_id)
        self.assertEqual(interesado.cliente_id,accion.poliza.cliente_id)
        self.assertEqual(interesado.vehiculo_id,accion.poliza.vehiculo_id)

    def test_todo_en_el_primer_mensaje_no_se_vuelve_a_preguntar(self):
        self.turno("buenas! quiero contratar un seguro para mi auto. Soy Laura Méndez, DNI 36222302, "
                   "patente AF234GH, Chevrolet Onix 2020")
        datos = BorradorPoliza.objects.get().datos
        self.assertEqual((datos["nombre"], datos["apellido"], datos["dni"]), ("Laura", "Méndez", "36222302"))
        self.assertEqual((datos["patente"], datos["marca"], datos["modelo"], datos["anio"]),
                         ("AF234GH", "Chevrolet", "Onix", 2020))

    def test_el_alta_reutiliza_identidad_y_datos_de_la_propuesta(self):
        fabricas.crear_interesado(contacto=self.contacto,nombre='Laura',apellido='Méndez',
            datos={'dni':'36222302','patente':'AF234GH','marca':'Chevrolet','modelo':'Onix',
                   'anio':2020,'uso':'particular','clase':'auto','chasis':'DEMOXYZ1234','valor_asegurado':'2000000'})
        respuesta=self.turno('quiero contratar el seguro para mi auto')
        self.assertIn('compañía',respuesta)
        borrador=BorradorPoliza.objects.get().datos
        self.assertEqual((borrador['nombre'],borrador['apellido'],borrador['dni']),('Laura','Méndez','36222302'))
        self.assertEqual(borrador['chasis'],'DEMOXYZ1234')

    def test_una_pregunta_en_el_medio_se_contesta_sin_abandonar_el_alta(self):
        self.turno("quiero asegurar mi auto")
        respuesta = self.turno("y cuanto me va a salir por mes?")
        self.assertIn("lo calcula el asesor", respuesta)
        self.assertIn("nombre y apellido", respuesta)
        respuesta = self.turno("que diferencia hay entre los planes?")
        self.assertIn("condiciones cargadas", respuesta)
        self.assertNotIn("Para registrarte", respuesta)
        self.assertTrue(BorradorPoliza.objects.get().activo)

    def test_arrepentirse_cancela(self):
        self.turno("quiero asegurar mi auto")
        self.turno("Diego Ponce")
        respuesta = self.turno("mejor lo pienso y despues les escribo")
        self.assertIn("cancelé la solicitud", respuesta)
        self.assertFalse(BorradorPoliza.objects.get().activo)
        self.assertFalse(AccionPendiente.objects.exists())

    def test_nombre_con_rotulo_no_duplica_el_apellido(self):
        self.turno("hola quiero contratar un seguro")
        self.turno("Nombre: Andrés Molina; DNI: 31444317")
        datos = BorradorPoliza.objects.get().datos
        self.assertEqual((datos["nombre"], datos["apellido"]), ("Andrés", "Molina"))

    def test_preguntar_si_aseguran_motos_se_contesta_primero(self):
        respuesta = self.turno("hola, ustedes aseguran motos?")
        self.assertTrue(respuesta.startswith("Sí, aseguramos"), respuesta)


@override_settings(BUSQUEDA_SEMANTICA=False)
class CotizarYContratarTests(AltaPorChatNaturalTests):
    """Decisión del equipo: después de cotizar, el bot sigue y puede tomar el alta."""

    DATOS = "AF234GH\nChevrolet Onix\n2020\nparticular\nBanfield"

    def cotizar(self):
        self.turno("hola cuanto sale asegurar un onix?")
        return self.turno(self.DATOS)

    def test_tras_cotizar_ofrece_contratar_y_el_bot_sigue(self):
        from negocio.bot import plantillas

        cierre = self.cotizar()
        self.assertEqual(cierre, plantillas.con_aviso_de_derivacion(plantillas.COTIZACION_REGISTRADA))
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo, "bot")

    def test_quiero_contratarlo_arranca_el_alta_con_el_vehiculo_ya_cargado(self):
        self.cotizar()
        respuesta = self.turno("dale, quiero contratarlo ya")
        datos = BorradorPoliza.objects.get().datos
        self.assertEqual((datos["patente"], datos["marca"], datos["modelo"], datos["anio"], datos["uso"]),
                         ("AF234GH", "Chevrolet", "Onix", 2020, "particular"))
        self.assertIn("nombre y apellido", respuesta)  # pide lo que falta, no lo que ya dio

    def test_un_si_despues_de_la_oferta_tambien_vale(self):
        self.cotizar()
        self.turno("si")
        self.assertTrue(BorradorPoliza.objects.get().activo)

    def test_volver_a_preguntar_el_precio_no_reinicia_la_cotizacion(self):
        from datos.models import Derivacion
        from negocio.bot import plantillas

        self.cotizar()
        respuesta = self.turno("y cuanto sale entonces?")
        self.assertEqual(respuesta, plantillas.COTIZACION_YA_PEDIDA)
        self.assertEqual(Derivacion.objects.count(), 1)

    def test_de_punta_a_punta_queda_la_accion_lista(self):
        self.cotizar()
        for texto in ("quiero contratarlo", "Valeria Núñez 39777320", "auto", "no sé", "ni idea", "Pampa", "2"):
            self.turno(texto)
        cierre = self.turno("hoy")
        self.assertIn("Preparé tu solicitud (Terceros Completo)", cierre)
        p = AccionPendiente.objects.get(tipo_accion="alta_poliza").parametros
        self.assertEqual((p["nombre"], p["patente"], p["modelo"], p["cobertura"]), ("Valeria", "AF234GH", "Onix", "intermedia"))
