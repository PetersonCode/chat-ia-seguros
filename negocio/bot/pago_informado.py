"""El cliente avisa que ya pagó: se le pide la referencia del comprobante.

«Pagué», «realicé el pago», «aboné», «transferí»… no son una consulta para un
asesor sino un pago que hay que registrar. El bot pide la referencia del
comprobante (letras y/o números) y, con ella, deja la acción `registrar_pago`
para que un aprobador la confirme: el pago se registra recién ahí, con
`negocio.polizas.registrar_pago`, igual que desde el panel.

Sin estado propio, como el alta y la cotización: el rastro es
`MARCA_PEDIDO_COMPROBANTE` en los mensajes del bot.
"""

from __future__ import annotations

import re

from datos.models import Direccion, Emisor, EstadoEnvio, Mensaje
from negocio.bot.clasificador import normalizar
from negocio.bot import plantillas

# Cuántas veces se pide la referencia antes de pasarle el caso a un asesor.
MAX_PEDIDOS = 2

# Frases en las que el cliente cuenta que ya pagó (sin acentos, minúsculas).
_DECLARA_PAGO = re.compile(
    r"\b(?:"
    r"pague|abone|transferi|deposite|"
    r"(?:realice|hice|efectue|mande|envie|te pase|les pase|ya hice) (?:el |la |un |una )?"
    r"(?:pago|transferencia|deposito|comprobante)|"
    r"ya esta pago|ya esta pagad[oa]|ya (?:lo |la )?pague|"
    r"(?:te|les) (?:mando|paso|envio) el comprobante"
    r")\b"
)
# Un rótulo delante de la referencia: «comprobante 1111222», «nro de operación: AB12».
_ROTULO = re.compile(
    r"\b(?:comprobante|referencia|ref|operacion|transaccion|transferencia|"
    r"codigo|numero|nro|n°|nº)\b\.?"
    r"(?:\s+de\s+(?:la\s+|el\s+)?(?:operacion|transferencia|comprobante|pago))?"
    r"\s*(?:es|nro|numero|n°|nº)?\s*[:#-]?\s*([a-z0-9][a-z0-9-]{3,59})\b",
)
_FICHA = re.compile(r"\b[a-z0-9][a-z0-9-]{3,59}\b")
# Un número solo, sin rótulo, recién cuenta desde estos dígitos: con menos
# suele ser un importe («pagué 45000»), no un comprobante.
_DIGITOS_SIN_ROTULO = 8
# Palabras que nunca son una referencia aunque vengan solas.
_NO_REFERENCIA = frozenset({
    "hola", "gracias", "dale", "listo", "bueno", "buenas", "perfecto", "ninguno",
    "ninguna", "nose", "pague", "abone", "transferi", "comprobante", "referencia",
    "despues", "luego", "ahora", "seguro", "poliza", "cuota", "pago", "okey",
    "desde", "para", "tengo", "esta", "este", "aqui", "alla", "foto", "imagen",
})
# Lo que tiene forma de dato pero no es un comprobante: póliza, expediente, fecha.
_OTRO_DATO = re.compile(r"pol-?\d+|sin-\d{4}-\d+|\d{1,2}-\d{1,2}-\d{2,4}")


# «Pagué y me sigue figurando la deuda» es un reclamo: no se pide comprobante.
_QUEJA = re.compile(
    r"\b(?:sigue|siguen|me sigue|me siguen) (?:figurando|apareciendo|cobrando|debiendo)|"
    r"\bme (?:figura|aparece) (?:la |una )?deuda|\bme cobraron|\bno (?:se )?(?:acredito|impacto)|"
    r"\bdos veces\b|\b2 veces\b|\bcobraron mal\b"
)


