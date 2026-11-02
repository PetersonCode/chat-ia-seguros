import csv
import io
from datetime import datetime, date
from decimal import Decimal

from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import (
    EstadoConsulta,
    Pago,
    Prioridad,
    TipoConsulta,
)


class ReportesGestionApiTests(ApiTestCase):
    DESDE = date(2026, 5, 10)
    HASTA = date(2026, 5, 11)

    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.zona = timezone.get_current_timezone()

    def _fecha(self, dia, hora=12):
        return timezone.make_aware(datetime(2026, 5, dia, hora), self.zona)

    def _consulta(self, tipo, estado, dia, hora=12):
        return fabricas.crear_consulta(
            self.conversacion,
            tipo=tipo,
            estado=estado,
            fecha_hora=self._fecha(dia, hora),
        )

    def _cargar_muestra(self):
        cerrada = self._consulta("saludo", EstadoConsulta.CERRADO, 10)
        saldo_revision = self._consulta(
            "saldo", EstadoConsulta.PENDIENTE_REVISION, 10, 23
        )
        saldo_derivado = self._consulta("saldo", EstadoConsulta.DERIVADO, 11, 0)
        siniestro_abierto = self._consulta("siniestro", EstadoConsulta.ABIERTO, 11, 23)
        fuera_periodo = self._consulta("reclamo", EstadoConsulta.CERRADO, 9, 23)

        fabricas.crear_derivacion(
            cerrada,
            self.aprobadora,
            prioridad=Prioridad.URGENTE,
            creada_en=self._fecha(10, 23),
        )
        fabricas.crear_derivacion(
            saldo_revision,
            self.aprobadora,
            prioridad=Prioridad.URGENTE,
            creada_en=self._fecha(11, 23),
        )
        fabricas.crear_derivacion(
            fuera_periodo,
            self.aprobadora,
            prioridad=Prioridad.URGENTE,
            creada_en=self._fecha(9, 23),
        )
        fabricas.crear_derivacion(
            siniestro_abierto,
            self.aprobadora,
            prioridad=Prioridad.NORMAL,
            creada_en=self._fecha(11, 23),
        )

        poliza = fabricas.crear_poliza(self.cliente)
        primera_cuota = fabricas.crear_cuota(poliza, importe=Decimal("1000.00"))
        segunda_cuota = fabricas.crear_cuota(poliza, importe=Decimal("234.50"))
        fuera_cuota = fabricas.crear_cuota(poliza, importe=Decimal("500.00"))
        Pago.objects.create(
            referencia="REPORTE-1001",
            cuota=primera_cuota,
            importe=Decimal("1000.00"),
            fecha_pago=self.DESDE,
            responsable=self.aprobadora,
        )
        Pago.objects.create(
            referencia="REPORTE-1002",
            cuota=segunda_cuota,
            importe=Decimal("234.50"),
            fecha_pago=self.HASTA,
            responsable=self.aprobadora,
        )
        Pago.objects.create(
            referencia="REPORTE-1003",
            cuota=fuera_cuota,
            importe=Decimal("500.00"),
            fecha_pago=date(2026, 5, 9),
            responsable=self.aprobadora,
        )

    @property
    def url(self):
        return (
            f"/api/reportes/gestion/?desde={self.DESDE.isoformat()}"
            f"&hasta={self.HASTA.isoformat()}"
        )

    def test_indicadores_coinciden_con_totales_calculables_a_mano(self):
        self._cargar_muestra()
        self.entrar(self.operador)

        respuesta = self.cliente_api.get(self.url)

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        reporte = respuesta.json()
        self.assertEqual(reporte["periodo"], {
            "desde": "2026-05-10",
            "hasta": "2026-05-11",
        })
        self.assertEqual(reporte["consultas"], {
            "total": 4,
            "cerradas": 1,
            "pendientes": 3,
        })
        self.assertEqual(
            {
                fila["codigo"]: fila["cantidad"]
                for fila in reporte["motivos"]
            },
            {"saldo": 2, "saludo": 1, "siniestro": 1},
        )
        self.assertEqual(reporte["derivaciones_urgentes"], 2)
        self.assertEqual(reporte["cobros"], {
            "cantidad": 2,
            "importe_total": "1234.50",
        })
        self.assertIn("fecha_pago", reporte["definiciones"]["cobros"])
        self.assertIn("creada_en", reporte["definiciones"]["derivaciones_urgentes"])

    def test_csv_exporta_el_mismo_periodo_y_filtra_contenido_de_formula(self):
        self._cargar_muestra()
        TipoConsulta.objects.filter(codigo="saldo").update(nombre="=2+2")
        self.entrar()

        respuesta = self.cliente_api.get(f"{self.url}&formato=csv")

        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta["Content-Type"].startswith("text/csv"))
        self.assertIn(
            'attachment; filename="reporte-gestion-2026-05-10-2026-05-11.csv"',
            respuesta["Content-Disposition"],
        )
        self.assertIn("private, no-store", respuesta["Cache-Control"])
        filas = list(csv.reader(io.StringIO(respuesta.content.decode("utf-8"))))
        self.assertEqual(filas[0], ["Desde", "2026-05-10"])
        self.assertEqual(filas[3][2:5], ["Total", "4", ""])
        self.assertTrue(any(len(fila) >= 3 and fila[2] == "'=2+2" for fila in filas))
        self.assertTrue(any(len(fila) >= 5 and fila[2] == "Importe total registrado" and fila[4] == "1234.50" for fila in filas))

    def test_requiere_sesion_y_rechaza_periodo_invalido_o_incompleto(self):
        self.assertEqual(self.cliente_api.get(self.url).status_code, 401)
        self.entrar()
        self.assertEqual(
            self.cliente_api.get(
                "/api/reportes/gestion/?desde=2026-05-12&hasta=2026-05-10"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.cliente_api.get("/api/reportes/gestion/?desde=2026-05-10").status_code,
            400,
        )
