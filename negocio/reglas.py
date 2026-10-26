from datetime import timedelta

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