def declara_pago(texto: str) -> bool:
    """Si el mensaje cuenta que ya pagó (no si pregunta cómo pagar ni se queja)."""
    normalizado = normalizar(texto)
    if not normalizado or _QUEJA.search(normalizado):
        return False
    if _DECLARA_PAGO.search(normalizado):
        # «¿Pagué la cuota de marzo?» es una pregunta por el saldo, no un aviso,
        # salvo que traiga la referencia.
        return "?" not in normalizado or extraer_referencia(texto, en_pedido=False) is not None
    # «Comprobante 1111222» sin más: también es un aviso de pago.
    return bool(re.match(r"^(?:el |mi )?comprobante\b", normalizado)) and (
        extraer_referencia(texto, en_pedido=False) is not None
    )


def extraer_referencia(texto: str, *, en_pedido: bool) -> str | None:
    """La referencia del comprobante: letras y/o números, de 4 a 60 caracteres.

    - Con rótulo («comprobante X», «nro de operación X»): X si tiene algún
      número o está en mayúsculas («AB12CD», «PAGOFACIL»).
    - Sin rótulo: un código con letras y números, o un número largo (un número
      corto suelto suele ser el importe).
    - Si el bot la estaba pidiendo (`en_pedido`) se acepta también lo que con
      el pedido delante no puede ser otra cosa: un número corto, unas letras
      con rótulo o un mensaje de una sola palabra («4455», «abcdef»).

    Nunca se toma una palabra común («hola», «dale»), una póliza, un
    expediente ni una fecha.
    """
    original = (texto or "").strip()
    normalizado = normalizar(original)
    if not normalizado:
        return None

    for rotulada in _ROTULO.finditer(normalizado):
        ficha = rotulada.group(1)
        if _descartable(ficha):
            continue
        escrita = _como_la_escribio(original, ficha)
        if any(c.isdigit() for c in ficha) or escrita.isupper() or en_pedido:
            return escrita

    # «Ya pagué» y en otro mensaje «1111222»: la ráfaga llega unida por líneas, y
    # un código solo en su renglón no es un importe dicho al pasar.
    for renglon in original.splitlines()[1:]:
        sola = normalizar(renglon).strip(" .!¡")
        if _FICHA.fullmatch(sola) and any(c.isdigit() for c in sola) and not _descartable(sola):
            return _como_la_escribio(renglon, sola)

    for ficha in _FICHA.findall(normalizado):
        if _descartable(ficha) or not any(c.isdigit() for c in ficha):
            continue
        if ficha.isdigit() and len(ficha) < _DIGITOS_SIN_ROTULO and not en_pedido:
            continue
        return _como_la_escribio(original, ficha)

    if en_pedido:
        sola = normalizado.strip(" .!¡")
        if _FICHA.fullmatch(sola) and not _descartable(sola):
            return _como_la_escribio(original, sola)
    return None


def _descartable(ficha: str) -> bool:
    return ficha in _NO_REFERENCIA or _OTRO_DATO.fullmatch(ficha) is not None


def _como_la_escribio(original: str, ficha_normalizada: str) -> str:
    """La referencia con las mayúsculas que usó el cliente."""
    for ficha in re.findall(r"[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ-]+", original):
        if normalizar(ficha) == ficha_normalizada:
            return ficha
    return ficha_normalizada.upper()


def pedidos_en_curso(conversacion_id: int) -> int:
    """Cuántas veces seguidas pidió el bot la referencia (0: no hay pedido en curso).

    Se cuentan los últimos mensajes del bot que llevan la marca. «Archivo
    recibido» no corta la cuenta: el cliente suele mandar la foto del
    comprobante entre medio.
    """
    salientes = (
        Mensaje.objects.filter(
            conversacion_id=conversacion_id,
            direccion=Direccion.SALIENTE,
            emisor=Emisor.BOT,
        )
        .exclude(estado_envio__in=[EstadoEnvio.RETENIDO, EstadoEnvio.DESCARTADO])
        .order_by("-id")
        .values_list("texto", flat=True)[:10]
    )
    pedidos = 0
    for texto in salientes:
        if texto == plantillas.ARCHIVO_RECIBIDO:
            continue
        if plantillas.MARCA_PEDIDO_COMPROBANTE not in (texto or ""):
            break
        pedidos += 1
    return pedidos
