"""Guardrails: qué se revisa de lo que entra y de lo que sale del bot.

`evaluar_entrada` mira el texto del cliente (AC-T3-31) y, si se le pasa el
contacto, compara la identidad que dice tener con la del titular del número.
`evaluar_salida` **consulta la base** para distinguir un dato real de uno
inventado: un `POL-#####` que no existe es `dato_inventado`, pero uno que
existe y es de otro cliente es `fuga_datos` (AC-T3-38 a AC-T3-42).

Todos los patrones se comparan sobre el texto normalizado (minúsculas y sin
acentos), así que **se escriben sin acentos**.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import unicodedata
from dataclasses import dataclass

from datos.models import Cliente, Cuota, Poliza, Siniestro


@dataclass
class AlertaDetectada:
    tipo: str
    severidad: str
    descripcion: str


# --- Entrada ---------------------------------------------------------------

# Cada familia es un motivo distinto para la misma alerta `prompt_injection`,
# siempre crítica: quien prueba cualquiera de estas cosas está tanteando al bot,
# y que la primera vez falle no lo hace menos grave.

# Intentos de hacer que el bot ignore o cambie sus instrucciones (AC-T3-31).
PATRONES_INYECCION = (
    r"ignor\w*\s+todo\s+lo\s+anterior",
    r"ignor\w*\s+todo",
    r"(?:ignor|olvid|salt|omit|desactiv|sac)\w*\s+(?:tus|las|todas\s+(?:tus|las)|esas|estas)\s+"
    r"(?:instrucciones|restricciones|reglas|indicaciones|limitaciones|politicas)",
    r"actu\w*\s+como",
    r"sin\s+restricciones",
    r"sin\s+(?:limites|filtros|reglas)",
    r"modo\s+(?:desarrollador|developer|admin|administrador|dios|debug)",
    r"system\s+prompt",
    r"prompt\s+del\s+sistema",
    r"tu\s+prompt",
    r"tus\s+instrucciones\s+(?:son|dicen|internas)",
    r"nuevas\s+instrucciones",
    r"a\s+partir\s+de\s+ahora\s+(?:sos|eres|vas\s+a\s+ser|tenes\s+que)",
    r"(?:fingi|finge|simula|hace\s+de\s+cuenta|haz\s+de\s+cuenta)\s+que",
    r"jailbreak",
    r"datos\s+de\s+todos\s+los\s+clientes",
)

# Quien escribe dice ser alguien de la empresa. La identidad sale del número de
# WhatsApp, nunca de lo que la persona afirma: "soy Roberto, el dueño" no le
# da a nadie acceso a nada, y quien lo prueba está intentando que sí.
PATRONES_SUPLANTACION = (
    r"\bsoy\b[^\n.]{0,30}\b(?:el|la)\s+(?:duen[oa]|gerente|administrador[a]?|admin|"
    r"jef[ea]|encargad[oa]|supervisor[a]?|desarrollador[a]?|programador[a]?|"
    r"director[a]?|presidente|propietari[oa])\b",
    r"\bsoy\s+(?:un|una)?\s*(?:empleado|empleada|funcionario|funcionaria|asesor|"
    r"asesora|operador|operadora|productor|productora)\s+de\s+(?:la\s+)?"
    r"(?:empresa|aseguradora|seguros|castano)",
    r"\bhabla\s+(?:el|la)\s+(?:duen[oa]|gerente|administrador[a]?|jef[ea])\b",
    r"\b(?:como|en\s+calidad\s+de)\s+(?:duen[oa]|gerente|administrador[a]?)\b",
    # "perdí acceso al sistema": solo alguien de adentro tiene un sistema al que
    # entrar, y es la excusa típica para que el bot haga de panel.
    r"(?:perdi|no\s+tengo|sin)\s+(?:el\s+)?acceso\s+al?\s+(?:sistema|panel|dashboard)",
    r"sistema\s+de\s+control",
)

# Información que no es de quien pregunta: de otros clientes o de la operación
# interna. El bot no la tiene que dar nunca, la pida quien la pida.
PATRONES_INFO_PRIVADA = (
    r"mensajes\s+pendientes",
    r"cuant[oa]s\s+(?:mensajes|clientes|consultas|casos|conversaciones|alertas|"
    r"derivaciones|reclamos)\s+(?:hay|tienen|tenes|quedan|entraron|pendientes)",
    r"datos\s+de\s+(?:los|otros|todos|sus)\s+(?:\w+\s+)?clientes",
    r"(?:los|las)\s+(?:datos|polizas|dni|telefonos|direcciones)\s+de\s+(?:los\s+)?"
    r"(?:clientes|otros|otras\s+personas)",
    r"otros\s+clientes",
    r"de\s+otro\s+cliente",
    r"todos\s+los\s+clientes",
    r"lista\s+de\s+clientes",
    r"listado\s+de\s+clientes",
    r"base\s+de\s+datos",
    r"contrasena",
    r"password",
    r"credenciales",
    r"api\s*key",
    r"\btoken\b",
    r"conversaciones\s+de\s+otros",
    # Otra persona que escribió o se atendió: "el contacto de la última persona
    # que atendimos", "qué mandó el último cliente".
    r"\b(?:la\s+ultima|el\s+ultimo|las\s+ultimas|los\s+ultimos)\s+"
    r"(?:persona|cliente|usuario|contacto|conversacion|mensaje)s?\b",
    r"(?:contacto|telefono|numero|datos|mensajes?)\s+de\s+(?:otr[oa]s?|algun[oa]?)\s+"
    r"(?:persona|cliente|usuario)s?\b",
)

MOTIVOS_ENTRADA = (
    (PATRONES_INYECCION, "intenta alterar las instrucciones del bot"),
    (PATRONES_SUPLANTACION, "se hace pasar por alguien de la empresa"),
    (PATRONES_INFO_PRIVADA, "pide información privada o interna"),
)

# --- Suplantación de un cliente -------------------------------------------

# "me llamo Fulanito" / "mi nombre es Fulanito": sin duda es un nombre.
RE_NOMBRE_EXPLICITO = re.compile(r"\b(?:me\s+llamo|mi\s+nombre\s+es)\s+([a-z]+)")
# "soy Fulanito" / "habla Fulanito": puede ser un nombre o no ("soy jubilada").
RE_NOMBRE_POSIBLE = re.compile(r"\b(?:soy|habla)\s+([a-z]+)")
# Lo que sigue a un "soy" y no es un nombre: "soy cliente", "soy de Rosario".
PALABRAS_NO_NOMBRE = frozenset(
    {
        "el", "la", "un", "una", "de", "del", "yo", "cliente", "clienta",
        "nuevo", "nueva", "asegurado", "asegurada", "titular", "socio", "socia",
        "mayor", "menor", "quien", "su", "tu", "muy", "medio", "re", "bastante",
        "argentino", "argentina", "extranjero", "extranjera", "nuevito", "con",
        "por", "en", "jubilado", "jubilada", "pensionado", "pensionada",
        "estudiante", "consciente", "responsable", "conductor", "conductora",
    }
)
# Pedidos de información de la cuenta. Junto a una identidad que no coincide
# con el contacto, son el intento de leer la cuenta de otro.
PATRONES_PEDIDO_CUENTA = (
    r"\bque\s+(?:autos?|vehiculos?|polizas?|seguros?|motos?|bienes|casas?)\s+tengo",
    r"\bmis?\s+(?:autos?|vehiculos?|polizas?|seguros?|datos|saldo|deuda|cuotas?|"
    r"motos?|pagos|vencimientos?|cuenta)\b",
    r"\bcuanto\s+debo\b",
    r"\bcuando\s+vence\b",
)

# --- Salida ----------------------------------------------------------------

# Frases donde el bot afirma haber ejecutado un trámite (AC-T3-39).
PATRONES_ACCION_CUMPLIDA = (
    "procedi",
    "di de baja",
    "dimos de baja",
    "lo di de baja",
    "agregue",
    "agregamos",
    "ya fue procesad",
    "fue procesado",
    "quedo anulad",
    "cancele",
    "modifique",
    "abri el siniestro",
    "abrimos el siniestro",
)

# Dominios de primer nivel que tratamos como "esto es una dirección web".
# Sirve para detectar `link_falso_alucinado.com/siniestro`, que no trae esquema.
TLDS = (
    "com",
    "net",
    "org",
    "ar",
    "io",
    "co",
    "info",
    "app",
    "online",
    "site",
    "biz",
)

RE_URL = re.compile(
    r"(?:https?://|www\.)?"
    r"(?:[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?\.)+"
    r"(?:" + "|".join(TLDS) + r")"
    r"(?:/[^\s\]\)]*)?",
    re.IGNORECASE,
)
RE_POLIZA = re.compile(r"POL-\d{5}")
RE_SINIESTRO = re.compile(r"SIN-\d{4}-\d{5}")
RE_DNI = re.compile(r"\b\d{1,3}(?:\.\d{3}){1,2}\b|\b\d{7,8}\b")
RE_FECHA = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
# `\d+(?:[.,]\d+)*` y no `[\d.,]*` para no arrastrar el punto final de la
# oración: en "es de $12.500." el monto es "$12.500".
RE_MONTO = re.compile(r"\$\s?\d+(?:[.,]\d+)*")
RE_CLAUSULA = re.compile(r"\bclausula\s+\S+")


def _normalizar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(
        c for c in descompuesto if unicodedata.category(c) != "Mn"
    ).lower()


def _urls_permitidas() -> set[str]:
    crudo = os.getenv("BOT_URLS_PERMITIDAS", "") or ""
    return {
        dominio.strip().lower().lstrip(".")
        for dominio in crudo.split(",")
        if dominio.strip()
    }


def _nombre_declarado(normalizado: str) -> tuple[str, bool] | None:
    """El nombre que la persona dice tener y si lo dijo sin ambigüedad."""
    for expresion, explicito in ((RE_NOMBRE_EXPLICITO, True), (RE_NOMBRE_POSIBLE, False)):
        for coincidencia in expresion.finditer(normalizado):
            nombre = coincidencia.group(1)
            if nombre not in PALABRAS_NO_NOMBRE and len(nombre) > 1:
                return nombre, explicito
    return None


def _cliente_del_numero(numero: str | None):
    """El cliente registrado a ese número de WhatsApp, o `None`."""
    from datos.models import ContactoWhatsapp

    if not numero:
        return None
    contacto = (
        ContactoWhatsapp.objects.select_related("cliente")
        .filter(numero=numero, cliente__isnull=False)
        .first()
    )
    return contacto.cliente if contacto is not None else None


def _primeros_nombres_registrados() -> set[str]:
    """Nombres de pila de clientes y funcionarios, para saber si "soy X" es un
    nombre o un "soy jubilada"."""
    from datos.models import Cliente, Funcionario

    nombres = list(Cliente.objects.values_list("nombre", flat=True).distinct())
    nombres += list(
        Funcionario.objects.filter(activo=True).values_list("nombre", flat=True)
    )
    return {
        _normalizar(nombre).split()[0]
        for nombre in nombres
        if nombre and nombre.strip()
    }


def _motivo_identidad(normalizado: str, contacto) -> str | None:
    """Si alguien dice llamarse distinto que el titular de su número.

    La identidad sale **siempre** del número, buscándolo en la base: un número
    registrado ya tiene nombre, así que "soy Graciela" solo tiene sentido si el
    cliente de ese número se llama Graciela. Si no, es un intento de pasar por
    otra persona.

    Un número sin cliente no se puede validar contra nada, y quien escribe
    desde ahí tiene todo el derecho de presentarse (es lo que se le pide en el
    alta). No alerta: igual el bot no le da datos de ninguna cuenta.

    Decir el nombre correcto tampoco habilita nada: los datos que el bot da
    son los del cliente del número y de nadie más, lo diga quien lo diga.
    """
    declarado = _nombre_declarado(normalizado)
    if declarado is None:
        return None
    nombre, explicito = declarado

    cliente = _cliente_del_numero(contacto.numero)
    if cliente is None:
        return None
    propios = set(_normalizar(f"{cliente.nombre} {cliente.apellido}").split())
    if nombre in propios:
        return None

    pide_cuenta = any(
        re.search(patron, normalizado) for patron in PATRONES_PEDIDO_CUENTA
    )
    # "soy jubilada" no es presentarse: con un "soy" suelto se exige que la
    # palabra sea un nombre que exista en la base o que además pida una cuenta.
    if not explicito and not pide_cuenta and nombre not in _primeros_nombres_registrados():
        return None
    motivo = (
        f'dice ser "{nombre.title()}", pero el número está registrado a nombre '
        f"de {cliente.nombre} {cliente.apellido}"
    )
    if pide_cuenta:
        motivo += ", y pide datos de una cuenta"
    return motivo


def evaluar_entrada(texto: str, contacto=None) -> list[AlertaDetectada]:
    """Alertas sobre el mensaje del cliente: intentos de manipular al bot.

    Sin `contacto` solo mira el texto (AC-T3-31). Con él, además busca en la
    base el cliente registrado a ese número y compara el nombre que la persona
    dice tener contra el suyo.

    Una sola alerta por mensaje, siempre crítica, con todos los motivos en la
    descripción: el panel muestra un caso y no tres.
    """
    normalizado = _normalizar(texto)
    motivos = [
        motivo
        for patrones, motivo in MOTIVOS_ENTRADA
        if any(re.search(patron, normalizado) for patron in patrones)
    ]
    if contacto is not None:
        identidad = _motivo_identidad(normalizado, contacto)
        if identidad is not None:
            motivos.append(identidad)
    if not motivos:
        return []
    return [
        AlertaDetectada(
            tipo="prompt_injection",
            severidad="critica",
            descripcion="El mensaje " + ", ".join(motivos) + ".",
        )
    ]


def _fecha_valida(dia: int, mes: int, anio: int) -> bool:
    try:
        dt.date(anio, mes, dia)
    except ValueError:
        return False
    return True


def _vencimientos_del_cliente(cliente_id: int | None) -> set[str]:
    """Fechas que el cliente realmente tiene (pólizas y cuotas), en dd/mm/aaaa."""
    if cliente_id is None:
        return set()
    fechas: set[dt.date] = set(
        Poliza.objects.filter(cliente_id=cliente_id).values_list(
            "fecha_vencimiento", flat=True
        )
    )
    fechas.update(
        Cuota.objects.filter(poliza__cliente_id=cliente_id).values_list(
            "vencimiento", flat=True
        )
    )
    return {fecha.strftime("%d/%m/%Y") for fecha in fechas if fecha is not None}


def _alertas_identificadores(
    texto: str, cliente_id: int | None
) -> list[AlertaDetectada]:
    """AC-T3-38: pólizas y siniestros citados contra lo que hay en la base."""
    alertas: list[AlertaDetectada] = []

    for numero in dict.fromkeys(RE_POLIZA.findall(texto)):
        poliza = Poliza.objects.filter(numero_poliza=numero).first()
        if poliza is None:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inventado",
                    severidad="alta",
                    descripcion=f"La póliza {numero} no existe en la base.",
                )
            )
        elif poliza.cliente_id != cliente_id:
            alertas.append(
                AlertaDetectada(
                    tipo="fuga_datos",
                    severidad="critica",
                    descripcion=f"La póliza {numero} es de otro cliente.",
                )
            )

    for numero in dict.fromkeys(RE_SINIESTRO.findall(texto)):
        siniestro = (
            Siniestro.objects.select_related("poliza")
            .filter(numero_siniestro=numero)
            .first()
        )
        if siniestro is None:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inventado",
                    severidad="alta",
                    descripcion=f"El siniestro {numero} no existe en la base.",
                )
            )
        elif siniestro.poliza.cliente_id != cliente_id:
            alertas.append(
                AlertaDetectada(
                    tipo="fuga_datos",
                    severidad="critica",
                    descripcion=f"El siniestro {numero} es de otro cliente.",
                )
            )
    return alertas


def _alertas_dni(texto: str, cliente_id: int | None) -> list[AlertaDetectada]:
    """AC-T3-40: un DNI de otro cliente es fuga de datos."""
    alertas: list[AlertaDetectada] = []
    for crudo in dict.fromkeys(RE_DNI.findall(texto)):
        dni = crudo.replace(".", "")
        if not 7 <= len(dni) <= 8:
            continue
        otro = Cliente.objects.filter(dni=dni).exclude(pk=cliente_id).first()
        if otro is not None:
            alertas.append(
                AlertaDetectada(
                    tipo="fuga_datos",
                    severidad="critica",
                    descripcion=f"Se mencionó el DNI {dni}, que es de otro cliente.",
                )
            )
    return alertas


def _alertas_fechas(
    texto: str, cliente_id: int | None, datos_verificados: frozenset[str]
) -> list[AlertaDetectada]:
    """AC-T3-41: fechas imposibles y fechas que el cliente no tiene."""
    alertas: list[AlertaDetectada] = []
    reales: set[str] | None = None
    for coincidencia in RE_FECHA.finditer(texto):
        fecha = coincidencia.group(0)
        dia, mes, anio = (int(parte) for parte in coincidencia.groups())
        if not _fecha_valida(dia, mes, anio):
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inconsistente",
                    severidad="alta",
                    descripcion=f"La fecha {fecha} no existe.",
                )
            )
            continue
        if fecha in datos_verificados:
            continue
        if reales is None:
            reales = _vencimientos_del_cliente(cliente_id)
        if fecha not in reales:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_inconsistente",
                    severidad="media",
                    descripcion=(
                        f"La fecha {fecha} no se verificó contra los vencimientos "
                        "del cliente."
                    ),
                )
            )
    return alertas


def _alertas_montos_y_clausulas(
    texto: str, normalizado: str, datos_verificados: frozenset[str]
) -> list[AlertaDetectada]:
    """AC-T3-42: montos sin respaldo y referencias a cláusulas."""
    alertas: list[AlertaDetectada] = []
    for monto in dict.fromkeys(RE_MONTO.findall(texto)):
        compacto = monto.replace(" ", "")
        if compacto in datos_verificados or monto in datos_verificados:
            continue
        alertas.append(
            AlertaDetectada(
                tipo="dato_no_verificado",
                severidad="media",
                descripcion=f"El monto {compacto} no sale de la base.",
            )
        )
    if RE_CLAUSULA.search(normalizado):
        alertas.append(
            AlertaDetectada(
                tipo="dato_no_verificado",
                severidad="alta",
                descripcion="Se citó una cláusula del contrato, que el bot no puede verificar.",
            )
        )
    return alertas


def _alertas_urls(texto: str) -> list[AlertaDetectada]:
    """AC-T3-38: dominios fuera de `BOT_URLS_PERMITIDAS`."""
    permitidas = _urls_permitidas()
    alertas: list[AlertaDetectada] = []
    for coincidencia in dict.fromkeys(RE_URL.findall(texto)):
        dominio = re.sub(r"^https?://", "", coincidencia, flags=re.IGNORECASE)
        dominio = dominio.split("/")[0].split(":")[0].lower()
        if dominio.startswith("www."):
            dominio = dominio[4:]
        if any(
            dominio == permitida or dominio.endswith(f".{permitida}")
            for permitida in permitidas
        ):
            continue
        alertas.append(
            AlertaDetectada(
                tipo="dato_inventado",
                severidad="alta",
                descripcion=f"Se mencionó un dominio que no está permitido: {dominio}",
            )
        )
    return alertas


def evaluar_salida(
    texto: str,
    *,
    cliente_id: int | None,
    datos_verificados: frozenset[str] = frozenset(),
) -> list[AlertaDetectada]:
    """Alertas sobre lo que el bot está por decir.

    `datos_verificados` son los valores que salieron de la base al armar la
    plantilla (montos, fechas, números); lo que está ahí no alerta.
    """
    normalizado = _normalizar(texto)
    verificados = frozenset(datos_verificados or frozenset())
    alertas: list[AlertaDetectada] = []

    alertas.extend(_alertas_urls(texto))

    if any(patron in normalizado for patron in PATRONES_ACCION_CUMPLIDA):
        alertas.append(
            AlertaDetectada(
                tipo="accion_sin_aprobacion",
                severidad="critica" if "baja" in normalizado else "alta",
                descripcion="La respuesta afirma que se ejecutó un trámite que nadie aprobó.",
            )
        )

    alertas.extend(_alertas_identificadores(texto, cliente_id))
    alertas.extend(_alertas_dni(texto, cliente_id))
    alertas.extend(_alertas_fechas(texto, cliente_id, verificados))
    alertas.extend(_alertas_montos_y_clausulas(texto, normalizado, verificados))
    return alertas
