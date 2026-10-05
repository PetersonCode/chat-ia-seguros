from datetime import time
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from datos import fabricas
from datos.models import (
    ContactoWhatsapp,
    ConsultaBot,
    Conversacion,
    EstadoConsulta,
    EstadoEnvio,
    Mensaje,
    TipoConsulta,
)

FIXTURE = (
    Path(__file__).parent / "fixtures" / "consultas_muestra.csv"
).resolve()


class ImportarConsultasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fabricas.crear_catalogos()
        cls.roberto = fabricas.crear_funcionario(
            nombre="Roberto",
            email="roberto@tests.local",
        )

    # AC-T4-25
    def test_importa_filas_con_y_sin_numero_y_guarda_origen(self):
        salida = StringIO()
        errores = StringIO()
        call_command(
            "importar_consultas_csv",
            str(FIXTURE),
            stdout=salida,
            stderr=errores,
        )

        consultas = {
            consulta.codigo_caso: consulta
            for consulta in ConsultaBot.objects.order_by("codigo_caso")
        }
        self.assertEqual(set(consultas), {"CASO-901", "CASO-902", "CASO-904", "CASO-905"})
        sin_numero = consultas["CASO-904"]
        self.assertIsNone(sin_numero.contacto_id)
        self.assertIsNone(sin_numero.conversacion_id)
        self.assertEqual(Mensaje.objects.filter(consulta=sin_numero).count(), 0)
        sin_cliente = consultas["CASO-905"]
        self.assertIsNotNone(sin_cliente.contacto_id)
        self.assertIsNone(sin_cliente.contacto.cliente_id)
        self.assertEqual(
            consultas["CASO-901"].conversacion_id,
            consultas["CASO-902"].conversacion_id,
        )
        self.assertEqual(Mensaje.objects.count(), 6)
        self.assertEqual(ContactoWhatsapp.objects.count(), 2)
        self.assertEqual(Conversacion.objects.count(), 2)

        con_whatsapp = consultas["CASO-901"]
        self.assertEqual(con_whatsapp.contacto.numero, "+5491155551001")
        self.assertEqual(
            con_whatsapp.datos_origen["fecha_hora"],
            "03-04-2024",
        )
        self.assertEqual(
            set(
                Mensaje.objects.filter(consulta=con_whatsapp).values_list(
                    "direccion", "emisor", "estado_envio"
                )
            ),
            {
                ("entrante", "cliente", EstadoEnvio.RECIBIDO),
                ("saliente", "bot", EstadoEnvio.ENVIADO),
            },
        )
        self.assertIn("creadas: 4", salida.getvalue())
        self.assertIn("con error: 1", salida.getvalue())
        self.assertIn("CASO-903", errores.getvalue())

    # AC-T4-26
    def test_aplica_reglas_de_estado_tipo_funcionario_y_fechas(self):
        salida = StringIO()
        call_command(
            "importar_consultas_csv",
            str(FIXTURE),
            stdout=salida,
            stderr=StringIO(),
        )
        alerta = ConsultaBot.objects.get(codigo_caso="CASO-901")
        resolucion_anterior = ConsultaBot.objects.get(codigo_caso="CASO-902")
        hora_local = alerta.fecha_hora.astimezone(
            ZoneInfo("America/Argentina/Buenos_Aires")
        ).time().replace(tzinfo=None)

        self.assertEqual(alerta.estado, EstadoConsulta.PENDIENTE_REVISION)
        self.assertEqual(alerta.tipo_consulta.codigo, "prompt_injection")
        self.assertEqual(alerta.fecha_hora.date().isoformat(), "2024-04-03")
        self.assertEqual(hora_local, time(0, 0))
        self.assertIn("00:00", alerta.notas_importacion)
        self.assertEqual(resolucion_anterior.funcionario_asignado, self.roberto)
        self.assertIsNone(resolucion_anterior.fecha_resolucion)
        self.assertIn("anterior", resolucion_anterior.notas_importacion)
        self.assertEqual(TipoConsulta.objects.count(), 12)

    # AC-T4-27
    def test_omite_duplicados_importa_el_resto_y_continua_tras_error(self):
        salida_inicial = StringIO()
        call_command(
            "importar_consultas_csv",
            str(FIXTURE),
            stdout=salida_inicial,
            stderr=StringIO(),
        )
        conteo_inicial = (
            ConsultaBot.objects.count(),
            ContactoWhatsapp.objects.count(),
            Mensaje.objects.count(),
        )

        salida_repetida = StringIO()
        call_command(
            "importar_consultas_csv",
            str(FIXTURE),
            stdout=salida_repetida,
            stderr=StringIO(),
        )
        self.assertIn("creadas: 0", salida_repetida.getvalue())
        self.assertIn("omitidas: 4", salida_repetida.getvalue())
        self.assertIn("con error: 1", salida_repetida.getvalue())
        self.assertEqual(
            (
                ConsultaBot.objects.count(),
                ContactoWhatsapp.objects.count(),
                Mensaje.objects.count(),
            ),
            conteo_inicial,
        )

    # AC-T4-27
    def test_dry_run_no_escribe(self):
        antes_dry_run = (
            ConsultaBot.objects.count(),
            ContactoWhatsapp.objects.count(),
            Conversacion.objects.count(),
            Mensaje.objects.count(),
        )
        salida_dry_run = StringIO()
        call_command(
            "importar_consultas_csv",
            str(FIXTURE),
            "--dry-run",
            stdout=salida_dry_run,
            stderr=StringIO(),
        )
        self.assertIn("creadas: 4", salida_dry_run.getvalue())
        self.assertEqual(
            (
                ConsultaBot.objects.count(),
                ContactoWhatsapp.objects.count(),
                Conversacion.objects.count(),
                Mensaje.objects.count(),
            ),
            antes_dry_run,
        )

