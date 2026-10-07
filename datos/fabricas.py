from datetime import date
from itertools import count
from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone

from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    ContactoWhatsapp,
    Conversacion,
    ConsultaBot,
    Cuota,
    Derivacion,
    EstadoAccion,
    EstadoAlerta,
    EstadoConsulta,
    EstadoConversacion,
    EstadoCuota,
    EstadoEnvio,
    EstadoPoliza,
    EstadoSiniestro,
    Funcionario,
    Mensaje,
    ModoConversacion,
    OrigenAlerta,
    Poliza,
    Prioridad,
    TipoAccion,
    TipoAlerta,
    TipoConsulta,
    TipoSeguro,
)

_funcionarios = count(1)
_clientes = count(1)
_contactos = count(1)
_polizas = count(1)
_cuotas = count(0)
_mensajes = count(1)
_consultas = count(1)

_TIPOS_SEGURO = (
    ("automotor", "Automotor"),
    ("hogar", "Hogar"),
    ("vida", "Vida"),
    ("comercio", "Comercio"),
    ("moto", "Moto"),
)

_TIPOS_CONSULTA = (
    ("saludo", "Saludo", "bot_responde"),
    ("saldo", "Saldo pendiente", "bot_responde"),
    ("vencimiento", "Vencimiento de póliza", "bot_responde"),
    ("siniestro", "Denuncia de siniestro", "bot_responde"),
    ("siniestro_urgente", "Siniestro urgente", "derivar_humano"),
    ("cotizacion", "Cotización", "derivar_humano"),
    ("consulta_cobertura", "Consulta de cobertura", "derivar_humano"),
    ("reclamo", "Reclamo", "derivar_humano"),
    ("baja", "Baja de póliza", "requiere_aprobacion"),
    ("modificacion", "Modificación de póliza", "requiere_aprobacion"),
    ("prompt_injection", "Intento de manipulación del bot", "seguridad"),
    ("otro", "Otra consulta", "derivar_humano"),
)


def crear_catalogos() -> None:
    for codigo, nombre in _TIPOS_SEGURO:
        TipoSeguro.objects.update_or_create(
            codigo=codigo,
            defaults={"nombre": nombre},
        )

    for codigo, nombre, politica in _TIPOS_CONSULTA:
        TipoConsulta.objects.update_or_create(
            codigo=codigo,
            defaults={"nombre": nombre, "politica": politica},
        )


def crear_funcionario(
    nombre: str = "Graciela",
    puede_aprobar: bool = True,
    **campos: Any,
) -> Funcionario:
    numero = next(_funcionarios)
    valores: dict[str, Any] = {
        "nombre": nombre,
        "email": f"funcionario{numero}@tests.local",
        "rol": "administracion" if puede_aprobar else "operador",
        "puede_aprobar": puede_aprobar,
        "activo": True,
    }
    valores.update(campos)
    funcionario = Funcionario.objects.create(**valores)
    get_user_model().objects.create_user(
        username=funcionario.email,
        email=funcionario.email,
        password="clave-de-prueba",
    )
    return funcionario


def crear_cliente(**campos: Any) -> Cliente:
    numero = next(_clientes)
    valores: dict[str, Any] = {
        "dni": f"{10_000_000 + numero:08d}",
        "nombre": "Cliente",
        "apellido": f"De Prueba {numero}",
        "activo": True,
    }
    valores.update(campos)
    return Cliente.objects.create(**valores)


def crear_contacto(
    cliente: Cliente | None = None, **campos: Any
) -> ContactoWhatsapp:
    numero = next(_contactos)
    valores: dict[str, Any] = {
        "numero": f"+549{numero:010d}",
        "cliente": cliente,
    }
    valores.update(campos)
    return ContactoWhatsapp.objects.create(**valores)


