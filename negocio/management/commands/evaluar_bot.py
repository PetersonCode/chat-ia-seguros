"""Mide el bot contra el corpus de conversaciones (negocio/bot/corpus_conversaciones.py).

    python manage.py evaluar_bot                 # reglas, LLM y su combinación; no toca la base
    python manage.py evaluar_bot --orquestador   # además el bot completo con los clientes
                                                 # demo, y deshace todo al final

Columnas: `reglas` (solo reglas), `llm` (Qwen con sus ejemplos), `combinado`
(la decisión que toma el bot, `combinar_clasificaciones`) y, con
`--orquestador`, `final` (lo que el bot hizo de verdad en la conversación).

Las VARIANTES del corpus nunca se le muestran a Qwen: su resultado se informa
aparte y es la medida honesta de si generaliza.

`--orquestador` corre dentro de una transacción que se revierte: no queda
ninguna conversación, consulta ni mensaje, y nada se envía por WhatsApp (los
envíos se disparan al confirmar la transacción, que nunca se confirma).
"""
from __future__ import annotations

import json
import time
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from datos.models import Mensaje
from negocio.bot.clasificador import clasificar, combinar_clasificaciones
from negocio.bot.corpus_conversaciones import CORPUS, VARIANTES, turnos
from negocio.bot.llm import clasificar_con_llm, cliente_llm


class _Deshacer(Exception):
    pass


class Command(BaseCommand):
    help = "Evalúa reglas, LLM, su combinación y (opcional) el orquestador contra el corpus."

    def add_arguments(self, parser):
        parser.add_argument("--orquestador", action="store_true")
        parser.add_argument("--json", dest="salida_json", default=None,
                            help="Ruta donde guardar el detalle en JSON.")

    def handle(self, *args, **opciones):
        llm = cliente_llm()
        filas = []
        for conversacion in CORPUS:
            historial: list[str] = []
            for texto, esperado in turnos(conversacion):
                filas.append(self._fila(llm, texto, esperado, historial, conversacion.estilo, "corpus"))
                historial.append(texto)
        for variante in VARIANTES:
            filas.append(self._fila(llm, variante.texto, variante.tipo, [], "variante", "control"))

        if opciones["orquestador"]:
            self._orquestador([f for f in filas if f["grupo"] == "corpus"])

        self._informe(filas, opciones["orquestador"])
        if opciones["salida_json"]:
            with open(opciones["salida_json"], "w", encoding="utf-8") as archivo:
                json.dump(filas, archivo, ensure_ascii=False, indent=1)

    @staticmethod
    def _fila(llm, texto, esperado, historial, estilo, grupo):
        inicio = time.monotonic()
        del_llm = clasificar_con_llm(llm, texto, historial)
        segundos = round(time.monotonic() - inicio, 2)
        reglas = clasificar(texto)
        return {
            "grupo": grupo, "estilo": estilo, "texto": texto, "esperado": esperado,
            "reglas": reglas, "llm": del_llm, "llm_seg": segundos,
            "combinado": combinar_clasificaciones(texto, reglas, del_llm),
        }

    def _orquestador(self, filas):
        from negocio.bot.orquestador import procesar_mensaje
        from negocio.whatsapp import registrar_entrante

        try:
            with transaction.atomic():
                indice = 0
                for conversacion in CORPUS:
                    for texto, _ in turnos(conversacion):
                        ultimo = None
                        for parte in texto.split("\n"):
                            ultimo = registrar_entrante(
                                wa_message_id=f"eval-{uuid.uuid4()}",
                                numero_raw=conversacion.whatsapp, texto=parte,
                            )
                        resultado = procesar_mensaje(ultimo.id)
                        fila = filas[indice]
                        if resultado.ignorado:
                            fila["final"] = None
                            fila["respuesta"] = "(no intervino: chat derivado a una persona)"
                        else:
                            fila["final"] = resultado.tipo_consulta
                            respuesta = Mensaje.objects.filter(pk=resultado.mensaje_respuesta_id).first()
                            fila["respuesta"] = respuesta.texto if respuesta else ""
                        indice += 1
                raise _Deshacer
        except _Deshacer:
            pass

    def _informe(self, filas, con_final):
        for grupo, titulo in (("corpus", "CORPUS (con ejemplos para Qwen)"),
                              ("control", "VARIANTES DE CONTROL (Qwen nunca las vio)")):
            columnas = ["reglas", "llm", "combinado"] + (["final"] if con_final and grupo == "corpus" else [])
            del_grupo = [f for f in filas if f["grupo"] == grupo]
            self.stdout.write(f"\n=== {titulo} ===")
            for fila in del_grupo:
                marcas = " ".join(
                    f"{c}={'OK' if fila.get(c) == fila['esperado'] else fila.get(c)}" for c in columnas
                )
                self.stdout.write(f"[{fila['esperado']:>18}] {marcas} | {fila['texto'][:70]!r}")
                if fila.get("respuesta"):
                    self.stdout.write(f"{'':21}  bot: {fila['respuesta'][:170]!r}")
            for c in columnas:
                evaluables = [f for f in del_grupo if not (c == "final" and f.get("final") is None)]
                aciertos = sum(1 for f in evaluables if f.get(c) == f["esperado"])
                self.stdout.write(f"{c:>10}: {aciertos}/{len(evaluables)} aciertos")
        tiempos = [f["llm_seg"] for f in filas]
        self.stdout.write(f"\nLLM: {sum(tiempos) / len(tiempos):.2f} s promedio por mensaje")
