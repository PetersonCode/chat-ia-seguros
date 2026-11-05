"""Corpus de mensajes reales-en-estilo: cómo escribe la gente, no cómo pincha al bot.

Cada cliente de la cartera demo tiene su manera de escribir. El corpus sirve
para tres cosas, así que no se pierde nada de lo que se aprende simulando:

1. `ejemplos_para_llm()` elige pares mensaje → código que se le muestran a Qwen
   como turnos previos (aprendizaje en contexto): un modelo chico mejora mucho
   más con ejemplos concretos que con reglas abstractas.
2. `negocio/tests/test_corpus_conversaciones.py` verifica que el clasificador
   final (reglas + LLM simulado) no retroceda en ninguno de estos mensajes.
3. `python manage.py evaluar_bot` mide reglas, Qwen y el orquestador completo
   contra este corpus (ver docs/OPERACION.md).

`tipo` es el código que el orquestador debe terminar usando. Cuando un mensaje
va en ráfaga con el anterior, `rafaga=True`: se agrupa antes de clasificar.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Mensaje:
    texto: str
    tipo: str
    rafaga: bool = False  # se manda pegado al anterior y se clasifica junto
    para_llm: bool = False  # se usa como ejemplo en el prompt de Qwen


@dataclass(frozen=True)
class Conversacion:
    whatsapp: str  # número del cliente en la cartera demo
    estilo: str
    mensajes: tuple[Mensaje, ...] = field(default_factory=tuple)


M = Mensaje

CORPUS: tuple[Conversacion, ...] = (
    Conversacion("+5491100000201", "formal, persona mayor", (
        M("Buenas tardes. Quisiera saber, por favor, cuánto adeudo de mi seguro.", "saldo", para_llm=True),
        M("¿Y en qué fecha vence la póliza del Corolla?", "vencimiento"),
        M("Le agradezco mucho, que tenga usted un buen día.", "agradecimiento"),
    )),
    Conversacion("+5491100000202", "abreviado, joven", (
        M("hola q tal", "saludo", para_llm=True),
        M("q debo algo?", "saldo", para_llm=True),
        M("xq me cobraron 2 veces la cuota??", "reclamo", para_llm=True),
        M("tmb kiero saber q me cubre el seguro del c3", "consulta_cobertura", para_llm=True),
    )),
    Conversacion("+5491100000203", "todo en mayúsculas", (
        M("NECESITO EL NUMERO DE LA GRUA ESTOY EN LA RUTA 2", "asistencia", para_llm=True),
        M("GRACIAS", "agradecimiento"),
    )),
    Conversacion("+5491100000204", "con errores de ortografía (moroso)", (
        M("ola kiero saver cuanto devo", "saldo", para_llm=True),
        M("como ago para pagar", "pago", para_llm=True),
        M("puedo pagar en cuotas lo q devo?", "pago"),
    )),
    Conversacion("+5491100000205", "dictado por voz, sin puntuación", (
        M("hola buen dia queria consultar si mi seguro cubre si me rompen el vidrio del auto para robarme algo",
          "consulta_cobertura", para_llm=True),
        M("y hasta cuando tengo el seguro del honda", "vencimiento"),
    )),
    Conversacion("+5491100000206", "con emojis", (
        M("holaaa 👋😊", "saludo", para_llm=True),
        M("me chocaron de atras en un semaforo 😡 estamos bien igual", "siniestro_urgente"),
        M("como hago la denuncia? 🙏", "siniestro", para_llm=True),
    )),
    Conversacion("+5491100000207", "en ráfaga de mensajes cortos", (
        M("hola", "vencimiento"),
        M("una consulta", "vencimiento", rafaga=True),
        M("cuando se me vence", "vencimiento", rafaga=True),
        M("el seguro del cruze", "vencimiento", rafaga=True),
    )),
    Conversacion("+5491100000208", "mezcla inglés", (
        M("hi! necesito el numero de policy del corolla", "vencimiento", para_llm=True),
        M("thanks!!", "agradecimiento"),
    )),
    Conversacion("+5491100000209", "trabajo, utilitario", (
        M("buen dia, quiero agregar a mi hijo como chofer de la fiorino", "modificacion", para_llm=True),
        M("tiene 19 años y registro hace 1", "modificacion"),  # sigue la misma solicitud: no se duplica
    )),
    Conversacion("+5491100000210", "pregunta precio", (
        M("cuanto me sale asegurar una moto 110?", "cotizacion"),
    )),
    Conversacion("+5491100000211", "enojada (morosa)", (
        M("es una verguenza, me siguen debitando y nadie me responde", "reclamo", para_llm=True),
        M("quiero hablar con una persona YA", "otro", para_llm=True),
    )),
    Conversacion("+5491100000212", "vendió el auto", (
        M("vendi la kangoo, como la saco del seguro?", "baja", para_llm=True),
    )),
    Conversacion("+5491100000213", "granizo", (
        M("anoche cayo piedra y me abollo todo el capot", "siniestro", para_llm=True),
        M("eso me lo cubren?", "consulta_cobertura", para_llm=True),
    )),
    Conversacion("+5491100000214", "lunfardo", (
        M("che me afanaron el estereo de la amarok", "siniestro_urgente"),  # «me robaron…» se deriva urgente
        M("la posta no se que hacer", "otro"),
    )),
    Conversacion("+5491100000215", "necesita la credencial", (
        M("necesito la tarjeta del seguro q me la pide la policia", "credencial"),
    )),
    Conversacion("+5491100000216", "no quiere recordatorios", (
        M("no me manden mas recordatorios porfa", "baja_avisos"),
    )),
    Conversacion("+5491100000217", "atrasada con las cuotas (morosa)", (
        M("estoy atrasada con las cuotas, puedo pagar la semana q viene?", "pago", para_llm=True),
    )),
    Conversacion("+5491100000218", "pregunta fuera del servicio", (
        M("a q hora abren la oficina", "otro", para_llm=True),
        M("pasame con alguien", "otro"),
    )),
    Conversacion("+5491100000219", "auto que no arranca", (
        M("buenas! el auto no arranca, estoy en la puerta de casa", "asistencia", para_llm=True),
        M("creo q es la bateria", "asistencia", para_llm=True),
    )),
    Conversacion("+5491100000220", "pregunta por la franquicia", (
        M("cuanto es la franquicia de mi poliza?", "consulta_cobertura", para_llm=True),
        M("y si me roban la fiorino que pasa", "consulta_cobertura", para_llm=True),
    )),
    # Simulación del 05/11/2026: cinco clientes reciben el recordatorio de la
    # cuota, avisan que pagaron, pasan el comprobante y preguntan la cobertura
    # (ver api/tests/test_simulacion_cobro_y_cobertura.py).
    Conversacion("+5491100007700", "formal, tras el recordatorio", (
        M("Buenas tardes, ya pagué la cuota de este mes.", "pago", para_llm=True),
        M("¿Qué me cubre mi póliza?", "consulta_cobertura"),
    )),
    Conversacion("+5491100007701", "apurado, sin tildes", (
        M("realice el pago recien", "pago", para_llm=True),
        M("y que cubre?", "consulta_cobertura"),
    )),
    Conversacion("+5491100007702", "home banking", (
        M("aboné por home banking", "pago", para_llm=True),
        M("mi seguro cubre granizo?", "consulta_cobertura"),
    )),
    Conversacion("+5491100007703", "transferencia", (
        M("te transferí hace un rato", "pago", para_llm=True),
        M("que cobertura tengo", "consulta_cobertura", para_llm=True),
    )),
    Conversacion("+5491100007704", "con faltas", (
        M("hice la transferencia, te paso el comprobante", "pago"),
        M("kiero saver q me cubre", "consulta_cobertura"),
    )),
    Conversacion("+5491126914442", "Daniel, prueba real", (
        M("Pague el seguro", "pago", para_llm=True),
        M("Comprobante 1111222", "pago"),
        M("Realice el pago", "pago"),
    )),
)


# Variantes de control: nunca se le muestran a Qwen. Miden si generaliza a
# formas nuevas de decir lo mismo, en vez de repetir los ejemplos de memoria.
VARIANTES: tuple[Mensaje, ...] = (
    M("buenas noches, me podrian decir cuanto me queda por pagar?", "saldo"),
    M("toy al dia con el seguro?", "saldo"),
    M("cuando caduca mi seguro", "vencimiento"),
    M("q onda todo bien?", "saludo"),
    M("buen diaaa", "saludo"),
    M("mil gracias genia", "agradecimiento"),
    M("se me pincho una goma en la panamericana a quien llamo", "asistencia"),
    M("me quede sin bateria en el super", "asistencia"),
    M("me robaron el auto recien de la puerta de casa", "siniestro_urgente"),
    M("ayer un colectivo me rayo toda la puerta del auto", "siniestro"),
    M("me cubre si se me inunda el auto?", "consulta_cobertura"),
    M("tengo cobertura de cristales?", "consulta_cobertura"),
    M("quiero cambiar los datos de mi direccion, me mude", "modificacion"),
    M("quiero cancelar el seguro de la camioneta", "baja"),
    M("me cobraron mal este mes", "reclamo"),
    M("pague y me sigue figurando deuda, que onda", "reclamo"),
    M("se puede pagar con mercado pago?", "pago"),
    M("cuanto saldria asegurar un gol 2015", "cotizacion"),
    M("dejen de mandarme avisos", "baja_avisos"),
    M("me pasas la credencial del auto?", "credencial"),
    M("quien gano el partido anoche", "ajeno"),
    M("necesito hablar con un humano", "otro"),
    M("estoy atrasado 2 meses, como regularizo", "pago"),
    M("kiero saver q me cubre", "consulta_cobertura"),
    M("ya esta pago el seguro de la moto", "pago"),
    M("deposite la cuota ayer", "pago"),
    M("les pase el comprobante por aca", "pago"),
)


def todos_los_mensajes():
    """(conversación, mensaje) en orden, incluidos los de ráfaga."""
    for conversacion in CORPUS:
        for mensaje in conversacion.mensajes:
            yield conversacion, mensaje


def turnos(conversacion: Conversacion) -> list[tuple[str, str]]:
    """Los turnos tal como los ve el clasificador: la ráfaga va unida por líneas."""
    resultado: list[tuple[str, str]] = []
    for mensaje in conversacion.mensajes:
        if mensaje.rafaga and resultado:
            texto, _ = resultado[-1]
            resultado[-1] = (texto + "\n" + mensaje.texto, mensaje.tipo)
        else:
            resultado.append((mensaje.texto, mensaje.tipo))
    return resultado


def ejemplos_para_llm() -> list[tuple[str, str]]:
    """Pares (mensaje, código) para mostrarle a Qwen como turnos previos."""
    return [(m.texto, m.tipo) for _, m in todos_los_mensajes() if m.para_llm]
