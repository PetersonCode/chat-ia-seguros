SALUDO = "¡Hola! ¿Cómo estás? Soy el asistente virtual de Seguros Castaño. Te puedo ayudar con tu saldo, el vencimiento de tus pólizas o cómo denunciar un siniestro. ¿Qué necesitás?"
SALDO = "Te cuento: tu saldo pendiente es de {monto} y el próximo vencimiento de pago es el {fecha}."
SIN_SALDO = "¡Buenas noticias! No tenés saldo pendiente. Gracias por estar al día."
VENCIMIENTO = "Acá tenés tus pólizas:\n{lineas}"
SIN_POLIZAS = "No encontré pólizas vigentes a tu nombre. Te paso con un asesor para que lo revise con vos."
SIN_CLIENTE = "Para darte esa información primero tenemos que validar tu identidad, así que te paso con un asesor que te va a ayudar."
SINIESTRO_INSTRUCCIONES = "Lamento lo que pasó. Para hacer la denuncia del siniestro necesitamos: fotos del daño, tu DNI, el número de póliza y una breve descripción de lo ocurrido. Un asesor va a registrar la denuncia y te confirma el número por acá."
SOLICITUD_REGISTRADA = "Listo, ya tomé tu solicitud. Un asesor la va a revisar y te confirma por este mismo chat."
DERIVACION = "Te paso con un asesor, que te va a responder a la brevedad. ¡Gracias por la paciencia!"
DERIVACION_URGENTE = "Entiendo que es urgente. Ya le avisé a un asesor para que se comunique con vos cuanto antes."
AVISO_NEUTRO = "¡Gracias por escribirnos! Un asesor va a revisar tu consulta y te responde a la brevedad."

# --- Asistencia en el camino -----------------------------------------------
# El teléfono depende de la cobertura contratada, así que sale de la póliza del
# cliente y no de una constante suelta: es un dato suyo, como el saldo.
TELEFONOS_ASISTENCIA = {
    "basica": "0800-333-1001",
    "intermedia": "0800-333-1002",
    "total": "0800-333-1003",
}
ASISTENCIA_UNICA = (
    "Para asistencia en el camino con tu póliza {numero_poliza} (cobertura "
    "{cobertura}) llamá al {telefono}. Atiende las 24 horas."
)
ASISTENCIA_VARIAS = (
    "El número de asistencia depende de la póliza. Estos son los tuyos:\n{lineas}"
)
LINEA_ASISTENCIA = "• {numero_poliza} (cobertura {cobertura}): {telefono}"
# Sin cobertura conocida no se inventa un número: lo atiende una persona.
SIN_ASISTENCIA = (
    "No encontré una póliza vigente para darte el número de asistencia. "
    "Te paso con un asesor para que te ayude."
)

# --- Alta de cliente -------------------------------------------------------
YA_ES_CLIENTE = (
    "¡Ya sos cliente de Seguros Castaño! No hace falta que te registres de "
    "nuevo. ¿En qué te puedo ayudar?"
)

# --- Cuando no entiende ----------------------------------------------------
# `MARCA_NO_ENTENDI` es el rastro en el log, igual que con el alta de datos: con
# eso el orquestador cuenta cuántas veces seguidas ya preguntó y, al llegar al
# tope, deriva en vez de volver a preguntar.
MARCA_NO_ENTENDI = "No estoy seguro de haber entendido."
NO_ENTENDI = (
    MARCA_NO_ENTENDI
    + " Puedo ayudarte con tu saldo, el vencimiento de tus pólizas o cómo"
    + " denunciar un siniestro. ¿Qué necesitás?"
)
# Una por intento, en orden: repetir la misma frase tres veces no ayuda a que
# el cliente lo diga de otra forma.
NO_ENTENDI_POR_INTENTO = (
    NO_ENTENDI,
    MARCA_NO_ENTENDI
    + " ¿Me lo contás con otras palabras? Por ejemplo: «cuánto debo»,"
    + " «cuándo vence mi póliza» o «tuve un choque».",
    MARCA_NO_ENTENDI
    + " Probemos una vez más: contame en una frase corta qué necesitás."
    + " Si no lo logro, te paso con un asesor.",
)

# --- Alta de datos antes de derivar ----------------------------------------
# `MARCA_PEDIDO_DATOS` es el rastro que deja el bot en el log de mensajes: con
# eso `registro.py` sabe que ya pidió los datos y desde dónde leer la respuesta
# del cliente. Por eso es una constante aparte y la plantilla se arma con ella:
# si se reescribe el texto, la marca y la detección no se pueden desincronizar.
MARCA_PEDIDO_DATOS = "Para registrarte necesito un par de datos."
PEDIDO_DATOS = MARCA_PEDIDO_DATOS + " ¿Me pasás {faltantes}?"
# No repite el nombre ni el DNI: un DNI en boca del bot es exactamente lo que
# `guardrails._alertas_dni` tiene que mirar con lupa, y confirmarlo no aporta.
DATOS_REGISTRADOS = "¡Gracias! Ya tengo tus datos. Te paso con un asesor, que te va a responder a la brevedad."

