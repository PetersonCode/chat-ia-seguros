from datetime import date, time
from unittest import TestCase

from datos.limpieza import (
    normalizar_dni,
    normalizar_telefono,
    normalizar_tipo_seguro,
    parsear_fecha_hora,
)


class LimpiezaTests(TestCase):
    # AC-T4-21
    def test_normalizar_dni_acepta_formatos_y_rechaza_valores_invalidos(self):
        casos = (
            ("28.111.222", "28111222"),
            (" 28111222 ", "28111222"),
            ("28-111-222", "28111222"),
        )
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_dni(entrada), esperado)

        for entrada in ("123456", "123456789", "28.111.A22", ""):
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValueError):
                    normalizar_dni(entrada)

    # AC-T4-22
    def test_normalizar_telefono_aplica_formato_canonico(self):
        casos = (
            ("+54 11 5555-1001", "+5491155551001"),
            ("+54 11 55551001", "+5491155551001"),
            ("1155552002", "+5491155552002"),
            ("011 5555-1004", "+5491155551004"),
            ("+54911 5555 1005", "+5491155551005"),
            ("5491155551003", "+5491155551003"),
            ("541155551003", "+5491155551003"),
        )
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_telefono(entrada), esperado)

        for entrada in ("", "   ", "+54 11 ABCD-1001", "123456789"):
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValueError):
                    normalizar_telefono(entrada)

    # AC-T4-23
    def test_parsear_fecha_hora_reconoce_formatos_explicitos(self):
        casos = (
            ("2024-04-01 09:15", date(2024, 4, 1), time(9, 15)),
            ("01/04/2024 10:30", date(2024, 4, 1), time(10, 30)),
            ("April 1 2024 11:00", date(2024, 4, 1), time(11, 0)),
            ("02-04-24 08:00", date(2024, 4, 2), time(8, 0)),
            ("2024/04/02 14:20", date(2024, 4, 2), time(14, 20)),
            ("3/4/24 09:00", date(2024, 4, 3), time(9, 0)),
            ("04.04.2024 10:00", date(2024, 4, 4), time(10, 0)),
        )
        for entrada, fecha, hora in casos:
            with self.subTest(entrada=entrada):
                resultado = parsear_fecha_hora(entrada)
                self.assertEqual(resultado.fecha, fecha)
                self.assertEqual(resultado.hora, hora)

    # AC-T4-23
    def test_parsear_fecha_sin_hora_y_rechaza_valores_invalidos(self):
        for entrada, esperado in (
            ("03-04-2024", date(2024, 4, 3)),
            ("2024-04-04", date(2024, 4, 4)),
            ("05/04/2024", date(2024, 4, 5)),
        ):
            with self.subTest(entrada=entrada):
                resultado = parsear_fecha_hora(entrada)
                self.assertEqual(resultado.fecha, esperado)
                self.assertIsNone(resultado.hora)

        for entrada in ("30/02/2024", "texto"):
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValueError):
                    parsear_fecha_hora(entrada)

    # AC-T4-24
    def test_normalizar_tipo_seguro_resuelve_aliases(self):
        casos = (
            ("Automotor", "automotor"),
            ("auto", "automotor"),
            ("AUTO", "automotor"),
            (" Auto ", "automotor"),
            ("casa", "hogar"),
            ("vivienda", "hogar"),
            ("negocio", "comercio"),
            ("local", "comercio"),
            ("motocicleta", "moto"),
            ("vida", "vida"),
        )
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_tipo_seguro(entrada), esperado)

        with self.assertRaises(ValueError):
            normalizar_tipo_seguro("desconocido")
