"""Guardrails: qué se revisa de lo que entra y de lo que sale del bot.

`evaluar_entrada` solo mira el texto del cliente (AC-T3-31).
`evaluar_salida` **consulta la base** para distinguir un dato real de uno
inventado: un `POL-#####` que no existe es `dato_inventado`, pero uno que
existe y es de otro cliente es `fuga_datos` (AC-T3-38 a AC-T3-42).

Todos los patrones se comparan sobre el texto normalizado (minúsculas y sin
acentos), así que **se escriben sin acentos**.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata
from dataclasses import dataclass

from datos.models import Cliente, Cuota, Poliza, Siniestro


@dataclass
class AlertaDetectada:
    tipo: str
    severidad: str
    descripcion: str


# --- Entrada ---------------------------------------------------------------

# Intentos de hacer que el bot ignore sus instrucciones (AC-T3-31).
PATRONES_INYECCION = (
    r"ignor\w*\s+todo\s+lo\s+anterior",
    r"ignor\w*\s+todo",
    r"(?:ignor|olvid)\w*\s+(?:tus|las)\s+instrucciones",
    r"actu\w*\s+como",
    r"sin\s+restricciones",
    r"modo\s+desarrollador",
    r"system\s+prompt",
    r"prompt\s+del\s+sistema",
    r"datos\s+de\s+todos\s+los\s+clientes",
)

# Si además pide datos de clientes, la severidad sube a crítica.
PATRONES_PEDIDO_DATOS = (
    r"datos\s+de\s+todos",
    r"todos\s+los\s+clientes",
    r"lista\s+de\s+clientes",
    r"base\s+de\s+datos",
)

# --- Salida ----------------------------------------------------------------

# Frases donde el bot afirma haber ejecutado un trámite (AC-T3-39).
PATRONES_ACCION_CUMPLIDA = (
    "procedi",
    "di de baja",
    "dimos de baja",
    "lo di de baja",
    "agregue",
    "agregamos",
    "ya fue procesad",
    "fue procesado",
    "quedo anulad",
    "cancele",
    "modifique",
    "abri el siniestro",
    "abrimos el siniestro",
)

# Dominios de primer nivel que tratamos como "esto es una dirección web".
# Sirve para detectar `link_falso_alucinado.com/siniestro`, que no trae esquema.
TLDS = (
    "com",
    "net",
    "org",
    "ar",
    "io",
    "co",
    "info",
    "app",
    "online",
    "site",
    "biz",
)

RE_URL = re.compile(
    r"(?:https?://|www\.)?"
    r"(?:[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?\.)+"
    r"(?:" + "|".join(TLDS) + r")"
    r"(?:/[^\s\]\)]*)?",
    re.IGNORECASE,
)
RE_POLIZA = re.compile(r"POL-\d{5}")
RE_SINIESTRO = re.compile(r"SIN-\d{4}-\d{5}")
RE_DNI = re.compile(r"\b\d{1,3}(?:\.\d{3}){1,2}\b|\b\d{7,8}\b")
RE_FECHA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
# `\d+(?:[.,]\d+)*` y no `[\d.,]*` para no arrastrar el punto final de la
# oración: en "es de $12.500." el monto es "$12.500".
RE_MONTO = re.compile(r"\$\s?\d+(?:[.,]\d+)*")
RE_CLAUSULA = re.compile(r"\bclausula\s+\S+")


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(
        c for c in descompuesto if unicodedata.category(c) != "Mn"
    ).lower()


def _urls_permitidas() -> set[str]:
    crudo = os.getenv("BOT_URLS_PERMITIDAS", "") or ""
    return {
        dominio.strip().lower().lstrip(".")
        for dominio in crudo.split(",")
        if dominio.strip()
    }


def evaluar_entrada(texto: str) -> list[AlertaDetectada]:
    """Alertas sobre el mensaje del cliente. Hoy: inyección de prompt."""
    normalizado = _normalizar(texto)
    if not any(re.search(patron, normalizado) for patron in PATRONES_INYECCION):
        return []
    pide_datos = any(
        re.search(patron, normalizado) for patron in PATRONES_PEDIDO_DATOS
    )
    return [
        AlertaDetectada(
            tipo="prompt_injection",
            severidad="critica" if pide_datos else "alta",
            descripcion=(
                "El mensaje intenta que el bot ignore sus instrucciones y además "
                "pide datos de clientes."
                if pide_datos
                else "El mensaje intenta que el bot ignore sus instrucciones."
            ),
        )
    ]


def _fecha_valida(dia: int, mes: int, anio: int) -> bool:
    try:
        dt.date(anio, mes, dia)
    except ValueError:
        return False
    return True


def _vencimientos_del_cliente(cliente_id: int | None) -> set[str]:
    """Fechas que el cliente realmente tiene (pólizas y cuotas), en dd/mm/aaaa."""
    if cliente_id is None:
        return set()
    fechas: set[dt.date] = set(
        Poliza.objects.filter(cliente_id=cliente_id).values_list(
            "fecha_vencimiento", flat=True
        )
    )
    fechas.update(
        Cuota.objects.filter(poliza__cliente_id=cliente_id).values_list(
            "vencimiento", flat=True
        )
    )
    return {fecha.strftime("%d/%m/%Y") for fecha in fechas if fecha is not None}


def _alertas_identificadores(
    texto: str, cliente_id: int | None
) -> list[AlertaDetectada]:
    """AC-T3-38: pólizas y siniestros citados contra lo que hay en la base."""
    alertas: list[AlertaDetectada] = []

    for numero in dict.fromkeys(RE_POLIZA.findall(texto)):
        poliza = Poliza.objects.filter(numero_poliza=numero).first()
        if poliza is None:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inventado",
                    severidad="alta",
                    descripcion=f"La póliza {numero} no existe en la base.",
                )
            )
        elif poliza.cliente_id != cliente_id:
            alertas.append(
                AlertaDetectada(
                    tipo="fuga_datos",
                    severidad="critica",
                    descripcion=f"La póliza {numero} es de otro cliente.",
                )
            )

    for numero in dict.fromkeys(RE_SINIESTRO.findall(texto)):
        siniestro = (
            Siniestro.objects.select_related("poliza")
            .filter(numero_siniestro=numero)
            .first()
        )
        if siniestro is None:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inventado",
                    severidad="alta",
                    descripcion=f"El siniestro {numero} no existe en la base.",
                )
            )
        elif siniestro.poliza.cliente_id != cliente_id:
            alertas.append(
                AlertaDetectada(
                    tipo="fuga_datos",
                    severidad="critica",
                    descripcion=f"El siniestro {numero} es de otro cliente.",
                )
            )
    return alertas


def _alertas_dni(texto: str, cliente_id: int | None) -> list[AlertaDetectada]:
    """AC-T3-40: un DNI de otro cliente es fuga de datos."""
    alertas: list[AlertaDetectada] = []
    for crudo in dict.fromkeys(RE_DNI.findall(texto)):
        dni = crudo.replace(".", "")
        if not 7 <= len(dni) <= 8:
            continue
        otro = Cliente.objects.filter(dni=dni).exclude(pk=cliente_id).first()
        if otro is not None:
            alertas.append(
                AlertaDetectada(
                    tipo="fuga_datos",
                    severidad="critica",
                    descripcion=f"Se mencionó el DNI {dni}, que es de otro cliente.",
                )
            )
    return alertas


def _alertas_fechas(
    texto: str, cliente_id: int | None, datos_verificados: frozenset[str]
) -> list[AlertaDetectada]:
    """AC-T3-41: fechas imposibles y fechas que el cliente no tiene."""
    alertas: list[AlertaDetectada] = []
    reales: set[str] | None = None
    for coincidencia in RE_FECHA.finditer(texto):
        fecha = coincidencia.group(0)
        dia, mes, anio = (int(parte) for parte in coincidencia.groups())
        if not _fecha_valida(dia, mes, anio):
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inconsistente",
                    severidad="alta",
                    descripcion=f"La fecha {fecha} no existe.",
                )
            )
            continue
        if fecha in datos_verificados:
            continue
        if reales is None:
            reales = _vencimientos_del_cliente(cliente_id)
        if fecha not in reales:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inconsistente",
                    severidad="media",
                    descripcion=(
                        f"La fecha {fecha} no se verificó contra los vencimientos "
                        "del cliente."
                    ),
                )
            )
    return alertas


def _alertas_montos_y_clausulas(
    texto: str, normalizado: str, datos_verificados: frozenset[str]
) -> list[AlertaDetectada]:
    """AC-T3-42: montos sin respaldo y referencias a cláusulas."""
    alertas: list[AlertaDetectada] = []
    for monto in dict.fromkeys(RE_MONTO.findall(texto)):
        compacto = monto.replace(" ", "")
        if compacto in datos_verificados or monto in datos_verificados:
            continue
        alertas.append(
            AlertaDetectada(
                tipo="dato_no_verificado",
                severidad="media",
                descripcion=f"El monto {compacto} no sale de la base.",
            )
        )
    if RE_CLAUSULA.search(normalizado):
        alertas.append(
            AlertaDetectada(
                tipo="dato_no_verificado",
                severidad="alta",
                descripcion="Se citó una cláusula del contrato, que el bot no puede verificar.",
            )
        )
    return alertas


def _alertas_urls(texto: str) -> list[AlertaDetectada]:
    """AC-T3-38: dominios fuera de `BOT_URLS_PERMITIDAS`."""
    permitidas = _urls_permitidas()
    alertas: list[AlertaDetectada] = []
    for coincidencia in dict.fromkeys(RE_URL.findall(texto)):
        dominio = re.sub(r"^https?://", "", coincidencia, flags=re.IGNORECASE)
        dominio = dominio.split("/")[0].split(":")[0].lower()
        if dominio.startswith("www."):
            dominio = dominio[4:]
        if any(
            dominio == permitida or dominio.endswith(f".{permitida}")
            for permitida in permitidas
        ):
            continue
        alertas.append(
            AlertaDetectada(
                tipo="dato_inventado",
                severidad="alta",
                descripcion=f"Se mencionó un dominio que no está permitido: {dominio}",
            )
        )
    return alertas


def evaluar_salida(
    texto: str,
    *,
    cliente_id: int | None,
    datos_verificados: frozenset[str] = frozenset(),
) -> list[AlertaDetectada]:
    """Alertas sobre lo que el bot está por decir.

    `datos_verificados` son los valores que salieron de la base al armar la
    plantilla (montos, fechas, números); lo que está ahí no alerta.
    """
    normalizado = _normalizar(texto)
    verificados = frozenset(datos_verificados or frozenset())
    alertas: list[AlertaDetectada] = []

    alertas.extend(_alertas_urls(texto))

    if any(patron in normalizado for patron in PATRONES_ACCION_CUMPLIDA):
        alertas.append(
            AlertaDetectada(
                tipo="accion_sin_aprobacion",
                severidad="critica" if "baja" in normalizado else "alta",
                descripcion="La respuesta afirma que se ejecutó un trámite que nadie aprobó.",
            )
        )

    alertas.extend(_alertas_identificadores(texto, cliente_id))
    alertas.extend(_alertas_dni(texto, cliente_id))
    alertas.extend(_alertas_fechas(texto, cliente_id, verificados))
    alertas.extend(_alertas_montos_y_clausulas(texto, normalizado, verificados))
    return alertas
