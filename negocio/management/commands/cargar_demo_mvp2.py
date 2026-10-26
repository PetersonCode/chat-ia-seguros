"""Carga optativa e idempotente de datos académicos, sin tocar el histórico."""
import os
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from datos.models import Cliente, DocumentoGeneral, Funcionario, Poliza
from negocio.clientes import alta_cliente
from negocio.documentos import aprobar_documento, crear_documento
from negocio.polizas import alta_poliza
from negocio.bot.orquestador import procesar_mensaje
from negocio.whatsapp import registrar_entrante


class Command(BaseCommand):
    help = "Carga una muestra ficticia del MVP 2 en desarrollo, sin restablecer usuarios."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG or os.getenv("WHATSAPP_MODO", "simulado").lower() != "simulado" or os.getenv("LLM_PROVIDER", "none").lower() != "none":
            raise CommandError("La demo requiere DJANGO_DEBUG=true, WHATSAPP_MODO=simulado y LLM_PROVIDER=none.")
        aprobador = Funcionario.objects.filter(activo=True, puede_aprobar=True).order_by("id").first()
        if aprobador is None:
            raise CommandError("Primero cargá los catálogos y funcionarios ficticios de 02_seed.sql.")
        cliente = Cliente.objects.filter(dni="90000001").first()
        if cliente and (cliente.nombre != "Cliente" or cliente.apellido != "Demostración"):
            raise CommandError("El DNI reservado para la demo está ocupado. No se modificó ese cliente.")
        nuevo = cliente is None
        if nuevo:
            cliente = alta_cliente(dni="90000001", nombre="Cliente", apellido="Demostración", telefono="+5491199990001", email="demo.cliente@example.com")
        inicio = timezone.localdate().replace(day=1)
        for bien, prima in [("Vehículo ficticio A · DEMO MVP2", "12000.00"), ("Vehículo ficticio B · DEMO MVP2", "8500.00")]:
            if not Poliza.objects.filter(cliente=cliente, bien_asegurado=bien).exists():
                alta_poliza(cliente.pk, tipo_seguro="automotor", cobertura="intermedia", fecha_inicio=inicio, fecha_vencimiento=inicio.replace(year=inicio.year + 1), prima_mensual=prima, bien_asegurado=bien)
        titulo = "Fuente ficticia para pruebas de granizo"
        if not DocumentoGeneral.objects.filter(titulo=titulo, version="DEMO-1").exists():
            documento = crear_documento(
                titulo=titulo, version="DEMO-1", referencia="Material académico ficticio, sin validez contractual",
                contenido="En este ejemplo académico, la cobertura de granizo tiene un límite ficticio de $100.000 según cláusula DEMO-1. Este texto sirve únicamente para probar citas documentales y no describe una póliza real.",
                funcionario_id=aprobador.pk,
            )
            aprobar_documento(documento.pk, aprobador.pk)
        if nuevo:
            for texto in ["Necesito dar de baja una póliza", "Tengo un reclamo por un cobro de más"]:
                mensaje = registrar_entrante(f"demo-{uuid4()}", "+5491199990001", texto)
                procesar_mensaje(mensaje.pk)
        self.stdout.write(self.style.SUCCESS("Demo preparada: Cliente Demostración, DNI ficticio 90000001, WhatsApp simulado +5491199990001."))
        self.stdout.write("Se conservaron el histórico y las contraseñas. Revisá las dos pólizas, las acciones pendientes y la biblioteca desde el panel.")
