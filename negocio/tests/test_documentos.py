from django.test import SimpleTestCase

from negocio.documentos import _partir_contenido, puntuar_fragmento


class RecuperacionLexicaTests(SimpleTestCase):
    def test_compara_palabras_normalizadas_sin_depender_de_un_modelo_semantico(self):
        coincidencias, terminos = puntuar_fragmento(
            "¿Qué cubre el vehículo?",
            "La cobertura cubre el vehiculo e incluye daños.",
        )

        self.assertEqual((coincidencias, terminos), (2, 2))

    def test_el_fragmentado_conserva_texto_y_limita_la_longitud(self):
        contenido = f"{'a' * 1500} una segunda parte"

        fragmentos = _partir_contenido(contenido)

        self.assertEqual("".join(fragmentos), contenido)
        self.assertTrue(all(len(fragmento) <= 1200 for fragmento in fragmentos))

    def test_el_fragmentado_no_crea_pasajes_vacios_por_espacios_repetidos(self):
        contenido = f"{'a' * 1200}{' ' * 1300}{'b' * 1200}"

        fragmentos = _partir_contenido(contenido)

        self.assertEqual(fragmentos, ["a" * 1200, "b" * 1200])
        self.assertTrue(all(fragmento.strip() for fragmento in fragmentos))
