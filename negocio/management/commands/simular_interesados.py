"""20 interesados ficticios que conversan con el bot como personas.

    python manage.py simular_interesados            # prueba y deshace todo
    python manage.py simular_interesados --guardar  # deja chats y solicitudes

Cada persona tiene sus datos y su forma de escribir (directa, todo junto, con
errores, en mayúsculas, con emojis, con dudas en el medio, que se arrepiente…)
y contesta según lo que el bot le pregunta. Mide si la IA logra juntar los
datos y dejar la acción lista para que un asesor solo confirme o rechace.

Números `+54911000003NN`: no existen, el bot nunca le escribe a nadie real. Con
`--guardar`, conviene detener el worker de WhatsApp mientras corre (ver
docs/OPERACION.md).
"""
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from datos.models import AccionPendiente, Mensaje
from negocio.bot.orquestador import procesar_mensaje
from negocio.whatsapp import registrar_entrante

_salida = []


def self_out(*partes):
    _salida.append(" ".join(str(p) for p in partes))


def P(numero, estilo, inicio, **datos):
    return {"numero": numero, "estilo": estilo, "inicio": inicio, **datos}


# objetivo: "alta" (contratar), "cotizar" (solo precio), "registro" (hacerse cliente), "curioso"
PERSONAS = [
    P("+5491100000301", "directo", ["hola, quiero asegurar mi auto"], objetivo="alta",
      nombre="Ramiro Castro", dni="35123401", patente="AE123FG", marca="Ford", modelo="Ka", anio="2018",
      clase="auto", uso="particular", compania="1", plan="intermedia", inicio_fecha="hoy"),
    P("+5491100000302", "todo junto en un mensaje", ["buenas! quiero contratar un seguro para mi auto. Soy Laura Méndez, DNI 36222302, patente AF234GH, Chevrolet Onix 2020"],
      objetivo="alta", nombre="Laura Méndez", dni="36222302", patente="AF234GH", marca="Chevrolet", modelo="Onix",
      anio="2020", clase="auto", uso="particular", compania="Cóndor Seguros", plan="todo riesgo", inicio_fecha="01/12/2026"),
    P("+5491100000303", "abreviado", ["hola q tal", "kiero asegurar el auto"], objetivo="alta",
      nombre="nico ferreyra", dni="37.333.303", patente="ab 345 cd", marca="vw", modelo="gol trend", anio="2016",
      clase="auto", uso="particular", compania="2", plan="la basica", inicio_fecha="desde mañana"),
    P("+5491100000304", "formal", ["Buenas tardes. Deseo contratar un seguro para mi camioneta."], objetivo="alta",
      nombre="Graciela Domínguez", dni="20111304", patente="AG456JK", marca="Toyota", modelo="Hilux", anio="2022",
      clase="camioneta", uso="comercial", compania="Pampa", plan="todo riesgo", inicio_fecha="hoy"),
    P("+5491100000305", "cotiza y después contrata", ["hola cuanto sale asegurar un fiat cronos?"], objetivo="cotizar_y_alta",
      nombre="Mariano Quiroga", dni="33444305", patente="AH567KL", marca="Fiat", modelo="Cronos", anio="2021",
      clase="auto", uso="particular", localidad="Quilmes", compania="3", plan="terceros completo", inicio_fecha="hoy"),
    P("+5491100000306", "mayúsculas", ["HOLA QUIERO SACAR SEGURO PARA MI AUTO"], objetivo="alta",
      nombre="ROBERTO SOSA", dni="25555306", patente="AJ678LM", marca="RENAULT", modelo="SANDERO", anio="2015",
      clase="AUTO", uso="PARTICULAR", compania="4", plan="BASICA", inicio_fecha="HOY"),
    P("+5491100000307", "con errores", ["ola nesecito asegurar mi auto xfa"], objetivo="alta",
      nombre="jesica gimenez", dni="40666307", patente="AK789MN", marca="peugeot", modelo="208", anio="2019",
      clase="auto", uso="particular", compania="5", plan="intermedia", inicio_fecha="hoy"),
    P("+5491100000308", "moto", ["buenas, quiero asegurar mi moto"], objetivo="alta",
      nombre="Franco Luna", dni="41777308", patente="A123BCD", marca="Honda", modelo="CB 190", anio="2023",
      clase="moto", uso="particular", compania="1", plan="basica", inicio_fecha="hoy"),
    P("+5491100000309", "utilitario de trabajo", ["hola, tengo una kangoo para laburar y la quiero asegurar"], objetivo="alta",
      nombre="Héctor Paz", dni="22888309", patente="AL890PQ", marca="Renault", modelo="Kangoo", anio="2017",
      clase="utilitario", uso="comercial", compania="2", plan="intermedia", inicio_fecha="hoy"),
    P("+5491100000310", "duda en el medio", ["hola quiero asegurar mi auto"], objetivo="alta", pregunta_en_medio="que diferencia hay entre los planes?",
      nombre="Carla Ibáñez", dni="38999310", patente="AM901QR", marca="Citroën", modelo="C3", anio="2020",
      clase="auto", uso="particular", compania="3", plan="intermedia", inicio_fecha="hoy"),
    P("+5491100000311", "solo quiere ser cliente", ["hola quiero hacerme cliente de ustedes"], objetivo="registro",
      nombre="Pablo Ortega", dni="34111311"),
    P("+5491100000312", "solo cotiza", ["cuanto me saldria asegurar un corolla 2019?"], objetivo="cotizar",
      patente="AN112RS", marca="Toyota", modelo="Corolla", anio="2019", uso="particular", localidad="Lanús"),
    P("+5491100000313", "solo saluda", ["hola buenas"], objetivo="curioso"),
    P("+5491100000314", "pregunta y se va", ["hola, ustedes aseguran motos?"], objetivo="curioso"),
    P("+5491100000315", "da el año con palabras", ["buen día, quiero asegurar mi auto"], objetivo="alta",
      nombre="Silvina Rojas", dni="29222315", patente="AP223ST", marca="Nissan", modelo="Kicks", anio="2021",
      clase="camioneta", uso="particular", compania="4", plan="todo riesgo", inicio_fecha="hoy", anio_texto="es del 2021"),
    P("+5491100000316", "con emojis", ["holaa 😊 quiero asegurar mi autito 🚗"], objetivo="alta",
      nombre="Micaela Vera", dni="42333316", patente="AR334TU", marca="Fiat", modelo="Mobi", anio="2022",
      clase="auto", uso="particular", compania="5", plan="basica", inicio_fecha="hoy"),
    P("+5491100000317", "datos con rótulos", ["hola quiero contratar un seguro"], objetivo="alta", rotulos=True,
      nombre="Andrés Molina", dni="31444317", patente="AS445UV", marca="Volkswagen", modelo="Polo", anio="2020",
      clase="auto", uso="particular", compania="1", plan="todo riesgo", inicio_fecha="hoy"),
    P("+5491100000318", "pregunta precio en el medio", ["quiero asegurar mi auto"], objetivo="alta", pregunta_en_medio="y cuanto me va a salir por mes?",
      nombre="Lorena Aguirre", dni="30555318", patente="AT556VW", marca="Chevrolet", modelo="Cruze", anio="2018",
      clase="auto", uso="particular", compania="2", plan="terceros completo", inicio_fecha="hoy"),
    P("+5491100000319", "se arrepiente", ["hola quiero asegurar mi auto"], objetivo="cancela",
      nombre="Diego Ponce", dni="27666319"),
    P("+5491100000320", "cotiza, contrata y no sabe el chasis ni el valor", ["buenas, precio para asegurar una ecosport?"], objetivo="cotizar_y_alta",
      nombre="Valeria Núñez", dni="39777320", patente="AU667WX", marca="Ford", modelo="EcoSport", anio="2017",
      clase="camioneta", uso="particular", localidad="Banfield", compania="Andina", plan="intermedia", inicio_fecha="hoy"),
]


