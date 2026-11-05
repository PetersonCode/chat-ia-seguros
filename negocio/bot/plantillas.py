SALUDO = "¡Hola! Soy el asistente de Seguros Castaño. Puedo informarte tu saldo, el vencimiento de tus pólizas o cómo denunciar un siniestro. ¿En qué te ayudo?"
SALDO = "Tu saldo pendiente es de {monto}. Próximo vencimiento de pago: {fecha}."
SIN_SALDO = "No tenés saldo pendiente. ¡Gracias por estar al día!"
VENCIMIENTO = "Estas son tus pólizas:\n{lineas}"
SIN_POLIZAS = "No encontramos pólizas vigentes a tu nombre. Te derivamos con un asesor."
SIN_CLIENTE = "No encuentro una póliza automotor asociada a este número. Puedo registrar tu consulta para que un asesor te ayude."
SINIESTRO_AVISO = "Recibimos tu aviso de siniestro y te derivamos con un asesor para continuar."
SINIESTRO_EXPEDIENTE = (
    "Si ya tenés un expediente, podés enviar una foto JPEG o PNG de hasta 5 MB "
    "e indicar su número SIN-AAAA-NNNNN en el texto del mensaje. Un asesor "
    "revisará el archivo. Si todavía no tenés expediente, contanos qué ocurrió "
    "y un asesor podrá registrar la denuncia. Recibir una foto o registrar una "
    "denuncia no confirma cobertura ni indemnización."
)
SINIESTRO_INSTRUCCIONES = SINIESTRO_AVISO + " " + SINIESTRO_EXPEDIENTE
# Lo que se suma al aviso de un siniestro de un cliente: la grúa de su póliza
# (sale de la base, como en «asistencia») y el recordatorio de la ambulancia.
SINIESTRO_GRUA = "Si necesitás grúa, el número de asistencia de tu póliza {numero_poliza} es {telefono}."
SINIESTRO_GRUA_VARIAS = "Si necesitás grúa, estos son los números de asistencia de tus pólizas:\n{lineas}"
SINIESTRO_SIN_GRUA = (
    "No encontramos un número de grúa cargado en tu póliza; el asesor te lo "
    "confirma por este chat."
)
SINIESTRO_AMBULANCIA = "Si hay personas heridas, llamá a una ambulancia (107) o al 911."
TELEFONOS_EMERGENCIA = frozenset({"107", "911"})
# Un choque de alguien que no es cliente: no hay póliza nuestra que lo cubra,
# así que no se deriva. Si ya es cliente, que escriba desde el número registrado.
SINIESTRO_SIN_CLIENTE = (
    "Lamentamos lo que pasó. No encontramos una póliza a tu nombre asociada a "
    "este número, así que no podemos gestionar el siniestro desde acá: la "
    "denuncia la tiene que hacer la aseguradora del vehículo. Si sos cliente "
    "nuestro, escribinos desde el número que tenés registrado. Si hay personas "
    "heridas, llamá primero a emergencias."
)
CONSULTA_DOCUMENTAL = (
    "Como información general, la fuente «{titulo}», versión {version} "
    "({referencia}), contiene este pasaje: “{pasaje}”. "
    "Esto no confirma que esa cobertura o condición aplique a tu póliza "
    "particular. Un asesor debe verificar las condiciones de tu contrato."
)
SOLICITUD_REGISTRADA = "Registramos tu solicitud. Un asesor la va a revisar y te va a confirmar por este medio."
# Seguimiento de una solicitud que ya está pendiente: no se abre otra.
SOLICITUD_YA_REGISTRADA = (
    "Ya tenemos tu solicitud registrada. El asesor que la revise va a ver también este mensaje "
    "y te confirma por este medio."
)
DERIVACION = "Te derivamos con un asesor, que te va a responder a la brevedad."
DERIVACION_URGENTE = "Entendemos que es urgente. Te derivamos con un asesor, que se va a comunicar con vos cuanto antes."
AVISO_NEUTRO = "Gracias por tu consulta. Te derivamos con un asesor, que te va a responder a la brevedad."
# Toda respuesta que deriva avisa que derivó. Si el texto no lo dice ya, el
# orquestador le suma esta línea (ver `con_aviso_de_derivacion`).
AVISO_DERIVADO = "Te derivamos con un asesor, que te va a responder por este chat."


