"""Etapa A: errores, sesión y reglas puras (AC-T3-01 a AC-T3-04)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from datos import fabricas
from negocio.errores import (
    DatosInvalidos,
    ErrorNegocio,
    EstadoInvalido,
    NoEncontrado,
    ParametrosIncompletos,
    PermisoDenegado,
)
from negocio.reglas import (
    RANGO_SEVERIDAD,
    color_por_severidad,
    severidad_por_rango,
    sin_respuesta,
    ventana_24h_abierta,
)
from negocio.bot.clasificador import clasificar, pide_un_humano
from negocio.sesion import funcionario_de


class ErroresTests(SimpleTestCase):
    # AC-T3-01
    def test_cada_error_tiene_su_codigo_y_conserva_el_mensaje(self):
        esperados = [
            (ErrorNegocio, "error_negocio"),
            (DatosInvalidos, "datos_invalidos"),
            (ParametrosIncompletos, "parametros_incompletos"),
            (PermisoDenegado, "permiso_denegado"),
            (NoEncontrado, "no_encontrado"),
            (EstadoInvalido, "estado_invalido"),
        ]
        for clase, codigo in esperados:
            with self.subTest(clase=clase.__name__):
                error = clase("Algo salió mal.")
                self.assertEqual(error.codigo, codigo)
                self.assertEqual(error.mensaje, "Algo salió mal.")
                self.assertEqual(str(error), "Algo salió mal.")

    # AC-T3-01
    def test_estado_invalido_acepta_un_codigo_mas_especifico(self):
        error = EstadoInvalido("Pasaron 24 h.", codigo="ventana_24h_cerrada")
        self.assertEqual(error.codigo, "ventana_24h_cerrada")
        self.assertEqual(error.mensaje, "Pasaron 24 h.")
        # La clase sigue teniendo su código genérico.
        self.assertEqual(EstadoInvalido.codigo, "estado_invalido")


class SesionTests(TestCase):
    # AC-T3-02
    def test_funcionario_de_resuelve_por_email_sin_distinguir_mayusculas(self):
        funcionario = fabricas.crear_funcionario("Graciela")
        user = get_user_model().objects.get(email=funcionario.email)
        user.email = funcionario.email.upper()
        user.save(update_fields=["email"])

        self.assertEqual(funcionario_de(user), funcionario)

    # AC-T3-02
    def test_funcionario_de_rechaza_anonimos_sin_email_e_inactivos(self):
        with self.assertRaises(PermisoDenegado):
            funcionario_de(None)

        sin_email = get_user_model()(username="sin-email", email="")
        with self.assertRaises(PermisoDenegado):
            funcionario_de(sin_email)

        ajeno = get_user_model().objects.create_user(
            username="ajeno@tests.local", email="ajeno@tests.local", password="x"
        )
        with self.assertRaises(PermisoDenegado):
            funcionario_de(ajeno)

        inactivo = fabricas.crear_funcionario("Inactivo", activo=False)
        user_inactivo = get_user_model().objects.get(email=inactivo.email)
        with self.assertRaises(PermisoDenegado):
            funcionario_de(user_inactivo)


class ReglasPurasTests(SimpleTestCase):
    # AC-T3-03
    def test_severidad_y_color(self):
        self.assertEqual(RANGO_SEVERIDAD, {"baja": 1, "media": 2, "alta": 3, "critica": 4})
        self.assertIsNone(severidad_por_rango(0))
        for rango, severidad in ((1, "baja"), (2, "media"), (3, "alta"), (4, "critica")):
            with self.subTest(rango=rango):
                self.assertEqual(severidad_por_rango(rango), severidad)

        for severidad, color in (
            ("critica", "rojo"),
            ("alta", "naranja"),
            ("media", "amarillo"),
            ("baja", "amarillo"),
            (None, "verde"),
        ):
            with self.subTest(severidad=severidad):
                self.assertEqual(color_por_severidad(severidad), color)

    # AC-T3-04
    def test_sin_respuesta_solo_si_el_bot_dejo_colgado_al_cliente(self):
        ahora = timezone.now()
        base = {
            "estado": "abierta",
            "modo": "bot",
            "ultimo_emisor": "cliente",
            "ultimo_fecha_hora": ahora - timedelta(minutes=11),
            "ahora": ahora,
        }
        self.assertTrue(sin_respuesta(**base))

        self.assertFalse(sin_respuesta(**{**base, "estado": "cerrada"}))
        self.assertFalse(sin_respuesta(**{**base, "modo": "humano"}))
        self.assertFalse(sin_respuesta(**{**base, "ultimo_emisor": "bot"}))
        self.assertFalse(sin_respuesta(**{**base, "ultimo_fecha_hora": None}))
        self.assertFalse(
            sin_respuesta(**{**base, "ultimo_fecha_hora": ahora - timedelta(minutes=9)})
        )

    # AC-T3-04
    def test_ventana_24h(self):
        ahora = timezone.now()
        self.assertTrue(ventana_24h_abierta(ahora - timedelta(hours=23), ahora))
        self.assertFalse(ventana_24h_abierta(ahora - timedelta(hours=25), ahora))
        self.assertFalse(ventana_24h_abierta(None, ahora))


class ListadoDePolizasTests(TestCase):
    """Preguntar qué pólizas o vehículos tiene es pedir el listado, no una
    consulta de cobertura: lo primero lo contesta el bot, lo segundo deriva."""

    def test_pedir_el_listado_cae_en_vencimiento(self):
        for texto in (
            "Queria saber si tengo polizas o vehiculos registrados",
            "que polizas tengo?",
            "cuales son mis polizas",
            "cuantas polizas tengo",
            "tengo algun vehiculo registrado?",
            "que vehiculos tengo asegurados",
            "que seguros tengo contratados",
            "mis polizas activas",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "vencimiento")

    def test_lo_que_sigue_siendo_de_otro_tipo(self):
        for texto, esperado in (
            ("que cubre mi poliza?", "consulta_cobertura"),
            ("que incluye mi cobertura?", "consulta_cobertura"),
            ("condiciones de la poliza", "consulta_cobertura"),
            ("cuanto cuesta una poliza nueva", "cotizacion"),
            ("quiero cotizar un seguro para mi moto", "cotizacion"),
            ("quiero dar de baja la poliza", "baja"),
            ("cuando vence mi seguro", "vencimiento"),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), esperado)


class JergaYCoberturaTests(TestCase):
    """Dos cruces del clasificador por reglas, sin tocar el orden (AC-T3-33)."""

    def test_la_jerga_rioplatense_cae_en_saludo(self):
        for texto in (
            "que onda todo bien?",
            "como andas",
            "como va",
            "holis",
            "todo bien?",
            "saludos",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "saludo")

    def test_preguntar_si_algo_esta_cubierto_no_es_un_siniestro(self):
        # Nombran un siniestro, pero preguntan por la cobertura: el bot no
        # puede contestarlas y deriva, en vez de mandar cómo denunciar.
        for texto in (
            "me cubre el granizo?",
            "esta cubierto el robo de ruedas?",
            "mi cobertura incluye choque con animales",
            "el granizo entra en mi cobertura?",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "consulta_cobertura")

    def test_contar_un_siniestro_sigue_siendo_siniestro(self):
        for texto in (
            "Mi auto choco ayer, como hago el siniestro?",
            "quiero denunciar un robo",
            "quiero hacer la denuncia por granizo",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "siniestro")

    def test_un_incidente_en_curso_se_clasifica_como_urgente(self):
        for texto in (
            "tuve un choque",
            "me robaron el auto",
            "estoy en el hospital",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "siniestro_urgente")

    def test_preguntar_si_el_seguro_cubre_robo_no_es_un_incidente(self):
        self.assertEqual(clasificar("¿mi seguro cubre robo?"), "consulta_cobertura")

    def test_un_saludo_no_le_roba_el_turno_a_un_pedido_real(self):
        self.assertEqual(clasificar("todo bien, quiero saber mi saldo"), "saldo")
        self.assertEqual(clasificar("hola, cuando vence mi poliza"), "vencimiento")

    def test_pedir_una_persona_se_reconoce_aunque_caiga_en_otro(self):
        for texto in (
            "necesito hablar con un asesor",
            "quiero hablar con alguien",
            "me atienda una persona por favor",
            "pasame con atencion al cliente",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(clasificar(texto), "otro")
                self.assertTrue(pide_un_humano(texto))

    def test_lo_que_no_es_un_pedido_de_persona(self):
        for texto in ("que onda todo bien?", "cuanto debo", "asdkjh qwe"):
            with self.subTest(texto=texto):
                self.assertFalse(pide_un_humano(texto))
