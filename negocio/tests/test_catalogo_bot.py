"""El bot lista seguros, compañías y planes (resumido); el detalle solo de una póliza."""

from django.test import override_settings

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import Mensaje, PlanCobertura
from negocio.bot import catalogo
from negocio.bot.orquestador import procesar_mensaje

PLANES = (
    ("Responsabilidad Civil", "basica"),
    ("Terceros Completo", "intermedia"),
    ("Todo Riesgo con franquicia", "total"),
)


class BaseCatalogo(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.litoral = fabricas.crear_compania(nombre="Litoral Seguros Generales")
        self.condor = fabricas.crear_compania(nombre="Cóndor Seguros")
        self.rio = fabricas.crear_compania(nombre="Aseguradora Río de la Plata")
        self.inactiva = fabricas.crear_compania(nombre="Vieja Aseguradora Fantasma", activa=False)
        for compania in (self.litoral, self.condor, self.rio, self.inactiva):
            for nombre, nivel in PLANES:
                self.plan(compania, nombre, nivel)

    def plan(self, compania, nombre, nivel, **campos):
        return PlanCobertura.objects.create(
            compania=compania, nombre=nombre, nivel=nivel, actualizado_por=self.aprobadora,
            cubre="DETALLE SECRETO DE COBERTURA", **campos,
        )


class CatalogoTests(BaseCatalogo):
    def test_pregunta_por_seguros_y_companias_con_distintos_verbos(self):
        for pregunta in (
            "¿Qué seguros tienen?", "que compañias trabajan?", "Con qué compañías trabajan ustedes?",
            "que aseguradoras manejan", "cuales son las compañias que ofrecen?", "qué seguros brindan?",
            "que seguros prestan?", "que companias hay?",
        ):
            with self.subTest(pregunta=pregunta):
                texto = catalogo.responder(pregunta)
                self.assertIsNotNone(texto, pregunta)
                for nombre in ("Litoral Seguros Generales", "Cóndor Seguros", "Aseguradora Río de la Plata"):
                    self.assertIn(nombre, texto)
                self.assertNotIn("Fantasma", texto)
                self.assertNotIn("DETALLE SECRETO", texto)

    def test_planes_de_una_compania_en_lista_resumida_sin_detalle(self):
        for pregunta in ("¿Qué coberturas tiene Litoral?", "que planes ofrece Cóndor?",
                         "qué servicios brinda Litoral Seguros?", "que categorias tiene Rio de la Plata?"):
            with self.subTest(pregunta=pregunta):
                texto = catalogo.responder(pregunta)
                self.assertIsNotNone(texto, pregunta)
                self.assertIn("Responsabilidad Civil (cobertura básica)", texto)
                self.assertIn("Terceros Completo (cobertura intermedia)", texto)
                self.assertIn("Todo Riesgo con franquicia (cobertura total)", texto)
                self.assertNotIn("DETALLE SECRETO", texto)

    def test_solo_nombra_los_planes_de_la_compania_preguntada(self):
        self.plan(self.condor, "Plan Exclusivo Cóndor", "total")

        texto = catalogo.responder("que planes tiene Litoral?")

        self.assertIn("Litoral Seguros Generales", texto)
        self.assertNotIn("Exclusivo", texto)
        self.assertNotIn("Cóndor", texto)

    def test_planes_sin_nombrar_compania_se_resumen_una_sola_vez_si_son_iguales(self):
        texto = catalogo.responder("¿qué planes tienen?")

        self.assertEqual(texto.count("Terceros Completo"), 1)
        self.assertIn("Litoral Seguros Generales", texto)

    def test_si_los_planes_difieren_se_listan_por_compania(self):
        self.plan(self.condor, "Plan Exclusivo Cóndor", "total")

        texto = catalogo.responder("¿qué coberturas tienen?")

        self.assertIn("Cóndor Seguros:", texto)
        self.assertIn("Plan Exclusivo Cóndor", texto)
        self.assertIn("Litoral Seguros Generales:", texto)

    def test_los_planes_inactivos_no_se_listan(self):
        PlanCobertura.objects.filter(compania=self.litoral, nombre="Terceros Completo").update(activo=False)

        texto = catalogo.responder("que planes tiene Litoral?")

        self.assertNotIn("Terceros Completo", texto)
        self.assertIn("Responsabilidad Civil", texto)

    def test_lo_que_cubre_una_poliza_no_es_catalogo(self):
        for pregunta in ("¿Qué cubre mi póliza?", "que cubre la poliza POL-00001", "y que cubre?",
                         "¿Qué coberturas tengo?", "mi poliza cubre granizo?", "que cubre el plan todo riesgo de Litoral?",
                         "que diferencia hay entre los planes?", "compara los planes de Litoral",
                         "que incluye el plan terceros completo?", "que franquicia tiene el todo riesgo?",
                         "tengo seguro con ustedes, cuanto debo?", "quiero asegurar mi auto", "hola, buen dia"):
            with self.subTest(pregunta=pregunta):
                self.assertIsNone(catalogo.responder(pregunta), pregunta)


@override_settings(BUSQUEDA_SEMANTICA=False)
class CatalogoEnElChatTests(BaseCatalogo):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()

    def _preguntar(self, texto, conversacion=None):
        conversacion = conversacion or self.conversacion
        mensaje = fabricas.crear_mensaje(conversacion, texto=texto)
        with self.captureOnCommitCallbacks(execute=True):
            resultado = procesar_mensaje(mensaje.id)
        return Mensaje.objects.get(pk=resultado.mensaje_respuesta_id)

    def test_un_cliente_recibe_la_lista_y_no_se_deriva(self):
        respuesta = self._preguntar("que companias trabajan?")

        self.assertIn("Litoral Seguros Generales", respuesta.texto)
        self.assertFalse(respuesta.consulta.derivaciones.exists())

    def test_un_desconocido_recibe_la_lista_sin_que_se_le_pidan_datos(self):
        desconocido = fabricas.crear_conversacion(fabricas.crear_contacto())

        respuesta = self._preguntar("que seguros tienen?", desconocido)

        self.assertIn("Cóndor Seguros", respuesta.texto)
        self.assertNotIn("DNI", respuesta.texto)
        self.assertFalse(respuesta.consulta.derivaciones.exists())

    def test_los_planes_de_una_compania_llegan_resumidos(self):
        respuesta = self._preguntar("que coberturas tiene Litoral?")

        self.assertIn("Todo Riesgo con franquicia (cobertura total)", respuesta.texto)
        self.assertNotIn("DETALLE SECRETO", respuesta.texto)

    def test_la_lista_no_dispara_alertas_del_bot(self):
        respuesta = self._preguntar("que planes tiene Litoral?")

        self.assertFalse(respuesta.alertas.exists())
        self.assertEqual(respuesta.estado_envio, "enviado")
