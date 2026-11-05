"""Lo aprendido simulando conversaciones con los 20 clientes demo no retrocede.

Qwen no corre en los tests: se simula su respuesta. Lo que se fija acá es lo que
depende del código (reglas, la combinación reglas + LLM, los ejemplos que se le
pasan a Qwen y la búsqueda en las condiciones). La calidad de Qwen se mide con
`python manage.py evaluar_bot`.
"""
from django.test import SimpleTestCase

from negocio.bot import plantillas
from negocio.bot.alta_poliza import quiere_alta
from negocio.bot.clasificador import clasificar, combinar_clasificaciones
from negocio.bot.corpus_conversaciones import CORPUS, VARIANTES, ejemplos_para_llm, turnos
from negocio.bot.llm import _con_ejemplos, _mensajes
from negocio.bot.prompts import CODIGOS_CONSULTA, SISTEMA_CLASIFICADOR
from negocio.coberturas import _tema_consultado
from negocio.tests.test_cotizacion_bot import BaseCotizacionBotTests


def _todos():
    for conversacion in CORPUS:
        yield from turnos(conversacion)
    for variante in VARIANTES:
        yield variante.texto, variante.tipo


class CombinacionTests(SimpleTestCase):
    def test_con_el_llm_acertando_el_bot_no_lo_estropea(self):
        for texto, esperado in _todos():
            del_llm = esperado if esperado in CODIGOS_CONSULTA else "otro"
            with self.subTest(texto=texto):
                self.assertEqual(combinar_clasificaciones(texto, clasificar(texto), del_llm), esperado)

    def test_si_el_llm_no_lo_ubica_ganan_las_reglas(self):
        self.assertEqual(combinar_clasificaciones("hola q tal", clasificar("hola q tal"), "otro"), "saludo")

    def test_sin_llm_decide_la_regla(self):
        self.assertEqual(combinar_clasificaciones("q debo algo?", clasificar("q debo algo?"), None), "saldo")

    def test_pedir_una_persona_deriva_aunque_el_llm_diga_reclamo(self):
        texto = "quiero hablar con una persona YA"
        self.assertEqual(combinar_clasificaciones(texto, clasificar(texto), "reclamo"), "otro")


class ReglasDeEscrituraInformalTests(SimpleTestCase):
    CASOS = (
        ("Buenas tardes. Quisiera saber, por favor, cuánto adeudo de mi seguro.", "saldo"),
        ("q debo algo?", "saldo"),
        ("ola kiero saver cuanto devo", "saldo"),
        ("toy al dia con el seguro?", "saldo"),
        ("como ago para pagar", "pago"),
        ("puedo pagar en cuotas lo q devo?", "pago"),
        ("estoy atrasada con las cuotas, puedo pagar la semana q viene?", "pago"),
        ("no me manden mas recordatorios porfa", "baja_avisos"),
        ("dejen de mandarme avisos", "baja_avisos"),
        ("buenas! el auto no arranca, estoy en la puerta de casa", "asistencia"),
        ("creo q es la bateria", "asistencia"),
        ("y si me roban la fiorino que pasa", "consulta_cobertura"),
        ("cuanto es la franquicia de mi poliza?", "consulta_cobertura"),
        ("kiero saver q me cubre", "consulta_cobertura"),
        ("thanks!!", "agradecimiento"),
    )

    def test_las_reglas_entienden_como_escribe_la_gente(self):
        for texto, esperado in self.CASOS:
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), esperado)

    def test_un_pedido_de_precio_no_arranca_un_alta(self):
        self.assertFalse(quiere_alta("cuanto me sale asegurar una moto 110?"))
        self.assertTrue(quiere_alta("quiero asegurar mi auto"))


class EjemplosParaQwenTests(SimpleTestCase):
    def test_los_ejemplos_van_como_turnos_resueltos_despues_del_sistema(self):
        mensajes = _con_ejemplos(_mensajes(SISTEMA_CLASIFICADOR, "hola", [], rotulo="Mensaje a clasificar"))
        ejemplos = ejemplos_para_llm()
        self.assertEqual(mensajes[0]["role"], "system")
        self.assertEqual(len(mensajes), 1 + 2 * len(ejemplos) + 1)
        self.assertEqual(mensajes[-1]["content"], "Mensaje a clasificar:\nhola")
        for texto, codigo in ejemplos:
            self.assertIn(codigo, CODIGOS_CONSULTA, texto)

    def test_las_variantes_de_control_nunca_se_usan_como_ejemplo(self):
        usados = {texto for texto, _ in ejemplos_para_llm()}
        for variante in VARIANTES:
            self.assertNotIn(variante.texto, usados)


class TemasDeCoberturaTests(SimpleTestCase):
    def test_el_relleno_y_la_escritura_informal_no_se_exigen_en_las_condiciones(self):
        self.assertEqual(_tema_consultado("cuanto es la franquicia de mi poliza?"), {"franquicia"})
        self.assertEqual(_tema_consultado("tmb kiero saber q me cubre el seguro del c3", {"c3"}), set())
        self.assertEqual(
            _tema_consultado("queria consultar si me rompen el vidrio para robarme algo"),
            {"rotura", "cristales", "robo"},
        )


class SolicitudSinDuplicarTests(BaseCotizacionBotTests):
    def test_un_detalle_de_seguimiento_no_abre_otra_solicitud(self):
        from datos.models import AccionPendiente, Mensaje

        conversacion = self._conversacion("1001")
        self._turno(conversacion, "quiero agregar a mi hijo como conductor")
        segundo = self._turno(conversacion, "quiero agregar tambien a mi esposa como conductora")

        self.assertEqual(AccionPendiente.objects.filter(tipo_accion="modificar_poliza").count(), 1)
        texto = Mensaje.objects.get(pk=segundo.mensaje_respuesta_id).texto
        self.assertEqual(texto, plantillas.SOLICITUD_YA_REGISTRADA)
