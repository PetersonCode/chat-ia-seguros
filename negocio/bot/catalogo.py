"""Qué seguros y compañías hay, y qué planes tiene cada una: la lista, sin el detalle.

El detalle de lo que cubre un plan solo se da cuando el cliente pregunta por una
póliza determinada (ver `negocio.coberturas`). Acá se contesta lo que cualquier
interesado o cliente puede saber: con quién trabajamos y qué planes ofrece cada una.
Todo sale de la base (compañías activas y planes activos), nada está escrito a mano.
"""

from __future__ import annotations

import re

from datos.models import Compania, PlanCobertura
from negocio.bot.clasificador import normalizar

SEGUROS = "autos, motos, camionetas y utilitarios"
ETIQUETA_NIVEL = {"basica": "básica", "intermedia": "intermedia", "total": "total"}
ORDEN_NIVEL = {"basica": 0, "intermedia": 1, "total": 2}

# Relleno de los nombres de compañía: no sirve para reconocerla.
RELLENO = frozenset({"de", "del", "la", "las", "los", "y", "seguros", "seguro", "aseguradora",
                     "compania", "companias", "generales", "general", "proteccion", "grupo"})

SUJETO_COMPANIAS = re.compile(r"\b(?:companias?|aseguradoras?|empresas?|marcas?)\b")
SUJETO_SEGUROS = re.compile(r"\bseguros\b|\b(?:tipos?|clases?|ramos?) de seguros?\b")
SUJETO_PLANES = re.compile(
    r"\b(?:coberturas|planes|servicios|categorias|opciones|productos|paquetes|alternativas|niveles|"
    r"tipos? de coberturas?|tipos? de planes?)\b"
)
VERBO = re.compile(
    r"\b(?:tienen|tenes|tiene|trabajan|trabajamos|trabaja|brindan|brinda|prestan|presta|ofrecen|ofrece|"
    r"manejan|maneja|comercializan|venden|operan|representan|hay|disponibles|cuentan|incluyen planes)\b"
)
PREGUNTA = re.compile(r"\?|\b(?:que|cuales|cual|cuantas|cuantos|con que|me podes decir|quisiera saber|quiero saber|"
                      r"necesito saber|decime|contame|pasame|mostrame)\b")
# Hablan de SU contrato o piden el detalle (qué cubre, qué diferencia hay, límites,
# exclusiones): eso lo contesta la póliza, no el catálogo.
PERSONAL = re.compile(
    r"\b(?:mi|mis|tengo|tenemos)\b|\bpol-\d+\b|\b(?:cubre|cubren|ampara|amparan|incluye|incluyen)\b|"
    r"\b(?:diferencias?|diferente|diferentes|comparar|compara|comparacion|detalles?|detallado|detallada|"
    r"limites?|franquicias?|exclusiones|excluye|excluyen|condiciones|clausulas?|precio|costo|cuesta|sale)\b"
)


def _distintivos(nombre: str) -> list[str]:
    return [p for p in normalizar(nombre).split() if p not in RELLENO]


def _sin_relleno(texto: str) -> str:
    return " ".join(p for p in normalizar(texto).split() if p not in {"de", "del", "la", "las", "los"})


def _companias_activas() -> list[Compania]:
    return list(Compania.objects.filter(activa=True).order_by("nombre"))


def _mencionadas(texto: str, companias: list[Compania]) -> list[Compania]:
    """Las compañías que el mensaje nombra (por su nombre distintivo)."""
    limpio = _sin_relleno(texto)
    encontradas = []
    for compania in companias:
        claves = _distintivos(compania.nombre)
        if not claves:
            continue
        frase = " ".join(p for p in claves if p not in {"de", "del", "la"})
        if re.search(rf"\b{re.escape(frase)}\b", limpio) or (len(claves[0]) >= 4 and re.search(rf"\b{re.escape(claves[0])}\b", limpio)):
            encontradas.append(compania)
    return encontradas


def _planes_por_compania(companias: list[Compania]) -> dict[int, list[PlanCobertura]]:
    planes: dict[int, list[PlanCobertura]] = {c.id: [] for c in companias}
    for plan in PlanCobertura.objects.filter(activo=True, compania_id__in=list(planes)).order_by("id"):
        planes[plan.compania_id].append(plan)
    for lista in planes.values():
        lista.sort(key=lambda p: (ORDEN_NIVEL.get(p.nivel or "", 9), p.id))
    return planes


def _linea_plan(plan: PlanCobertura) -> str:
    nivel = f" (cobertura {ETIQUETA_NIVEL[plan.nivel]})" if plan.nivel in ETIQUETA_NIVEL else ""
    return f"• {plan.nombre}{nivel}"


def _lista_companias(companias: list[Compania]) -> str:
    return "\n".join(f"• {c.nombre}" for c in companias)


CIERRE = (
    "Si querés el detalle de lo que cubre una póliza, preguntame por la tuya "
    "(por ejemplo «¿qué cubre mi póliza?»). Y si querés asegurar tu vehículo, escribime «quiero asegurar mi auto»."
)


def respuesta_companias(companias: list[Compania]) -> str:
    return (
        f"Trabajamos con seguros para {SEGUROS}, con estas compañías:\n{_lista_companias(companias)}\n\n"
        "Si querés saber qué planes tiene alguna, preguntame por esa compañía."
    )


def respuesta_planes(companias: list[Compania], elegidas: list[Compania]) -> str | None:
    """Los planes de las compañías nombradas, o de todas si no se nombró ninguna."""
    destino = elegidas or companias
    planes = _planes_por_compania(destino)
    con_planes = [c for c in destino if planes[c.id]]
    if not con_planes:
        return None
    nombres = {c.id: tuple((p.nombre, p.nivel) for p in planes[c.id]) for c in con_planes}
    if len(set(nombres.values())) == 1 and not elegidas:
        # Todas ofrecen lo mismo: se dice una sola vez.
        lista = "\n".join(_linea_plan(p) for p in planes[con_planes[0].id])
        return (
            "Estos son los planes que ofrecen nuestras compañías:\n"
            f"{lista}\n\nCompañías: {', '.join(c.nombre for c in con_planes)}.\n\n{CIERRE}"
        )
    bloques = []
    for compania in con_planes:
        bloques.append(f"{compania.nombre}:\n" + "\n".join(_linea_plan(p) for p in planes[compania.id]))
    return "Estos son los planes disponibles:\n\n" + "\n\n".join(bloques) + f"\n\n{CIERRE}"


def responder(texto: str) -> str | None:
    """La lista de compañías o de planes si el mensaje la pide; `None` si es otra cosa."""
    normalizado = normalizar(texto)
    if not normalizado or PERSONAL.search(normalizado) or not PREGUNTA.search(normalizado):
        return None
    habla_de_planes = bool(SUJETO_PLANES.search(normalizado))
    habla_de_companias = bool(SUJETO_COMPANIAS.search(normalizado) or SUJETO_SEGUROS.search(normalizado))
    if not (habla_de_planes or habla_de_companias) or not VERBO.search(normalizado):
        return None
    companias = _companias_activas()
    if not companias:
        return None
    nombradas = _mencionadas(texto, companias)
    if habla_de_planes or nombradas:
        planes = respuesta_planes(companias, nombradas)
        if planes:
            return planes
    return respuesta_companias(companias)
