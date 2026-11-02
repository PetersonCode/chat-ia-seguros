from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings

from datos import fabricas
from datos.models import Cliente, DocumentoGeneral, Poliza, ConsultaBot


class DemoMvp2Tests(TestCase):
    @override_settings(DEBUG=True)
    def test_repetir_demo_no_duplica_datos_ni_cambia_contrasenas(self):
        from django.contrib.auth import get_user_model
        fabricas.crear_catalogos()
        funcionario = fabricas.crear_funcionario()
        usuario = get_user_model().objects.get(username=funcionario.email)
        clave = usuario.password
        with patch.dict("os.environ", {"WHATSAPP_MODO": "simulado", "LLM_PROVIDER": "none"}):
            call_command("cargar_demo_mvp2", stdout=StringIO())
            cantidades = (Cliente.objects.count(), Poliza.objects.count(), DocumentoGeneral.objects.count(), ConsultaBot.objects.count())
            call_command("cargar_demo_mvp2", stdout=StringIO())
        self.assertEqual(cantidades, (1, 2, 1, 2))
        self.assertEqual(cantidades, (Cliente.objects.count(), Poliza.objects.count(), DocumentoGeneral.objects.count(), ConsultaBot.objects.count()))
        usuario.refresh_from_db()
        self.assertEqual(usuario.password, clave)

    @override_settings(DEBUG=False)
    def test_demo_se_rechaza_fuera_de_desarrollo(self):
        with self.assertRaises(CommandError):
            call_command("cargar_demo_mvp2", stdout=StringIO())
        self.assertFalse(Cliente.objects.exists())
