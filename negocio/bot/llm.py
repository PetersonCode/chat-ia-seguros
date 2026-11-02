"""Clientes de LLM (AC-T3-34).

El LLM solo **clasifica** y, si está configurado, redacta el **saludo**. Nunca
es fuente de datos (R12): los montos, fechas y números salen de la base y se
insertan en las plantillas fijas.

Si el LLM falla, tarda más de `TIMEOUT_SEGUNDOS` o contesta un código fuera del
catálogo de `prompts.CODIGOS_CONSULTA`, el orquestador cae al clasificador por
reglas. Con `LLM_PROVIDER=none` no se hace ninguna llamada.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol
from urllib import request

from negocio.bot.prompts import (
    CODIGOS_CONSULTA,
    MAX_HISTORIAL,
    SISTEMA_CLASIFICADOR,
    SISTEMA_SALUDO,
)

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = 15


class LLMClient(Protocol):
    """Lo mínimo que el orquestador le pide a un LLM."""

    def clasificar(self, texto: str, historial: list[str]) -> str | None:
        """Código de `CODIGOS_CONSULTA`, o `None` si no se pudo clasificar."""

    def charlar(self, texto: str, historial: list[str]) -> str | None:
        """Texto libre para el saludo, o `None` para usar la plantilla fija."""


def _mensajes(
    sistema: str, texto: str, historial: list[str], rotulo: str = "Mensaje del cliente"
) -> list[dict[str, str]]:
    """Arma el cuerpo del chat con, como máximo, `MAX_HISTORIAL` mensajes.

    El historial va como contexto en un único turno rotulado, no como turnos
    `user` sueltos. Mandándolos sueltos el modelo no distingue cuál de todos
    tiene que atender y arrastra la intención de los anteriores: un "tuve un
    accidente" después de haber hablado de saldos se clasificaba `saldo`, con
    lo que un siniestro urgente podía terminar respondido con la plantilla de
    pólizas en vez de derivarse a una persona.
    """
    mensajes = [{"role": "system", "content": sistema}]
    previos = list(historial or [])[-MAX_HISTORIAL:]
    if previos:
        contexto = "\n".join(f"- {linea}" for linea in previos)
        mensajes.append(
            {
                "role": "user",
                "content": (
                    "Mensajes anteriores del cliente, solo como contexto. "
                    f"No respondas a estos:\n{contexto}"
                ),
            }
        )
        mensajes.append({"role": "assistant", "content": "Entendido."})
    mensajes.append({"role": "user", "content": f"{rotulo}:\n{texto}"})
    return mensajes


class NullLLM:
    """No hay LLM: el orquestador usa reglas y plantillas fijas."""

    def clasificar(self, texto: str, historial: list[str]) -> str | None:
        return None

    def charlar(self, texto: str, historial: list[str]) -> str | None:
        return None


class FakeLLM:
    """LLM de prueba. `respuestas` define qué contesta a cada llamada."""

    def __init__(
        self,
        clasificacion: str | None = None,
        charla: str | None = None,
        excepcion: Exception | None = None,
    ) -> None:
        self.clasificacion = clasificacion
        self.charla = charla
        self.excepcion = excepcion
        self.llamadas: list[tuple[str, str, list[str]]] = []

    def clasificar(self, texto: str, historial: list[str]) -> str | None:
        self.llamadas.append(("clasificar", texto, list(historial or [])))
        if self.excepcion is not None:
            raise self.excepcion
        return self.clasificacion

    def charlar(self, texto: str, historial: list[str]) -> str | None:
        self.llamadas.append(("charlar", texto, list(historial or [])))
        if self.excepcion is not None:
            raise self.excepcion
        return self.charla


class OpenAICompatClient:
    """`POST {LLM_BASE_URL}/chat/completions` con `urllib`, sin dependencias."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        modelo: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.modelo = modelo or os.getenv("LLM_MODEL", "")

    def _completar(self, mensajes: list[dict[str, str]]) -> str | None:
        cuerpo = json.dumps(
            {"model": self.modelo, "messages": mensajes, "temperature": 0}
        ).encode("utf-8")
        peticion = request.Request(
            f"{self.base_url}/chat/completions",
            data=cuerpo,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with request.urlopen(peticion, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        opciones = datos.get("choices") or []
        if not opciones:
            return None
        contenido = (opciones[0].get("message") or {}).get("content")
        return contenido.strip() if isinstance(contenido, str) else None

    def clasificar(self, texto: str, historial: list[str]) -> str | None:
        contenido = self._completar(
            _mensajes(
                SISTEMA_CLASIFICADOR, texto, historial, rotulo="Mensaje a clasificar"
            )
        )
        if contenido is None:
            return None
        codigo = contenido.strip().strip(".").lower()
        return codigo if codigo in CODIGOS_CONSULTA else None

    def charlar(self, texto: str, historial: list[str]) -> str | None:
        return self._completar(_mensajes(SISTEMA_SALUDO, texto, historial))


def cliente_llm() -> LLMClient:
    """Devuelve el cliente que corresponde a `LLM_PROVIDER`."""
    proveedor = os.getenv("LLM_PROVIDER", "none").strip().lower()
    if proveedor in {"", "none"}:
        return NullLLM()
    if proveedor == "openai_compat":
        if not os.getenv("LLM_BASE_URL") or not os.getenv("LLM_MODEL"):
            logger.warning(
                "LLM_PROVIDER=openai_compat sin LLM_BASE_URL o LLM_MODEL: se usan reglas."
            )
            return NullLLM()
        return OpenAICompatClient()
    logger.warning("LLM_PROVIDER desconocido (%s): se usan reglas.", proveedor)
    return NullLLM()


def clasificar_con_llm(
    cliente: LLMClient, texto: str, historial: list[str]
) -> str | None:
    """Clasifica con el LLM tragándose cualquier falla (AC-T3-34)."""
    try:
        codigo = cliente.clasificar(texto, historial)
    except Exception:
        logger.exception("El LLM falló al clasificar; se usa el clasificador por reglas.")
        return None
    if codigo is None:
        return None
    codigo = str(codigo).strip().lower()
    if codigo not in CODIGOS_CONSULTA:
        logger.warning("El LLM devolvió un código fuera del catálogo: %r", codigo)
        return None
    return codigo


def charlar_con_llm(
    cliente: LLMClient, texto: str, historial: list[str]
) -> str | None:
    """Pide el saludo al LLM tragándose cualquier falla."""
    try:
        respuesta = cliente.charlar(texto, historial)
    except Exception:
        logger.exception("El LLM falló al redactar el saludo; se usa la plantilla.")
        return None
    if not respuesta or not str(respuesta).strip():
        return None
    return str(respuesta).strip()
