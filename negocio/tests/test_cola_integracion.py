from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier

from django.core.management import call_command
from django.db import close_old_connections

from datos import fabricas
from datos.models import FinalizacionAccion, Mensaje, TrabajoWhatsApp
from datos.tests.transacciones import PruebaConTransacciones
from negocio.acciones import aprobar_accion, finalizar_gestion_externa, solicitar_accion
from negocio.errores import EstadoInvalido
from negocio.tests.test_whatsapp import _payload_texto
from negocio.whatsapp import procesar_webhook


class ColaConCommitsRealesTests(PruebaConTransacciones):
    def test_dos_aprobaciones_concurrentes_resuelven_una_sola_vez(self):
        funcionario = fabricas.crear_funcionario()
        consulta = fabricas.crear_consulta()
        accion = solicitar_accion(consulta.pk, "reembolso", parametros={"importe": "100"})
        barrera = Barrier(2)

        def aprobar():
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                aprobar_accion(accion.pk, funcionario.pk)
                return "aprobada"
            except EstadoInvalido:
                return "ya_resuelta"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as equipo:
            futuros = [equipo.submit(aprobar) for _ in range(2)]
            resultados = [f.result(timeout=15) for f in futuros]
        self.assertCountEqual(resultados, ["aprobada", "ya_resuelta"])

    def test_webhook_y_worker_cierran_conexiones_sin_perder_el_trabajo(self):
        fabricas.crear_catalogos()
        procesar_webhook(_payload_texto("wamid.integracion", "5491199997700", "hola"))
        self.assertEqual(TrabajoWhatsApp.objects.get().estado, "pendiente")
        call_command("reprocesar_pendientes", stdout=StringIO())
        self.assertEqual(TrabajoWhatsApp.objects.get().estado, "completado")
        respuesta = Mensaje.objects.get(direccion="saliente")
        self.assertEqual(respuesta.estado_envio, "enviado")
        call_command("reprocesar_pendientes", stdout=StringIO())
        self.assertEqual(Mensaje.objects.filter(direccion="saliente").count(), 1)

    def test_dos_finalizaciones_concurrentes_registran_una_sola(self):
        funcionario = fabricas.crear_funcionario()
        consulta = fabricas.crear_consulta()
        accion = solicitar_accion(consulta.pk, "reembolso", parametros={"importe": "100"})
        aprobar_accion(accion.pk, funcionario.pk)
        barrera = Barrier(2)

        def finalizar():
            close_old_connections()
            try:
                barrera.wait(timeout=10)
                finalizar_gestion_externa(accion.pk, funcionario.pk, referencia="REF-001", motivo="Gestión comprobada")
                return "completada"
            except EstadoInvalido:
                return "ya_completada"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as equipo:
            futuros = [equipo.submit(finalizar) for _ in range(2)]
            resultados = [f.result(timeout=15) for f in futuros]
        self.assertCountEqual(resultados, ["completada", "ya_completada"])
        self.assertEqual(FinalizacionAccion.objects.count(), 1)