def con_aviso_de_derivacion(texto: str) -> str:
    """El texto con el aviso de derivación al final, salvo que ya lo diga."""
    if "deriv" in (texto or "").lower():
        return texto
    return f"{texto.rstrip()} {AVISO_DERIVADO}" if texto else AVISO_DERIVADO

# --- Charla que no es una consulta -------------------------------------------
# Agradecer o despedirse se contesta y se cierra: no se repregunta ni se deriva.
# Son el respaldo de lo que redacta el LLM, o lo único si no hay LLM.
AGRADECIMIENTO = "¡De nada! Si necesitás algo más sobre tu seguro, escribime cuando quieras."
DESPEDIDA = "¡Hasta luego! Cualquier consulta sobre tu seguro, escribime cuando quieras."
# Fuera de tema se contesta siempre con el texto fijo, nunca con el LLM: un
# modelo libre terminaría respondiendo la receta o la cuenta que le pidieron.
FUERA_DE_TEMA = (
    "Disculpá, solo puedo ayudarte con temas de tu seguro: saldo, vencimiento "
    "de pólizas, siniestros, asistencia en el camino o cotizaciones. Si "
    "necesitás algo de eso, contame."
)

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
# El cliente mandó un número que no puede ser un DNI: se le dice qué está mal en
# vez de repetirle la misma pregunta. Lleva la marca para contar como pedido.
PEDIDO_DNI_REVISAR = (
    MARCA_PEDIDO_DATOS
    + " El número que me mandaste no parece un DNI: tiene que tener 7 u 8 números, sin puntos ni letras."
    + " ¿Me lo escribís de nuevo?"
)
# No repite el nombre ni el DNI: un DNI en boca del bot es exactamente lo que
# `guardrails._alertas_dni` tiene que mirar con lupa, y confirmarlo no aporta.
DATOS_REGISTRADOS = "¡Gracias! Ya registré tus datos. Te derivamos con un asesor, que te va a responder a la brevedad."

# --- Datos para cotizar (P5) ------------------------------------------------
# Igual que con el alta: `MARCA_PEDIDO_COTIZACION` es el rastro en el log. Con eso
# `cotizacion.py` sabe que ya pidió los datos y desde dónde leer lo que contestó
# el cliente. `COTIZACION_REGISTRADA` es además el cierre del pedido: lo que se
# diga después es una cotización nueva. Ninguna de las dos repite un dato del
# cliente (patente, año…), así que no hay nada que verificar ni que retener.
MARCA_PEDIDO_COTIZACION = "Para prepararte la cotización necesito algunos datos del vehículo."
PEDIDO_COTIZACION = (
    MARCA_PEDIDO_COTIZACION
    + " ¿Me pasás {faltantes}? Si podés, mandámelos uno por línea y en ese orden."
)
# Con un solo dato pendiente no hay orden ni líneas que pedir.
PEDIDO_COTIZACION_UNO = MARCA_PEDIDO_COTIZACION + " ¿Me pasás {faltantes}?"
COTIZACION_REGISTRADA = (
    "¡Gracias! Con estos datos un asesor te prepara la cotización y te escribe por acá."
    # Decisión del equipo: el bot sigue en la charla y ofrece contratar ya.
    " Si ya querés contratarlo, escribime «quiero contratarlo» y te preparo la solicitud con "
    "estos datos; el asesor te confirma el precio antes de emitir."
)
# Vuelve a preguntar el precio con una cotización ya pedida: no se reinicia.
COTIZACION_YA_PEDIDA = (
    "Ya le pasé tu pedido de cotización al asesor, que te escribe por acá con el precio. "
    "Si querés contratarlo ya, escribime «quiero contratarlo» y te preparo la solicitud."
)
# Aviso de seguimiento a los 2 y 5 días en «cotizando» (lo entrega el motor de avisos).
SEGUIMIENTO_COTIZACION = (
    "Hola {nombre}, ¿pudiste ver la cotización que te pasamos? "
    "Si tenés dudas o querés ajustar algo, contanos."
)
# Un interesado sin nombre propio (se llama como su número) no se saluda por número.
SEGUIMIENTO_COTIZACION_SIN_NOMBRE = (
    "Hola, ¿pudiste ver la cotización que te pasamos? "
    "Si tenés dudas o querés ajustar algo, contanos."
)

