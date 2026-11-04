from django.core.management.base import BaseCommand
from django.conf import settings
from negocio.busqueda_semantica import MODELO


class Command(BaseCommand):
    help = 'Descarga explícitamente el modelo gratuito de búsqueda local (una vez por instalación).'

    def handle(self, **options):
        import os
        os.environ.setdefault('HF_HOME', str(settings.MODELO_BUSQUEDA_DIR / 'hub'))
        os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
        from fastembed import TextEmbedding
        modelo = TextEmbedding(model_name=MODELO, cache_dir=str(settings.MODELO_BUSQUEDA_DIR), threads=2)
        next(modelo.embed(['prueba de búsqueda de coberturas']))
        self.stdout.write(self.style.SUCCESS('Modelo preparado. Reiniciá web y worker para habilitarlo.'))
