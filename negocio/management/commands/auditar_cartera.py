"""Diagnóstico de solo lectura para completar históricos antes de la exposición."""
from django.core.management.base import BaseCommand
from django.db.models import F
from datos.models import Poliza


class Command(BaseCommand):
    help = 'Lista pólizas automotor incompletas y superposiciones históricas; no modifica datos.'

    def handle(self, *args, **options):
        polizas = Poliza.objects.filter(tipo_seguro__codigo='automotor').order_by('id')
        incompletas = polizas.filter(vehiculo__isnull=True) | polizas.filter(compania__isnull=True) | polizas.filter(comision_pct__isnull=True)
        self.stdout.write(f'Pólizas incompletas: {incompletas.count()}')
        for p in incompletas.iterator():
            faltantes = [nombre for nombre, valor in [('vehículo', p.vehiculo_id),
                ('compañía', p.compania_id), ('porcentaje', p.comision_pct)] if valor is None]
            self.stdout.write(f'{p.numero_poliza}: faltan {", ".join(faltantes)}. Ficha: /panel/cliente/?id={p.cliente_id}')
        pares = polizas.filter(vehiculo__isnull=False).exclude(estado='dada_de_baja').filter(
            vehiculo__polizas__id__gt=F('id'),
            vehiculo__polizas__fecha_inicio__lte=F('fecha_vencimiento'),
            vehiculo__polizas__fecha_vencimiento__gte=F('fecha_inicio'),
            vehiculo__polizas__estado__in=['vigente', 'vencida'],
        ).values_list('numero_poliza', 'vehiculo__polizas__numero_poliza')
        pares = list(pares)
        self.stdout.write(f'Pares superpuestos históricos: {len(pares)}')
        for a, b in pares:
            self.stdout.write(f'{a} / {b}: revisar antes de modificar vigencia o vehículo.')
