"""Reintenta los mensajes que quedaron sin respuesta del bot (AC-T3-46).

    python manage.py reprocesar_pendientes

Busca conversaciones abiertas en modo `bot` cuyo último mensaje es del cliente,
tiene más de un minuto y todavía no generó una consulta (porque el hilo murió,
se reinició el proceso, etc.) y les corre `procesar_mensaje` una sola vez.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from datos.models import Conversacion, Emisor, EstadoConversacion, Mensaje, ModoConversacion
from negocio.bot.orquestador import procesar_mensaje

ANTIGUEDAD_MINIMA = timedelta(minutes=1)


class Command(BaseCommand):
    help = "Procesa los mensajes del cliente que quedaron sin respuesta del bot."

    def handle(self, *args, **opciones):
        limite = timezone.now() - ANTIGUEDAD_MINIMA
        procesadas = 0

        conversaciones = Conversacion.objects.filter(
            estado=EstadoConversacion.ABIERTA,
            modo=ModoConversacion.BOT,
        ).order_by("id")

        for conversacion in conversaciones:
            ultimo = (
                Mensaje.objects.filter(conversacion=conversacion)
                .order_by("-fecha_hora", "-id")
                .first()
            )
            if ultimo is None:
                continue
            if ultimo.emisor != Emisor.CLIENTE:
                continue
            if ultimo.fecha_hora > limite:
                continue
            if ultimo.consulta_id is not None:
                continue
            procesar_mensaje(ultimo.id)
            procesadas += 1

        self.stdout.write(f"Conversaciones procesadas: {procesadas}")