def responder(persona, bot, estado):
    """Lo que contestaría la persona a lo que dijo el bot (o None si termina)."""
    b = bot.lower()
    d = persona
    # Preguntas intermedias que la persona hace una sola vez.
    if d.get("pregunta_en_medio") and not estado.get("pregunto") and ("compañía" in b or "cobertura" in b or "plan" in b):
        estado["pregunto"] = True
        return d["pregunta_en_medio"]
    if d["objetivo"] == "cancela" and ("patente" in b or "dni" in b) and not estado.get("cancelo"):
        estado["cancelo"] = True
        return "mejor lo pienso y despues les escribo, cancelar"
    if d["objetivo"] in ("cotizar", "cotizar_y_alta") and "datos del vehículo" in b:
        return "\n".join([d["patente"], f"{d['marca']} {d['modelo']}", d["anio"], d["uso"], d["localidad"]])
    if "un asesor te prepara la cotización" in b:
        if d["objetivo"] == "cotizar_y_alta" and not estado.get("pidio_alta"):
            estado["pidio_alta"] = True
            return "dale, quiero contratarlo ya"
        return None
    if "preparé tu solicitud" in b or "solicitud ya está preparada" in b or "registramos tu solicitud" in b or "ya registré tus datos" in b:
        return None
    if "cancelé la preparación" in b or "cancelé la solicitud" in b:
        return None
    if d.get("rotulos") and not estado.get("rotulos_dados") and ("nombre" in b or "patente" in b):
        estado["rotulos_dados"] = True
        return (f"Nombre: {d['nombre']}; DNI: {d['dni']}; Patente: {d['patente']}; Marca: {d['marca']}; "
                f"Modelo: {d['modelo']}; Año: {d['anio']}")
    for clave, palabras in (
        ("nombre", ("nombre y apellido",)), ("dni", ("dni",)), ("patente", ("patente",)),
        ("marca", ("marca",)), ("modelo", ("modelo",)), ("anio", ("qué año", "que año")),
        ("clase", ("auto, moto", "moto, camioneta")), ("uso", ("qué uso", "que uso")),
    ):
        if any(p in b for p in palabras) and d.get(clave):
            if clave == "anio" and d.get("anio_texto"):
                return d["anio_texto"]
            return d[clave] if clave != "nombre" or "dni" not in b else f"{d['nombre']} {d['dni']}"
    if "chasis" in b:
        return "no lo tengo"
    if "valor asegurado" in b:
        return "ni idea"
    if "desde qué fecha" in b or "desde que fecha" in b:
        return d.get("inicio_fecha", "hoy")
    if "hasta qué fecha" in b or "hasta que fecha" in b:
        return "por un año"
    if ("qué plan" in b or "qué cobertura querés" in b) and d.get("plan"):
        return d["plan"]
    if "compañía" in b and d.get("compania"):
        return d["compania"]
    if d["objetivo"] == "curioso":
        return None if estado.get("turnos", 0) >= 1 else None
    return "?"  # la persona no sabe qué contestar: es una falla de comunicación


