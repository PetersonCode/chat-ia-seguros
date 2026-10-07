#!/usr/bin/env python3
"""Verifica que cada criterio de aceptación (AC-Tn-xx) tenga con qué comprobarse.

Uso (desde la raíz del repositorio):
    python SDD/verificar.py          resumen de las 4 tareas
    python SDD/verificar.py T3       detalle de una tarea; termina con error si le falta algo

Un AC queda cubierto si lo cita (en un comentario) un test de Python dentro de una carpeta `tests/`,
un test de JavaScript `*.test.js`, o una línea TILDADA `- [x]` de `SDD/qa/*.md`.
Solo usa la biblioteca estándar.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SDD = Path(__file__).resolve().parent
RAIZ = SDD.parent
RE_AC = re.compile(r"\bAC-T[1-4]-\d{2}\b")
RE_DEFINICION = re.compile(r"^\|\s*(AC-T[1-4]-\d{2})\s*\|\s*(\*\*\(QA\)\*\*)?", re.M)
RE_TILDADO = re.compile(r"^\s*[-*]\s*\[[xX]\]")
IGNORAR = {".git", ".venv", "venv", "node_modules", "__pycache__", "SDD"}


def definidos() -> dict[str, dict[str, bool]]:
    """{tarea: {AC: es_qa}}"""
    salida: dict[str, dict[str, bool]] = {}
    for spec in sorted(SDD.glob("T[1-4]-*.md")):
        tarea = spec.name[:2]
        for ac, qa in RE_DEFINICION.findall(spec.read_text(encoding="utf-8")):
            salida.setdefault(tarea, {})[ac] = bool(qa)
    return salida


def evidencias() -> tuple[dict[str, list[str]], set[str]]:
    """({AC: [dónde está cubierto]}, {AC citados en cualquier lado})"""
    cubiertos: dict[str, list[str]] = {}
    citados: set[str] = set()

    def anotar(ac: str, donde: str, cubre: bool = True) -> None:
        citados.add(ac)
        if cubre:
            cubiertos.setdefault(ac, []).append(donde)

    for ruta in RAIZ.rglob("*"):
        if not ruta.is_file() or set(ruta.relative_to(RAIZ).parts) & IGNORAR:
            continue
        es_test_py = ruta.suffix == ".py" and "tests" in ruta.parts
        es_test_js = ruta.name.endswith(".test.js")
        if es_test_py or es_test_js:
            for ac in set(RE_AC.findall(ruta.read_text(encoding="utf-8", errors="ignore"))):
                anotar(ac, str(ruta.relative_to(RAIZ)))
    for ruta in sorted((SDD / "qa").glob("*.md")):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            for ac in RE_AC.findall(linea):
                anotar(ac, f"SDD/qa/{ruta.name} (QA)", cubre=bool(RE_TILDADO.match(linea)))
    return cubiertos, citados


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8")
    filtro = sys.argv[1].upper() if len(sys.argv) > 1 else None
    if filtro and not re.fullmatch(r"T[1-4]", filtro):
        print("Uso: python SDD/verificar.py [T1|T2|T3|T4]")
        return 2
    acs, (cubiertos, citados) = definidos(), evidencias()
    todos = {ac for por_tarea in acs.values() for ac in por_tarea}
    falla = False

    for tarea in sorted(acs):
        if filtro and tarea != filtro:
            continue
        lista = acs[tarea]
        faltan = [ac for ac in lista if ac not in cubiertos]
        print(f"{tarea}: {len(lista) - len(faltan)}/{len(lista)} AC cubiertos")
        if filtro:
            for ac in lista:
                marca = "OK " if ac in cubiertos else "FALTA"
                tipo = " (QA manual)" if lista[ac] else ""
                donde = ", ".join(cubiertos.get(ac, [])) or "-"
                print(f"  [{marca}] {ac}{tipo}: {donde}")
            falla = falla or bool(faltan)

    for ac in sorted(citados - todos):
        print(f"ERROR: se cita {ac}, que no existe en ninguna spec")
        falla = True
    return 1 if falla else 0


if __name__ == "__main__":
    sys.exit(main())
