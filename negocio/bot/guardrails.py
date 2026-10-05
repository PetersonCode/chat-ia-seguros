import re
import unicodedata
from dataclasses import dataclass


@dataclass
class AlertaDetectada:
    tipo: str
    severidad: str
    descripcion: str


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.lower()


def _pasar_a_set(texto: str):
    return {token for token in re.findall(r"[a-z0-9]+", _normalizar(texto)) if token}


def evaluar_entrada(texto: str):
    texto_norm = _normalizar(texto)
    alertas = []
    patrones_inyeccion = [
        "ignora todo",
        "ignorá todo",
        "olvidá tus instrucciones",
        "actuá como",
        "sin restricciones",
        "no seas",
        "como un bot sin",
        "revelá todos los datos",
        "datos de todos",
    ]
    if any(p in texto_norm for p in patrones_inyeccion):
        alertas.append(
            AlertaDetectada(
                tipo="prompt_injection",
                severidad="alta",
                descripcion="Se detectó un intento de manipular al bot.",
            )
        )
    return alertas


def evaluar_salida(texto: str, *, cliente_id: int | None, datos_verificados: frozenset[str] = frozenset()):
    texto_norm = _normalizar(texto)
    alertas = []
    if re.search(r"(?:https?://|www\.)\S+", texto):
        for match in re.findall(r"(?:https?://|www\.)\S+", texto):
            dominio = re.sub(r"^https?://", "", match)
            dominio = dominio.split("/")[0].split(":")[0]
            if dominio and not any(dominio.endswith(p) for p in ("seguroscastano.com", "castano.com", "localhost")):
                if "bot_urls_permitidas" not in texto_norm:
                    alertas.append(
                        AlertaDetectada(
                            tipo="dato_inventado",
                            severidad="alta",
                            descripcion=f"Se mencionó un dominio no permitido: {dominio}",
                        )
                    )
    patrones_accion = [
        "procedi", "di de baja", "dimos de baja", "agregué", "agregamos", "ya fue procesad", "fue procesado",
        "quedó anulad", "cancelé", "modifiqué", "abrí el siniestro", "abrimos el siniestro", "lo di de baja",
    ]
    if any(p in texto_norm for p in patrones_accion):
        severidad = "critica" if "baja" in texto_norm or "di de baja" in texto_norm or "dimos de baja" in texto_norm else "alta"
        alertas.append(
            AlertaDetectada(
                tipo="accion_sin_aprobacion",
                severidad=severidad,
                descripcion="La salida afirma que se ejecutó una acción sin aprobación.",
            )
        )

    for patron in (r"POL-[0-9]{5}", r"SIN-[0-9]{4}-[0-9]{5}"):
        if re.search(patron, texto):
            # Si no hay evidencia y no está en datos verificados, se trata como dato inventado.
            if not any(token in datos_verificados for token in re.findall(patron, texto)):
                alertas.append(
                    AlertaDetectada(
                        tipo="dato_inventado",
                        severidad="alta",
                        descripcion="Se citó un identificador que no se verificó con la base de datos.",
                    )
                )

    for dnis in re.findall(r"\d{7,8}", texto):
        if dnis and cliente_id is not None:
            # Para una prueba simple no se relaciona con base; se exige que las salidas con DNI no verificados se ignoren o marquen según se use.
            if dnis not in datos_verificados:
                alertas.append(
                    AlertaDetectada(
                        tipo="dato_no_verificado",
                        severidad="media",
                        descripcion=f"Se mencionó un DNI no verificado: {dnis}",
                    )
                )

    # Fechas inválidas o no verificadas
    fechas = re.findall(r"\b\d{1,2}/\d{1,2}/\d{4}\b", texto)
    for fecha in fechas:
        if fecha not in datos_verificados:
            if fecha.startswith("30/02") or fecha.startswith("31/02"):
                alertas.append(
                    AlertaDetectada(
                        tipo="dato_inconsistente",
                        severidad="alta",
                        descripcion=f"La fecha {fecha} es imposible.",
                    )
                )
            else:
                alertas.append(
                    AlertaDetectada(
                        tipo="dato_inconsistente",
                        severidad="media",
                        descripcion=f"La fecha {fecha} no fue verificada.",
                    )
                )

    montos = re.findall(r"\$\s?[0-9][0-9\.,]*", texto)
    for monto in montos:
        if monto.replace("$", "").replace(".", "").replace(",", "") not in datos_verificados and monto not in datos_verificados:
            alertas.append(
                AlertaDetectada(
                    tipo="dato_no_verificado",
                    severidad="media",
                    descripcion=f"El monto {monto} no se verificó con la base.",
                )
            )

    if "clausula" in texto_norm:
        alertas.append(
            AlertaDetectada(
                tipo="dato_no_verificado",
                severidad="alta",
                descripcion="Se hizo referencia a una cláusula no verificada.",
            )
        )

    return alertas
