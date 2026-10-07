"""Manda un mensaje al bot sin pasar por Meta (AC-T3-45).

    python manage.py simular_whatsapp +5491155551001 "cuánto me falta pagar"

Corre `procesar_mensaje` **sin hilo**, así se ve el resultado en la consola.
"""

from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from datos.models import Alerta, Mensaje
from negocio.bot.orquestador import procesar_mensaje
from negocio.whatsapp import registrar_entrante


class Command(BaseCommand):
    help = "Simula un mensaje entrante de WhatsApp y muestra qué contesta el bot."

    def add_arguments(self, parser):
        parser.add_argument("numero", help="Número del cliente, p. ej. +5491155551001")
        parser.add_argument("texto", help="Texto del mensaje")

    def handle(self, *args, **opciones):
        numero = opciones["numero"]
        texto = opciones["texto"]

        mensaje = registrar_entrante(
            wa_message_id=f"sim-{uuid.uuid4()}",
            numero_raw=numero,
            texto=texto,
        )
        if mensaje is None:
            raise CommandError("No se pudo registrar el mensaje entrante.")

        self.stdout.write(f"Entrante #{mensaje.id} de {mensaje.conversacion.contacto.numero}")
        self.stdout.write(f"  > {texto}")

        resultado = procesar_mensaje(mensaje.id)
        if resultado.ignorado:
            self.stdout.write(
                self.style.WARNING("El bot no intervino (conversación en modo humano o ya procesada).")
            )
            return

        self.stdout.write(f"Tipo de consulta: {resultado.tipo_consulta}")
        respuesta = Mensaje.objects.filter(pk=resultado.mensaje_respuesta_id).first()
        if respuesta is not None:
            self.stdout.write(f"Respuesta ({respuesta.estado_envio}):")
            for linea in respuesta.texto.splitlines():
                self.stdout.write(f"  < {linea}")

        alertas = Alerta.objects.filter(consulta__mensajes=mensaje).distinct()
        if not alertas:
            self.stdout.write(self.style.SUCCESS("Sin alertas."))
            return
        self.stdout.write(self.style.WARNING(f"{len(alertas)} alerta(s):"))
        for alerta in alertas:
            self.stdout.write(f"  - [{alerta.severidad}] {alerta.tipo}: {alerta.descripcion}")
