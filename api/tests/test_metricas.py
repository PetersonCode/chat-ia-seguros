from datetime import date, datetime, timedelta

from django.utils import timezone

from api.metricas import rango_del_periodo
from api.tests.base import ApiTestCase
from datos import fabricas, selectors
from datos.models import EstadoConsulta


class MetricasPanelTests(ApiTestCase):
    DESDE = date(2026, 5, 10)
    HASTA = date(2026, 5, 11)

    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.zona = timezone.get_current_timezone()

    def _fecha(self, dia, hora=12, minuto=0):
        return timezone.make_aware(datetime(2026, 5, dia, hora, minuto), self.zona)

    def _consulta(self, tipo, dia, hora=12):
        return fabricas.crear_consulta(
            self.conversacion,
            tipo=tipo,
            estado=EstadoConsulta.CERRADO,
            fecha_hora=self._fecha(dia, hora),
        )

    def _cargar_muestra(self):
        saldo = self._consulta("saldo", 10)
        vencimiento = self._consulta("vencimiento", 10, 13)
        siniestro = self._consulta("siniestro_urgente", 11)
        self._consulta("saludo", 11, 13)
        # Fuera del período (cae en el período anterior: 8 y 9 de mayo).
        self._consulta("saldo", 9, 23)
        fabricas.crear_derivacion(siniestro, self.aprobadora, motivo="Siniestro grave")
        fabricas.crear_derivacion(saldo, self.aprobadora, motivo="Solicitud de descuento")
        fabricas.crear_derivacion(vencimiento, self.aprobadora, motivo="Solicitud de descuento")
        return saldo

    def test_totales_efectividad_y_derivadas(self):
        self._cargar_muestra()
        datos = selectors.metricas_panel(self.DESDE, self.HASTA)
        self.assertEqual(datos["consultas"]["total"], 4)
        self.assertEqual(datos["derivadas"], 3)
        self.assertEqual(datos["efectividad_pct"], 25.0)

    def test_variacion_contra_periodo_anterior(self):
        self._cargar_muestra()
        datos = selectors.metricas_panel(self.DESDE, self.HASTA)
        # Período anterior = 8 y 9 de mayo: una sola consulta (la del día 9).
        self.assertEqual(datos["consultas"]["variacion_pct"], 300.0)

    def test_sin_periodo_anterior_no_hay_variacion(self):
        self._consulta("saldo", 10)
        datos = selectors.metricas_panel(self.DESDE, self.HASTA)
        self.assertIsNone(datos["consultas"]["variacion_pct"])

    def test_ramos_suman_el_total_y_no_incluyen_hogar(self):
        self._cargar_muestra()
        datos = selectors.metricas_panel(self.DESDE, self.HASTA)
        ramos = {r["codigo"]: r for r in datos["ramos"]}
        self.assertEqual(set(ramos), {"automotor", "accidentes", "otros"})
        self.assertEqual(ramos["automotor"]["cantidad"], 2)
        self.assertEqual(ramos["accidentes"]["cantidad"], 1)
        self.assertEqual(ramos["otros"]["cantidad"], 1)
        self.assertEqual(sum(r["porcentaje"] for r in datos["ramos"]), 100.0)
        nombres = [r["nombre"] for r in datos["ramos"]]
        self.assertNotIn("Seguros de Vida y Accidentes", nombres)
        self.assertIn("Siniestros automotores", nombres)

    def test_motivos_de_derivacion_ordenados_por_frecuencia(self):
        self._cargar_muestra()
        motivos = selectors.metricas_panel(self.DESDE, self.HASTA)["motivos_derivacion"]
        self.assertEqual(motivos[0]["motivo"], "Solicitud de descuento")
        self.assertEqual(motivos[0]["cantidad"], 2)
        self.assertEqual(motivos[0]["porcentaje"], 66.7)
        self.assertEqual(motivos[1]["motivo"], "Siniestro grave")

    def test_tiempo_de_respuesta_promedio_en_minutos(self):
        entrante = fabricas.crear_mensaje(self.conversacion, fecha_hora=self._fecha(10, 12, 0))
        fabricas.crear_mensaje(
            self.conversacion,
            direccion="saliente",
            emisor="bot",
            estado_envio="enviado",
            fecha_hora=self._fecha(10, 12, 3),
            respuesta_a=entrante,
        )
        datos = selectors.metricas_panel(self.DESDE, self.HASTA)
        self.assertEqual(datos["tiempo_respuesta_min"], 3.0)

    def test_sin_datos_devuelve_vacios_sin_dividir_por_cero(self):
        datos = selectors.metricas_panel(self.DESDE, self.HASTA)
        self.assertEqual(datos["consultas"]["total"], 0)
        self.assertIsNone(datos["efectividad_pct"])
        self.assertIsNone(datos["tiempo_respuesta_min"])
        self.assertEqual(datos["motivos_derivacion"], [])

    def test_rangos_de_los_filtros(self):
        hoy = date(2026, 11, 4)
        self.assertEqual(rango_del_periodo("hoy", hoy), (hoy, hoy))
        self.assertEqual(rango_del_periodo("7dias", hoy), (hoy - timedelta(days=6), hoy))
        self.assertEqual(rango_del_periodo("mes", hoy), (date(2026, 11, 1), hoy))


class MetricasApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()

    def test_requiere_sesion(self):
        respuesta = self.cliente_api.get("/api/metricas/")
        self.assertIn(respuesta.status_code, (401, 403))

    def test_devuelve_json_con_el_periodo_pedido(self):
        self.entrar()
        fabricas.crear_consulta(self.conversacion, tipo="saldo")
        respuesta = self.cliente_api.get("/api/metricas/?periodo=hoy")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["periodo"]["nombre"], "hoy")
        self.assertEqual(cuerpo["consultas"]["total"], 1)
        self.assertEqual([r["codigo"] for r in cuerpo["ramos"]], ["automotor", "accidentes", "otros"])

    def test_periodo_invalido_se_rechaza(self):
        self.entrar()
        respuesta = self.cliente_api.get("/api/metricas/?periodo=siempre")
        self.assertEqual(respuesta.status_code, 400)

    def test_exporta_csv(self):
        self.entrar()
        fabricas.crear_consulta(self.conversacion, tipo="saldo")
        respuesta = self.cliente_api.get("/api/metricas/?periodo=hoy&formato=csv")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("text/csv", respuesta["Content-Type"])
        self.assertIn("Siniestros automotores", respuesta.content.decode("utf-8"))