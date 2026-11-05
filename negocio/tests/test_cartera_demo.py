"""La cartera demo carga datos coherentes y el bot puede responder con ellos."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from datos import fabricas
from datos.models import (
    Cliente, Compania, CondicionesPoliza, ContactoWhatsapp, PlanCobertura, Poliza, Vehiculo,
)
from negocio.coberturas import responder_cobertura


@override_settings(BUSQUEDA_SEMANTICA=False)
class CarteraDemoTests(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        fabricas.crear_funcionario("Admin", puede_aprobar=True, rol="administrador")
        call_command("cargar_cartera_demo", stdout=StringIO())

    def test_cantidades_y_coherencia(self):
        self.assertEqual(Compania.objects.count(), 5)
        self.assertEqual(PlanCobertura.objects.count(), 15)
        for compania in Compania.objects.all():
            self.assertEqual(
                sorted(PlanCobertura.objects.filter(compania=compania).values_list("nivel", flat=True)),
                ["basica", "intermedia", "total"],
            )
        self.assertEqual(Cliente.objects.count(), 20)
        self.assertTrue(20 <= Vehiculo.objects.count() <= 40)
        self.assertEqual(Poliza.objects.count(), Vehiculo.objects.count())  # una póliza por vehículo
        for poliza in Poliza.objects.select_related("compania"):
            condiciones = CondicionesPoliza.objects.select_related("plan").get(poliza=poliza)
            self.assertEqual(condiciones.plan.compania_id, poliza.compania_id)
            self.assertEqual(condiciones.plan.nivel, poliza.cobertura)
            self.assertEqual(condiciones.documento.estado, "aprobado")
        # Ningún número real: todos son +54911000002NN.
        self.assertFalse(ContactoWhatsapp.objects.exclude(numero__startswith="+54911000002").exists())

    def test_el_bot_responde_la_cobertura_segun_el_plan(self):
        basica = Poliza.objects.filter(cobertura="basica").first()
        total = Poliza.objects.filter(cobertura="total").first()
        for poliza, esperado in ((basica, "No cubre granizo"), (total, "granizo sin tope")):
            contacto = ContactoWhatsapp.objects.get(cliente=poliza.cliente)
            conversacion = fabricas.crear_conversacion(contacto)
            texto, fuente = responder_cobertura(
                f"¿Mi póliza {poliza.numero_poliza} cubre el granizo?", conversacion
            )
            self.assertIsNotNone(fuente, texto)
            self.assertIn(esperado, texto)

    def test_no_se_carga_dos_veces(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("cargar_cartera_demo", stdout=StringIO())
