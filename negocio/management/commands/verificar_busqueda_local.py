"""Prueba explícita del modelo real, fuera de la suite determinista."""
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings
from negocio.busqueda_semantica import similitud, modelo_local, vector


class Command(BaseCommand):
    help = 'Verifica embeddings locales reales y una pregunta fuera de dominio, sin APIs.'

    def handle(self, **options):
        modelo_local.cache_clear()
        vector.cache_clear()
        with override_settings(BUSQUEDA_SEMANTICA=True):
            fuente = 'La cobertura incluye rotura de cristales y parabrisas del automotor. Se excluye el desgaste.'
            consulta = 'Se me astilló el vidrio delantero del vehículo, ¿el seguro se hace cargo?'
            puntaje = similitud(consulta, fuente)
            ajena = similitud('¿Cuál es el horario de la oficina?', fuente)
            if puntaje is None or ajena is None or puntaje < 0.50 or ajena >= 0.50:
                raise CommandError('El modelo local no superó la prueba. Revisá preparación y versión.')
            self.stdout.write(self.style.SUCCESS(f'Paráfrasis: {puntaje:.4f}; fuera de dominio: {ajena:.4f}. Inferencia local correcta.'))
