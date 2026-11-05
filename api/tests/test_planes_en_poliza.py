"""Cobertura de una póliza con una sola fuente: el plan de la compañía.

Antes el alta en la ficha pedía básica/intermedia/total y el plan se cargaba
aparte en la página Pólizas, así que los dos podían contradecirse. Ahora el
plan define el nivel y copia sus condiciones desde el alta.
"""
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import CondicionesPoliza, Poliza
from negocio.cartera import completar_cartera
from negocio.errores import DatosInvalidos


@override_settings(BUSQUEDA_SEMANTICA=False)
class PlanEnLaPolizaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.compania = fabricas.crear_compania()
        self.entrar()

    def plan(self, compania=None, **campos):
        datos = {
            "compania_id": (compania or self.compania).id,
            "nombre": "Terceros completo",
            "nivel": "intermedia",
            "cubre": "Responsabilidad civil y cristales.",
            "no_cubre": "Granizo.",
            "limites": "Hasta $100.000.000.",
            "asistencia": "0800-123-4567",
        }
        datos.update(campos)
        respuesta = self.cliente_api.post("/api/planes-cobertura/", datos, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return respuesta.json()

    def alta(self, **campos):
        hoy = timezone.localdate()
        datos = {
            "tipo_seguro": "automotor",
            "cobertura": "basica",
            "fecha_inicio": hoy.isoformat(),
            "fecha_vencimiento": (hoy + timedelta(days=365)).isoformat(),
            "prima_mensual": "10000",
            "compania_id": self.compania.id,
        }
        datos.update(campos)
        return self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/polizas/", datos, format="json"
        )

    def test_el_plan_define_el_nivel_y_copia_sus_condiciones_en_el_alta(self):
        plan = self.plan(nivel="intermedia")

        respuesta = self.alta(cobertura="basica", plan_id=plan["id"])

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["cobertura"], "intermedia")  # gana el plan, no lo tipeado
        self.assertEqual(cuerpo["plan"]["nombre"], "Terceros completo")
        self.assertTrue(cuerpo["condiciones_cargadas"])
        condiciones = CondicionesPoliza.objects.get(poliza_id=cuerpo["id"])
        self.assertEqual(condiciones.plan_id, plan["id"])
        self.assertEqual(condiciones.cubre, plan["cubre"])
        self.assertEqual(condiciones.documento.estado, "aprobado")  # lo puede citar el bot

    def test_un_plan_de_otra_compania_no_crea_la_poliza(self):
        ajeno = self.plan(compania=fabricas.crear_compania())
        antes = Poliza.objects.count()

        respuesta = self.alta(plan_id=ajeno["id"])

        self.assertEqual(respuesta.status_code, 400, respuesta.content)
        self.assertEqual(Poliza.objects.count(), antes)

    def test_sin_plan_el_alta_sigue_funcionando(self):
        respuesta = self.alta(cobertura="total")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        self.assertEqual(respuesta.json()["cobertura"], "total")
        self.assertIsNone(respuesta.json()["plan"])
        self.assertFalse(respuesta.json()["condiciones_cargadas"])

    def test_un_plan_nuevo_exige_nivel(self):
        datos = {"compania_id": self.compania.id, "nombre": "Sin nivel", "cubre": "Algo."}

        respuesta = self.cliente_api.post("/api/planes-cobertura/", datos, format="json")

        self.assertEqual(respuesta.status_code, 400, respuesta.content)

    def test_aplicar_un_plan_en_polizas_sincroniza_el_nivel(self):
        poliza = fabricas.crear_poliza(self.cliente, compania=self.compania, cobertura="basica")
        plan = self.plan(nivel="total")

        respuesta = self.cliente_api.patch(
            f"/api/polizas/{poliza.id}/condiciones/",
            {"plan_id": plan["id"], "plan_version": plan["version"]},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        poliza.refresh_from_db()
        self.assertEqual(poliza.cobertura, "total")

    def test_no_se_cambia_de_compania_dejando_un_plan_ajeno(self):
        plan = self.plan()
        poliza_id = self.alta(plan_id=plan["id"]).json()["id"]
        otra = fabricas.crear_compania()

        with self.assertRaises(DatosInvalidos):
            completar_cartera(poliza_id, funcionario_id=self.aprobadora.id, compania_id=otra.id)

        self.assertEqual(Poliza.objects.get(pk=poliza_id).compania_id, self.compania.id)
