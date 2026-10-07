"""Supervisión humana: qué hace un funcionario con lo que el bot retuvo.

Un mensaje `retenido` nunca sale solo: alguien lo libera tal cual, lo corrige o
lo descarta. Las tres cosas cierran las alertas que lo retuvieron, y las dos
primeras disparan el envío.

Aprobador obligatorio en `liberar_respuesta`, `descartar_respuesta` y
`reabrir_consulta` (contrato, sección 6).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from datos.models import (
    Conversacion,
    ConsultaBot,
    Direccion,
    Emisor,
    EstadoAlerta,
    EstadoConsulta,
    EstadoEnvio,
    Funcionario,
    Mensaje,
    ModoConversacion,
)
from datos.selectors import alertas_abiertas
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)
from negocio.reglas import ventana_24h_abierta
from negocio.whatsapp import enviar_pendientes

MOTIVO_MINIMO = 5
RESOLUCION_LIBERADA = "Liberada sin cambios"
RESOLUCION_CORREGIDA = "Respuesta corregida por el funcionario"


def _funcionario(funcionario_id: int, *, aprobador: bool) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id, activo=True).first()
    if funcionario is None:
        raise PermisoDenegado("El funcionario no existe o no está activo.")
    if aprobador and not funcionario.puede_aprobar:
        raise PermisoDenegado("Hace falta un funcionario con permiso de aprobación.")
    return funcionario


def _mensaje_retenido(mensaje_id: int) -> Mensaje:
    mensaje = (
        Mensaje.objects.select_related("conversacion", "consulta")
        .filter(pk=mensaje_id)
        .first()
    )
    if mensaje is None:
        raise NoEncontrado("El mensaje no existe.")
    if mensaje.estado_envio != EstadoEnvio.RETENIDO:
        raise EstadoInvalido("El mensaje ya no está retenido.")
    return mensaje


def _conversacion(conversacion_id: int) -> Conversacion:
    conversacion = Conversacion.objects.filter(pk=conversacion_id).first()
    if conversacion is None:
        raise NoEncontrado("La conversación no existe.")
    return conversacion


def _cerrar_alertas(
    mensaje: Mensaje, funcionario: Funcionario, estado: str, resolucion: str
) -> None:
    alertas_abiertas(mensaje_id=mensaje.id).update(
        estado=estado,
        resuelta_por=funcionario,
        resuelta_en=timezone.now(),
        resolucion=resolucion,
    )


def _registrar_revision(
    consulta: ConsultaBot | None, funcionario: Funcionario, texto: str
) -> None:
    if consulta is None:
        return
    consulta.respuesta_corregida = texto
    consulta.revisado_por = funcionario
    consulta.revisado_en = timezone.now()
    consulta.save(
        update_fields=["respuesta_corregida", "revisado_por", "revisado_en"]
    )


def liberar_respuesta(
    mensaje_id: int, funcionario_id: int, texto_corregido: str | None = None
) -> Mensaje:
    """Libera la respuesta retenida, tal cual o reemplazada por otra."""
    funcionario = _funcionario(funcionario_id, aprobador=True)
    mensaje = _mensaje_retenido(mensaje_id)
    conversacion = mensaje.conversacion
    corregido = (texto_corregido or "").strip()

    with transaction.atomic():
        if corregido:
            # AC-T3-25: lo del bot se descarta y sale el texto del funcionario.
            mensaje.estado_envio = EstadoEnvio.DESCARTADO
            mensaje.save(update_fields=["estado_envio"])
            sale = Mensaje.objects.create(
                conversacion=conversacion,
                consulta=mensaje.consulta,
                direccion=Direccion.SALIENTE,
                emisor=Emisor.FUNCIONARIO,
                funcionario=funcionario,
                texto=corregido,
                estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
                fecha_hora=timezone.now(),
            )
            _cerrar_alertas(
                mensaje, funcionario, EstadoAlerta.RESUELTA, RESOLUCION_CORREGIDA
            )
            _registrar_revision(mensaje.consulta, funcionario, corregido)
        else:
            # AC-T3-24: sale tal cual y las alertas quedan descartadas.
            mensaje.estado_envio = EstadoEnvio.PENDIENTE_ENVIO
            mensaje.save(update_fields=["estado_envio"])
            sale = mensaje
            _cerrar_alertas(
                mensaje, funcionario, EstadoAlerta.DESCARTADA, RESOLUCION_LIBERADA
            )

    enviar_pendientes(conversacion.id)
    sale.refresh_from_db()
    return sale


def descartar_respuesta(mensaje_id: int, funcionario_id: int, motivo: str) -> Mensaje:
    """Descarta la respuesta retenida: no sale nada al cliente (AC-T3-26)."""
    if not motivo or len(motivo.strip()) < MOTIVO_MINIMO:
        raise DatosInvalidos(
            f"El motivo tiene que tener al menos {MOTIVO_MINIMO} caracteres."
        )
    funcionario = _funcionario(funcionario_id, aprobador=True)
    mensaje = _mensaje_retenido(mensaje_id)
    motivo = motivo.strip()

    with transaction.atomic():
        mensaje.estado_envio = EstadoEnvio.DESCARTADO
        mensaje.error = motivo
        mensaje.save(update_fields=["estado_envio", "error"])
        _cerrar_alertas(mensaje, funcionario, EstadoAlerta.RESUELTA, motivo)
    return mensaje


def tomar_conversacion(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """El funcionario se queda con la conversación y el bot deja de responder."""
    funcionario = _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
    conversacion.modo = ModoConversacion.HUMANO
    conversacion.funcionario = funcionario
    conversacion.save(update_fields=["modo", "funcionario"])
    return conversacion


def devolver_al_bot(conversacion_id: int, funcionario_id: int) -> Conversacion:
    """Devuelve la conversación al bot y la deja sin responsable."""
    _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
    conversacion.modo = ModoConversacion.BOT
    conversacion.funcionario = None
    conversacion.save(update_fields=["modo", "funcionario"])
    return conversacion


def responder_como_humano(
    conversacion_id: int, funcionario_id: int, texto: str
) -> Mensaje:
    """Mensaje escrito por un funcionario. Requiere la ventana de 24 h abierta."""
    if not texto or not texto.strip():
        raise DatosInvalidos("El mensaje no puede estar vacío.")
    funcionario = _funcionario(funcionario_id, aprobador=False)
    conversacion = _conversacion(conversacion_id)
    if not ventana_24h_abierta(
        conversacion.ultimo_mensaje_cliente_en, timezone.now()
    ):
        raise EstadoInvalido(
            "Pasaron más de 24 h desde el último mensaje del cliente.",
            codigo="ventana_24h_cerrada",
        )

    mensaje = Mensaje.objects.create(
        conversacion=conversacion,
        direccion=Direccion.SALIENTE,
        emisor=Emisor.FUNCIONARIO,
        funcionario=funcionario,
        texto=texto.strip(),
        estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
        fecha_hora=timezone.now(),
    )
    enviar_pendientes(conversacion.id)
    mensaje.refresh_from_db()
    return mensaje


def reabrir_consulta(consulta_id: int, funcionario_id: int) -> ConsultaBot:
    """Vuelve a poner en revisión una consulta que se había cerrado (AC-T3-29)."""
    _funcionario(funcionario_id, aprobador=True)
    consulta = ConsultaBot.objects.filter(pk=consulta_id).first()
    if consulta is None:
        raise NoEncontrado("La consulta no existe.")
    if consulta.estado != EstadoConsulta.CERRADO:
        raise EstadoInvalido("Solo se puede reabrir una consulta cerrada.")
    consulta.estado = EstadoConsulta.PENDIENTE_REVISION
    consulta.save(update_fields=["estado"])
    return consulta
