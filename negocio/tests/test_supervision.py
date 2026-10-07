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
    descartar_respuesta,
    devolver_al_bot,
    liberar_respuesta,
    reabrir_consulta,
    responder_como_humano,
    tomar_conversacion,
)


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

    # AC-T3-28
    def test_responder_como_humano_con_la_ventana_abierta_crea_y_envia(self):
        mensaje = responder_como_humano(
            self.conversacion.id, self.operador.id, "  Te llamo en 5 minutos.  "
        )
        self.assertEqual(mensaje.texto, "Te llamo en 5 minutos.")
        self.assertEqual(mensaje.emisor, "funcionario")
        self.assertEqual(mensaje.funcionario_id, self.operador.id)
        self.assertEqual(mensaje.estado_envio, EstadoEnvio.ENVIADO)

    # AC-T3-28
    def test_responder_con_la_ventana_cerrada_da_el_codigo_especifico(self):
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
