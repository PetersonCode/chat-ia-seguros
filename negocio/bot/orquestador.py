"""El bot: de un mensaje entrante a una respuesta guardada (y quizá retenida).

Secuencia (AC-T3-30 a AC-T3-44):
    modo humano → idempotencia → consulta (`CASO-###`) → `evaluar_entrada`
    → clasificar → política → armar respuesta → `evaluar_salida`
    → guardar → enviar

Todo pasa dentro de `transaction.atomic`; el envío al cliente queda para
después del commit. El LLM solo clasifica y, como mucho, redacta el saludo:
los datos salen de `selectors` y se insertan en las plantillas fijas (R12).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection, transaction
from django.utils import timezone

from datos.models import (
    Alerta,
    ConsultaBot,
    Direccion,
    Emisor,
    EstadoAlerta,
    EstadoConsulta,
    EstadoEnvio,
    EstadoPoliza,
    Mensaje,
    OrigenAlerta,
    Politica,
    TipoConsulta,
)
from datos.selectors import (
    funcionario_por_nombre,
    historial_reciente,
    polizas_vigentes,
    resumen_polizas,
)
from negocio.acciones import derivar, solicitar_accion
from negocio.bot import plantillas
from negocio.bot.clasificador import clasificar as clasificar_por_reglas
from negocio.bot.guardrails import AlertaDetectada, evaluar_entrada, evaluar_salida
from negocio.bot.llm import charlar_con_llm, clasificar_con_llm, cliente_llm
from negocio.bot.plantillas import formatear_fecha, formatear_monto
from negocio.whatsapp import enviar_pendientes

logger = logging.getLogger(__name__)

# Llave del advisory lock que serializa la numeración de casos (AC-T3-30).
LOCK_CODIGO_CASO = 4242

# Qué acción pide cada tipo con política `requiere_aprobacion` (sección 3).
ACCION_POR_TIPO = {
    "baja": "baja_poliza",
    "modificacion": "modificar_poliza",
}

# A quién se deriva cada tipo con política `derivar_humano` (sección 3).
DERIVACION_POR_TIPO = {
    "siniestro_urgente": ("Roberto", "urgente"),
}
DERIVACION_POR_DEFECTO = ("Graciela", "normal")

ACLARACION_SIN_POLIZA_UNICA = "el cliente tiene 0 o varias pólizas vigentes"


@dataclass
class ResultadoBot:
    ignorado: bool
    tipo_consulta: str | None
    mensaje_respuesta_id: int | None
    retenido: bool
    alertas: list[str]


@dataclass
class _Respuesta:
    """Lo que el bot va a decir, más lo que hay que hacer además de decirlo."""

    texto: str
    datos_verificados: frozenset[str] = frozenset()
    derivar_a: tuple[str, str] | None = None
    accion: tuple[str, int | None, dict] | None = None
    alertas_entrada: list[AlertaDetectada] = field(default_factory=list)


def _proximo_codigo_caso() -> str:
    """`CASO-###` = el mayor existente + 1, serializado por advisory lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_CODIGO_CASO])
        cursor.execute(
            """
            SELECT COALESCE(MAX(SUBSTRING(codigo_caso FROM 'CASO-([0-9]+)$')::int), 0)
            FROM consultas_bot
            WHERE codigo_caso ~ '^CASO-[0-9]+$'
            """
        )
        maximo = cursor.fetchone()[0] or 0
    return f"CASO-{maximo + 1:03d}"


def _funcionario_destino(nombre: str):
    """El funcionario por nombre; si no está, el primer aprobador activo."""
    from datos.models import Funcionario

    funcionario = funcionario_por_nombre(nombre)
    if funcionario is not None:
        return funcionario
    return Funcionario.objects.filter(activo=True, puede_aprobar=True).order_by("id").first()


def _respuesta_saldo(cliente_id: int) -> _Respuesta:
    resumen = list(resumen_polizas(cliente_id))
    if not resumen:
        return _Respuesta(plantillas.SIN_POLIZAS, derivar_a=DERIVACION_POR_DEFECTO)
    total = sum((fila.saldo_pendiente or Decimal("0")) for fila in resumen)
    if total <= 0:
        return _Respuesta(plantillas.SIN_SALDO)
    proximos = sorted(
        fila.proximo_vencimiento_pago
        for fila in resumen
        if fila.proximo_vencimiento_pago is not None
    )
    monto = formatear_monto(total)
    fecha = formatear_fecha(proximos[0] if proximos else None)
    return _Respuesta(
        plantillas.SALDO.format(monto=monto, fecha=fecha),
        datos_verificados=frozenset({monto, fecha}),
    )


