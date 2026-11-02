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

# Orden de evaluación. Los diez tipos de AC-T3-33 conservan su orden relativo;
# los tres que se agregaron después se intercalan donde no se lo roban a nadie:
#   `pago` después de `saldo`, para que "cuánto me falta pagar" siga siendo saldo;
#   `asistencia` después de `siniestro`, para que un choque siga siendo un choque
#   aunque además pida una grúa;
#   `registro` después de `cotizacion`, para que "cuánto cuesta ser cliente" siga
#   siendo una cotización.
ORDEN = (
    "siniestro_urgente",
    "baja",
    "modificacion",
    "reclamo",
    "saldo",
    "vencimiento",
    "pago",
    "siniestro",
    "asistencia",
    "cotizacion",
    "consulta_cobertura",
    "registro",
    "saludo",
)

# Patrones por tipo, ya sin acentos y en minúsculas (ver `normalizar`).
PATRONES: dict[str, tuple[str, ...]] = {
    # Urgencia explícita o un siniestro en curso que no admite espera.
    "siniestro_urgente": (
        "urgente",
        "urgencia",
        "emergencia",
        "tuve un choque",
        "tuve un accidente",
        "me robaron el auto",
        "me robaron el coche",
        "estoy en el hospital",
        "estoy hospitalizado",
        "estoy hospitalizada",
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
        "me descontaron",
        "descontaron dos veces",
        "me debitaron de mas",
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
        # "¿Qué pólizas tengo?" es un pedido del listado de pólizas, y eso es
        # exactamente lo que contesta esta plantilla ("Estas son tus pólizas:").
        # Sin estos patrones caía en consulta_cobertura, que deriva a una
        # persona, y el cliente se quedaba sin la respuesta que el bot ya tenía.
        # Van en plural y con el verbo adelante a propósito: un "poliza" suelto
        # también aparece en "cuanto cuesta una poliza", que es una cotización.
        "tengo polizas",
        "tengo alguna poliza",
        "mis polizas",
        "que polizas",
        "cuales polizas",
        "cuantas polizas",
        "polizas registradas",
        "polizas activas",
        "tengo vehiculo",
        "algun vehiculo",
        "mis vehiculos",
        "que vehiculos",
        "vehiculo registrado",
        "vehiculos registrados",
        "tengo asegurado",
        "tengo contratado",
        "mis seguros",
        "que seguros tengo",
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
    # Cobranza: adelantos, medios de pago, planes. No lo resuelve el bot —toca
    # plata y no hay nada que pueda decidir solo—, pero sí sabe a quién pasarlo.
    "pago": (
        "adelantar",
        "adelanto",
        "por adelantado",
        "pagar antes",
        "medios de pago",
        "formas de pago",
        "forma de pago",
        "como pago",
        "donde pago",
        "quiero pagar",
        "plan de pago",
        "refinanciar",
        "financiar",
        "cuotas adelantadas",
    ),
    # Asistencia en el camino: es lo único de esta tanda que el bot contesta
    # solo, porque el teléfono sale de la cobertura de la póliza del cliente.
    "asistencia": (
        "grua",
        "remolque",
        "auxilio",
        "asistencia mecanica",
        "asistencia en el camino",
        "asistencia al vehiculo",
        "numero de asistencia",
        "telefono de asistencia",
        "me quede varado",
        "me quede tirado",
        "no me arranca",
        "no arranca el auto",
        "se me pincho",
        "sin bateria",
        "cerrajero",
    ),
    # Alguien que todavía no es cliente y quiere serlo.
    "registro": (
        "registrarme",
        "registrarse",
        "darme de alta",
        "darme el alta",
        "alta como cliente",
        "hacerme cliente",
        "hacer cliente",
        "sumarme",
        "ser cliente",
        "asociarme",
        "afiliarme",
        "no soy cliente",
        "todavia no soy cliente",
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
        "que documentacion",
        "que documentos",
        "que papeles",
        "requisitos para",
        "documentacion necesaria",
        "documentos necesarios",
    ),
    # Va último en ORDEN, así que acá solo cae lo que ningún otro tipo pidió:
    # es el lugar seguro para la jerga rioplatense. "todo bien" no le roba nada
    # a "todo bien, quiero mi saldo", porque saldo se evalúa antes.
    "saludo": (
        "hola",
        "buenas",
        "buen dia",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "que tal",
        "que onda",
        "como andas",
        "como anda",
        "como va",
        "todo bien",
        "holis",
        "saludos",
        "gracias",
    ),
}


def normalizar(texto: str) -> str:
    """Minúsculas y sin acentos, para que 'Chocó' y 'choco' sean lo mismo."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    sin_acentos = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sin_acentos.lower()).strip()


# Señales de que el mensaje **pregunta** por la cobertura en vez de contar algo
# que pasó. Van sin acentos, como el resto.
PREGUNTA_COBERTURA = (
    "cubre",
    "cubierto",
    "cubierta",
    "cobertura",
    "que incluye",
)


def corregir_cruce_cobertura(tipo: str, texto: str) -> str:
    """Corrige el único cruce donde `siniestro` se come una pregunta de cobertura.

    "¿Me cubre el granizo?" nombra un siniestro pero pregunta por lo que cubre
    el contrato. Como `siniestro` se evalúa antes que `consulta_cobertura`,
    ganaba él y el bot contestaba cómo *denunciar* un siniestro, que no es lo
    que se preguntó. El orden de `ORDEN` no se toca (AC-T3-33): se corrige solo
    este cruce, y solo cuando el ganador fue `siniestro`.

    Se aplica también a lo que contesta el LLM, que comete el mismo error
    ("¿cubre choque con animales?" lo manda a siniestro). Si se corrigiera solo
    en las reglas, el bot se portaría distinto según el LLM esté arriba o no.
    """
    if tipo != "siniestro":
        return tipo
    normalizado = normalizar(texto)
    if any(marca in normalizado for marca in PREGUNTA_COBERTURA):
        return "consulta_cobertura"
    return tipo


def _esta_negado(prefijo: str) -> bool:
    # La negación debe afectar al hecho, no a otra parte del mensaje:
    # “no tengo el número de póliza, me robaron” sigue siendo urgente.
    return bool(re.search(
        r"\b(?:no|nunca|sin)(?:\s+(?:he|hemos|habia|habiamos|me|nos|siquiera|"
        r"tampoco|aun|todavia|fue|es|era|hubo|un|una|ningun|ninguna))*\s*$",
        prefijo,
    ))


def clasificar(texto: str) -> str:
    """Devuelve el código de `TipoConsulta` para un mensaje del cliente."""
    normalizado = normalizar(texto)
    if not normalizado:
        return "otro"
    # Hechos relatados: no dependen de una frase exacta ni del modelo de IA.
    # Se excluyen negaciones y preguntas generales, sin ocultar otro incidente
    # afirmativo que aparezca después en el mismo mensaje.
    frases = re.split(r"[.!?;,]|\bpero\b", normalizado)
    for frase in frases:
        incidentes = re.finditer(
            r"\b(?:choque|chocamos|chocaron|me chocaron|tuve un (?:choque|accidente)|"
            r"tuvimos un accidente|me robaron|nos robaron|estoy (?:en (?:el )?hospital|hospitalizad[oa])|"
            r"hay heridos|estoy herid[oa])\b", frase
        )
        for incidente in incidentes:
            if _esta_negado(frase[:incidente.start()]):
                continue
            pregunta_general = any(marca in frase for marca in PREGUNTA_COBERTURA)
            hecho_explicito = re.search(
                r"\b(?:me|nos) (?:chocaron|robaron)\b|\b(?:tuve|tuvimos|estoy|hay heridos)\b", incidente.group()
            )
            if not pregunta_general or hecho_explicito:
                return "siniestro_urgente"
    for tipo in ORDEN:
        candidatos = normalizado
        if tipo == "siniestro_urgente":
            for frase in frases:
                if any(marca in frase for marca in PREGUNTA_COBERTURA):
                    continue
                for patron in PATRONES[tipo]:
                    if any(not _esta_negado(frase[:m.start()]) for m in re.finditer(re.escape(patron), frase)):
                        return tipo
            continue
        if any(patron in candidatos for patron in PATRONES[tipo]):
            return corregir_cruce_cobertura(tipo, texto)
    return "otro"


# Pedir hablar con una persona cae en `otro` —no hay un tipo para eso— pero no
# es que el bot no haya entendido: es exactamente lo que el cliente pidió. Sin
# esta distinción, el paso de "no entendí, ¿qué necesitás?" le repreguntaría a
# alguien que ya fue clarísimo.
PEDIDOS_DE_HUMANO = (
    "hablar con un asesor",
    "hablar con una persona",
    "hablar con alguien",
    "hablar con un humano",
    "hablar con un operador",
    "con un asesor",
    "un asesor",
    "una persona real",
    "atencion al cliente",
    "me atienda alguien",
    "me atienda una persona",
    "pasame con",
    "comunicarme con",
    "quiero un humano",
)


def pide_un_humano(texto: str) -> bool:
    """Si el mensaje pide explícitamente hablar con una persona."""
    normalizado = normalizar(texto)
    return any(patron in normalizado for patron in PEDIDOS_DE_HUMANO)
