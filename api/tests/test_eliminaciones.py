"""Borrado físico de póliza, plan y compañía por el rol administrador."""
from django.test import override_settings
from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import (
    AccionPendiente, Cliente, Compania, CondicionesPoliza, Cotizacion, Cuota,
    DocumentoGeneral, DocumentoPoliza, PlanCobertura, Poliza, Siniestro, Vehiculo,
)
from negocio.documentos import aprobar_documento, crear_documento
from negocio.coberturas import vincular_documento
from negocio.eliminaciones import eliminar_compania, eliminar_plan, eliminar_poliza
from negocio.errores import EstadoInvalido, PermisoDenegado


@override_settings(BUSQUEDA_SEMANTICA=False)
class EliminacionesTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.admin = fabricas.crear_funcionario("Admin", puede_aprobar=True, rol="administrador")
        self.compania = fabricas.crear_compania()
        self.vehiculo = fabricas.crear_vehiculo(self.cliente)
        self.poliza = fabricas.crear_poliza(self.cliente, compania=self.compania, vehiculo=self.vehiculo)
        fabricas.crear_cuota(self.poliza)
        self.entrar(self.admin)

    def plan(self, compania=None):
        r = self.cliente_api.post("/api/planes-cobertura/", {
            "compania_id": (compania or self.compania).id, "nombre": f"Plan {timezone.now().timestamp()}",
            "nivel": "intermedia", "cubre": "Responsabilidad civil.", "asistencia": "0800-123-4567",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def aplicar(self, plan, poliza=None):
        poliza = poliza or self.poliza
        r = self.cliente_api.patch(f"/api/polizas/{poliza.id}/condiciones/",
                                   {"plan_id": plan["id"], "plan_version": plan["version"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)

    # --- póliza ------------------------------------------------------------

    def test_borrar_poliza_se_lleva_lo_suyo_y_deja_cliente_vehiculo_y_documento_general(self):
        self.aplicar(self.plan())
        generado = CondicionesPoliza.objects.get(poliza=self.poliza).documento_id
        general = crear_documento(titulo="Condiciones generales de la compañía", version="1",
                                  referencia="Ejemplo", contenido="Texto general.", funcionario_id=self.admin.id)
        aprobar_documento(general.id, self.admin.id)
        vincular_documento(self.poliza.numero_poliza, general.id, self.admin.id)
        fabricas.crear_accion(fabricas.crear_consulta(self.conversacion), poliza=self.poliza)

        r = self.cliente_api.post(f"/api/polizas/{self.poliza.id}/eliminar-definitivo/", {}, format="json")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(Poliza.objects.filter(pk=self.poliza.id).exists())
        self.assertFalse(Cuota.objects.filter(poliza_id=self.poliza.id).exists())
        self.assertFalse(CondicionesPoliza.objects.exists())
        self.assertFalse(AccionPendiente.objects.filter(poliza_id=self.poliza.id).exists())
        self.assertFalse(DocumentoGeneral.objects.filter(pk=generado).exists())
        self.assertFalse(DocumentoPoliza.objects.exists())
        self.assertTrue(DocumentoGeneral.objects.filter(pk=general.id).exists())
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.id).exists())
        self.assertTrue(Vehiculo.objects.filter(pk=self.vehiculo.id).exists())

    def test_una_poliza_con_siniestro_no_se_borra(self):
        Siniestro.objects.create(numero_siniestro="SIN-2026-00009", poliza=self.poliza,
                                 fecha_ocurrencia=timezone.localdate(), descripcion="Choque")
        with self.assertRaises(EstadoInvalido):
            eliminar_poliza(self.poliza.id, self.admin.id)
        self.assertTrue(Poliza.objects.filter(pk=self.poliza.id).exists())

    # --- plan ----------------------------------------------------------------

    def test_borrar_plan_deja_la_copia_como_condiciones_particulares(self):
        plan = self.plan()
        self.aplicar(plan)

        r = self.cliente_api.post(f"/api/planes-cobertura/{plan['id']}/eliminar/", {}, format="json")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(PlanCobertura.objects.filter(pk=plan["id"]).exists())
        condiciones = CondicionesPoliza.objects.get(poliza=self.poliza)
        self.assertIsNone(condiciones.plan_id)
        self.assertEqual(condiciones.cubre, "Responsabilidad civil.")

    # --- compañía --------------------------------------------------------------

    def test_borrar_compania_en_cascada_y_los_clientes_quedan_sin_poliza(self):
        self.aplicar(self.plan())
        otro_cliente = fabricas.crear_cliente()
        fabricas.crear_poliza(otro_cliente, compania=self.compania)
        ajena = fabricas.crear_poliza(otro_cliente, compania=fabricas.crear_compania())
        fabricas.crear_cotizacion(compania=self.compania)

        r = self.cliente_api.post(f"/api/companias/{self.compania.id}/eliminar-definitivo/", {}, format="json")

        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["borrados"]["polizas"], 2)
        self.assertFalse(Compania.objects.filter(pk=self.compania.id).exists())
        self.assertFalse(Poliza.objects.filter(compania_id=self.compania.id).exists())
        self.assertFalse(PlanCobertura.objects.filter(compania_id=self.compania.id).exists())
        self.assertFalse(Cotizacion.objects.filter(compania_id=self.compania.id).exists())
        self.assertTrue(Cliente.objects.filter(pk__in=[self.cliente.id, otro_cliente.id]).count() == 2)
        self.assertTrue(Poliza.objects.filter(pk=ajena.id).exists())

    def test_compania_con_siniestro_no_borra_nada(self):
        Siniestro.objects.create(numero_siniestro="SIN-2026-00010", poliza=self.poliza,
                                 fecha_ocurrencia=timezone.localdate(), descripcion="Choque")
        with self.assertRaises(EstadoInvalido):
            eliminar_compania(self.compania.id, self.admin.id)
        self.assertTrue(Compania.objects.filter(pk=self.compania.id).exists())

    # --- permisos ----------------------------------------------------------------

    def test_solo_el_administrador_borra(self):
        plan = self.plan()
        for funcion, objetivo in ((eliminar_poliza, self.poliza.id), (eliminar_plan, plan["id"]),
                                  (eliminar_compania, self.compania.id)):
            with self.assertRaises(PermisoDenegado):
                funcion(objetivo, self.aprobadora.id)
        self.entrar()
        for ruta in (f"/api/polizas/{self.poliza.id}/eliminar-definitivo/",
                     f"/api/planes-cobertura/{plan['id']}/eliminar/",
                     f"/api/companias/{self.compania.id}/eliminar-definitivo/"):
            self.assertEqual(self.cliente_api.post(ruta, {}, format="json").status_code, 403, ruta)
        self.assertTrue(Poliza.objects.filter(pk=self.poliza.id).exists())
