SALUDO = "¡Hola! Soy el asistente de Seguros Castaño. Puedo informarte tu saldo, el vencimiento de tus pólizas o cómo denunciar un siniestro. ¿En qué te ayudo?"
SALDO = "Tu saldo pendiente es de {monto}. Próximo vencimiento de pago: {fecha}."
SIN_SALDO = "No tenés saldo pendiente. ¡Gracias por estar al día!"
VENCIMIENTO = "Estas son tus pólizas:\n{lineas}"
SIN_POLIZAS = "No encontramos pólizas vigentes a tu nombre. Te derivamos con un asesor."
SIN_CLIENTE = "Para darte esa información necesitamos validar tu identidad. Te derivamos con un asesor."
SINIESTRO_INSTRUCCIONES = (
    "Si ya tenés un expediente, podés enviar una foto JPEG o PNG de hasta 5 MB "
    "e indicar su número SIN-AAAA-NNNNN en el texto del mensaje. Un asesor "
    "revisará el archivo. Si todavía no tenés expediente, contanos qué ocurrió "
    "y un asesor podrá registrar la denuncia. Recibir una foto o registrar una "
    "denuncia no confirma cobertura ni indemnización."
)
CONSULTA_DOCUMENTAL = (
    "Como información general, la fuente «{titulo}», versión {version} "
    "({referencia}), contiene este pasaje: “{pasaje}”. "
    "Esto no confirma que esa cobertura o condición aplique a tu póliza "
    "particular. Un asesor debe verificar las condiciones de tu contrato."
)
SOLICITUD_REGISTRADA = "Registramos tu solicitud. Un asesor la va a revisar y te va a confirmar por este medio."
DERIVACION = "Te derivamos con un asesor, que te va a responder a la brevedad."
DERIVACION_URGENTE = "Entendemos que es urgente. Ya avisamos a un asesor para que se comunique con vos cuanto antes."
AVISO_NEUTRO = "Gracias por tu consulta, un asesor te responderá a la brevedad."

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
    "No encontramos una póliza vigente para darte el número de asistencia. "
    "Te derivamos con un asesor."
)

# --- Alta de cliente -------------------------------------------------------
YA_ES_CLIENTE = (
    "Ya figurás como cliente, así que no hace falta registrarte de nuevo. "
    "¿En qué te puedo ayudar?"
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
DATOS_REGISTRADOS = "¡Gracias! Ya registré tus datos. Te derivamos con un asesor, que te va a responder a la brevedad."

RECHAZO_SEGURIDAD = "No puedo ayudarte con ese pedido. Si tenés una consulta sobre tu seguro, escribime y te ayudo."
SOLO_TEXTO = (
    "Puedo leer texto y recibir fotos JPEG o PNG de hasta 5 MB para un expediente "
    "indicado con su número. Otros tipos de archivo no se incorporan."
)
FOTO_SINIESTRO_EXPEDIENTE = (
    "No incorporé la foto porque falta el número del expediente. Reenviála con "
    "SIN-AAAA-NNNNN en el texto del mensaje; si todavía no tenés ese número, "
    "pedí a un asesor que registre la denuncia."
)
FOTO_SINIESTRO_ERROR = (
    "No pude vincular la foto a un expediente verificado. Un asesor podrá "
    "ayudarte. Recibir una foto no confirma cobertura ni indemnización."
)
FOTO_SINIESTRO_INCORPORADA = (
    "La foto se incorporó al expediente {numero_siniestro} para que un asesor "
    "la revise. Esto no confirma cobertura ni indemnización."
)
FOTO_SINIESTRO_INVALIDA = (
    "No pude incorporar la foto. Enviá una imagen JPEG o PNG válida de hasta "
    "5 MB. Si el problema continúa, un asesor podrá ayudarte."
)
ACCION_APROBADA = "Tu solicitud de {descripcion} fue aprobada y procesada."
ACCION_APROBADA_PENDIENTE = (
    "Tu solicitud de {descripcion} fue aprobada, pero todavía no fue realizada. "
    "Un asesor completará la gestión y te confirmará por este medio."
)
ACCION_RECHAZADA = "No pudimos procesar tu solicitud. Un asesor se va a comunicar con vos."

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
