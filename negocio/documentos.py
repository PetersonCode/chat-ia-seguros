from __future__ import annotations

import math
import re
import unicodedata

from django.db import transaction
from django.utils import timezone

from datos.models import DocumentoGeneral, EstadoDocumento, FragmentoDocumento, Funcionario
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado, PermisoDenegado

MAXIMO_CONTENIDO = 500_000
MAXIMO_FRAGMENTO = 1200
MAXIMO_RESULTADOS = 5


def _aprobador(funcionario_id):
    funcionario = Funcionario.objects.select_for_update().filter(pk=funcionario_id).first()
    if funcionario is None:
        raise NoEncontrado("El funcionario no existe.")
    if not funcionario.activo or not funcionario.puede_aprobar:
        raise PermisoDenegado("La gestión documental requiere un aprobador activo.")
    return funcionario


STOPWORDS = {
    "a", "al", "algo", "como", "con", "cual", "cuando", "de", "del", "donde",
    "el", "ella", "en", "es", "esta", "este", "la", "las", "lo", "los", "mas",
    "me", "mi", "mis", "o", "para", "pero", "por", "que", "se", "sin", "su",
    "sus", "un", "una", "unas", "uno", "unos", "y", "yo",
}


def _normalizar(texto: str) -> str:
    texto = texto.lower().replace("ñ", "\x00")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return texto.replace("\x00", "ñ")


def _terminos(texto: str) -> set[str]:
    return {
        termino
        for termino in re.findall(r"[a-zñ0-9]+", _normalizar(texto))
        if termino not in STOPWORDS
    }


def _partir_contenido(contenido: str) -> list[str]:
    contenido = " ".join(contenido.split())
    fragmentos = []
    inicio = 0
    while len(contenido) - inicio > MAXIMO_FRAGMENTO:
        fin = inicio + MAXIMO_FRAGMENTO
        for indice in range(fin, inicio, -1):
            if contenido[indice - 1].isspace():
                fin = indice
                break
        fragmento = contenido[inicio:fin]
        if fragmento.strip():
            fragmentos.append(fragmento)
        inicio = fin
    if inicio < len(contenido):
        fragmento = contenido[inicio:]
        if fragmento.strip():
            fragmentos.append(fragmento)
    return fragmentos


def _requeridos(cantidad_terminos: int) -> int:
    return min(cantidad_terminos, max(1, math.ceil(cantidad_terminos / 2)))


def puntuar_fragmento(consulta: str, texto: str) -> tuple[int, int]:
    """Devuelve términos coincidentes y total de términos buscables."""
    terminos_consulta = _terminos(consulta)
    coincidencias = terminos_consulta & _terminos(texto)
    return len(coincidencias), len(terminos_consulta)


@transaction.atomic
def crear_documento(
    *,
    titulo: str,
    version: str,
    referencia: str,
    contenido: str,
    funcionario_id: int,
) -> DocumentoGeneral:
    titulo = titulo.strip()
    version = version.strip()
    referencia = referencia.strip()
    contenido = contenido.strip()
    if not titulo or not version or not referencia:
        raise DatosInvalidos("Título, versión y referencia son obligatorios.")
    if not contenido or len(contenido) > MAXIMO_CONTENIDO:
        raise DatosInvalidos(
            f"El contenido debe tener entre 1 y {MAXIMO_CONTENIDO} caracteres."
        )
    if DocumentoGeneral.objects.filter(titulo=titulo, version=version).exists():
        raise DatosInvalidos("Ya existe un documento con ese título y versión.")
    funcionario = _aprobador(funcionario_id)
    documento = DocumentoGeneral.objects.create(
        titulo=titulo,
        version=version,
        referencia=referencia,
        estado=EstadoDocumento.BORRADOR,
        creado_por=funcionario,
    )
    FragmentoDocumento.objects.bulk_create(
        [
            FragmentoDocumento(documento=documento, orden=orden, texto=texto)
            for orden, texto in enumerate(_partir_contenido(contenido), start=1)
        ]
    )
    return documento


@transaction.atomic
def aprobar_documento(documento_id: int, funcionario_id: int) -> DocumentoGeneral:
    documento = (
        DocumentoGeneral.objects.select_for_update()
        .filter(pk=documento_id)
        .first()
    )
    if documento is None:
        raise NoEncontrado("El documento no existe.")
    if documento.estado != EstadoDocumento.BORRADOR:
        raise EstadoInvalido("Solo se pueden aprobar documentos en borrador.")
    if not documento.fragmentos.exists():
        raise DatosInvalidos("No se puede aprobar un documento sin contenido.")
    funcionario = _aprobador(funcionario_id)
    documento.estado = EstadoDocumento.APROBADO
    documento.aprobado_por = funcionario
    documento.aprobado_en = timezone.now()
    documento.save(update_fields=("estado", "aprobado_por", "aprobado_en"))
    return documento


@transaction.atomic
def retirar_documento(documento_id: int, funcionario_id: int) -> DocumentoGeneral:
    documento = (
        DocumentoGeneral.objects.select_for_update()
        .filter(pk=documento_id)
        .first()
    )
    if documento is None:
        raise NoEncontrado("El documento no existe.")
    if documento.estado != EstadoDocumento.APROBADO:
        raise EstadoInvalido("Solo se pueden retirar documentos aprobados.")
    funcionario = _aprobador(funcionario_id)
    documento.estado = EstadoDocumento.RETIRADO
    documento.retirado_por = funcionario
    documento.retirado_en = timezone.now()
    documento.save(update_fields=("estado", "retirado_por", "retirado_en"))
    return documento


def buscar_fragmentos(consulta: str) -> dict:
    terminos_consulta = _terminos(consulta)
    if not terminos_consulta:
        return {
            "respaldo_suficiente": False,
            "mensaje": (
                "No hay términos significativos para buscar en las fuentes aprobadas; "
                "no se ofrece una respuesta."
            ),
            "resultados": [],
        }

    resultados = []
    for fragmento in FragmentoDocumento.objects.filter(
        documento__estado=EstadoDocumento.APROBADO
    ).select_related("documento"):
        coincidencias, total_terminos = puntuar_fragmento(consulta, fragmento.texto)
        if coincidencias < _requeridos(total_terminos):
            continue
        documento = fragmento.documento
        resultados.append(
            {
                "documento_id": documento.id,
                "fragmento_id": fragmento.id,
                "titulo": documento.titulo,
                "version": documento.version,
                "referencia": documento.referencia,
                "pasaje": fragmento.texto,
                "coincidencias": coincidencias,
                "terminos_consulta": total_terminos,
            }
        )
    resultados.sort(
        key=lambda resultado: (
            -resultado["coincidencias"] / resultado["terminos_consulta"],
            -resultado["coincidencias"],
            resultado["titulo"].casefold(),
            resultado["documento_id"],
        )
    )
    resultados = resultados[:MAXIMO_RESULTADOS]
    return {
        "respaldo_suficiente": bool(resultados),
        "mensaje": (
            "Se encontraron pasajes coincidentes en fuentes aprobadas."
            if resultados
            else "No hay respaldo suficiente en las fuentes aprobadas; no se ofrece una respuesta."
        ),
        "resultados": resultados,
    }
