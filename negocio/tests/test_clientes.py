"""ABM manual de clientes (AC-T3-47 a AC-T3-49).

Las validaciones son el único motivo por el que este módulo existe: sin ellas
alcanzaría con un `save()`. Por eso los casos de error pesan más que los felices.
"""

from __future__ import annotations

from django.test import TestCase

from datos import fabricas
from datos.models import Cliente, ContactoWhatsapp, EstadoPoliza
from negocio.clientes import (
    alta_cliente,
    dar_de_baja_cliente,
    modificar_cliente,
    reactivar_cliente,
)
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado


class AltaClienteTests(TestCase):
    def _alta(self, **campos):
        valores = {
            "dni": "28111222",
            "nombre": "Juan",
            "apellido": "García",
            "telefono": "11 2691-4442",
            "email": "juan@tests.local",
        }
        valores.update(campos)
        return alta_cliente(**valores)

    # AC-T3-47
    def test_el_alta_crea_el_cliente_y_su_contacto_de_whatsapp(self):
        cliente = self._alta()

        self.assertEqual(cliente.dni, "28111222")
        self.assertTrue(cliente.activo)
        contacto = ContactoWhatsapp.objects.get(cliente=cliente)
        self.assertEqual(contacto.numero, "+5491126914442")

    # AC-T3-47
    def test_el_dni_se_normaliza_y_no_se_puede_repetir(self):
        self._alta(dni="28.111.222")
        self.assertEqual(Cliente.objects.get(dni="28111222").nombre, "Juan")

        with self.assertRaises(DatosInvalidos):
            self._alta(dni="28111222", telefono="11 3203-2060")

    # AC-T3-47
    def test_un_dni_con_formato_invalido_se_rechaza(self):
        for dni in ("", "123", "abcdefgh", "123456789012"):
            with self.subTest(dni=dni):
                with self.assertRaises(DatosInvalidos):
                    self._alta(dni=dni)

    # AC-T3-47
    def test_el_telefono_se_normaliza_y_no_se_puede_repetir(self):
        self._alta(telefono="+54 9 11 2691-4442")
        self.assertTrue(
            ContactoWhatsapp.objects.filter(numero="+5491126914442").exists()
        )

        with self.assertRaises(DatosInvalidos):
            self._alta(dni="30444555", telefono="011 2691 4442")

    # AC-T3-47
    def test_un_telefono_invalido_se_rechaza(self):
        for telefono in ("", "123", "no tengo"):
            with self.subTest(telefono=telefono):
                with self.assertRaises(DatosInvalidos):
                    self._alta(telefono=telefono)

    # AC-T3-47
    def test_nombre_y_apellido_son_obligatorios_y_sin_numeros(self):
        for campos in (
            {"nombre": ""},
            {"nombre": "   "},
            {"apellido": ""},
            {"nombre": "Juan 2"},
            {"apellido": "28111222"},
        ):
            with self.subTest(**campos):
                with self.assertRaises(DatosInvalidos):
                    self._alta(**campos)

    # AC-T3-47
    def test_el_email_vacio_se_guarda_como_null_y_el_invalido_se_rechaza(self):
        cliente = self._alta(email="")
        self.assertIsNone(cliente.email)

        with self.assertRaises(DatosInvalidos):
            self._alta(dni="30444555", telefono="11 3203-2060", email="no-es-un-email")

    # AC-T3-47
    def test_si_el_telefono_falla_no_queda_el_cliente_a_medias(self):
        """El alta es atómica: o quedan las dos filas, o ninguna."""
        otro = fabricas.crear_cliente(dni="30444555")
        fabricas.crear_contacto(otro, numero="+5491126914442")

        with self.assertRaises(DatosInvalidos):
            self._alta(dni="33999888", telefono="11 2691-4442")

        self.assertFalse(Cliente.objects.filter(dni="33999888").exists())

    # AC-T3-47
    def test_un_contacto_sin_cliente_se_adopta_en_vez_de_rechazarse(self):
        """El prospecto que ya le escribió al bot y después se da de alta."""
        huerfano = fabricas.crear_contacto(None, numero="+5491126914442")

        cliente = self._alta(telefono="11 2691-4442")

        huerfano.refresh_from_db()
        self.assertEqual(huerfano.cliente_id, cliente.id)
        # Se reusa la fila: el número no se duplica y la conversación previa
        # sigue colgando del mismo contacto.
        self.assertEqual(
            ContactoWhatsapp.objects.filter(numero="+5491126914442").count(), 1
        )

    # AC-T3-47
    def test_un_contacto_de_otro_cliente_nunca_se_adopta(self):
        otro = fabricas.crear_cliente(dni="30444555")
        fabricas.crear_contacto(otro, numero="+5491126914442")

        with self.assertRaises(DatosInvalidos):
            self._alta(telefono="11 2691-4442")


