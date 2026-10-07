SALUDO = "¡Hola! Soy el asistente de Seguros Castaño. Puedo informarte tu saldo, el vencimiento de tus pólizas o cómo denunciar un siniestro. ¿En qué te ayudo?"
SALDO = "Tu saldo pendiente es de {monto}. Próximo vencimiento de pago: {fecha}."
SIN_SALDO = "No tenés saldo pendiente. ¡Gracias por estar al día!"
VENCIMIENTO = "Estas son tus pólizas:\n{lineas}"
SIN_POLIZAS = "No encontramos pólizas vigentes a tu nombre. Te derivamos con un asesor."
SIN_CLIENTE = "Para darte esa información necesitamos validar tu identidad. Te derivamos con un asesor."
SINIESTRO_INSTRUCCIONES = "Para denunciar un siniestro necesitamos: fotos del daño, tu DNI, el número de póliza y una breve descripción de lo ocurrido. Un asesor va a registrar la denuncia y te va a confirmar el número."
SOLICITUD_REGISTRADA = "Registramos tu solicitud. Un asesor la va a revisar y te va a confirmar por este medio."
DERIVACION = "Te derivamos con un asesor, que te va a responder a la brevedad."
DERIVACION_URGENTE = "Entendemos que es urgente. Ya avisamos a un asesor para que se comunique con vos cuanto antes."
AVISO_NEUTRO = "Gracias por tu consulta, un asesor te responderá a la brevedad."
RECHAZO_SEGURIDAD = "No puedo ayudarte con ese pedido. Si tenés una consulta sobre tu seguro, escribime y te ayudo."
SOLO_TEXTO = "Por ahora solo puedo leer mensajes de texto."
ACCION_APROBADA = "Tu solicitud de {descripcion} fue aprobada y procesada."
ACCION_RECHAZADA = "No pudimos procesar tu solicitud. Un asesor se va a comunicar con vos."

# --- Formatos (sección 5 de la spec) ---------------------------------------
# Dinero `$12.500` / `$12.500,50`: miles con `.`, decimales con `,` y solo si
# no es entero. Fechas `dd/mm/aaaa`.
LINEA_VENCIMIENTO = "• {numero_poliza} ({tipo_seguro}): vence el {fecha}{marca}"
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