def conversar(persona, limite=26):
    transcript, estado = [], {}
    pendientes = list(persona["inicio"])
    for _ in range(limite):
        texto = pendientes.pop(0) if pendientes else None
        if texto is None:
            break
        ultimo = registrar_entrante(wa_message_id=f"sim-{uuid.uuid4()}", numero_raw=persona["numero"], texto=texto)
        transcript.append(("CLIENTE", texto))
        if pendientes:  # ráfaga: el resto va pegado
            continue
        r = procesar_mensaje(ultimo.id)
        if r.ignorado:
            transcript.append(("BOT", "(no intervino: chat derivado a una persona)"))
            break
        bot = Mensaje.objects.get(pk=r.mensaje_respuesta_id).texto
        transcript.append(("BOT", bot))
        estado["turnos"] = estado.get("turnos", 0) + 1
        siguiente = responder(persona, bot, estado)
        if siguiente is None:
            break
        if siguiente == "?" and estado.get("perdido"):
            transcript.append(("FALLA", "la persona no entiende qué le piden"))
            break
        estado["perdido"] = siguiente == "?"
        pendientes.append("no entiendo que me pedis" if siguiente == "?" else siguiente)
    acciones = list(AccionPendiente.objects.filter(consulta__contacto__numero=persona["numero"]).values_list("tipo_accion", "estado", "parametros"))
    return transcript, acciones




def correr(solo=None):
    resumen = []
    for persona in PERSONAS:
        if solo and persona["numero"][-3:] not in solo:
            continue
        transcript, acciones = conversar(persona)
        self_out(f"\n######## {persona['numero']} · {persona['estilo']} · objetivo={persona['objetivo']}")
        for quien, texto in transcript:
            self_out(f"  {quien:7}> {texto.replace(chr(10), ' / ')[:230]}")
        for tipo, estado, parametros in acciones:
            self_out(f"  ACCION  > {tipo} [{estado}] {parametros}")
        resumen.append((persona["numero"], persona["objetivo"], [a[0] for a in acciones],
                        any(q == "FALLA" for q, _ in transcript)))
    self_out("\n==== RESUMEN ====")
    for numero, objetivo, acciones, falla in resumen:
        self_out(f"{numero} {objetivo:15} acciones={acciones} {'FALLA' if falla else ''}")
    altas = sum(1 for _, _, a, _ in resumen if "alta_poliza" in a)
    self_out(f"Solicitudes de alta de póliza: {altas}; altas de cliente: {sum(1 for _, _, a, _ in resumen if 'alta_cliente' in a)}")


class _Deshacer(Exception):
    pass


class Command(BaseCommand):
    help = "Simula 20 interesados conversando con el bot y resume qué solicitudes quedaron listas."

    def add_arguments(self, parser):
        parser.add_argument("--solo", default="",
                            help="Últimos 3 dígitos de las personas a correr, separados por coma (p. ej. 305,320).")
        parser.add_argument("--guardar", action="store_true",
                            help="Deja las conversaciones y solicitudes (por defecto se deshace todo).")

    def handle(self, *args, **opciones):
        _salida.clear()
        solo = {x.strip() for x in opciones["solo"].split(",") if x.strip()}
        if opciones["guardar"]:
            correr(solo)
        else:
            try:
                with transaction.atomic():
                    correr(solo)
                    raise _Deshacer
            except _Deshacer:
                self_out("(prueba: se deshizo todo)")
        self.stdout.write(chr(10).join(_salida))
