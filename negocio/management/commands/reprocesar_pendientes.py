"""Consume la cola durable de WhatsApp y recupera mensajes salientes.

    python manage.py reprocesar_pendientes --continuo
"""

from __future__ import annotations

import logging
import math
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from datos.models import (
    Conversacion,
    Direccion,
    Emisor,
    EstadoConversacion,
    EstadoEnvio,
    EstadoTrabajoWhatsApp,
    Mensaje,
    ModoConversacion,
    TipoTrabajoWhatsApp,
    TrabajoWhatsApp,
)
from negocio.whatsapp import (
    MAX_INTENTOS_ENVIO,
    PREFIJO_NO_SOPORTADO,
    ejecutar_trabajo_whatsapp,
    enviar_pendientes,
)

ANTIGUEDAD_MINIMA = timedelta(minutes=1)
LEASE_TRABAJO = timedelta(minutes=15)
MAX_INTENTOS_TRABAJO = 8
MAX_ESPERA_MINUTOS = 60
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Procesa trabajos durables de WhatsApp y envía respuestas pendientes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--continuo",
            action="store_true",
            help="Mantiene el procesador activo y revisa la cola periódicamente.",
        )
        parser.add_argument(
            "--intervalo",
            type=float,
            default=2.0,
            help="Segundos entre sondeos cuando se usa --continuo.",
        )
        parser.add_argument(
            "--reintentar-fallidos",
            action="store_true",
            help="Rehabilita tareas y envíos que agotaron sus intentos.",
        )

    def handle(self, *args, **opciones):
        if not math.isfinite(opciones["intervalo"]) or opciones["intervalo"] <= 0:
            raise CommandError("--intervalo debe ser finito y mayor que cero.")

        if opciones["reintentar_fallidos"]:
            self._rehabilitar_fallidos()

        while True:
            self._encolar_legacy_sin_tarea()
            procesadas = self._procesar_disponibles()
            enviados = self._enviar_disponibles()
            if not opciones["continuo"]:
                self.stdout.write(f"Trabajos completados: {procesadas}")
                self.stdout.write(f"Mensajes salientes enviados: {enviados}")
                return
            if procesadas or enviados:
                logger.info(
                    "WhatsApp worker: %s trabajos completados, %s mensajes enviados.",
                    procesadas,
                    enviados,
                )
            time.sleep(opciones["intervalo"])

    def _encolar_legacy_sin_tarea(self) -> None:
        """Recupera mensajes de instalaciones anteriores a la cola SQL."""
        limite = timezone.now() - ANTIGUEDAD_MINIMA
        conversaciones = Conversacion.objects.filter(
            estado=EstadoConversacion.ABIERTA,
            modo=ModoConversacion.BOT,
        )
        for conversacion in conversaciones:
            mensaje = (
                Mensaje.objects.filter(conversacion=conversacion)
                .order_by("-fecha_hora", "-id")
                .first()
            )
            if (
                mensaje is None
                or mensaje.direccion != Direccion.ENTRANTE
                or mensaje.emisor != Emisor.CLIENTE
                or mensaje.fecha_hora > limite
                or mensaje.consulta_id is not None
                or (mensaje.texto or "").startswith(PREFIJO_NO_SOPORTADO)
            ):
                continue
            TrabajoWhatsApp.objects.get_or_create(
                mensaje=mensaje,
                defaults={"tipo": TipoTrabajoWhatsApp.TEXTO},
            )

    def _reclamar(self) -> TrabajoWhatsApp | None:
        ahora = timezone.now()
        vencido = ahora - LEASE_TRABAJO
        with transaction.atomic():
            TrabajoWhatsApp.objects.filter(
                estado=EstadoTrabajoWhatsApp.PROCESANDO,
                tomado_en__lte=vencido,
                intentos__gte=MAX_INTENTOS_TRABAJO,
            ).update(
                estado=EstadoTrabajoWhatsApp.FALLIDO,
                tomado_en=None,
                ultimo_error="El proceso no completó el trabajo antes de vencer el último lease.",
            )
            trabajo = (
                TrabajoWhatsApp.objects.select_for_update(skip_locked=True)
                .filter(
                    Q(
                        estado=EstadoTrabajoWhatsApp.PENDIENTE,
                        disponible_en__lte=ahora,
                    )
                    | Q(
                        estado=EstadoTrabajoWhatsApp.PROCESANDO,
                        tomado_en__lte=vencido,
                        intentos__lt=MAX_INTENTOS_TRABAJO,
                    )
                )
                .order_by("disponible_en", "id")
                .first()
            )
            if trabajo is None:
                return None
            trabajo.estado = EstadoTrabajoWhatsApp.PROCESANDO
            trabajo.intentos += 1
            trabajo.tomado_en = ahora
            trabajo.ultimo_error = None
            trabajo.save(
                update_fields=["estado", "intentos", "tomado_en", "ultimo_error"]
            )
            return trabajo

    def _procesar_disponibles(self) -> int:
        procesadas = 0
        while True:
            trabajo = self._reclamar()
            if trabajo is None:
                return procesadas
            trabajo_id = trabajo.id
            intentos = trabajo.intentos
            tomado_en = trabajo.tomado_en
            try:
                ejecutar_trabajo_whatsapp(trabajo_id)
            except Exception as error:
                ahora = timezone.now()
                estado = (
                    EstadoTrabajoWhatsApp.PENDIENTE
                    if intentos < MAX_INTENTOS_TRABAJO
                    else EstadoTrabajoWhatsApp.FALLIDO
                )
                espera = min(2 ** min(intentos - 1, 10), MAX_ESPERA_MINUTOS)
                TrabajoWhatsApp.objects.filter(
                    pk=trabajo_id,
                    estado=EstadoTrabajoWhatsApp.PROCESANDO,
                    intentos=intentos,
                    tomado_en=tomado_en,
                ).update(
                    estado=estado,
                    disponible_en=ahora + timedelta(minutes=espera),
                    tomado_en=None,
                    ultimo_error=str(error),
                )
                logger.exception(
                    "Falló el trabajo durable de WhatsApp %s (intento %s).",
                    trabajo_id,
                    intentos,
                )
            else:
                actualizada = TrabajoWhatsApp.objects.filter(
                    pk=trabajo_id,
                    estado=EstadoTrabajoWhatsApp.PROCESANDO,
                    intentos=intentos,
                    tomado_en=tomado_en,
                ).update(
                    estado=EstadoTrabajoWhatsApp.COMPLETADO,
                    completado_en=timezone.now(),
                    tomado_en=None,
                    ultimo_error=None,
                )
                procesadas += actualizada
            finally:
                close_old_connections()

    def _enviar_disponibles(self) -> int:
        ahora = timezone.now()
        conversaciones = list(
            Mensaje.objects.filter(
                direccion=Direccion.SALIENTE,
            )
            .filter(
                Q(estado_envio=EstadoEnvio.PENDIENTE_ENVIO)
                | Q(
                    estado_envio=EstadoEnvio.FALLIDO,
                    proximo_intento_envio__lte=ahora,
                    intentos_envio__lt=MAX_INTENTOS_ENVIO,
                )
            )
            .values_list("conversacion_id", flat=True)
            .distinct()
        )
        enviados = 0
        for conversacion_id in conversaciones:
            enviados += enviar_pendientes(conversacion_id)
            close_old_connections()
        return enviados

    def _rehabilitar_fallidos(self) -> None:
        ahora = timezone.now()
        TrabajoWhatsApp.objects.filter(
            estado=EstadoTrabajoWhatsApp.FALLIDO
        ).update(
            estado=EstadoTrabajoWhatsApp.PENDIENTE,
            intentos=0,
            disponible_en=ahora,
            tomado_en=None,
            completado_en=None,
            ultimo_error=None,
        )
        Mensaje.objects.filter(
            direccion=Direccion.SALIENTE,
            estado_envio=EstadoEnvio.FALLIDO,
            intentos_envio__gte=MAX_INTENTOS_ENVIO,
        ).exclude(error="ventana_24h_cerrada").update(
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            intentos_envio=0,
            proximo_intento_envio=None,
            error=None,
        )
