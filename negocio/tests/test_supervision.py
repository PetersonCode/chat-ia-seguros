"""Etapa D: supervisión humana (AC-T3-24 a AC-T3-29)."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import (
    Alerta,
    EstadoAlerta,
    EstadoConsulta,
    EstadoEnvio,
    Mensaje,
)
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)
from negocio.supervision import (
    cerrar_casos,
    descartar_respuesta,
    devolver_al_bot,
    liberar_respuesta,
    reabrir_consulta,
    responder_como_humano,
    tomar_conversacion,
    vaciar_chat,
)
from negocio.bot.plantillas import DERIVACION, DERIVACION_URGENTE
from negocio.whatsapp import enviar_pendientes, registrar_entrante


class BaseSupervisionTests(TestCase):
    def setUp(self):
        self.aprobador = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
        self.operador = fabricas.crear_funcionario("Diego", puede_aprobar=False)
        self.cliente = fabricas.crear_cliente()
        self.contacto = fabricas.crear_contacto(self.cliente)
        self.conversacion = fabricas.crear_conversacion(
            self.contacto, ultimo_mensaje_cliente_en=timezone.now()
        )
        self.consulta = fabricas.crear_consulta(self.conversacion)

    def _retenido(self, texto: str = "Tu póliza POL-99999 fue dada de baja.") -> Mensaje:
        mensaje = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto=texto,
            estado_envio=EstadoEnvio.RETENIDO,
            wa_message_id=None,
        )
        self.alerta = fabricas.crear_alerta(
            self.consulta, mensaje=mensaje, tipo="dato_inventado", severidad="alta"
        )
        return mensaje


class LiberarTests(BaseSupervisionTests):
    # AC-T3-24
    def test_liberar_sin_texto_envia_el_original_y_descarta_sus_alertas(self):
        mensaje = self._retenido()
        resultado = liberar_respuesta(mensaje.id, self.aprobador.id)

        self.assertEqual(resultado.id, mensaje.id)
        self.assertEqual(resultado.estado_envio, EstadoEnvio.ENVIADO)

        self.alerta.refresh_from_db()
        self.assertEqual(self.alerta.estado, EstadoAlerta.DESCARTADA)
        self.assertEqual(self.alerta.resuelta_por_id, self.aprobador.id)
        self.assertIsNotNone(self.alerta.resuelta_en)
        self.assertEqual(self.alerta.resolucion, "Liberada sin cambios")
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.revisado_por_id, self.aprobador.id)
        self.assertIsNotNone(self.consulta.revisado_en)

    # AC-T3-25
    def test_liberar_con_correccion_descarta_el_original_y_manda_el_texto_nuevo(self):
        mensaje = self._retenido()
        resultado = liberar_respuesta(
            mensaje.id, self.aprobador.id, "Un asesor va a revisar tu pedido."
        )

        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.DESCARTADO)

        self.assertNotEqual(resultado.id, mensaje.id)
        self.assertEqual(resultado.emisor, "funcionario")
        self.assertEqual(resultado.funcionario_id, self.aprobador.id)
        self.assertEqual(resultado.texto, "Un asesor va a revisar tu pedido.")
        self.assertEqual(resultado.estado_envio, EstadoEnvio.ENVIADO)

        self.alerta.refresh_from_db()
        self.assertEqual(self.alerta.estado, EstadoAlerta.RESUELTA)

        self.consulta.refresh_from_db()
        self.assertEqual(
            self.consulta.respuesta_corregida, "Un asesor va a revisar tu pedido."
        )
        self.assertEqual(self.consulta.revisado_por_id, self.aprobador.id)
        self.assertIsNotNone(self.consulta.revisado_en)

    # AC-T3-27
    def test_un_operador_no_puede_liberar(self):
        mensaje = self._retenido()
        with self.assertRaises(PermisoDenegado):
            liberar_respuesta(mensaje.id, self.operador.id)
        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.RETENIDO)

    # AC-T3-27
    def test_un_mensaje_que_ya_no_esta_retenido_es_estado_invalido(self):
        mensaje = self._retenido()
        liberar_respuesta(mensaje.id, self.aprobador.id)
        with self.assertRaises(EstadoInvalido):
            liberar_respuesta(mensaje.id, self.aprobador.id)

    # AC-T3-27
    def test_un_id_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            liberar_respuesta(999999, self.aprobador.id)
        with self.assertRaises(NoEncontrado):
            descartar_respuesta(999999, self.aprobador.id, "motivo largo")
        with self.assertRaises(NoEncontrado):
            reabrir_consulta(999999, self.aprobador.id)


class DescartarTests(BaseSupervisionTests):
    # AC-T3-26
    def test_descartar_con_motivo_no_envia_nada_y_resuelve_las_alertas(self):
        mensaje = self._retenido()
        resultado = descartar_respuesta(
            mensaje.id, self.aprobador.id, "Inventó el número de póliza."
        )

        self.assertEqual(resultado.estado_envio, EstadoEnvio.DESCARTADO)
        self.assertEqual(resultado.error, "Inventó el número de póliza.")
        self.assertFalse(
            Mensaje.objects.filter(estado_envio=EstadoEnvio.ENVIADO).exists()
        )

        self.alerta.refresh_from_db()
        self.assertEqual(self.alerta.estado, EstadoAlerta.RESUELTA)
        self.assertEqual(self.alerta.resolucion, "Inventó el número de póliza.")

    # AC-T3-26
    def test_un_motivo_de_menos_de_cinco_caracteres_es_datos_invalidos(self):
        mensaje = self._retenido()
        for motivo in ("", "   ", "mal", "nop "):
            with self.subTest(motivo=motivo):
                with self.assertRaises(DatosInvalidos):
                    descartar_respuesta(mensaje.id, self.aprobador.id, motivo)
        mensaje.refresh_from_db()
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.RETENIDO)

    # AC-T3-27
    def test_un_operador_no_puede_descartar(self):
        mensaje = self._retenido()
        with self.assertRaises(PermisoDenegado):
            descartar_respuesta(mensaje.id, self.operador.id, "motivo suficiente")


class ConversacionTests(BaseSupervisionTests):
    # AC-T3-28
    def test_tomar_y_devolver_la_conversacion(self):
        tomada = tomar_conversacion(self.conversacion.id, self.operador.id)
        self.assertEqual(tomada.modo, "humano")
        self.assertEqual(tomada.funcionario_id, self.operador.id)

        devuelta = devolver_al_bot(self.conversacion.id, self.operador.id)
        self.assertEqual(devuelta.modo, "bot")
        self.assertIsNone(devuelta.funcionario_id)

    def test_tomar_descarta_la_respuesta_comun_y_envia_solo_lo_autorizado(self):
        comun = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto="Tu saldo es de $10.000.",
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            wa_message_id=None,
        )
        derivacion = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto=DERIVACION,
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            wa_message_id=None,
        )
        derivacion_urgente = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto=DERIVACION_URGENTE,
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            wa_message_id=None,
        )
        liberada = fabricas.crear_mensaje(
            self.conversacion,
            consulta=self.consulta,
            direccion="saliente",
            emisor="bot",
            texto="Respuesta revisada.",
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            wa_message_id=None,
        )
        self.consulta.respuesta_bot = liberada.texto
        self.consulta.revisado_por = self.aprobador
        self.consulta.revisado_en = timezone.now()
        self.consulta.respuesta_corregida = liberada.texto
        self.consulta.save(
            update_fields=[
                "respuesta_bot",
                "revisado_por",
                "revisado_en",
                "respuesta_corregida",
            ]
        )
        humana = fabricas.crear_mensaje(
            self.conversacion,
            direccion="saliente",
            emisor="funcionario",
            funcionario=self.operador,
            texto="Te ayudo con tu consulta.",
            estado_envio=EstadoEnvio.PENDIENTE_ENVIO,
            wa_message_id=None,
        )

        tomada = tomar_conversacion(self.conversacion.id, self.operador.id)

        self.assertEqual(tomada.funcionario_id, self.operador.id)
        comun.refresh_from_db()
        derivacion.refresh_from_db()
        derivacion_urgente.refresh_from_db()
        liberada.refresh_from_db()
        humana.refresh_from_db()
        self.assertEqual(comun.estado_envio, EstadoEnvio.DESCARTADO)
        self.assertEqual(comun.error, "atencion_humana")
        self.assertEqual(derivacion.estado_envio, EstadoEnvio.ENVIADO)
        self.assertEqual(derivacion_urgente.estado_envio, EstadoEnvio.ENVIADO)
        self.assertEqual(liberada.estado_envio, EstadoEnvio.ENVIADO)
        self.assertEqual(humana.estado_envio, EstadoEnvio.ENVIADO)

        devolver_al_bot(self.conversacion.id, self.operador.id)
        self.assertEqual(enviar_pendientes(self.conversacion.id), 0)
        comun.refresh_from_db()
        self.assertEqual(comun.estado_envio, EstadoEnvio.DESCARTADO)

    def test_respuesta_liberada_sin_cambios_sale_durante_atencion_humana(self):
        tomar_conversacion(self.conversacion.id, self.operador.id)
        mensaje = self._retenido("Respuesta segura para liberar.")
        self.consulta.respuesta_bot = mensaje.texto
        self.consulta.save(update_fields=["respuesta_bot"])

        resultado = liberar_respuesta(mensaje.id, self.aprobador.id)

        self.assertEqual(resultado.estado_envio, EstadoEnvio.ENVIADO)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.revisado_por_id, self.aprobador.id)
        self.assertEqual(self.consulta.nota_revision, "Liberada sin cambios")

    def test_cualquier_funcionario_activo_puede_reasignar_pero_solo_el_asignado_actua(
        self,
    ):
        tomar_conversacion(self.conversacion.id, self.operador.id)
        tomada = tomar_conversacion(self.conversacion.id, self.aprobador.id)
        self.assertEqual(tomada.funcionario_id, self.aprobador.id)

        with self.assertRaises(PermisoDenegado):
            responder_como_humano(self.conversacion.id, self.operador.id, "Hola.")
        with self.assertRaises(PermisoDenegado):
            devolver_al_bot(self.conversacion.id, self.operador.id)

        mensaje = responder_como_humano(
            self.conversacion.id, self.aprobador.id, "Te llamo en 5 minutos."
        )
        self.assertEqual(mensaje.funcionario_id, self.aprobador.id)

    def test_no_se_puede_responder_ni_devolver_un_chat_que_no_se_tomo(self):
        with self.assertRaises(EstadoInvalido):
            responder_como_humano(self.conversacion.id, self.operador.id, "Hola.")
        with self.assertRaises(EstadoInvalido):
            devolver_al_bot(self.conversacion.id, self.operador.id)

    # AC-T3-28
    def test_responder_como_humano_con_la_ventana_abierta_crea_y_envia(self):
        tomar_conversacion(self.conversacion.id, self.operador.id)
        mensaje = responder_como_humano(
            self.conversacion.id, self.operador.id, "  Te llamo en 5 minutos.  "
        )
        self.assertEqual(mensaje.texto, "Te llamo en 5 minutos.")
        self.assertEqual(mensaje.emisor, "funcionario")
        self.assertEqual(mensaje.funcionario_id, self.operador.id)
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.ENVIADO)

    # AC-T3-28
    def test_responder_con_la_ventana_cerrada_da_el_codigo_especifico(self):
        tomar_conversacion(self.conversacion.id, self.operador.id)
        self.conversacion.ultimo_mensaje_cliente_en = timezone.now() - timedelta(hours=25)
        self.conversacion.save(update_fields=["ultimo_mensaje_cliente_en"])

        with self.assertRaises(EstadoInvalido) as error:
            responder_como_humano(self.conversacion.id, self.operador.id, "hola")
        self.assertEqual(error.exception.codigo, "ventana_24h_cerrada")
        self.assertFalse(Mensaje.objects.filter(emisor="funcionario").exists())

    # AC-T3-28
    def test_responder_con_texto_vacio_es_datos_invalidos(self):
        for texto in ("", "   "):
            with self.subTest(texto=texto):
                with self.assertRaises(DatosInvalidos):
                    responder_como_humano(self.conversacion.id, self.operador.id, texto)

    # AC-T3-27
    def test_una_conversacion_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            tomar_conversacion(999999, self.operador.id)


class ReabrirTests(BaseSupervisionTests):
    # AC-T3-29
    def test_reabrir_una_consulta_cerrada_la_deja_pendiente_de_revision(self):
        self.consulta.estado = EstadoConsulta.CERRADO
        self.consulta.save(update_fields=["estado"])

        resultado = reabrir_consulta(self.consulta.id, self.aprobador.id)
        self.assertEqual(resultado.estado, EstadoConsulta.PENDIENTE_REVISION)

    # AC-T3-29
    def test_reabrir_una_consulta_en_otro_estado_es_estado_invalido(self):
        for estado in (
            EstadoConsulta.ABIERTO,
            EstadoConsulta.PENDIENTE_REVISION,
            EstadoConsulta.DERIVADO,
        ):
            with self.subTest(estado=estado):
                self.consulta.estado = estado
                self.consulta.save(update_fields=["estado"])
                with self.assertRaises(EstadoInvalido):
                    reabrir_consulta(self.consulta.id, self.aprobador.id)

    # AC-T3-27
    def test_un_operador_no_puede_reabrir(self):
        self.consulta.estado = EstadoConsulta.CERRADO
        self.consulta.save(update_fields=["estado"])
        with self.assertRaises(PermisoDenegado):
            reabrir_consulta(self.consulta.id, self.operador.id)
        self.assertEqual(Alerta.objects.count(), 0)


class CerrarCasosTests(BaseSupervisionTests):
    """Cerrar el trabajo (los `CASO-###`) sin cerrar el canal."""

    def test_cierra_los_casos_abiertos_y_deja_la_conversacion_abierta(self):
        self.consulta.estado = EstadoConsulta.ABIERTO
        self.consulta.save(update_fields=["estado"])

        cerrados = cerrar_casos(self.conversacion.id, self.operador.id)

        self.assertEqual([caso.id for caso in cerrados], [self.consulta.id])
        self.consulta.refresh_from_db()
        self.conversacion.refresh_from_db()
        self.assertEqual(self.consulta.estado, EstadoConsulta.CERRADO)
        self.assertEqual(self.consulta.fecha_resolucion, timezone.localdate())
        # El chat sigue abierto: el cliente puede volver a escribir.
        self.assertEqual(self.conversacion.estado, "abierta")

    def test_tambien_cierra_los_derivados_y_los_pendientes_de_revision(self):
        derivado = fabricas.crear_consulta(
            self.conversacion, estado=EstadoConsulta.DERIVADO
        )
        pendiente = fabricas.crear_consulta(
            self.conversacion, estado=EstadoConsulta.PENDIENTE_REVISION
        )

        cerrar_casos(self.conversacion.id, self.operador.id)

        for caso in (derivado, pendiente):
            caso.refresh_from_db()
            self.assertEqual(caso.estado, EstadoConsulta.CERRADO)

    def test_no_cierra_mientras_haya_una_respuesta_retenida(self):
        self._retenido()

        with self.assertRaises(EstadoInvalido):
            cerrar_casos(self.conversacion.id, self.operador.id)

        self.consulta.refresh_from_db()
        self.assertNotEqual(self.consulta.estado, EstadoConsulta.CERRADO)

    def test_sin_casos_abiertos_es_estado_invalido(self):
        self.consulta.estado = EstadoConsulta.CERRADO
        self.consulta.save(update_fields=["estado"])

        with self.assertRaises(EstadoInvalido):
            cerrar_casos(self.conversacion.id, self.operador.id)

    def test_una_conversacion_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            cerrar_casos(999999, self.operador.id)


class VaciarChatTests(BaseSupervisionTests):
    """Vaciar el chat cierra la conversación: el bot arranca sin contexto."""

    def test_cierra_la_conversacion_y_la_devuelve_al_bot(self):
        tomar_conversacion(self.conversacion.id, self.operador.id)

        vaciar_chat(self.conversacion.id, self.operador.id)

        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.estado, "cerrada")
        self.assertIsNotNone(self.conversacion.cerrada_en)
        self.assertEqual(self.conversacion.modo, "bot")
        self.assertIsNone(self.conversacion.funcionario_id)

    def test_el_proximo_mensaje_abre_una_conversacion_sin_historial(self):
        fabricas.crear_mensaje(self.conversacion, texto="soy el dueño")
        vaciar_chat(self.conversacion.id, self.operador.id)

        nuevo = registrar_entrante("wamid.nuevo", self.contacto.numero, "hola")

        self.assertNotEqual(nuevo.conversacion_id, self.conversacion.id)
        self.assertEqual(
            list(Mensaje.objects.filter(conversacion_id=nuevo.conversacion_id)),
            [nuevo],
        )

    def test_no_borra_mensajes_casos_ni_alertas(self):
        self._retenido()
        liberar_respuesta(
            Mensaje.objects.get(estado_envio=EstadoEnvio.RETENIDO).id,
            self.aprobador.id,
        )
        mensajes = Mensaje.objects.count()

        vaciar_chat(self.conversacion.id, self.operador.id)

        self.assertEqual(Mensaje.objects.count(), mensajes)
        self.assertTrue(Alerta.objects.filter(consulta=self.consulta).exists())

    def test_no_vacia_con_una_respuesta_retenida(self):
        self._retenido()

        with self.assertRaises(EstadoInvalido):
            vaciar_chat(self.conversacion.id, self.operador.id)

        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.estado, "abierta")

    def test_una_conversacion_ya_cerrada_es_estado_invalido(self):
        vaciar_chat(self.conversacion.id, self.operador.id)

        with self.assertRaises(EstadoInvalido):
            vaciar_chat(self.conversacion.id, self.operador.id)