def _respuesta_vencimiento(cliente_id: int) -> _Respuesta:
    resumen = list(resumen_polizas(cliente_id))
    if not resumen:
        return _Respuesta(plantillas.SIN_POLIZAS, derivar_a=DERIVACION_POR_DEFECTO)
    lineas: list[str] = []
    verificados: set[str] = set()
    for fila in resumen:
        fecha = formatear_fecha(fila.fecha_vencimiento)
        lineas.append(
            plantillas.LINEA_VENCIMIENTO.format(
                numero_poliza=fila.numero_poliza,
                tipo_seguro=fila.tipo_seguro,
                fecha=fecha,
                marca=(
                    plantillas.MARCA_VENCIDA
                    if fila.estado == EstadoPoliza.VENCIDA
                    else ""
                ),
            )
        )
        verificados.update({fila.numero_poliza, fecha})
    return _Respuesta(
        plantillas.VENCIMIENTO.format(lineas="\n".join(lineas)),
        datos_verificados=frozenset(verificados),
    )


def _respuesta_requiere_aprobacion(tipo: str, cliente_id: int | None) -> _Respuesta:
    """AC-T3-37: la póliza solo se adjunta si hay exactamente una vigente."""
    vigentes = list(polizas_vigentes(cliente_id)) if cliente_id is not None else []
    if len(vigentes) == 1:
        poliza_id: int | None = vigentes[0].id
        parametros: dict = {}
    else:
        poliza_id = None
        parametros = {"aclaracion": ACLARACION_SIN_POLIZA_UNICA}
    return _Respuesta(
        plantillas.SOLICITUD_REGISTRADA,
        accion=(ACCION_POR_TIPO[tipo], poliza_id, parametros),
    )


def _respuesta_derivacion(tipo: str) -> _Respuesta:
    destino = DERIVACION_POR_TIPO.get(tipo, DERIVACION_POR_DEFECTO)
    texto = (
        plantillas.DERIVACION_URGENTE
        if tipo == "siniestro_urgente"
        else plantillas.DERIVACION
    )
    return _Respuesta(texto, derivar_a=destino)


def _respuesta_saludo(texto: str, historial: list[str], llm) -> _Respuesta:
    """AC-T3-36: el saludo puede venir del LLM, pero igual pasa por guardrails."""
    del_llm = charlar_con_llm(llm, texto, historial)
    return _Respuesta(del_llm or plantillas.SALUDO)


def _armar_respuesta(
    tipo: str, politica: str, *, cliente_id: int | None, texto: str, historial: list[str], llm
) -> _Respuesta:
    if politica == Politica.SEGURIDAD:
        return _Respuesta(plantillas.RECHAZO_SEGURIDAD)
    if politica == Politica.REQUIERE_APROBACION:
        return _respuesta_requiere_aprobacion(tipo, cliente_id)
    if politica == Politica.DERIVAR_HUMANO:
        return _respuesta_derivacion(tipo)

    # Política `bot_responde`: saludo, saldo, vencimiento, siniestro.
    if tipo == "saludo":
        return _respuesta_saludo(texto, historial, llm)
    if tipo == "siniestro":
        return _Respuesta(plantillas.SINIESTRO_INSTRUCCIONES)
    if cliente_id is None:
        # AC-T3-35: sin cliente no se puede dar información de la cuenta.
        return _Respuesta(plantillas.SIN_CLIENTE, derivar_a=DERIVACION_POR_DEFECTO)
    if tipo == "saldo":
        return _respuesta_saldo(cliente_id)
    if tipo == "vencimiento":
        return _respuesta_vencimiento(cliente_id)
    return _Respuesta(plantillas.DERIVACION, derivar_a=DERIVACION_POR_DEFECTO)


def _crear_alertas(
    consulta: ConsultaBot,
    alertas: list[AlertaDetectada],
    mensaje: Mensaje | None = None,
) -> None:
    for alerta in alertas:
        Alerta.objects.create(
            consulta=consulta,
            mensaje=mensaje,
            tipo=alerta.tipo,
            severidad=alerta.severidad,
            descripcion=alerta.descripcion,
            origen=OrigenAlerta.AUTOMATICA,
            estado=EstadoAlerta.ABIERTA,
        )


def _crear_saliente(
    conversacion, consulta: ConsultaBot, texto: str, estado: str
) -> Mensaje:
    return Mensaje.objects.create(
        conversacion=conversacion,
        consulta=consulta,
        direccion=Direccion.SALIENTE,
        emisor=Emisor.BOT,
        texto=texto,
        estado_envio=estado,
        fecha_hora=timezone.now(),
    )


