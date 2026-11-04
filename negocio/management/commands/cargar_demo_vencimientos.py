"""Datos ficticios para mostrar la pantalla; nunca se carga al iniciar la app."""
import os
from datetime import timedelta
from uuid import uuid4
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from datos.models import Cliente, Poliza, TipoSeguro, Cuota, Conversacion
from negocio.clientes import alta_cliente
from negocio.whatsapp import registrar_entrante
from negocio.bot.orquestador import procesar_mensaje


class Command(BaseCommand):
    help='Prepara tres pólizas ficticias con vencimientos a 1, 7 y 21 días y un chat simulado.'

    @transaction.atomic
    def handle(self, **options):
        if not settings.DEBUG or os.getenv('WHATSAPP_MODO','simulado')!='simulado' or os.getenv('LLM_PROVIDER','none') not in ('none',''):
            raise CommandError('Este lote solo funciona en desarrollo, WhatsApp simulado y LLM desactivado.')
        cliente=Cliente.objects.filter(dni='48009020').first()
        if cliente and (cliente.nombre,cliente.apellido)!=('Ana','Demostración'):
            raise CommandError('La identidad ficticia reservada está ocupada.')
        if cliente is None:
            cliente=alta_cliente(dni='48009020',nombre='Ana',apellido='Demostración',telefono='+5491100009020',email='ana.demo@example.com')
        contacto=cliente.contactos.filter(numero='+5491100009020').first()
        if contacto is None:raise CommandError('El teléfono ficticio reservado no coincide; no se sobrescribió.')
        hoy=timezone.localdate()
        for sufijo,dias in [(1,1),(2,7),(3,21)]:
            numero=f'POL-9020{sufijo}'
            poliza=Poliza.objects.filter(numero_poliza=numero).first()
            if poliza and poliza.cliente_id!=cliente.pk:raise CommandError('Una póliza ficticia reservada está ocupada.')
            if poliza is None:
                poliza=Poliza.objects.create(numero_poliza=numero,cliente=cliente,
                    tipo_seguro=TipoSeguro.objects.get(codigo='automotor'),cobertura='intermedia',estado='vigente',
                    fecha_inicio=hoy-timedelta(days=90),fecha_vencimiento=hoy+timedelta(days=dias),
                    prima_mensual='25000',bien_asegurado=f'Auto ficticio {sufijo} · exposición')
                Cuota.objects.create(poliza=poliza,periodo=hoy.replace(day=1),importe='25000',estado='pendiente',
                    vencimiento=hoy+timedelta(days=dias))
        reciente=Conversacion.objects.filter(contacto=contacto,estado='abierta',ultimo_mensaje_cliente_en__gt=timezone.now()-timedelta(hours=24)).exists()
        if not reciente:
            m=registrar_entrante('demo-vencimientos-'+uuid4().hex,contacto.numero,'Hola')
            procesar_mensaje(m.pk)
        self.stdout.write(self.style.SUCCESS('Pantalla lista: Ana Demostración, POL-90201/2/3, saldo inicial $25.000 por póliza.'))
        self.stdout.write('Las fechas existentes y los pagos no se restablecen al repetir este comando. Solo se habilita un chat simulado reciente.')
