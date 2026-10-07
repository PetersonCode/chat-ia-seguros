"""Etapa C: supervisión por HTTP (AC-T2-10 a AC-T2-14)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import EstadoAlerta, EstadoConsulta, EstadoEnvio


class BandejaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.entrar()
        self.consulta = fabricas.crear_consulta(self.conversacion)
        fabricas.crear_mensaje(
            self.conversacion,
            texto="¿cuánto debo?",
            fecha_hora=timezone.now() - timedelta(minutes=30),
        )

    # AC-T2-10
    def test_la_bandeja_trae_el_resumen_completo_de_cada_conversacion(self):
        fabricas.crear_alerta(self.consulta, severidad="alta")
        fabricas.crear_mensaje(
            self.conversacion,
            direccion="saliente",
            emisor="bot",
            texto="respuesta frenada",
            estado_envio=EstadoEnvio.RETENIDO,
            wa_message_id=None,
        )

        resultados = self.cliente_api.get("/api/conversaciones/").json()["resultados"]
        fila = next(f for f in resultados if f["id"] == self.conversacion.id)

        self.assertEqual(fila["whatsapp"], "+5491155551001")
        self.assertEqual(fila["cliente"]["apellido"], "Fernández")
        self.assertEqual(fila["estado"], "abierta")
        self.assertEqual(fila["modo"], "bot")
        self.assertIsNone(fila["atendida_por"])
        self.assertEqual(fila["alertas_abiertas"], 1)
        self.assertEqual(fila["severidad_maxima"], "alta")
        self.assertEqual(fila["color"], "naranja")
        self.assertEqual(fila["respuestas_retenidas"], 1)
        self.assertTrue(fila["ventana_24h_abierta"])
        self.assertEqual(fila["ultimo_mensaje"]["texto"], "respuesta frenada")
        self.assertEqual(fila["ultimo_mensaje"]["emisor"], "bot")

    # AC-T2-10
    def test_sin_alertas_la_severidad_es_nula_y_el_color_verde(self):
        resultados = self.cliente_api.get("/api/conversaciones/").json()["resultados"]
        fila = next(f for f in resultados if f["id"] == self.conversacion.id)
        self.assertIsNone(fila["severidad_maxima"])
        self.assertEqual(fila["color"], "verde")

    # AC-T2-10
    def test_sin_respuesta_marca_las_que_el_bot_dejo_colgadas(self):
        resultados = self.cliente_api.get("/api/conversaciones/").json()["resultados"]
        fila = next(f for f in resultados if f["id"] == self.conversacion.id)
        self.assertTrue(fila["sin_respuesta"])

    # AC-T2-10
    def test_los_filtros_de_la_query_llegan_al_selector(self):
        fabricas.crear_alerta(self.consulta, severidad="alta")
        otra = fabricas.crear_conversacion(
            fabricas.crear_contacto(None, numero="+5491155559999")
        )

        con_alertas = self.cliente_api.get("/api/conversaciones/?con_alertas=1").json()
        self.assertEqual([f["id"] for f in con_alertas["resultados"]], [self.conversacion.id])

        esperando = self.cliente_api.get("/api/conversaciones/?esperando_humano=1").json()
        self.assertEqual(esperando["resultados"], [])

        buscando = self.cliente_api.get("/api/conversaciones/?q=Fernández").json()
        self.assertEqual([f["id"] for f in buscando["resultados"]], [self.conversacion.id])

        cerradas = self.cliente_api.get("/api/conversaciones/?estado=cerrada").json()
        self.assertEqual(cerradas["resultados"], [])
        self.assertIsNotNone(otra.id)

    # AC-T2-11
    def test_el_detalle_trae_cliente_info_con_sus_polizas_y_las_alertas_abiertas(self):
        poliza = fabricas.crear_poliza(self.cliente)
        fabricas.crear_cuota(poliza, importe="8000.00")
        abierta = fabricas.crear_alerta(self.consulta, severidad="alta")
        # La base exige resuelta_por y resuelta_en cuando el estado es resuelta.
        fabricas.crear_alerta(
            self.consulta,
            estado=EstadoAlerta.RESUELTA,
            resuelta_por=self.aprobadora,
            resuelta_en=timezone.now(),
        )

        payload = self.cliente_api.get(
            f"/api/conversaciones/{self.conversacion.id}/"
        ).json()

        self.assertEqual(payload["cliente_info"]["dni"], "27345678")
        self.assertEqual(len(payload["cliente_info"]["polizas"]), 1)
        self.assertEqual(
            payload["cliente_info"]["polizas"][0]["numero_poliza"], poliza.numero_poliza
        )
        self.assertEqual(payload["cliente_info"]["polizas"][0]["saldo_pendiente"], "8000.00")
        self.assertEqual([a["id"] for a in payload["alertas"]], [abierta.id])
        # El detalle también trae todo lo del resumen.
        self.assertIn("ventana_24h_abierta", payload)

    # AC-T2-11
    def test_un_contacto_sin_cliente_tiene_cliente_info_nulo(self):
        anonima = fabricas.crear_conversacion(
            fabricas.crear_contacto(None, numero="+5491155558888")
        )
        payload = self.cliente_api.get(f"/api/conversaciones/{anonima.id}/").json()
        self.assertIsNone(payload["cliente_info"])
        self.assertIsNone(payload["cliente"])

    # AC-T2-11
    def test_una_conversacion_inexistente_es_404(self):
        self.assertError(
            self.cliente_api.get("/api/conversaciones/999999/"), 404, "no_encontrado"
        )

    # AC-T2-12
    def test_los_mensajes_vienen_en_orden_con_sus_alertas_y_filtrados(self):
        primero = fabricas.crear_mensaje(
            self.conversacion,
            texto="primero",
            fecha_hora=timezone.now() - timedelta(minutes=10),
        )
        segundo = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto="segundo",
            estado_envio=EstadoEnvio.RETENIDO,
            wa_message_id=None,
            fecha_hora=timezone.now() - timedelta(minutes=5),
        )
        alerta = fabricas.crear_alerta(self.consulta, mensaje=segundo)

        todos = self.cliente_api.get(
            f"/api/conversaciones/{self.conversacion.id}/mensajes/"
        ).json()["mensajes"]
        ids = [mensaje["id"] for mensaje in todos]
        self.assertLess(ids.index(primero.id), ids.index(segundo.id))
        self.assertEqual(
            next(m for m in todos if m["id"] == segundo.id)["alertas"], [alerta.id]
        )

        desde = self.cliente_api.get(
            f"/api/conversaciones/{self.conversacion.id}/mensajes/?despues_de={primero.id}"
        ).json()["mensajes"]
        self.assertTrue(all(mensaje["id"] > primero.id for mensaje in desde))

    # AC-T2-12
    def test_un_despues_de_que_no_es_numero_es_400(self):
        self.assertError(
            self.cliente_api.get(
                f"/api/conversaciones/{self.conversacion.id}/mensajes/?despues_de=ayer"
            ),
            400,
            "datos_invalidos",
        )


class AccionesDeSupervisionTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.consulta = fabricas.crear_consulta(self.conversacion)

    def _retenido(self):
        mensaje = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto="Tu póliza POL-99999 fue dada de baja.",
            estado_envio=EstadoEnvio.RETENIDO,
            wa_message_id=None,
        )
        self.alerta = fabricas.crear_alerta(self.consulta, mensaje=mensaje)
        return mensaje

    # AC-T2-13
    def test_tomar_y_devolver_devuelven_el_detalle(self):
        self.entrar()
        tomada = self.cliente_api.post(
            f"/api/conversaciones/{self.conversacion.id}/tomar/"
        )
        self.assertEqual(tomada.status_code, 200, tomada.content)
        self.assertEqual(tomada.json()["modo"], "humano")
        self.assertEqual(tomada.json()["atendida_por"]["id"], self.aprobadora.id)
        self.assertIn("cliente_info", tomada.json())

        devuelta = self.cliente_api.post(
            f"/api/conversaciones/{self.conversacion.id}/devolver/"
        )
        self.assertEqual(devuelta.json()["modo"], "bot")
        self.assertIsNone(devuelta.json()["atendida_por"])

    # AC-T2-13
    def test_responder_devuelve_201_con_el_mensaje(self):
        self.entrar()
        respuesta = self.cliente_api.post(
            f"/api/conversaciones/{self.conversacion.id}/responder/",
            {"texto": "Te llamo en 5 minutos."},
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        payload = respuesta.json()
        self.assertEqual(payload["texto"], "Te llamo en 5 minutos.")
        self.assertEqual(payload["emisor"], "funcionario")
        self.assertEqual(payload["funcionario"]["id"], self.aprobadora.id)

    # AC-T2-13
    def test_liberar_devuelve_el_mensaje_que_sale_al_cliente(self):
        self.entrar()
        mensaje = self._retenido()
        payload = self.cliente_api.post(
            f"/api/mensajes/{mensaje.id}/liberar/", {}, format="json"
        ).json()
        self.assertEqual(payload["id"], mensaje.id)
        self.assertEqual(payload["estado_envio"], "enviado")

    # AC-T2-13
    def test_liberar_con_correccion_devuelve_el_mensaje_nuevo(self):
        self.entrar()
        mensaje = self._retenido()
        payload = self.cliente_api.post(
            f"/api/mensajes/{mensaje.id}/liberar/",
            {"texto_corregido": "Un asesor te contacta."},
            format="json",
        ).json()
        self.assertNotEqual(payload["id"], mensaje.id)
        self.assertEqual(payload["texto"], "Un asesor te contacta.")
        self.assertEqual(payload["emisor"], "funcionario")

    # AC-T2-13
    def test_descartar_devuelve_el_mensaje_descartado(self):
        self.entrar()
        mensaje = self._retenido()
        payload = self.cliente_api.post(
            f"/api/mensajes/{mensaje.id}/descartar/",
            {"motivo": "Inventó el número de póliza."},
            format="json",
        ).json()
        self.assertEqual(payload["estado_envio"], "descartado")

    # AC-T2-13
    def test_liberar_y_descartar_exigen_aprobador(self):
        self.entrar(self.operador)
        mensaje = self._retenido()
        for ruta, cuerpo in (
            (f"/api/mensajes/{mensaje.id}/liberar/", {}),
            (f"/api/mensajes/{mensaje.id}/descartar/", {"motivo": "porque si"}),
        ):
            with self.subTest(ruta=ruta):
                self.assertError(
                    self.cliente_api.post(ruta, cuerpo, format="json"),
                    403,
                    "permiso_denegado",
                )

    # AC-T2-13
    def test_reabrir_devuelve_la_consulta_y_exige_aprobador(self):
        self.consulta.estado = EstadoConsulta.CERRADO
        self.consulta.save(update_fields=["estado"])

        self.entrar(self.operador)
        self.assertError(
            self.cliente_api.post(f"/api/consultas/{self.consulta.id}/reabrir/"),
            403,
            "permiso_denegado",
        )

        self.cliente_api.logout()
        self.entrar()
        payload = self.cliente_api.post(
            f"/api/consultas/{self.consulta.id}/reabrir/"
        ).json()
        self.assertEqual(payload["id"], self.consulta.id)
        self.assertEqual(payload["estado"], "pendiente_revision")
        self.assertEqual(payload["codigo_caso"], self.consulta.codigo_caso)


class ListadosTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.entrar()
        self.consulta = fabricas.crear_consulta(self.conversacion)

    # AC-T2-14
    def test_alertas_filtra_por_tipo_severidad_y_estado(self):
        abierta = fabricas.crear_alerta(
            self.consulta, tipo="dato_inventado", severidad="alta"
        )
        fabricas.crear_alerta(
            self.consulta,
            tipo="fuga_datos",
            severidad="critica",
            estado=EstadoAlerta.RESUELTA,
            resuelta_por=self.aprobadora,
            resuelta_en=timezone.now(),
        )

        por_defecto = self.cliente_api.get("/api/alertas/").json()
        self.assertEqual([a["id"] for a in por_defecto["resultados"]], [abierta.id])

        por_tipo = self.cliente_api.get("/api/alertas/?tipo=fuga_datos&estado=").json()
        self.assertEqual(len(por_tipo["resultados"]), 1)
        self.assertEqual(por_tipo["resultados"][0]["tipo"], "fuga_datos")

        por_severidad = self.cliente_api.get("/api/alertas/?severidad=critica&estado=").json()
        self.assertEqual(len(por_severidad["resultados"]), 1)

        fila = por_defecto["resultados"][0]
        self.assertEqual(fila["conversacion_id"], self.conversacion.id)
        self.assertEqual(fila["consulta_id"], self.consulta.id)

    # AC-T2-14
    def test_consultas_cerradas_con_alertas_solo_trae_esas(self):
        self.consulta.estado = EstadoConsulta.CERRADO
        self.consulta.save(update_fields=["estado"])
        fabricas.crear_alerta(self.consulta, severidad="alta")

        sin_alertas = fabricas.crear_consulta(
            self.conversacion, estado=EstadoConsulta.CERRADO
        )

        payload = self.cliente_api.get("/api/consultas/cerradas-con-alertas/").json()
        ids = [c["id"] for c in payload["resultados"]]
        self.assertIn(self.consulta.id, ids)
        self.assertNotIn(sin_alertas.id, ids)

        fila = next(c for c in payload["resultados"] if c["id"] == self.consulta.id)
        self.assertEqual(fila["alertas_abiertas"], 1)
        self.assertEqual(fila["severidad_maxima"], "alta")
        self.assertEqual(fila["cliente"]["apellido"], "Fernández")
