from datetime import timedelta
from decimal import Decimal

RANGO_SEVERIDAD = {"baja": 1, "media": 2, "alta": 3, "critica": 4}


def severidad_por_rango(rango: int) -> str | None:
    if rango == 0:
        return None
    if 1 <= rango <= 4:
        return {1: "baja", 2: "media", 3: "alta", 4: "critica"}[rango]
    if rango < 0:
        return None
    return "critica"


def color_por_severidad(severidad: str | None) -> str:
    if severidad is None:
        return "verde"
    return {
        "critica": "rojo",
        "alta": "naranja",
        "media": "amarillo",
        "baja": "amarillo",
    }.get(severidad.lower(), "verde")


def sin_respuesta(*, estado: str, modo: str, ultimo_emisor: str | None, ultimo_fecha_hora, ahora):
    if estado != "abierta":
        return False
    if modo != "bot":
        return False
    if ultimo_emisor != "cliente":
        return False
    if ultimo_fecha_hora is None:
        return False
    return (ahora - ultimo_fecha_hora) > timedelta(minutes=10)


def ventana_24h_abierta(ultimo_mensaje_cliente_en, ahora) -> bool:
    if ultimo_mensaje_cliente_en is None:
        return False
    return ahora - ultimo_mensaje_cliente_en < timedelta(hours=24)


UMBRAL_AUMENTO_SIGNIFICATIVO = Decimal("15")


def aumento_significativo(actual, nueva, umbral=UMBRAL_AUMENTO_SIGNIFICATIVO) -> bool:
    """Si `nueva` supera a `actual` en `umbral` por ciento o más (P5).

    Se compara con `Decimal` y sin dividir: `(nueva - actual) * 100 >= actual * umbral`
    evita el redondeo binario de un `float` justo en el borde (15 % exacto cuenta).
    Sin una prima actual positiva no hay contra qué comparar, y no se avisa nada.
    """
    actual = Decimal(str(actual))
    nueva = Decimal(str(nueva))
    umbral = Decimal(str(umbral))
    if actual <= 0:
        return False
    return (nueva - actual) * 100 >= actual * umbral