class ImportarCsvValidationTests(SimpleTestCase):
    def test_rechaza_csv_sin_columnas_requeridas(self):
        with TemporaryDirectory() as temporal:
            ruta = Path(temporal) / "columnas_invalidas.csv"
            ruta.write_text(
                "caso_id,fecha_hora\nCASO-999,2024-04-01\n",
                encoding="utf-8",
            )
            with self.assertRaises(CommandError):
                call_command("importar_consultas_csv", str(ruta))


class VerificarConexionTests(SimpleTestCase):
    # AC-T4-28
    def test_conexion_usa_transaccion_solo_lectura_y_solo_selects(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            ("PostgreSQL 17.0 de prueba",),
            *((0,) for _ in range(15)),
        ]
        fake_connection = SimpleNamespace(
            cursor=MagicMock(return_value=cursor),
            ops=SimpleNamespace(quote_name=lambda nombre: f'"{nombre}"'),
        )
        salida = StringIO()

        with (
            patch(
                "datos.management.commands.verificar_conexion.connection",
                fake_connection,
            ),
            patch(
                "datos.management.commands.verificar_conexion.transaction",
                SimpleNamespace(atomic=MagicMock()),
            ),
        ):
            call_command(
                "verificar_conexion",
                stdout=salida,
                stderr=StringIO(),
            )

        sentencias = [llamada.args[0] for llamada in cursor.execute.call_args_list]
        self.assertEqual(sentencias[0], "SET TRANSACTION READ ONLY")
        self.assertEqual(len(sentencias), 17)
        self.assertTrue(
            all(
                sentencia.startswith(("SET TRANSACTION", "SELECT"))
                for sentencia in sentencias
            )
        )
        self.assertIn("PostgreSQL 17.0 de prueba", salida.getvalue())
        self.assertIn("funcionarios: 0", salida.getvalue())
        self.assertIn("acciones_pendientes: 0", salida.getvalue())