def crear_poliza(
    cliente: Cliente | None = None, **campos: Any
) -> Poliza:
    crear_catalogos()
    numero = next(_polizas)
    valores: dict[str, Any] = {
        "numero_poliza": f"POL-{numero:05d}",
        "cliente": cliente or crear_cliente(),
        "tipo_seguro": TipoSeguro.objects.get(codigo="automotor"),
        "cobertura": "intermedia",
        "estado": EstadoPoliza.VIGENTE,
        "fecha_inicio": date(2025, 1, 1),
        "fecha_vencimiento": date(2026, 1, 1),
        "prima_mensual": "1000.00",
    }
    valores.update(campos)
    return Poliza.objects.create(**valores)


def crear_cuota(poliza: Poliza, **campos: Any) -> Cuota:
    numero = next(_cuotas)
    periodo = date(2025 + numero // 12, numero % 12 + 1, 1)
    valores: dict[str, Any] = {
        "poliza": poliza,
        "periodo": periodo,
        "importe": "1000.00",
        "vencimiento": periodo.replace(day=15),
        "estado": EstadoCuota.PENDIENTE,
    }
    valores.update(campos)
    return Cuota.objects.create(**valores)


def crear_conversacion(
    contacto: ContactoWhatsapp | None = None, **campos: Any
) -> Conversacion:
    valores: dict[str, Any] = {
        "contacto": contacto or crear_contacto(),
        "estado": EstadoConversacion.ABIERTA,
        "modo": ModoConversacion.BOT,
    }
    valores.update(campos)
    return Conversacion.objects.create(**valores)


def crear_mensaje(conversacion: Conversacion, **campos: Any) -> Mensaje:
    numero = next(_mensajes)
    valores: dict[str, Any] = {
        "conversacion": conversacion,
        "direccion": "entrante",
        "emisor": "cliente",
        "texto": f"Mensaje de prueba {numero}",
        "estado_envio": EstadoEnvio.RECIBIDO,
        "wa_message_id": f"wamid.test.{numero}",
        "fecha_hora": timezone.now(),
    }
    valores.update(campos)
    return Mensaje.objects.create(**valores)


def crear_consulta(
    conversacion: Conversacion | None = None,
    tipo: str = "saludo",
    **campos: Any,
) -> ConsultaBot:
    crear_catalogos()
    numero = next(_consultas)
    valores: dict[str, Any] = {
        "codigo_caso": f"CASO-{numero:03d}",
        "fecha_hora": timezone.now(),
        "contacto": conversacion.contacto if conversacion else None,
        "conversacion": conversacion,
        "tipo_consulta": TipoConsulta.objects.get(codigo=tipo),
        "estado": EstadoConsulta.PENDIENTE_REVISION,
    }
    valores.update(campos)
    return ConsultaBot.objects.create(**valores)


def crear_alerta(consulta: ConsultaBot, **campos: Any) -> Alerta:
    valores: dict[str, Any] = {
        "consulta": consulta,
        "tipo": TipoAlerta.DATO_INVENTADO,
        "severidad": "alta",
        "descripcion": "Alerta de prueba",
        "origen": OrigenAlerta.AUTOMATICA,
        "estado": EstadoAlerta.ABIERTA,
    }
    valores.update(campos)
    return Alerta.objects.create(**valores)


def crear_accion(
    consulta: ConsultaBot, **campos: Any
) -> AccionPendiente:
    valores: dict[str, Any] = {
        "consulta": consulta,
        "tipo_accion": TipoAccion.BAJA_POLIZA,
        "estado": EstadoAccion.PENDIENTE,
        "parametros": {},
    }
    valores.update(campos)
    return AccionPendiente.objects.create(**valores)


def crear_derivacion(
    consulta: ConsultaBot,
    derivado_a: Funcionario,
    **campos: Any,
) -> Derivacion:
    valores: dict[str, Any] = {
        "consulta": consulta,
        "derivado_a": derivado_a,
        "prioridad": Prioridad.NORMAL,
        "motivo": "Derivación de prueba",
    }
    valores.update(campos)
    return Derivacion.objects.create(**valores)
