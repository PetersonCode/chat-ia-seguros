"""El golden set completo (AC-T3-33 y AC-T3-44).

Un solo archivo de datos (`golden_set.json`) sirve para dos cosas: comprobar
que el clasificador por reglas acierta el tipo, y que los guardrails sacan
**exactamente** los tipos de alerta esperados, ni más ni menos.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.test import TestCase

from negocio.bot.clasificador import clasificar
from negocio.bot.guardrails import evaluar_entrada, evaluar_salida
from negocio.tests.datos_prueba import crear_escenario

GOLDEN_SET = json.loads(
    (Path(__file__).resolve().parent / "golden_set.json").read_text(encoding="utf-8")
)


class GoldenSetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.escenario = crear_escenario()

    def _cliente_id(self, etiqueta: str | None) -> int | None:
        if etiqueta is None:
            return None
        return self.escenario.contacto(etiqueta).cliente_id

    # AC-T3-33
    def test_el_clasificador_por_reglas_acierta_los_tipos_del_golden_set(self):
        casos = [c for c in GOLDEN_SET if c["tipo_esperado"] is not None]
        self.assertGreaterEqual(len(casos), 10)
        for caso in casos:
            with self.subTest(caso=caso["caso"]):
                self.assertEqual(clasificar(caso["mensaje"]), caso["tipo_esperado"])

    # AC-T3-33
    def test_lo_que_no_coincide_con_ninguna_regla_queda_en_otro(self):
        self.assertEqual(clasificar("asdfgh qwerty zxcvb"), "otro")
        self.assertEqual(clasificar(""), "otro")

    # AC-T3-44
    def test_el_golden_set_da_exactamente_las_alertas_esperadas(self):
        for caso in GOLDEN_SET:
            with self.subTest(caso=caso["caso"]):
                entrada = sorted({a.tipo for a in evaluar_entrada(caso["mensaje"])})
                self.assertEqual(
                    entrada,
                    sorted(set(caso["alertas_entrada"])),
                    f"{caso['caso']}: alertas de entrada distintas",
                )
                salida = sorted(
                    {
                        a.tipo
                        for a in evaluar_salida(
                            caso["salida"],
                            cliente_id=self._cliente_id(caso["contacto"]),
                            datos_verificados=frozenset(caso["datos_verificados"]),
                        )
                    }
                )
                self.assertEqual(
                    salida,
                    sorted(set(caso["alertas_salida"])),
                    f"{caso['caso']}: alertas de salida distintas",
                )

    # AC-T3-44
    def test_el_golden_set_incluye_casos_buenos_que_no_alertan(self):
        buenos = [
            caso
            for caso in GOLDEN_SET
            if not caso["alertas_entrada"] and not caso["alertas_salida"]
        ]
        self.assertGreaterEqual(len(buenos), 4)
