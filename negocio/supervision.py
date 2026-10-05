from __future__ import annotations

from django.utils import timezone

from datos.models import Conversacion, ConsultaBot, Mensaje
from negocio.errores import EstadoInvalido, PermisoDenegado


def _funcionario_aprobador(funcionario_id: int):
    from datos.models import Funcionario

    funcionario = Funcionario.objects.filter(pk=funcionario_id, activo=True, puede_aprobar=True).first()
    if funcionario is None:
        raise PermisoDenegado("El funcionario no tiene permiso para supervisar.")
    return funcionario


def liberar_respuesta(mensaje_id: int, funcionario_id: int, texto_corregido: str | None = None) -> Mensaje:
    _funcionario_aprobador(funcionario_id)
    mensaje = Mensaje.objects.get(pk=mensaje_id)
    if mensaje.estado_envio != "retenido":
        raise EstadoInvalido("El mensaje ya no está retenido.")
    if texto_corregido is not None and texto_corregido.strip():
        mensaje.texto = texto_corregido.strip()
    mensaje.estado_envio = "pendiente_envio"
    mensaje.save(update_fields=["texto", "estado_envio"])
    return mensaje


def descartar_respuesta(mensaje_id: int, funcionario_id: int, motivo: str) -> Mensaje:
    _funcionario_aprobador(funcionario_id)
    mensaje = Mensaje.objects.get(pk=mensaje_id)
    if mensaje.estado_envio != "retenido":
        raise EstadoInvalido("El mensaje ya no está retenido.")
    mensaje.estado_envio = "descartado"
    mensaje.error = motivo
    mensaje.save(update_fields=["estado_envio", "error"])
    return mensaje


def tomar_conversacion(conversacion_id: int, funcionario_id: int) -> Conversacion:
    funcionario = _funcionario_aprobador(funcionario_id)
    conversacion = Conversacion.objects.get(pk=conversacion_id)
    conversacion.funcionario = funcionario
    conversacion.modo = "humano"
    conversacion.save(update_fields=["funcionario", "modo"])
    return conversacion


def devolver_al_bot(conversacion_id: int, funcionario_id: int) -> Conversacion:
    _funcionario_aprobador(funcionario_id)
    conversacion = Conversacion.objects.get(pk=conversacion_id)
    conversacion.modo = "bot"
    conversacion.funcionario = None
    conversacion.save(update_fields=["modo", "funcionario"])
    return conversacion


def responder_como_humano(conversacion_id: int, funcionario_id: int, texto: str) -> Mensaje:
    _funcionario_aprobador(funcionario_id)
    conversacion = Conversacion.objects.get(pk=conversacion_id)
    return Mensaje.objects.create(
        conversacion=conversacion,
        direccion="saliente",
        emisor="funcionario",
        texto=texto,
        estado_envio="pendiente_envio",
        fecha_hora=timezone.now(),
        funcionario_id=funcionario_id,
    )


def reabrir_consulta(consulta_id: int, funcionario_id: int) -> ConsultaBot:
    _funcionario_aprobador(funcionario_id)
    consulta = ConsultaBot.objects.get(pk=consulta_id)
    consulta.estado = "abierto"
    consulta.save(update_fields=["estado"])
    return consulta