class ModificarClienteTests(TestCase):
    def setUp(self):
        self.cliente = alta_cliente(
            dni="28111222",
            nombre="Juan",
            apellido="García",
            telefono="11 2691-4442",
            email="juan@tests.local",
        )

    # AC-T3-48
    def test_solo_se_actualiza_lo_que_viene(self):
        modificar_cliente(self.cliente.id, nombre="Juan Carlos")

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Juan Carlos")
        self.assertEqual(self.cliente.apellido, "García")
        self.assertEqual(self.cliente.email, "juan@tests.local")

    # AC-T3-48
    def test_el_email_vacio_lo_borra_y_ausente_lo_deja(self):
        modificar_cliente(self.cliente.id, nombre="Juan Carlos")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.email, "juan@tests.local")

        modificar_cliente(self.cliente.id, email="")
        self.cliente.refresh_from_db()
        self.assertIsNone(self.cliente.email)

    # AC-T3-48
    def test_el_propio_dni_no_cuenta_como_repetido(self):
        modificar_cliente(self.cliente.id, dni="28.111.222")

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.dni, "28111222")

    # AC-T3-48
    def test_no_se_puede_tomar_el_dni_ni_el_telefono_de_otro(self):
        alta_cliente(
            dni="30444555",
            nombre="María",
            apellido="López",
            telefono="11 3203-2060",
        )

        with self.assertRaises(DatosInvalidos):
            modificar_cliente(self.cliente.id, dni="30444555")
        with self.assertRaises(DatosInvalidos):
            modificar_cliente(self.cliente.id, telefono="11 3203-2060")

    # AC-T3-48
    def test_cambiar_el_telefono_reusa_el_contacto_existente(self):
        modificar_cliente(self.cliente.id, telefono="11 3203-2060")

        contactos = ContactoWhatsapp.objects.filter(cliente=self.cliente)
        self.assertEqual(contactos.count(), 1)
        self.assertEqual(contactos.get().numero, "+5491132032060")

    # AC-T3-48
    def test_al_modificar_tambien_se_adopta_un_contacto_sin_cliente(self):
        huerfano = fabricas.crear_contacto(None, numero="+5491132032060")

        modificar_cliente(self.cliente.id, telefono="11 3203-2060")

        huerfano.refresh_from_db()
        self.assertEqual(huerfano.cliente_id, self.cliente.id)
        self.assertEqual(
            ContactoWhatsapp.objects.filter(numero="+5491132032060").count(), 1
        )

    # AC-T3-48
    def test_un_cliente_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            modificar_cliente(999999, nombre="Nadie")


class BajaClienteTests(TestCase):
    def setUp(self):
        self.cliente = alta_cliente(
            dni="28111222",
            nombre="Juan",
            apellido="García",
            telefono="11 2691-4442",
        )

    # AC-T3-49
    def test_la_baja_es_logica_y_conserva_la_fila_y_el_contacto(self):
        dar_de_baja_cliente(self.cliente.id)

        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.activo)
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.id).exists())
        self.assertTrue(
            ContactoWhatsapp.objects.filter(cliente=self.cliente).exists()
        )

    # AC-T3-49
    def test_no_se_da_de_baja_a_un_cliente_con_polizas_vigentes(self):
        fabricas.crear_poliza(self.cliente, estado=EstadoPoliza.VIGENTE)

        with self.assertRaises(EstadoInvalido):
            dar_de_baja_cliente(self.cliente.id)

        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.activo)

    # AC-T3-49
    def test_con_las_polizas_dadas_de_baja_si_se_puede(self):
        fabricas.crear_poliza(self.cliente, estado=EstadoPoliza.DADA_DE_BAJA)

        dar_de_baja_cliente(self.cliente.id)

        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.activo)

    # AC-T3-49
    def test_dar_de_baja_dos_veces_es_estado_invalido(self):
        dar_de_baja_cliente(self.cliente.id)
        with self.assertRaises(EstadoInvalido):
            dar_de_baja_cliente(self.cliente.id)

    # AC-T3-49
    def test_reactivar_devuelve_al_cliente_y_no_se_repite(self):
        dar_de_baja_cliente(self.cliente.id)
        reactivar_cliente(self.cliente.id)

        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.activo)
        with self.assertRaises(EstadoInvalido):
            reactivar_cliente(self.cliente.id)