def procesar_mensaje(mensaje_id: int) -> ResultadoBot:
    """Procesa un mensaje entrante y deja la respuesta del bot guardada."""
    mensaje = Mensaje.objects.select_related(
        "conversacion", "conversacion__contacto"
    ).get(pk=mensaje_id)
    conversacion = mensaje.conversacion

    # AC-T3-30: si un humano tomó la conversación, el bot no interviene.
    if conversacion.modo == "humano":
        return ResultadoBot(True, None, None, False, [])
    # AC-T3-30: idempotencia. El mensaje ya tiene su consulta, ya se procesó.
    if mensaje.consulta_id is not None:
        return ResultadoBot(True, None, None, False, [])

    texto = (mensaje.texto or "").strip()
    contacto = conversacion.contacto
    cliente_id = contacto.cliente_id if contacto else None

    alertas_entrada = evaluar_entrada(texto)
    llm = cliente_llm()
    historial = [
        previo.texto
        for previo in historial_reciente(conversacion.id)
        if previo.id != mensaje.id
    ]

    if alertas_entrada:
        # AC-T3-32: con inyección no se llama al LLM y se responde el rechazo.
        tipo = "prompt_injection"
    else:
        tipo = clasificar_con_llm(llm, texto, historial) or clasificar_por_reglas(texto)

    tipo_obj = TipoConsulta.objects.filter(codigo=tipo).first()
    if tipo_obj is None:
        logger.warning("Tipo de consulta desconocido (%s); se usa 'otro'.", tipo)
        tipo = "otro"
        tipo_obj = TipoConsulta.objects.get(codigo="otro")

    if alertas_entrada:
        respuesta = _Respuesta(plantillas.RECHAZO_SEGURIDAD)
    else:
        respuesta = _armar_respuesta(
            tipo,
            tipo_obj.politica,
            cliente_id=cliente_id,
            texto=texto,
            historial=historial,
            llm=llm,
        )

    alertas_salida = evaluar_salida(
        respuesta.texto,
        cliente_id=cliente_id,
        datos_verificados=respuesta.datos_verificados,
    )

    with transaction.atomic():
        consulta = ConsultaBot.objects.create(
            codigo_caso=_proximo_codigo_caso(),
            fecha_hora=timezone.now(),
            contacto=contacto,
            conversacion=conversacion,
            mensaje_usuario=texto,
            respuesta_bot=respuesta.texto,
            tipo_consulta=tipo_obj,
            estado=EstadoConsulta.ABIERTO,
        )
        mensaje.consulta = consulta
        mensaje.save(update_fields=["consulta"])

        _crear_alertas(consulta, alertas_entrada, mensaje)

        retenido = bool(alertas_salida)
        saliente = _crear_saliente(
            conversacion,
            consulta,
            respuesta.texto,
            EstadoEnvio.RETENIDO if retenido else EstadoEnvio.PENDIENTE_ENVIO,
        )
        _crear_alertas(consulta, alertas_salida, saliente)

        aviso: Mensaje | None = None
        if retenido:
            # AC-T3-43: el cliente recibe un aviso neutro y un humano revisa.
            aviso = _crear_saliente(
                conversacion,
                consulta,
                plantillas.AVISO_NEUTRO,
                EstadoEnvio.PENDIENTE_ENVIO,
            )

        if alertas_entrada or retenido:
            consulta.estado = EstadoConsulta.PENDIENTE_REVISION
            consulta.save(update_fields=["estado"])
        elif respuesta.accion is None and respuesta.derivar_a is None:
            consulta.estado = EstadoConsulta.CERRADO
            consulta.save(update_fields=["estado"])

        if respuesta.accion is not None:
            tipo_accion, poliza_id, parametros = respuesta.accion
            solicitar_accion(consulta.id, tipo_accion, poliza_id, parametros)

        destino = respuesta.derivar_a or (
            DERIVACION_POR_DEFECTO if retenido else None
        )
        if destino is not None:
            nombre, prioridad = destino
            funcionario = _funcionario_destino(nombre)
            if funcionario is not None:
                derivar(
                    consulta.id,
                    funcionario.id,
                    prioridad,
                    motivo=f"Derivación automática del bot ({tipo}).",
                )
            else:
                logger.warning("No hay aprobador activo para derivar la consulta %s.", consulta.id)

    transaction.on_commit(lambda: enviar_pendientes(conversacion.id))

    tipos = [alerta.tipo for alerta in alertas_entrada + alertas_salida]
    return ResultadoBot(
        ignorado=False,
        tipo_consulta=tipo,
        mensaje_respuesta_id=saliente.id,
        retenido=retenido,
        alertas=tipos,
    )
