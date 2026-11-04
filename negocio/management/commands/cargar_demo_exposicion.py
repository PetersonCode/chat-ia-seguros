"""Escenario automotor reproducible con datos ficticios del PDF aportado."""
import os
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from datos.models import Cliente, Poliza, TipoSeguro, Cuota, DocumentoGeneral, Funcionario
from negocio.clientes import alta_cliente
from negocio.documentos import crear_documento, aprobar_documento
from negocio.coberturas import vincular_documento


class Command(BaseCommand):
    help = 'Carga a Lucía Rivas y una póliza automotor ficticia, sus cuotas y condiciones; no cambia contraseñas.'

    @transaction.atomic
    def handle(self, **options):
        if not settings.DEBUG or os.getenv('WHATSAPP_MODO','simulado') != 'simulado' or os.getenv('LLM_PROVIDER','none') not in ('none',''):
            raise CommandError('La exposición requiere desarrollo, WhatsApp simulado y LLM desactivado.')
        aprobador=Funcionario.objects.filter(activo=True,puede_aprobar=True).order_by('id').first()
        if aprobador is None:
            raise CommandError('Primero preparar funcionarios y catálogos ficticios.')
        cliente=Cliente.objects.filter(dni='48009001').first()
        if cliente and (cliente.nombre,cliente.apellido) != ('Lucía','Rivas'):
            raise CommandError('El DNI ficticio reservado está ocupado. No se modificó esa persona.')
        if cliente is None:
            cliente=alta_cliente(dni='48009001',nombre='Lucía',apellido='Rivas',telefono='+5491100009001',email='lucia.rivas@example.com')
        if not cliente.contactos.filter(numero='+5491100009001').exists():
            raise CommandError('El contacto reservado no coincide con la demo. Revisar sin sobrescribirlo.')
        poliza=Poliza.objects.filter(numero_poliza='POL-90101').first()
        if poliza and (poliza.cliente_id != cliente.pk or poliza.tipo_seguro.codigo != 'automotor'):
            raise CommandError('La póliza ficticia reservada está ocupada. No se modificó.')
        if poliza is None:
            poliza=Poliza.objects.create(numero_poliza='POL-90101',cliente=cliente,tipo_seguro=TipoSeguro.objects.get(codigo='automotor'),
                cobertura='total',estado='vigente',fecha_inicio=date(2026,1,1),fecha_vencimiento=date(2026,12,31),
                prima_mensual=Decimal('48000.00'),bien_asegurado='Automotor ficticio de Lucía · demostración académica')
            for mes,estado in [(10,'vencida'),(11,'pendiente')]:
                Cuota.objects.create(poliza=poliza,periodo=date(2026,mes,1),importe=Decimal('48000.00'),vencimiento=date(2026,mes,15),estado=estado)
        fuentes = [
            ('Condiciones ficticias automotor total',
             'La cobertura automotor total incluye responsabilidad civil por daños a terceros hasta $80.000.000 por evento, robo total e incendio total o parcial, cristales y cerraduras, daños propios por choque y granizo. Valor del vehículo hasta $25.000.000. Cristales y cerraduras hasta $250.000 por año. Franquicia por choque $350.000 por evento. Granizo hasta $1.500.000 por año. Exclusiones: desgaste, fallas mecánicas, objetos personales, uso comercial no declarado, competencias, conducción sin habilitación y daños intencionales. Estas condiciones son ficticias y no garantizan indemnización.'),
            ('Servicio ficticio de asistencia automotor total',
             'Para la póliza automotor total ficticia, el teléfono de asistencia y grúa de ejemplo es 0800-333-1003, las 24 horas. Remolque hasta 300 km por evento, hasta 6 eventos por año, por caminos habilitados y accesibles. Incluye remolque, arranque de batería y cambio de rueda con auxilio utilizable. No incluye rescate fuera de calzada, extracción de sumergidos ni reparación mecánica integral. No se garantiza tiempo de llegada ni se reserva una grúa desde el bot. Teléfono de ejemplo: no llamar durante la demostración.'),
        ]
        for titulo,contenido in fuentes:
            doc=DocumentoGeneral.objects.filter(titulo=titulo,version='PDF-2026-10-29').first()
            if doc is None:
                doc=crear_documento(titulo=titulo,version='PDF-2026-10-29',referencia='PDF ficticio aportado por el equipo, páginas 2 y 4; solo automotor',contenido=contenido,funcionario_id=aprobador.pk)
                aprobar_documento(doc.pk,aprobador.pk)
            vincular_documento(poliza.numero_poliza,doc.pk,aprobador.pk)
        self.stdout.write(self.style.SUCCESS('Exposición preparada: Lucía Rivas, +5491100009001, POL-90101. Saldo inicial $96.000; grúa de ejemplo 0800-333-1003.'))
        self.stdout.write('Sin validación manual de identidad. Probar saldo, grúa y cobertura; dejar la urgencia para el final porque pausa el bot. Fechas de este lote: año 2026.')
