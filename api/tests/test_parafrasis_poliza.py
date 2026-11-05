"""Preguntas independientes: ninguna depende de acertar un turno anterior."""
from django.test import override_settings
from datos import fabricas
from datos.models import Mensaje, Derivacion
from api.tests.base import ApiTestCase
from negocio.bot.orquestador import procesar_mensaje

RESUMENES = (
    '¿Qué cubre mi póliza?', 'que cubre mi poliza', 'QUE CUBRE MI POLIZA',
    '¿Qué incluye mi seguro?', '¿Qué protege mi seguro?', '¿Qué cobertura tengo?',
    '¿Cuál es mi cobertura?', 'Mostrame la cobertura de mi auto',
    'Contame qué incluye mi póliza', '¿Qué prestaciones tiene mi seguro?',
    'Necesito saber qué cubre mi seguro', '¿Qué protección tengo contratada?',
    'Hola, ¿qué cubre mi póliza?',
    'No quiero denunciar nada: solo saber qué cubre mi póliza.',
    '¿Qué tipo de cobertura tengo?', '¿Cuáles son mis coberturas?',
)
GRANIZO = (
    '¿Mi póliza cubre granizo?', '¿Mi seguro cubre pedrisco?',
    '¿Estoy cubierto ante una granizada?', 'Si cae piedra, ¿me cubre mi seguro?',
    '¿Mi auto está protegido contra granizo?', '¿El seguro me ampara ante el granizo?',
    '¿La pedrada entra en mi cobertura?', '¿Mi póliza contempla daños por granizo?',
    '¿Me pagan el daño de granizo con mi seguro?', '¿El plan que tengo incluye granizo?',
    '¿Mi cobertura cubre hurto?',
)
CRISTALES = (
    '¿Mi póliza cubre parabrisas?', '¿Mi seguro incluye vidrios?',
    '¿Mi póliza incluye la luneta?', '¿Mi póliza cubre las ventanillas?',
    '¿Si se rompe mi parabrisas está cubierto?', '¿La rotura de un vidrio entra en mi seguro?',
    '¿Me cubre si se astilla mi parabrisas?', '¿Está cubierto el cristal delantero de mi auto?',
    '¿Qué dice mi póliza sobre roturas de cristales?', '¿Mi seguro ampara la rotura de cristales?',
    '¿Qué protección tengo si se quiebra la luneta?', '¿Mi póliza cubre daños a terceros?',
    '¿Tengo responsabilidad civil en mi seguro?', '¿Mi póliza protege a terceros?',
)
SIN_DATOS = (
    '¿Mi póliza protege frente a una sustracción?', '¿Mi póliza cubre robo?',
    '¿Mi póliza cubre inundación?', '¿Mi seguro cubre daños por terremoto?',
    '¿Mi seguro cubre el equipaje?', '¿Mi póliza cubre el motor por desgaste?',
    '¿Mi póliza cubre un viaje al exterior?', '¿Mi póliza me paga una estadía de hotel?',
)
HECHOS = (
    'Me chocaron en la autopista', 'Me robaron mi moto, ¿qué cubre?',
    'Se me rompió el parabrisas', 'Estoy en el hospital después de un choque',
    'Me cayó granizo ayer, ¿mi póliza cubre el daño?',
    'Me cayó granizo y no sé si mi seguro lo cubre',
)
ASISTENCIA = (
    'Necesito el número de la grúa', '¿Cuál es mi teléfono de asistencia?',
    'Estoy varado, ¿a quién llamo?', 'Mi auto no arranca, necesito auxilio',
    '¿A qué número pido un remolque?',
)


@override_settings(BUSQUEDA_SEMANTICA=False)
class ParafrasisPolizaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.poliza = fabricas.crear_poliza(self.cliente)
        self.entrar()
        r = self.cliente_api.patch(f'/api/polizas/{self.poliza.id}/condiciones/', {
            'cubre': 'Responsabilidad civil por daños a terceros y rotura de cristales.',
            'no_cubre': 'No cubre granizo ni hurto.',
            'limites': 'Hasta $100.000.000.', 'asistencia': '0800-123-4567',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)

    def comprobar(self, pregunta, tipo):
        m = fabricas.crear_mensaje(self.conversacion, texto=pregunta)
        with self.captureOnCommitCallbacks(execute=True):
            r = procesar_mensaje(m.id)
        salida = Mensaje.objects.get(pk=r.mensaje_respuesta_id)
        self.conversacion.refresh_from_db()
        self.assertFalse(r.retenido, (pregunta, r.alertas, salida.texto))
        self.assertEqual(salida.estado_envio, 'enviado', (pregunta, salida.texto))
        if tipo in ('resumen','granizo','cristales'):
            self.assertEqual(r.tipo_consulta,'consulta_cobertura',(pregunta,salida.texto))
            self.assertEqual(self.conversacion.modo,'bot',(pregunta,salida.texto))
            self.assertFalse(Derivacion.objects.exists())
            self.assertIn('Responsabilidad civil',salida.texto)
            self.assertIn('No cubre granizo ni hurto',salida.texto)
        elif tipo == 'sin_datos':
            self.assertEqual(self.conversacion.modo,'humano',(pregunta,salida.texto))
            self.assertIn('No encuentro un pasaje suficiente',salida.texto)
        elif tipo == 'hecho':
            self.assertIn(r.tipo_consulta,('siniestro','siniestro_urgente'),(pregunta,salida.texto))
            self.assertEqual(self.conversacion.modo,'humano')
            self.assertTrue(Derivacion.objects.exists())
        else:
            self.assertEqual(self.conversacion.modo,'bot',(pregunta,salida.texto))
            self.assertIn('0800-123-4567',salida.texto)


def caso(pregunta,tipo):
    def prueba(self):
        self.comprobar(pregunta,tipo)
    prueba.__doc__=pregunta
    return prueba


for grupo,tipo in ((RESUMENES,'resumen'),(GRANIZO,'granizo'),(CRISTALES,'cristales'),
                   (SIN_DATOS,'sin_datos'),(HECHOS,'hecho'),(ASISTENCIA,'asistencia')):
    for indice,pregunta in enumerate(grupo,1):
        setattr(ParafrasisPolizaTests,f'test_{tipo}_{indice:02}',caso(pregunta,tipo))
