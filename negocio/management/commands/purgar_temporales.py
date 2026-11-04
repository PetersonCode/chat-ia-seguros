"""Limpieza limitada a cuotas de acceso y contextos de selección vencidos."""
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone
from datetime import timedelta
from datos.models import ContextoCobertura


class Command(BaseCommand):
    help = 'Elimina selecciones temporales vencidas y límites de acceso antiguos; conserva mensajes y auditoría.'

    def handle(self, **options):
        contextos, _ = ContextoCobertura.objects.filter(expira_en__lt=timezone.now()).delete()
        with connection.cursor() as c:
            c.execute('DELETE FROM limites_acceso WHERE inicio < %s', [timezone.now()-timedelta(days=1)])
            limites = c.rowcount
        self.stdout.write(f'Contextos vencidos: {contextos}; cuotas antiguas: {limites}.')
