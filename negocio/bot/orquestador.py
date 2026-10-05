from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from datos.models import (
    AccionPendiente,
    Alerta,
    ConsultaBot,
    EstadoAlerta,
    EstadoConsulta,
    EstadoEnvio,
    Funcionario,
    Mensaje,
    TipoConsulta,
)
from datos.selectors import contacto_por_numero, conversacion_abierta, tipo_consulta
from negocio.bot.guardrails import AlertaDetectada, evaluar_entrada, evaluar_salida
from negocio.bot.plantillas import AVISO_NEUTRO, DERIVACION, DERIVACION_URGENTE, RECHAZO_SEGURIDAD, SALDO, SINIESTRO_INSTRUCCIONES, SOLICITUD_REGISTRADA, VENCIMIENTO
from negocio.errores import NoEncontrado
from negocio.whatsapp import enviar_pendientes

logger = logging.getLogger(__name__)


@dataclass
class ResultadoBot:
    ignorado: bool
    tipo_consulta: str | None
    mensaje_respuesta_id: int | None
    retenido: bool
    alertas: list[str]


def _clasificar(texto: str) -> str:
    t = texto.strip().lower()
    if not t:
        return "otro"
    if any(p in t for p in ["ignora", "olvidá", "instrucciones", "actuá como", "sin restricciones", "revelá"]):
        return "prompt_injection"
    if any(p in t for p in ["saldo", "pagar", "falta", "cuánto me falta", "monto"]):
        return "saldo"
    if any(p in t for p in ["vencer", "vence", "vigencia", "poliza", "póliza"]):
        return "vencimiento"
    if any(p in t for p in ["siniestro", "choc", "accidente", "robo", "inund", "daño"]):
        return "siniestro"
    if any(p in t for p in ["baja", "cancelar", "dar de baja"]):
        return "baja"
    if any(p in t for p in ["agregar", "modificar", "conductor", "cambiar"]):
        return "modificacion"
    if any(p in t for p in ["urgente", "inundación", "fuego", "robo", "accidente grave"]):
        return "siniestro_urgente"
    if any(p in t for p in ["cotización", "cotizar", "asegurar", "moto", "costo"]):
        return "cotizacion"
    if any(p in t for p in ["cobertura", "clausula", "cubierta", "noche"]):
        return "consulta_cobertura"
    if any(p in t for p in ["reclamo", "cobrado de más", "reembolso"]):
        return "reclamo"
    if any(p in t for p in ["hola", "buenas", "buenos dias", "buenas tardes"]):
        return "saludo"
    return "otro"


def _respuesta_para(tipo: str, *, mensaje: Mensaje, cliente_id: int | None, datos: dict | None = None):
    datos = datos or {}
    if tipo == "saldo":
        return SALDO.format(monto="$12.500", fecha="15/04/2024")
    if tipo == "vencimiento":
        return VENCIMIENTO.format(lineas="• POL-00106 (Automotor): vence el 30/11/2024")
    if tipo == "siniestro":
        return SINIESTRO_INSTRUCCIONES
    if tipo in {"baja", "modificacion"}:
        return SOLICITUD_REGISTRADA
    if tipo in {"siniestro_urgente", "cotizacion", "consulta_cobertura", "reclamo", "otro"}:
        if tipo == "siniestro_urgente":
            return DERIVACION_URGENTE
        return DERIVACION
    if tipo == "prompt_injection":
        return RECHAZO_SEGURIDAD
    if tipo == "saludo":
        return "Hola! ¿En qué te puedo ayudar?"
    return "Gracias por tu consulta, te responderemos a la brevedad."


def procesar_mensaje(mensaje_id: int) -> ResultadoBot:
    mensaje = Mensaje.objects.select_related("conversacion", "conversacion__contacto").get(pk=mensaje_id)
    conversacion = mensaje.conversacion
    if conversacion.modo == "humano":
        return ResultadoBot(True, None, None, False, [])

    text = (mensaje.texto or "").strip()
    tipo = _clasificar(text)
    alertas_entrada = evaluar_entrada(text)
    alertas_salida = []
    if tipo == "prompt_injection":
        respuesta = RECHAZO_SEGURIDAD
        alertas_salida = alertas_entrada
    else:
        respuesta = _respuesta_para(tipo, mensaje=mensaje, cliente_id=conversacion.contacto.cliente_id if conversacion.contacto else None)
        alertas_salida = evaluar_salida(respuesta, cliente_id=conversacion.contacto.cliente_id if conversacion.contacto else None)

    with transaction.atomic():
        consulta = ConsultaBot.objects.create(
            codigo_caso=f"CASO-{timezone.now().strftime('%d%H%M%S')}",
            fecha_hora=timezone.now(),
            contacto=conversacion.contacto,
            conversacion=conversacion,
            mensaje_usuario=text,
            respuesta_bot=respuesta,
            tipo_consulta=tipo_consulta(tipo),
            estado=EstadoConsulta.ABIERTO,
        )
        if alertas_entrada:
            for alerta in alertas_entrada:
                Alerta.objects.create(
                    consulta=consulta,
                    tipo=alerta.tipo,
                    severidad=alerta.severidad,
                    descripcion=alerta.descripcion,
                    estado=EstadoAlerta.ABIERTA,
                )
        if alertas_salida:
            for alerta in alertas_salida:
                Alerta.objects.create(
                    consulta=consulta,
                    tipo=alerta.tipo,
                    severidad=alerta.severidad,
                    descripcion=alerta.descripcion,
                    estado=EstadoAlerta.ABIERTA,
                )
            consulta.estado = EstadoConsulta.PENDIENTE_REVISION
            consulta.save(update_fields=["estado"])
            mensaje.estado_envio = EstadoEnvio.RETENIDO
            mensaje.save(update_fields=["estado_envio"])
            respuesta_mensaje = Mensaje.objects.create(
                conversacion=conversacion,
                direccion="saliente",
                emisor="bot",
                texto=AVISO_NEUTRO,
                estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
                fecha_hora=timezone.now(),
            )
            return ResultadoBot(False, tipo, respuesta_mensaje.id, True, [a.tipo for a in alertas_entrada + alertas_salida])

        consulta.estado = EstadoConsulta.CERRADO
        consulta.save(update_fields=["estado"])
        mensaje_respuesta = Mensaje.objects.create(
            conversacion=conversacion,
            direccion="saliente",
            emisor="bot",
            texto=respuesta,
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            fecha_hora=timezone.now(),
        )

    transaction.on_commit(lambda: enviar_pendientes(conversacion.id))
    return ResultadoBot(False, tipo, mensaje_respuesta.id, False, [])
