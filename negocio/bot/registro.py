"""Alta de datos antes de derivar a una persona: nombre y DNI.

A un desconocido —un contacto sin cliente en la base— el bot no lo deriva en
seco: primero le pide nombre y DNI, y recién con eso pasa el caso a un asesor,
que lo recibe listo para darlo de alta.

**No agrega estado.** No hay tabla ni columna para "le estamos pidiendo los
datos": el log de mensajes ya lo dice. El rastro es `MARCA_PEDIDO_DATOS` en un
saliente del bot, y lo que el cliente contestó son sus entrantes posteriores a
ese saliente. Leer el DNI solo después del pedido es justamente lo que evita
que un `30444555` anterior —un número de póliza, un importe, el DNI de otro—
se tome por el documento de quien escribe.

El LLM no participa (R12): nombre y DNI salen de expresiones regulares.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from datos.models import ConsultaBot, Direccion, Emisor, EstadoEnvio, Mensaje
from negocio.bot import plantillas

# Cuántas veces pide los datos antes de derivar igual. Sin este techo, alguien
# que no quiere o no puede darlos no llega nunca a un humano, y eso es peor que
# derivarlo incompleto: el asesor siempre puede pedírselos él.
MAX_PEDIDOS = 2

# Mismo criterio que `guardrails.RE_DNI`, para que lo que acá se toma por
# documento sea exactamente lo que allá se vigila: 7 u 8 dígitos, con o sin
# puntos de miles.
RE_DNI = re.compile(r"\b\d{1,3}(?:\.\d{3}){1,2}\b|\b\d{7,8}\b")

# Una palabra de un nombre: letras (con acentos), apóstrofos y guiones. Se
# escribe con `[^\W\d_]` y no con `\w` porque `\w` incluye dígitos.
_PALABRA = r"[^\W\d_](?:[^\W\d_]|['’-])*"
RE_NOMBRE = re.compile(rf"^{_PALABRA}(?:\s+{_PALABRA}){{0,4}}$", re.UNICODE)

# "Hola, mi nombre es Juan Pérez" -> "Juan Pérez". El orden importa: lo más
# largo primero, si no "mi nombre es" se corta en "nombre:".
PREFIJOS_NOMBRE = (
    "mi nombre completo es",
    "nombre y apellido:",
    "nombre completo:",
    "mi nombre es",
    "me llamo",
    "nombre:",
    "soy",
)

# Si alguna de estas palabras aparece en el candidato, no es un nombre. Están
# sin acentos porque se comparan normalizadas. No incluye partículas como "de"
# o "la": son parte de apellidos reales ("Juan de la Cruz").
PALABRAS_NO_NOMBRE = frozenset(
    {
        "hola", "buenas", "buen", "dia", "dias", "tardes", "noches",
        "gracias", "dni", "documento", "numero", "si", "no", "ok", "dale",
        "favor", "quiero", "necesito", "hablar", "asesor", "humano",
        "urgente", "ayuda", "consulta", "seguro", "poliza", "es", "mi",
    }
)

# Cómo se le nombra cada dato al cliente en el pedido.
ETIQUETAS = {
    "nombre": "tu nombre y apellido",
    "dni": "tu DNI (solo números)",
}

NO_SE_MOSTRARON = frozenset({EstadoEnvio.RETENIDO, EstadoEnvio.DESCARTADO})


@dataclass(frozen=True)
class DatosRegistro:
    """Lo que se juntó para dar de alta a quien escribe, y cuánto se insistió.

    `nombre_cliente` es el que dio él; `nombre_perfil` es el de su perfil de
    WhatsApp, que Meta manda y `registrar_entrante` guarda. El del perfil sirve
    de respaldo —así nadie queda atascado por no escribir su nombre— pero suele
    ser un apodo ("Dani"), y por eso `resumen` avisa de dónde salió para que el
    asesor lo confirme.
    """

    nombre_cliente: str | None = None
    nombre_perfil: str | None = None
    dni: str | None = None
    intentos: int = 0

    @property
    def nombre(self) -> str | None:
        return self.nombre_cliente or self.nombre_perfil

    @property
    def nombre_es_del_perfil(self) -> bool:
        return self.nombre_cliente is None and self.nombre_perfil is not None

    @property
    def faltantes(self) -> tuple[str, ...]:
        """Lo que todavía hay que pedirle **a él**, en orden de pedido.

        El nombre figura mientras no lo haya escrito, aunque tengamos el del
        perfil: el primer pedido tiene que nombrar los dos datos.
        """
        faltan = []
        if self.nombre_cliente is None:
            faltan.append("nombre")
        if self.dni is None:
            faltan.append("dni")
        return tuple(faltan)

    @property
    def completos(self) -> bool:
        """Alcanza para derivar: el DNI lo tiene que dar él, el nombre puede
        salir del perfil."""
        return self.dni is not None and self.nombre is not None

    def texto_faltantes(self) -> str:
        return " y ".join(ETIQUETAS[campo] for campo in self.faltantes)

    def resumen(self) -> str:
        """Una línea para el motivo de la derivación, que es lo que ve el asesor."""
        partes = []
        if self.nombre:
            origen = (
                " (nombre del perfil de WhatsApp, conviene confirmarlo)"
                if self.nombre_es_del_perfil
                else ""
            )
            partes.append(f"nombre {self.nombre}{origen}")
        else:
            partes.append("sin nombre")
        partes.append(f"DNI {self.dni}" if self.dni else "sin DNI")
        if not self.completos:
            partes.append(f"no los completó en {self.intentos} pedido(s)")
        return "Datos para registrar: " + "; ".join(partes) + "."


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _sin_prefijo(segmento: str) -> tuple[str, bool]:
    """Corta el "me llamo" de adelante. Devuelve el resto y si hubo prefijo.

    Busca sobre el texto en minúsculas pero recorta sobre el original, para no
    perder los acentos ni las mayúsculas del nombre. `lower()` no cambia el
    largo en español, así que los índices siguen alineados.
    """
    bajo = segmento.lower()
    for prefijo in PREFIJOS_NOMBRE:
        posicion = bajo.find(prefijo)
        if posicion != -1:
            return segmento[posicion + len(prefijo) :], True
    return segmento, False


def _nombre_en(texto: str) -> str | None:
    """El nombre que hay en un mensaje del cliente, o `None`.

    Sin un "me llamo" que lo anuncie se exigen dos palabras: a un "dale" o un
    "urgente" sueltos no hay que tomarlos por nombre.
    """
    for segmento in re.split(r"[\n,;.!?]+", texto or ""):
        candidato, con_prefijo = _sin_prefijo(segmento)
        candidato = RE_DNI.sub(" ", candidato)
        candidato = re.sub(r"\s+", " ", candidato).strip(" -:")
        if not candidato or not RE_NOMBRE.match(candidato):
            continue
        palabras = candidato.split()
        if len(palabras) < (1 if con_prefijo else 2):
            continue
        if any(_sin_acentos(p).lower() in PALABRAS_NO_NOMBRE for p in palabras):
            continue
        return candidato.title() if candidato.islower() else candidato
    return None


def _dni_en(texto: str) -> str | None:
    for crudo in RE_DNI.findall(texto or ""):
        dni = crudo.replace(".", "")
        if 7 <= len(dni) <= 8:
            return dni
    return None


def datos_del_registro(conversacion_id: int, contacto) -> DatosRegistro:
    """Reconstruye el alta desde el log: qué se pidió y qué contestó el cliente.

    Los entrantes se leen desde el **primer** pedido, no desde el último: si dio
    el nombre en la primera vuelta y el DNI en la segunda, los dos cuentan.
    """
    mensajes = list(
        Mensaje.objects.filter(conversacion_id=conversacion_id)
        .order_by("fecha_hora", "id")
        .only("id", "direccion", "emisor", "texto", "estado_envio")
    )

    intentos = 0
    primer_pedido: int | None = None
    for indice, mensaje in enumerate(mensajes):
        if (
            mensaje.direccion == Direccion.SALIENTE
            and plantillas.MARCA_PEDIDO_DATOS in (mensaje.texto or "")
            # Un pedido retenido o descartado no llegó: no gastó un intento.
            and mensaje.estado_envio not in NO_SE_MOSTRARON
        ):
            intentos += 1
            if primer_pedido is None:
                primer_pedido = indice

    nombre_perfil = (getattr(contacto, "nombre_perfil", None) or "").strip() or None
    if primer_pedido is None:
        return DatosRegistro(nombre_perfil=nombre_perfil, intentos=0)

    nombre: str | None = None
    dni: str | None = None
    for mensaje in mensajes[primer_pedido + 1 :]:
        if mensaje.direccion != Direccion.ENTRANTE or mensaje.emisor != Emisor.CLIENTE:
            continue
        nombre = nombre or _nombre_en(mensaje.texto or "")
        dni = dni or _dni_en(mensaje.texto or "")

    return DatosRegistro(
        nombre_cliente=nombre,
        nombre_perfil=nombre_perfil,
        dni=dni,
        intentos=intentos,
    )


def alta_es_por_registro(conversacion_id: int) -> bool:
    """Si el alta en curso nació de un "quiero registrarme".

    Cambia cómo termina: un alta pedida por el cliente se cierra dejando la
    acción lista para aprobar y nada más; una que el bot intercaló antes de
    derivar también deriva, porque ahí había algo más que atender.

    Se lee del log, como todo lo demás de este módulo: el tipo quedó guardado
    en la `ConsultaBot` del turno en que la persona lo pidió.
    """
    return ConsultaBot.objects.filter(
        conversacion_id=conversacion_id, tipo_consulta__codigo="registro"
    ).exists()


def parametros_de_alta(datos: DatosRegistro, contacto) -> dict:
    """Los parámetros de la acción `alta_cliente`, con lo que se haya juntado.

    El apellido sale de partir el nombre por el primer espacio. Si el cliente
    dio una sola palabra no se inventa nada: la acción nace sin apellido,
    `_faltantes` lo reporta y el panel se lo pide a quien va a aprobar. Es
    justamente para eso que existe `completar_parametros`.
    """
    parametros: dict = {"telefono": getattr(contacto, "numero", "")}
    nombre = (datos.nombre or "").strip()
    if nombre:
        partes = nombre.split()
        parametros["nombre"] = partes[0]
        if len(partes) > 1:
            parametros["apellido"] = " ".join(partes[1:])
    if datos.dni:
        parametros["dni"] = datos.dni
    if datos.nombre_es_del_perfil:
        # Para que quien aprueba sepa que ese nombre no lo escribió el cliente.
        parametros["origen_nombre"] = "perfil de WhatsApp"
    return parametros
