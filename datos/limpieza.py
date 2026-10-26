import re
from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass(frozen=True)
class FechaParseada:
    fecha: date
    hora: time | None


_FORMATOS_FECHA_HORA = (
    "%Y-%m-%d %H:%M",
    "%d/%m/%Y %H:%M",
    "%B %d %Y %H:%M",
    "%d-%m-%y %H:%M",
    "%Y/%m/%d %H:%M",
    "%d/%m/%y %H:%M",
    "%d.%m.%Y %H:%M",
)
_FORMATOS_FECHA = (
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
)
_ALIAS_TIPO_SEGURO = {
    "automotor": "automotor",
    "auto": "automotor",
    "hogar": "hogar",
    "casa": "hogar",
    "vivienda": "hogar",
    "comercio": "comercio",
    "negocio": "comercio",
    "local": "comercio",
    "moto": "moto",
    "motocicleta": "moto",
    "vida": "vida",
}


def normalizar_dni(raw: str) -> str:
    dni = re.sub(r"[.\-\s]", "", raw)
    if re.fullmatch(r"[0-9]{7,8}", dni) is None:
        raise ValueError("El DNI debe contener 7 u 8 dígitos.")
    return dni


def normalizar_telefono(raw: str) -> str:
    if not raw or not raw.strip() or any(caracter.isalpha() for caracter in raw):
        raise ValueError("El teléfono no tiene un formato válido.")

    digitos = re.sub(r"[^0-9]", "", raw)
    if digitos.startswith("54"):
        digitos = digitos[2:]
    if digitos.startswith("0"):
        digitos = digitos[1:]
    if len(digitos) == 11 and digitos.startswith("9"):
        digitos = digitos[1:]
    if len(digitos) != 10:
        raise ValueError("El teléfono debe contener 10 dígitos nacionales.")
    return f"+549{digitos}"


def parsear_fecha_hora(raw: str) -> FechaParseada:
    entrada = raw.strip()
    for formato in _FORMATOS_FECHA_HORA:
        try:
            resultado = datetime.strptime(entrada, formato)
        except ValueError:
            continue
        return FechaParseada(fecha=resultado.date(), hora=resultado.time())

    for formato in _FORMATOS_FECHA:
        try:
            resultado = datetime.strptime(entrada, formato)
        except ValueError:
            continue
        return FechaParseada(fecha=resultado.date(), hora=None)

    raise ValueError(f"No se pudo interpretar la fecha y hora: {raw!r}.")


def normalizar_tipo_seguro(raw: str) -> str:
    tipo = _ALIAS_TIPO_SEGURO.get(raw.strip().casefold())
    if tipo is None:
        raise ValueError(f"Tipo de seguro desconocido: {raw!r}.")
    return tipo
