"""Clasificador por reglas (AC-T3-33).

Es el camino por defecto y también la red de contención cuando el LLM no está
configurado, falla o contesta un código fuera del catálogo (AC-T3-34).

El **orden** de las reglas es parte del criterio de aceptación y no es
arbitrario: lo más específico va primero, porque un mensaje como
"NECESITO HABLAR CON ALGUIEN URGENTE mi casa se inundó" también coincide con
`siniestro`, y queremos `siniestro_urgente`.
"""

import re
import unicodedata

# Orden de evaluación exigido por AC-T3-33.
ORDEN = (
    "siniestro_urgente",
    "baja",
    "modificacion",
    "reclamo",
    "saldo",
    "vencimiento",
    "siniestro",
    "cotizacion",
    "consulta_cobertura",
    "saludo",
)

# Patrones por tipo, ya sin acentos y en minúsculas (ver `normalizar`).
PATRONES: dict[str, tuple[str, ...]] = {
    # Urgencia explícita o un siniestro en curso que no admite espera.
    "siniestro_urgente": (
        "urgente",
        "urgencia",
        "emergencia",
        "se inundo",
        "se esta inundando",
        "se incendio",
        "incendio",
        "ahora mismo",
        "es grave",
        "accidente grave",
    ),
    "baja": (
        "dar de baja",
        "darla de baja",
        "de baja",
        "baja del seguro",
        "baja de la poliza",
        "cancelar la poliza",
        "cancelar el seguro",
        "anular la poliza",
        "quiero cancelar",
        "no quiero mas el seguro",
    ),
    "modificacion": (
        "agregar",
        "sumar a",
        "conductor",
        "modificar",
        "cambiar",
        "actualizar mis datos",
        "cambio de domicilio",
    ),
    "reclamo": (
        "reclamo",
        "reclamar",
        "me cobraron de mas",
        "cobraron de mas",
        "cobro mal",
        "cobro de mas",
        "queja",
        "reembolso",
        "devolucion del dinero",
    ),
    "saldo": (
        "saldo",
        "cuanto debo",
        "cuanto me falta",
        "falta pagar",
        "tengo que pagar",
        "deuda",
        "debo pagar",
        "estoy al dia",
        "mi cuenta corriente",
    ),
    "vencimiento": (
        "vence",
        "vencimiento",
        "vencen",
        "vigencia",
        "hasta cuando",
        "cuando se renueva",
        "renovacion",
    ),
    "siniestro": (
        "siniestro",
        "choque",
        "choco",
        "chocaron",
        "accidente",
        "me robaron",
        "robo",
        "granizo",
        "denuncia",
        "el dano",
        "los danos",
    ),
    "cotizacion": (
        "cotizacion",
        "cotizar",
        "cuanto cuesta",
        "cuanto sale",
        "cuanto saldria",
        "precio",
        "presupuesto",
        "quiero asegurar",
        "asegurar una",
        "asegurar un",
        "contratar un seguro",
    ),
    "consulta_cobertura": (
        "cobertura",
        "cubre",
        "esta cubierto",
        "clausula",
        "condiciones de la poliza",
        "que incluye",
    ),
    "saludo": (
        "hola",
        "buenas",
        "buen dia",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "que tal",
        "gracias",
    ),
}


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para que 'Chocó' y 'choco' sean lo mismo."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_acentos.lower()).strip()


def clasificar(texto: str) -> str:
    """Devuelve el código de `TipoConsulta` para un mensaje del cliente."""
    normalizado = normalizar(texto)
    if not normalizado:
        return "otro"
    for tipo in ORDEN:
        if any(patron in normalizado for patron in PATRONES[tipo]):
            return tipo
    return "otro"
