from django.core.management.base import BaseCommand
from negocio.gestion_diaria import procesar

class Command(BaseCommand):
    help='Programa avisos y prepara envíos operativos dentro de la ventana de WhatsApp.'
    def add_arguments(self,parser):parser.add_argument('--dry-run',action='store_true')
    def handle(self,*args,**kwargs):self.stdout.write(str(procesar(dry_run=kwargs['dry_run'])))