# --- Pago informado por el cliente -------------------------------------------
# «Pagué», «transferí»…: se pide la referencia del comprobante y, con ella, queda
# la acción `registrar_pago` para que un aprobador la confirme. La marca es el
# rastro en el log, como en el alta (ver `pago_informado.pedidos_en_curso`).
MARCA_PEDIDO_COMPROBANTE = "Para registrar tu pago necesito la referencia del comprobante."
PEDIDO_COMPROBANTE = (
    MARCA_PEDIDO_COMPROBANTE
    + " ¿Me pasás el número o código de la operación que figura en el comprobante?"
    + " Puede tener letras y/o números."
)
PEDIDO_COMPROBANTE_REVISAR = (
    MARCA_PEDIDO_COMPROBANTE
    + " No pude leer una referencia en tu mensaje. Escribime solo el número o código"
    + " de la operación (letras y/o números), por ejemplo: 0012345678 o MP-AB1234."
)
# No dice que el pago quedó registrado: eso pasa cuando un aprobador lo confirma.
PAGO_INFORMADO = (
    "¡Gracias! Recibimos el comprobante {referencia} de tu pago. Un asesor lo va a "
    "verificar y te confirma por este medio cuando quede registrado."
)
PAGO_YA_INFORMADO = (
    "Ese comprobante ({referencia}) ya lo tenemos registrado. El asesor que lo revise "
    "te confirma por este medio."
)
PAGO_SIN_CUOTAS = (
    "Recibimos la referencia {referencia}, pero no encontramos cuotas pendientes en tus "
    "pólizas. Te derivamos con un asesor para que revise el comprobante."
)
PAGO_SIN_REFERENCIA = (
    "No pude leer la referencia del comprobante. Te derivamos con un asesor para "
    "que te ayude a registrar el pago."
)

RECHAZO_SEGURIDAD ="No puedo ayudarte con ese pedido. Si tenés una consulta sobre tu seguro, escribime y te ayudo."
SOLO_TEXTO = (
    "Puedo leer texto y recibir fotos JPEG o PNG de hasta 5 MB para un expediente "
    "indicado con su número. Otros tipos de archivo no se incorporan."
)
# Única respuesta a una foto, video, documento o audio del cliente. El bot no
# opina sobre el archivo: si trae un expediente se incorpora igual, en silencio,
# y lo revisa un asesor. Se repite tal cual aunque manden varios seguidos.
ARCHIVO_RECIBIDO = "Archivo recibido."
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
# `{patente}` queda vacío salvo que la póliza tenga vehículo (P1).
LINEA_VENCIMIENTO = "• {numero_poliza} ({tipo_seguro}{bien}): vence el {fecha}{marca}{patente}"
MARCA_VENCIDA = " — VENCIDA"
MARCA_PATENTE = " · {patente}"


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


VARIANTES = {
    RECHAZO_SEGURIDAD: ("Solo puedo ayudarte con consultas de seguros dentro de los permisos establecidos. ¿Qué necesitás consultar?",),
    SOLO_TEXTO: ("Por ahora puedo interpretar mensajes escritos. Escribí tu consulta para continuar.",),
    DERIVACION: ("Un asesor continuará con tu consulta en este chat.",),
}


def es_repeticion(texto, anterior):
    return bool(anterior) and ' '.join(texto.lower().split()) == ' '.join(anterior.lower().split())


def sin_repetir(texto, anterior):
    if not es_repeticion(texto, anterior):
        return texto
    variantes = VARIANTES.get(texto)
    return variantes[0] if variantes else 'Te reitero la información disponible: ' + texto
