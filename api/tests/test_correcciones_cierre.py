from datetime import date
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.test import override_settings

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import (
    AccionPendiente, Alerta, ConsultaBot, Derivacion, DocumentoGeneral,
    EstadoDocumento, FinalizacionAccion, Mensaje, Poliza, Cuota,
)
from negocio.acciones import solicitar_accion
from negocio.bot.clasificador import clasificar
from negocio.bot.guardrails import evaluar_salida
from negocio.bot.llm import FakeLLM
from negocio.bot.orquestador import procesar_mensaje
from negocio.whatsapp import registrar_entrante


class CorreccionesDeCierreTests(ApiTestCase):
    @override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher"])
    def test_login_con_hash_de_la_aplicacion_normal(self):
        from django.contrib.auth import get_user_model
        usuario = get_user_model().objects.get(username=self.aprobadora.email)
        usuario.set_password("clave-de-prueba")
        usuario.save(update_fields=["password"])
        self.assertTrue(usuario.password.startswith("pbkdf2_sha256$"))
        self.cliente_api.logout()
        self.assertTrue(self.cliente_api.login(username=usuario.username, password="clave-de-prueba"))

    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.entrar()

    def _turno(self, texto, numero="+5491155551001"):
        mensaje = registrar_entrante(f"correccion-{Mensaje.objects.count()}", numero, texto)
        with self.captureOnCommitCallbacks(execute=True):
            resultado = procesar_mensaje(mensaje.pk)
        mensaje.conversacion.refresh_from_db()
        return mensaje, resultado

    def _documento(self, contenido="La cobertura de granizo tiene un límite de $100.000 según cláusula 3.1."):
        respuesta = self.cliente_api.post("/api/documentos/", {
            "titulo": "Guía de pruebas", "version": "1", "referencia": "Manual aprobado de prueba",
            "contenido": contenido,
        }, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        return respuesta.json()["id"]

    def test_variantes_urgentes_pausan_y_avisan_sin_modelo(self):
        for i, texto in enumerate(["Choqué y necesito ayuda", "Me chocaron", "Me robaron la moto", "Estoy en hospital"]):
            with self.subTest(texto=texto):
                contacto = fabricas.crear_contacto(self.cliente, numero=f"+54911999970{i:02d}")
                mensaje, resultado = self._turno(texto, contacto.numero)
                self.assertEqual(resultado.tipo_consulta, "siniestro_urgente")
                self.assertEqual(mensaje.conversacion.modo, "humano")
                self.assertTrue(Derivacion.objects.filter(consulta__mensajes=mensaje, prioridad="urgente").exists())
                self.assertEqual(Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).estado_envio, "enviado")

    def test_cobertura_y_negacion_no_disparan_emergencia(self):
        for texto in ["¿Mi seguro cubre robo?", "¿Cubre choque con animales?", "No tuve un choque", "Nunca estuve en el hospital", "No es una emergencia"]:
            with self.subTest(texto=texto):
                self.assertNotEqual(clasificar(texto), "siniestro_urgente")
        self.assertEqual(clasificar("No estoy herido, pero me robaron la moto"), "siniestro_urgente")
        self.assertEqual(clasificar("No tengo el número de póliza me robaron la moto"), "siniestro_urgente")

    def test_confirmacion_de_registro_llega_al_derivar(self):
        numero = "+5491199997100"
        self._turno("Necesito hablar con un asesor", numero)
        mensaje, resultado = self._turno("Juan Pérez, DNI 30111222", numero)
        respuesta = Mensaje.objects.get(pk=resultado.mensaje_respuesta_id)
        self.assertEqual(mensaje.conversacion.modo, "humano")
        self.assertEqual(respuesta.estado_envio, "enviado")
        self.assertNotIn("30111222", respuesta.texto)

    def test_respuesta_insegura_se_retiene_pero_el_aviso_si_llega(self):
        with patch("negocio.bot.orquestador.cliente_llm", return_value=FakeLLM(clasificacion="saludo", charla="Tu póliza POL-99999 está al día.")):
            mensaje, resultado = self._turno("hola buenas")
        self.assertTrue(resultado.retenido)
        self.assertEqual(Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).estado_envio, "retenido")
        self.assertEqual(Mensaje.objects.filter(conversacion=mensaje.conversacion, estado_envio="enviado").count(), 1)

    def test_documento_aprobado_con_importe_y_clausula_respalda_la_cita(self):
        did = self._documento()
        self.cliente_api.post(f"/api/documentos/{did}/aprobar/")
        _, resultado = self._turno("¿Qué cobertura hay contra granizo?")
        self.assertFalse(resultado.retenido)
        self.assertEqual(Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).estado_envio, "enviado")
        self.assertIn("$100.000", Mensaje.objects.get(pk=resultado.mensaje_respuesta_id).texto)

    def test_evidencia_no_autoriza_un_importe_agregado_ni_un_documento_retirado(self):
        did = self._documento()
        self.cliente_api.post(f"/api/documentos/{did}/aprobar/")
        fragmento = DocumentoGeneral.objects.get(pk=did).fragmentos.get()
        cita = f"Fuente: “{fragmento.texto}”"
        self.assertEqual(evaluar_salida(cita, cliente_id=self.cliente.pk, fragmento_documental_id=fragmento.pk), [])
        self.assertTrue(evaluar_salida(cita + " Además te devolveremos $500.", cliente_id=self.cliente.pk, fragmento_documental_id=fragmento.pk))
        self.cliente_api.post(f"/api/documentos/{did}/retirar/")
        self.assertTrue(evaluar_salida(cita, cliente_id=self.cliente.pk, fragmento_documental_id=fragmento.pk))

    def test_biblioteca_se_administra_y_el_operador_no_ve_borradores(self):
        did = self._documento()
        self.assertEqual(self.cliente_api.get("/api/documentos/").json()["total"], 1)
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.get("/api/documentos/").json()["total"], 0)
        self.assertEqual(self.cliente_api.get(f"/api/documentos/{did}/").status_code, 404)
        self.assertEqual(self.cliente_api.post(f"/api/documentos/{did}/aprobar/").status_code, 403)
        self.entrar()
        self.cliente_api.post(f"/api/documentos/{did}/aprobar/")
        self.entrar(self.operador)
        detalle = self.cliente_api.get(f"/api/documentos/{did}/").json()
        self.assertIn("$100.000", detalle["contenido"])
        self.assertEqual(self.cliente_api.get("/api/documentos/?estado=inventado").status_code, 400)

    def _accion_externa(self):
        consulta = fabricas.crear_consulta(self.conversacion)
        return solicitar_accion(consulta.pk, "reembolso", parametros={"importe": "100"})

    def test_aprobar_finalizar_y_cerrar_con_historial(self):
        accion = self._accion_externa()
        self.assertEqual(self.cliente_api.post(f"/api/acciones/{accion.pk}/aprobar/").status_code, 200)
        ruta_cierre = f"/api/conversaciones/{self.conversacion.pk}/cerrar-casos/"
        self.assertEqual(self.cliente_api.post(ruta_cierre).status_code, 409)
        otro = fabricas.crear_funcionario("Otro aprobador")
        self.entrar(otro)
        self.aprobadora.activo = False
        self.aprobadora.save(update_fields=["activo"])
        datos = {"referencia": "COMPROBANTE-DEMO-001", "motivo": "Gestión externa comprobada"}
        ruta = f"/api/acciones/{accion.pk}/finalizar/"
        final = self.cliente_api.post(ruta, datos, format="json")
        self.assertEqual(final.status_code, 200, final.content)
        self.assertEqual(final.json()["estado"], "ejecutada")
        self.assertEqual(final.json()["resuelta_por"]["id"], self.aprobadora.pk)
        self.assertEqual(final.json()["finalizacion"]["funcionario"]["id"], otro.pk)
        self.assertEqual(self.cliente_api.post(ruta, datos, format="json").status_code, 409)
        self.assertEqual(FinalizacionAccion.objects.count(), 1)
        self.assertEqual(self.cliente_api.post(ruta_cierre).status_code, 200)

    def test_finalizacion_exige_permiso_estado_y_evidencia(self):
        accion = self._accion_externa()
        ruta = f"/api/acciones/{accion.pk}/finalizar/"
        datos = {"referencia": "REF-001", "motivo": "Gestión realizada"}
        self.assertEqual(self.cliente_api.post(ruta, datos, format="json").status_code, 409)
        self.cliente_api.post(f"/api/acciones/{accion.pk}/aprobar/")
        self.assertEqual(self.cliente_api.post(ruta, {}, format="json").status_code, 400)
        self.entrar(self.operador)
        self.assertEqual(self.cliente_api.post(ruta, datos, format="json").status_code, 403)
        self.assertFalse(FinalizacionAccion.objects.exists())

    def test_sql_no_permite_simular_finalizacion_sin_registro(self):
        accion = self._accion_externa()
        self.cliente_api.post(f"/api/acciones/{accion.pk}/aprobar/")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AccionPendiente.objects.filter(pk=accion.pk).update(estado="ejecutada")

    def test_primas_invalidas_no_generan_datos_y_cero_no_genera_deuda(self):
        datos = {"tipo_seguro": "automotor", "cobertura": "intermedia", "fecha_inicio": "2026-01-10", "fecha_vencimiento": "2027-01-10"}
        ruta = f"/api/clientes/{self.cliente.pk}/polizas/"
        for prima in ["NaN", "Infinity", "-Infinity", "0.001", "10000000000", "-1", "1e1000000"]:
            with self.subTest(prima=prima):
                respuesta = self.cliente_api.post(ruta, {**datos, "prima_mensual": prima}, format="json")
                self.assertEqual(respuesta.status_code, 400, respuesta.content)
        self.assertEqual(Poliza.objects.count(), 0)
        self.assertEqual(Cuota.objects.count(), 0)
        cero = self.cliente_api.post(ruta, {**datos, "prima_mensual": "0"}, format="json")
        self.assertEqual(cero.status_code, 201, cero.content)
        self.assertEqual(cero.json()["cuotas"], [])
        self.assertEqual(cero.json()["saldo_pendiente"], "0.00")