RECHAZO_SEGURIDAD = "Perdón, con eso no te puedo ayudar. Si tenés alguna consulta sobre tu seguro, contame y lo vemos."
SOLO_TEXTO = "Perdón, por ahora solo puedo leer mensajes de texto. ¿Me lo escribís?"
ACCION_APROBADA = "¡Buenas noticias! Tu solicitud de {descripcion} fue aprobada y procesada."
ACCION_RECHAZADA = "No pudimos avanzar con tu solicitud. Un asesor se va a comunicar con vos para contarte los detalles."

# --- Sin repetirse --------------------------------------------------------
# Dos mensajes idénticos seguidos suenan a máquina. Si la respuesta es igual a
# lo último que leyó el cliente, se usa una variante con el mismo sentido. Solo
# hay variantes de los textos sin datos: los que llevan montos o fechas no se
# reescriben, se repiten avisando (`REPETICION`).
VARIANTES = {
    SALUDO: (
        "¡Hola de nuevo! ¿En qué te puedo ayudar? Puedo contarte tu saldo, "
        "cuándo vencen tus pólizas o cómo denunciar un siniestro.",
    ),
    DERIVACION: (
        "Ya le avisé a un asesor: te va a escribir por acá apenas pueda.",
        "Tu consulta ya está en manos de un asesor, que te responde a la brevedad.",
    ),
    DERIVACION_URGENTE: (
        "Tu caso ya está marcado como urgente: un asesor se va a comunicar con "
        "vos cuanto antes.",
    ),
    AVISO_NEUTRO: (
        "Recibimos tu mensaje. Un asesor lo está revisando y te responde a la brevedad.",
    ),
    RECHAZO_SEGURIDAD: (
        "Eso no lo puedo hacer. Si querés, te ayudo con tu saldo, tus pólizas o "
        "un siniestro.",
    ),
    SOLO_TEXTO: (
        "Ese tipo de mensaje todavía no lo puedo leer. ¿Me lo contás por escrito?",
    ),
    SIN_CLIENTE: (
        "Como todavía no pude validar tu identidad, un asesor va a seguir la "
        "consulta con vos.",
    ),
    SOLICITUD_REGISTRADA: (
        "Tu solicitud ya quedó anotada. Un asesor la revisa y te confirma por este chat.",
    ),
    SIN_SALDO: ("Seguís al día: no tenés saldo pendiente.",),
    SIN_POLIZAS: (
        "Sigo sin encontrar pólizas vigentes a tu nombre; un asesor lo va a "
        "revisar con vos.",
    ),
    SIN_ASISTENCIA: (
        "Sigo sin encontrar una póliza vigente para darte el número de "
        "asistencia; un asesor te va a ayudar.",
    ),
    SINIESTRO_INSTRUCCIONES: (
        "Para seguir con la denuncia, mandanos fotos del daño, tu DNI, el número "
        "de póliza y contanos brevemente qué pasó. Un asesor la registra y te "
        "confirma el número.",
    ),
    YA_ES_CLIENTE: (
        "Ya figurás como cliente, así que no hace falta registrarte. Contame qué necesitás.",
    ),
}
# Para lo que no tiene variante (los textos con datos, el pedido de datos del
# alta): el mismo texto, avisando que se repite. No agrega datos, así que lo
# verificado sigue valiendo, y las marcas del log se buscan con `in`.
REPETICION = "Te lo repito por las dudas:\n{texto}"


def _normalizado(texto: str | None) -> str:
    return " ".join((texto or "").split()).casefold()


def es_repeticion(texto: str | None, anterior: str | None) -> bool:
    """Si `texto` es, salvo espacios y mayúsculas, lo mismo que `anterior`."""
    return bool(anterior) and _normalizado(texto) == _normalizado(anterior)


def sin_repetir(texto: str, anterior: str | None) -> str:
    """`texto`, o una variante si es idéntico al último mensaje que leyó el cliente."""
    if not es_repeticion(texto, anterior):
        return texto
    for variante in VARIANTES.get(texto, ()):
        if not es_repeticion(variante, anterior):
            return variante
    return REPETICION.format(texto=texto)


# --- Formatos (sección 5 de la spec) ---------------------------------------
# Dinero `$12.500` / `$12.500,50`: miles con `.`, decimales con `,` y solo si
# no es entero. Fechas `dd/mm/aaaa`.
# `{bien}` nombra lo asegurado cuando está cargado: a quien pregunta "¿tengo
# vehículos registrados?" el número de póliza solo no le dice nada.
LINEA_VENCIMIENTO = "• {numero_poliza} ({tipo_seguro}{bien}): vence el {fecha}{marca}"
MARCA_VENCIDA = " — VENCIDA"


def formatear_monto(valor) -> str:
    """`Decimal('12500')` -> `'$12.500'`; `Decimal('12500.50')` -> `'$12.500,50'`."""
    from decimal import Decimal

    numero = Decimal(str(valor or 0))
    entero = int(numero)
    centavos = abs(int((numero - entero) * 100))
    miles = f"{abs(entero):,}".replace(",", ".")
    signo = "-" if numero < 0 else ""
    if centavos:
        return f"{signo}${miles},{centavos:02d}"
    return f"{signo}${miles}"


def formatear_fecha(fecha) -> str:
    """`date(2024, 4, 15)` -> `'15/04/2024'`; `None` -> `'-'`."""
    if fecha is None:
        return "-"
    return fecha.strftime("%d/%m/%Y")
