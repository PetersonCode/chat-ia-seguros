"""Datos para cotizar: patente, marca y modelo, año, uso y localidad (P5).

Cuando alguien pregunta cuánto sale asegurar su auto, el bot no lo deriva en
seco: primero le pide, **en ese orden**, los cinco datos que un asesor necesita
para cotizar, y recién con lo que haya juntado pasa el caso a Graciela. Así la
persona arranca con el vehículo en la mano en vez de empezar la charla de cero.

**No agrega estado**, igual que `registro.py`: el rastro es `MARCA_PEDIDO_COTIZACION`
en un saliente del bot, y lo que el cliente contestó son sus entrantes
posteriores a ese saliente. Se pide como mucho `MAX_PEDIDOS` veces; después se
deriva con lo que haya, porque seguir insistiendo es dejarlo sin atención.

El LLM no participa (R12): todo sale de expresiones regulares y de listas
cortas, y **lo que no se puede leer con certeza se deja vacío**. Un dato
dudoso no se inventa ni se adivina: el asesor lo pregunta, y la conversación
completa está a la vista en el panel.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from datos.limpieza import normalizar_patente
from datos.models import Direccion, Emisor, Mensaje, UsoVehiculo
from negocio.bot import plantillas
from negocio.bot.registro import MAX_PEDIDOS, NO_SE_MOSTRARON

__all__ = ["DatosCotizacion", "MAX_PEDIDOS", "datos_de_la_cotizacion"]

ANIO_MINIMO = 1950

# El orden del pedido (y de las etiquetas).
ETIQUETAS = {
    "patente": "la patente",
    "marca_modelo": "marca y modelo",
    "anio": "el año",
    "uso": "el uso (particular, comercial…)",
    "localidad": "la localidad",
}

NOMBRES = {
    "patente": "patente",
    "marca_modelo": "marca y modelo",
    "anio": "año",
    "uso": "uso",
    "localidad": "localidad",
}

# Marcas de dos palabras: sin esta lista «Alfa Romeo Giulietta» quedaría con
# marca «Alfa» y modelo «Romeo Giulietta».
MARCAS_DE_DOS_PALABRAS = frozenset(
    {
        "alfa romeo", "mercedes benz", "land rover", "great wall",
        "aston martin", "rolls royce", "ssang yong", "range rover",
    }
)

# Palabras (sin acentos) → uso del vehículo (los valores de `UsoVehiculo`).
USO_POR_PALABRA = {
    "particular": UsoVehiculo.PARTICULAR,
    "personal": UsoVehiculo.PARTICULAR,
    "familiar": UsoVehiculo.PARTICULAR,
    "comercial": UsoVehiculo.COMERCIAL,
    "trabajo": UsoVehiculo.COMERCIAL,
    "laboral": UsoVehiculo.COMERCIAL,
    "remis": UsoVehiculo.REMIS_TAXI,
    "remise": UsoVehiculo.REMIS_TAXI,
    "taxi": UsoVehiculo.REMIS_TAXI,
    "uber": UsoVehiculo.REMIS_TAXI,
    "cabify": UsoVehiculo.REMIS_TAXI,
    "carga": UsoVehiculo.CARGA,
    "flete": UsoVehiculo.CARGA,
    "camion": UsoVehiculo.CARGA,
}

# Segmentos que no dicen nada y se descartan enteros.
RELLENO = frozenset(
    {
        "hola", "buenas", "buen dia", "buenos dias", "buenas tardes",
        "buenas noches", "gracias", "muchas gracias", "dale", "ok", "listo",
        "si", "no", "claro", "perfecto", "por favor", "ahi va", "ahi te paso",
    }
)

# Si aparece alguna de estas palabras en lo que sobra, no es un dato sino
# charla ("hola, mi patente es…"): se descarta todo, no se adivina.
NO_ES_DATO = frozenset(
    {
        "hola", "buenas", "buen", "dia", "dias", "tardes", "noches", "gracias",
        "favor", "mi", "mis", "es", "son", "soy", "estoy", "vivo", "tengo",
        "patente", "dominio", "ano", "anio", "uso", "marca", "modelo",
        "localidad", "ciudad", "quiero", "necesito", "cotizar", "cotizacion",
        "seguro", "poliza", "cobertura", "precio", "cuanto", "cuesta", "sale",
        "asegurar", "auto", "vehiculo", "camioneta", "un", "una", "dale", "ok",
        "listo", "ahi", "va", "no", "si", "nada", "te", "paso", "datos", "aca",
        "van", "todo", "siguiente",
    }
)

# Etiquetas al empezar un renglón: «marca: Toyota», «localidad: Rosario».
_RE_ETIQUETA = re.compile(
    r"^\s*(marca\s+y\s+modelo|marca|modelo|localidad|ciudad|zona|vivo\s+en|soy\s+de)\b"
    r"\s*[:=\-]?\s*(\S.*)$",
    re.IGNORECASE,
)
_RE_ETIQUETA_PATENTE = re.compile(r"^\s*(?:la\s+)?(?:patente|dominio)\s*(?:es|:)?\s*", re.IGNORECASE)
_RE_VINETA = re.compile(r"^\s*(?:[-•*]|\d{1,2}\s*[.)])\s+")

# Auto nuevo y moto nueva son inconfundibles y valen en cualquier lado. Las
# viejas (ABC123 / 123ABC) también parecen modelos ("CBR 250"): con separador
# solo valen si son el renglón entero.
_PATENTES_CLARAS = (
    re.compile(r"\b([A-Za-z]{2})[\s.-]?(\d{3})[\s.-]?([A-Za-z]{2})\b"),
    re.compile(r"\b([A-Za-z])[\s.-]?(\d{3})[\s.-]?([A-Za-z]{3})\b"),
)
_PATENTES_VIEJAS = (
    re.compile(r"\b([A-Za-z]{3})[\s.-]?(\d{3})\b"),
    re.compile(r"\b(\d{3})[\s.-]?([A-Za-z]{3})\b"),
)
_RE_ANIO = re.compile(r"\(?((?:19[5-9]|20\d)\d)\)?")
# Palabras que anuncian un dato y se van con él: «año 2020», «uso particular».
_ROTULOS = frozenset({"uso", "de", "para", "es", "del", "ano", "anio", "modelo"})


@dataclass(frozen=True)
class DatosCotizacion:
    """Lo que se juntó para cotizar, y cuántas veces se pidió."""

    patente: str | None = None
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    uso: str | None = None
    localidad: str | None = None
    intentos: int = 0

    @property
    def faltantes(self) -> tuple[str, ...]:
        """Los datos que faltan, en el orden del pedido."""
        faltan = []
        if self.patente is None:
            faltan.append("patente")
        if self.marca is None or self.modelo is None:
            faltan.append("marca_modelo")
        if self.anio is None:
            faltan.append("anio")
        if self.uso is None:
            faltan.append("uso")
        if self.localidad is None:
            faltan.append("localidad")
        return tuple(faltan)

    @property
    def completos(self) -> bool:
        return not self.faltantes

    def _etiqueta(self, campo: str) -> str:
        if campo == "marca_modelo":
            if self.marca is not None:
                return "el modelo"
            if self.modelo is not None:
                return "la marca"
        return ETIQUETAS[campo]

    def texto_faltantes(self) -> str:
        """«la patente, marca y modelo y el año» (para el pedido)."""
        etiquetas = [self._etiqueta(campo) for campo in self.faltantes]
        if len(etiquetas) <= 1:
            return "".join(etiquetas)
        return ", ".join(etiquetas[:-1]) + " y " + etiquetas[-1]

    def como_datos(self) -> dict[str, Any]:
        """Para `Interesado.datos`: solo lo que se juntó."""
        datos = {
            "patente": self.patente,
            "marca": self.marca,
            "modelo": self.modelo,
            "anio": self.anio,
            "uso": self.uso,
            "localidad": self.localidad,
        }
        return {clave: valor for clave, valor in datos.items() if valor is not None}

    def resumen(self) -> str:
        """Una línea para el motivo de la derivación, que es lo que ve el asesor."""
        if not self.como_datos():
            return "Datos para cotizar: no dio ninguno."
        partes = []
        if self.patente:
            partes.append(f"patente {self.patente}")
        marca_modelo = " ".join(p for p in (self.marca, self.modelo) if p)
        if marca_modelo:
            partes.append(f"vehículo {marca_modelo}")
        if self.anio:
            partes.append(f"año {self.anio}")
        if self.uso:
            partes.append(f"uso {UsoVehiculo(self.uso).label.lower()}")
        if self.localidad:
            partes.append(f"localidad {self.localidad}")
        texto = "Datos para cotizar: " + "; ".join(partes) + "."
        if not self.completos:
            faltan = ", ".join(NOMBRES[campo] for campo in self.faltantes)
            texto += f" Faltan: {faltan} (no los completó en {self.intentos} pedido(s))."
        return texto


# --- Texto -----------------------------------------------------------------


def _sin_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _normalizado(texto: str) -> str:
    """Minúsculas, sin acentos ni signos: para comparar contra las listas."""
    limpio = re.sub(r"[^\w\s]", " ", _sin_acentos(texto).lower())
    return " ".join(limpio.split())


def _segmentos(texto: str) -> list[str]:
    """Los renglones de una respuesta. Separa por línea, `;` y coma (menos la decimal)."""
    segmentos = []
    for crudo in re.split(r"[\n;]+|,(?!\d)", texto or ""):
        segmento = _RE_VINETA.sub("", crudo).strip(" \t.!¡?¿")
        if segmento and _normalizado(segmento) not in RELLENO:
            segmentos.append(segmento)
    return segmentos


def _titulo(texto: str) -> str:
    return texto.title() if texto.islower() else texto


# --- Extracción de cada dato -------------------------------------------------


def _quitar(texto: str, inicio: int, fin: int) -> str:
    return " ".join(f"{texto[:inicio]} {texto[fin:]}".split())


def _patente_en(segmento: str) -> tuple[str, str] | None:
    """(patente, lo que sobra del renglón), o `None`."""
    sin_etiqueta = _RE_ETIQUETA_PATENTE.sub("", segmento, count=1)
    for patron in _PATENTES_CLARAS:
        for coincidencia in patron.finditer(segmento):
            try:
                patente = normalizar_patente("".join(coincidencia.groups()))
            except ValueError:
                continue
            return patente, _quitar(segmento, coincidencia.start(), coincidencia.end())
    for patron in _PATENTES_VIEJAS:
        for coincidencia in patron.finditer(segmento):
            junta = "".join(coincidencia.groups())
            # Sin separador (CBR250) vale donde esté; con separador, solo si es todo el renglón.
            contigua = coincidencia.group(0) == junta
            es_todo = patron.fullmatch(sin_etiqueta.strip()) is not None
            if not (contigua or es_todo):
                continue
            try:
                patente = normalizar_patente(junta)
            except ValueError:
                continue
            return patente, _quitar(segmento, coincidencia.start(), coincidencia.end())
    return None


def _uso_en(segmento: str) -> tuple[str, str] | None:
    """(uso, lo que sobra), por palabra clave. Quita también el «uso», «de», «para» que lo anuncia."""
    palabras = segmento.split()
    for indice, palabra in enumerate(palabras):
        uso = USO_POR_PALABRA.get(_normalizado(palabra))
        if uso is None:
            continue
        desde = indice
        while desde > 0 and _normalizado(palabras[desde - 1]) in _ROTULOS:
            desde -= 1
        return uso.value, " ".join(palabras[:desde] + palabras[indice + 1 :])
    return None


def _anio_en(segmento: str) -> tuple[int, str] | None:
    """(año, lo que sobra). Con varios números de cuatro cifras, el último es el año.

    Se va con su rótulo si lo tiene: «año 2020», «modelo 2020», «del 2020».
    """
    maximo = timezone.localdate().year + 1
    palabras = segmento.split()
    candidatos = []
    for indice, palabra in enumerate(palabras):
        coincidencia = _RE_ANIO.fullmatch(palabra.strip(".,;:"))
        if coincidencia and ANIO_MINIMO <= int(coincidencia.group(1)) <= maximo:
            candidatos.append((indice, int(coincidencia.group(1))))
    if not candidatos:
        return None
    indice, anio = candidatos[-1]
    desde = indice
    while desde > 0 and _normalizado(palabras[desde - 1]) in _ROTULOS:
        desde -= 1
    return anio, " ".join(palabras[:desde] + palabras[indice + 1 :])


def _texto_libre(resto: str) -> str | None:
    """Lo que sobra de un renglón, si parece un dato (un nombre, un lugar) y no charla."""
    limpio = re.sub(r"^(?:tengo\s+(?:un|una)|mi\s+(?:auto|moto|veh[ií]culo)\s+es(?:\s+(?:un|una))?|vivo\s+en|soy\s+de|estoy\s+en|en)\s+", "", resto.strip(" -:.,;"), flags=re.IGNORECASE)
    palabras = limpio.split()
    if _normalizado(limpio) in {"el", "la", "mi", "un", "una"}:
        return None
    if not palabras or len(palabras) > 6 or len(limpio) > 60:
        return None
    if sum(c.isalpha() for c in limpio) < 2:
        return None
    if any(_normalizado(p) in NO_ES_DATO for p in palabras):
        return None
    return _titulo(limpio)


def _separar_marca_modelo(texto: str) -> tuple[str, str | None]:
    palabras = texto.split()
    if len(palabras) >= 2 and _normalizado(" ".join(palabras[:2])) in MARCAS_DE_DOS_PALABRAS:
        corte = 2
    else:
        corte = 1
    marca = " ".join(palabras[:corte])
    modelo = " ".join(palabras[corte:]) or None
    return marca, modelo


# --- Interpretar una tanda de respuestas -------------------------------------


def _interpretar(respuestas: list[str], actuales: dict[str, Any]) -> dict[str, Any]:
    """Suma a lo ya sabido lo que se pueda leer con certeza en estas respuestas.

    Primero lo que se reconoce solo (patente, año, uso, renglones con rótulo).
    Lo que sobra son textos libres —marca y modelo, localidad— y solo se asignan
    cuando no hay duda (ver `_asignar_libres`). Con «Toyota Corolla Rosario» en un
    renglón y dos datos por completar no se sabe dónde corta, y se deja para el
    asesor.
    """
    datos = dict(actuales)
    # En el orden en que el cliente los escribió: ("patente"|"anio"|"uso"|"libre", texto).
    eventos: list[tuple[str, str | None]] = []

    for respuesta in respuestas:
        for segmento in _segmentos(respuesta):
            if segmento.endswith(":"):
                continue  # «te paso todo:» anuncia lo que viene, no es un dato
            etiquetado = _RE_ETIQUETA.match(segmento)
            if etiquetado:
                _asignar_con_etiqueta(datos, _normalizado(etiquetado.group(1)), etiquetado.group(2))
                continue
            resto = segmento
            tipados: list[str] = []
            if hallado := _patente_en(resto):
                datos.setdefault('patente',hallado[0]); resto = hallado[1]
                tipados.append("patente")
            if hallado := _uso_en(resto):
                datos.setdefault('uso',hallado[0]); resto = hallado[1]
                tipados.append("uso")
            if hallado := _anio_en(resto):
                datos.setdefault('anio',hallado[0]); resto = hallado[1]
                tipados.append("anio")
            libre = _texto_libre(resto) if resto.strip(" -:.,;") else None
            eventos.extend(_eventos_del_renglon(tipados, libre))

    _asignar_libres(datos, eventos)
    return datos


def _eventos_del_renglon(
    tipados: list[str], libre: str | None
) -> list[tuple[str, str | None]]:
    """Los eventos de un renglón, en el orden en que el pedido los espera.

    En un mismo renglón la patente va primero, el vehículo después y el año al
    final («AB123CD Toyota Corolla 2020»). Si el renglón junta solo un uso con un
    texto libre («particular Rosario» o «Toyota particular») no se sabe de qué
    lado cae: el texto queda como `libre_dudoso` y no se ubica por posición.
    """
    if libre is None:
        return [(tipo, None) for tipo in tipados]
    if "patente" in tipados or "anio" in tipados:
        orden = [t for t in ("patente",) if t in tipados]
        orden += ["libre"]
        orden += [t for t in ("anio", "uso") if t in tipados]
        return [(tipo, libre if tipo == "libre" else None) for tipo in orden]
    if tipados:  # solo un uso
        return [("libre_dudoso", libre), *[(tipo, None) for tipo in tipados]]
    return [("libre", libre)]


def _anio_exacto(valor: str) -> int | None:
    """El año si el valor es solo eso («2012»), y es razonable."""
    coincidencia = _RE_ANIO.fullmatch(valor.strip(" .,;:"))
    maximo = timezone.localdate().year + 1
    if coincidencia and ANIO_MINIMO <= int(coincidencia.group(1)) <= maximo:
        return int(coincidencia.group(1))
    return None


def _asignar_con_etiqueta(datos: dict[str, Any], etiqueta: str, valor: str) -> None:
    # «Modelo 2012» se dice tanto del modelo del auto como de su año.
    if etiqueta == "modelo" and (anio := _anio_exacto(valor)) is not None:
        if datos.get("anio") is None:
            datos["anio"] = anio
        return
    libre = _texto_libre(valor)
    if libre is None:
        return
    if etiqueta == "marca y modelo":
        if datos.get("marca") is None and datos.get("modelo") is None:
            _poner_vehiculo(datos, libre)
    elif etiqueta == "marca":
        datos["marca"] = datos.get("marca") or libre
    elif etiqueta == "modelo":
        datos["modelo"] = datos.get("modelo") or libre
    elif datos.get("localidad") is None:  # localidad, ciudad, zona, vivo en, soy de
        datos["localidad"] = libre


def _asignar_libres(datos: dict[str, Any], eventos: list[tuple[str, str | None]]) -> None:
    """Reparte los textos libres entre «marca y modelo» y «localidad» sin adivinar.

    El pedido sale en un orden fijo (patente, marca y modelo, año, uso, localidad),
    y quien contesta uno por línea lo respeta. Eso alcanza para decidir cuando:

    * falta un solo dato libre: todo lo libre es ese;
    * faltan los dos y hay dos renglones libres: el primero es el vehículo;
    * faltan los dos y hay un renglón libre: es el vehículo si después viene el año
      o el uso, o si justo antes vino la patente; es la localidad si antes vino el
      año o el uso. Si nada lo ubica, no se asigna.

    Cualquier otro caso es ambiguo y queda sin completar.
    """
    es_libre = ("libre", "libre_dudoso")
    libres = [texto for tipo, texto in eventos if tipo in es_libre]
    if not libres:
        return
    pide_vehiculo = datos.get("marca") is None or datos.get("modelo") is None
    pide_localidad = datos.get("localidad") is None

    if pide_vehiculo and pide_localidad:
        if len(libres) == 2:
            _poner_vehiculo(datos, libres[0])
            datos["localidad"] = libres[1]
        elif len(libres) == 1:
            posicion = next(i for i, (tipo, _) in enumerate(eventos) if tipo in es_libre)
            if eventos[posicion][0] == "libre_dudoso":
                return
            antes = [tipo for tipo, _ in eventos[:posicion]]
            despues = [tipo for tipo, _ in eventos[posicion + 1 :]]
            if any(tipo in ("anio", "uso") for tipo in despues) or antes[-1:] == ["patente"]:
                _poner_vehiculo(datos, libres[0])
            elif any(tipo in ("anio", "uso") for tipo in antes):
                datos["localidad"] = libres[0]
    elif pide_vehiculo:
        _poner_vehiculo(datos, " ".join(libres))
    elif pide_localidad:
        datos["localidad"] = ", ".join(libres)


def _poner_vehiculo(datos: dict[str, Any], texto: str) -> None:
    if datos.get("marca") is None and datos.get("modelo") is None:
        marca, modelo = _separar_marca_modelo(texto)
        datos["marca"] = marca
        if modelo is not None:
            datos["modelo"] = modelo
    elif datos.get("marca") is None:
        datos["marca"] = texto
    else:
        datos["modelo"] = texto


# --- Reconstruir el pedido desde el log --------------------------------------


def _es_del_bot_y_visible(mensaje: Mensaje) -> bool:
    return (
        mensaje.direccion == Direccion.SALIENTE
        and mensaje.estado_envio not in NO_SE_MOSTRARON
    )


def datos_de_la_cotizacion(conversacion_id: int) -> DatosCotizacion:
    """Reconstruye el pedido desde el log: qué se pidió y qué contestó el cliente.

    Cuenta solo desde el último cierre (`COTIZACION_REGISTRADA`), así una
    cotización nueva en la misma conversación empieza de cero. La patente, que
    es inconfundible, también se lee de lo que dijo **antes** del primer pedido
    («quiero cotizar el AB123CD»); también se aprovechan los datos explícitos del primer mensaje y la ficha del mismo contacto.
    """
    mensajes = list(
        Mensaje.objects.filter(conversacion_id=conversacion_id)
        .order_by("fecha_hora", "id")
        .only("id", "direccion", "emisor", "texto", "estado_envio")
    )
    inicio = 0
    for indice, mensaje in enumerate(mensajes):
        if _es_del_bot_y_visible(mensaje) and plantillas.COTIZACION_REGISTRADA in (mensaje.texto or ""):
            inicio = indice + 1
    mensajes = mensajes[inicio:]

    pedidos = [
        indice
        for indice, mensaje in enumerate(mensajes)
        if _es_del_bot_y_visible(mensaje)
        and plantillas.MARCA_PEDIDO_COTIZACION in (mensaje.texto or "")
    ]

    def del_cliente(desde: int, hasta: int) -> list[str]:
        return [
            mensaje.texto or ""
            for mensaje in mensajes[desde:hasta]
            if mensaje.direccion == Direccion.ENTRANTE and mensaje.emisor == Emisor.CLIENTE
        ]

    datos: dict[str, Any] = {}
    antes = pedidos[0] if pedidos else len(mensajes)
    for texto in del_cliente(0, antes):
        for segmento in _segmentos(texto):
            hallada = _patente_en(segmento)
            if hallada:
                datos["patente"] = hallada[0]
    datos = _interpretar(del_cliente(0, antes), datos)

    for posicion, indice in enumerate(pedidos):
        fin = pedidos[posicion + 1] if posicion + 1 < len(pedidos) else len(mensajes)
        datos = _interpretar(del_cliente(indice + 1, fin), datos)

    # Reutilizar la ficha del mismo contacto sin arrastrar otro vehículo.
    from datos.models import Conversacion
    from negocio.interesados import interesado_abierto_de
    contacto_id = Conversacion.objects.filter(pk=conversacion_id).values_list('contacto_id',flat=True).first()
    interesado = interesado_abierto_de(contacto_id) if contacto_id else None
    guardados = interesado.datos if interesado else {}
    if inicio == 0 and (not datos.get('patente') or datos.get('patente') == guardados.get('patente')):
        for campo in ('patente','marca','modelo','anio','uso','localidad'):
            if not datos.get(campo) and guardados.get(campo):datos[campo]=guardados[campo]

    return DatosCotizacion(
        patente=datos.get("patente"),
        marca=datos.get("marca"),
        modelo=datos.get("modelo"),
        anio=datos.get("anio"),
        uso=datos.get("uso"),
        localidad=datos.get("localidad"),
        intentos=len(pedidos),
    )
