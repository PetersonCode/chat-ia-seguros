"""Etapa C: acciones contractuales y derivaciones (AC-T3-16 a AC-T3-23)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import (
    AccionPendiente,
    ConductorPoliza,
    Cuota,
    Derivacion,
    EstadoAccion,
    EstadoConsulta,
    EstadoPoliza,
    Mensaje,
    Poliza,
    Siniestro,
    TipoAccion,
)
from negocio.acciones import (
    aprobar_accion,
    atender_derivacion,
    completar_parametros,
    derivar,
    rechazar_accion,
    solicitar_accion,
)
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    ParametrosIncompletos,
    PermisoDenegado,
)


class BaseAccionesTests(TestCase):
    def setUp(self):
        self.aprobador = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
        self.operador = fabricas.crear_funcionario("Diego", puede_aprobar=False)
        self.cliente = fabricas.crear_cliente()
        self.contacto = fabricas.crear_contacto(self.cliente)
        self.conversacion = fabricas.crear_conversacion(
            self.contacto, ultimo_mensaje_cliente_en=timezone.now()
        )
        self.consulta = fabricas.crear_consulta(self.conversacion)
        self.poliza = fabricas.crear_poliza(self.cliente)


class SolicitarAccionTests(BaseAccionesTests):
    # AC-T3-16
    def test_crea_una_accion_pendiente_sin_tocar_datos_del_cliente(self):
        cuota = fabricas.crear_cuota(self.poliza)
        antes = (self.poliza.estado, self.cliente.activo, cuota.estado)

        accion = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )

        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)
        self.assertEqual(accion.poliza_id, self.poliza.id)
        self.poliza.refresh_from_db()
        self.cliente.refresh_from_db()
        cuota.refresh_from_db()
        self.assertEqual(
            (self.poliza.estado, self.cliente.activo, cuota.estado), antes
        )

    # AC-T3-16
    def test_un_tipo_invalido_es_datos_invalidos(self):
        with self.assertRaises(DatosInvalidos):
            solicitar_accion(self.consulta.id, "regalar_poliza")

    # AC-T3-16
    def test_no_duplica_la_misma_accion_en_la_misma_conversacion(self):
        primera = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )
        otra_consulta = fabricas.crear_consulta(self.conversacion)
        segunda = solicitar_accion(
            otra_consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )

        self.assertEqual(primera.id, segunda.id)
        self.assertEqual(AccionPendiente.objects.count(), 1)

    # AC-T3-16
    def test_una_consulta_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            solicitar_accion(999999, TipoAccion.BAJA_POLIZA)


class AprobarAccionTests(BaseAccionesTests):
    # AC-T3-17
    def test_aprobar_una_baja_deja_la_poliza_dada_de_baja_y_la_accion_ejecutada(self):
        accion = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )
        resultado = aprobar_accion(accion.id, self.aprobador.id)

        self.assertEqual(resultado.estado, EstadoAccion.EJECUTADA)
        self.assertEqual(resultado.resuelta_por_id, self.aprobador.id)
        self.assertIsNotNone(resultado.resuelta_en)
        self.poliza.refresh_from_db()
        self.assertEqual(self.poliza.estado, EstadoPoliza.DADA_DE_BAJA)

    # AC-T3-17
    def test_una_baja_sin_poliza_pide_los_parametros_y_sigue_pendiente(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, None)
        with self.assertRaises(ParametrosIncompletos):
            aprobar_accion(accion.id, self.aprobador.id)

        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)

    # AC-T3-17
    def test_una_poliza_ya_dada_de_baja_es_estado_invalido(self):
        self.poliza.estado = EstadoPoliza.DADA_DE_BAJA
        self.poliza.save(update_fields=["estado"])
        accion = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )

        with self.assertRaises(EstadoInvalido):
            aprobar_accion(accion.id, self.aprobador.id)
        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)

    # AC-T3-18
    def test_agregar_conductor_crea_el_conductor_con_el_dni_normalizado(self):
        accion = solicitar_accion(
            self.consulta.id,
            TipoAccion.AGREGAR_CONDUCTOR,
            self.poliza.id,
            {"nombre": "Hijo De Prueba", "dni": "28.111.222", "relacion": "hijo"},
        )
        aprobar_accion(accion.id, self.aprobador.id)

        conductor = ConductorPoliza.objects.get(poliza=self.poliza)
        self.assertEqual(conductor.dni, "28111222")
        self.assertEqual(conductor.relacion, "hijo")
        self.assertTrue(conductor.activo)

    # AC-T3-18
    def test_agregar_conductor_sin_relacion_queda_en_otro(self):
        accion = solicitar_accion(
            self.consulta.id,
            TipoAccion.AGREGAR_CONDUCTOR,
            self.poliza.id,
            {"nombre": "Alguien", "dni": "28111333"},
        )
        aprobar_accion(accion.id, self.aprobador.id)
        self.assertEqual(ConductorPoliza.objects.get(poliza=self.poliza).relacion, "otro")

    # AC-T3-18
    def test_agregar_conductor_sin_nombre_ni_dni_sigue_pendiente(self):
        accion = solicitar_accion(
            self.consulta.id, TipoAccion.AGREGAR_CONDUCTOR, self.poliza.id, {}
        )
        with self.assertRaises(ParametrosIncompletos):
            aprobar_accion(accion.id, self.aprobador.id)

        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)
        self.assertFalse(ConductorPoliza.objects.exists())

    # AC-T3-18
    def test_reembolso_y_modificacion_se_ejecutan_sin_cambiar_datos(self):
        cuota = fabricas.crear_cuota(self.poliza)
        casos = (
            (TipoAccion.REEMBOLSO, {"importe": "3200.00"}),
            (TipoAccion.MODIFICAR_POLIZA, {"detalle": "cambio de cobertura"}),
        )
        for tipo, parametros in casos:
            with self.subTest(tipo=tipo):
                consulta = fabricas.crear_consulta(self.conversacion)
                accion = solicitar_accion(consulta.id, tipo, self.poliza.id, parametros)
                aprobar_accion(accion.id, self.aprobador.id)
                accion.refresh_from_db()
                self.assertEqual(accion.estado, EstadoAccion.EJECUTADA)

        self.poliza.refresh_from_db()
        cuota.refresh_from_db()
        self.assertEqual(self.poliza.estado, EstadoPoliza.VIGENTE)
        self.assertEqual(cuota.estado, "pendiente")
        self.assertEqual(Cuota.objects.count(), 1)

    # AC-T3-18
    def test_reembolso_sin_importe_y_modificacion_sin_detalle_piden_parametros(self):
        for tipo in (TipoAccion.REEMBOLSO, TipoAccion.MODIFICAR_POLIZA):
            with self.subTest(tipo=tipo):
                consulta = fabricas.crear_consulta(self.conversacion)
                accion = solicitar_accion(consulta.id, tipo, self.poliza.id, {})
                with self.assertRaises(ParametrosIncompletos):
                    aprobar_accion(accion.id, self.aprobador.id)

    # AC-T3-18
    def test_apertura_de_siniestro_numera_de_forma_secuencial(self):
        anio = timezone.now().year
        for esperado in (1, 2):
            with self.subTest(esperado=esperado):
                consulta = fabricas.crear_consulta(self.conversacion)
                accion = solicitar_accion(
                    consulta.id,
                    TipoAccion.APERTURA_SINIESTRO,
                    self.poliza.id,
                    {
                        "fecha_ocurrencia": date(2025, 5, 1).isoformat(),
                        "descripcion": "Granizo",
                    },
                )
                aprobar_accion(accion.id, self.aprobador.id)
                self.assertTrue(
                    Siniestro.objects.filter(
                        numero_siniestro=f"SIN-{anio}-{esperado:05d}"
                    ).exists()
                )

    # AC-T3-18
    def test_apertura_de_siniestro_sin_fecha_ni_descripcion_pide_parametros(self):
        accion = solicitar_accion(
            self.consulta.id, TipoAccion.APERTURA_SINIESTRO, self.poliza.id, {}
        )
        with self.assertRaises(ParametrosIncompletos):
            aprobar_accion(accion.id, self.aprobador.id)
        self.assertFalse(Siniestro.objects.exists())

    # AC-T3-19
    def test_al_aprobar_se_avisa_al_cliente_y_se_envia(self):
        accion = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )
        aprobar_accion(accion.id, self.aprobador.id)

        aviso = Mensaje.objects.get(emisor="funcionario")
        self.assertIn(f"baja de la póliza {self.poliza.numero_poliza}", aviso.texto)
        self.assertIn("fue aprobada y procesada", aviso.texto)
        self.assertEqual(aviso.estado_envio, "enviado")

    # AC-T3-19
    def test_el_aviso_de_reembolso_usa_el_formato_de_dinero(self):
        accion = solicitar_accion(
            self.consulta.id,
            TipoAccion.REEMBOLSO,
            self.poliza.id,
            {"importe": "3200.00"},
        )
        aprobar_accion(accion.id, self.aprobador.id)
        self.assertIn("reembolso de $3.200", Mensaje.objects.get(emisor="funcionario").texto)

    # AC-T3-19
    def test_si_el_envio_falla_la_accion_queda_ejecutada_igual(self):
        accion = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )
        with patch(
            "negocio.acciones.enviar_pendientes", side_effect=OSError("sin red")
        ):
            with self.assertRaises(OSError):
                aprobar_accion(accion.id, self.aprobador.id)

        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.EJECUTADA)
        self.poliza.refresh_from_db()
        self.assertEqual(self.poliza.estado, EstadoPoliza.DADA_DE_BAJA)

    # AC-T3-19
    def test_si_la_consulta_no_tiene_conversacion_no_se_envia_nada(self):
        suelta = fabricas.crear_consulta(None)
        accion = solicitar_accion(suelta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        aprobar_accion(accion.id, self.aprobador.id)
        self.assertFalse(Mensaje.objects.filter(emisor="funcionario").exists())


class RechazarAccionTests(BaseAccionesTests):
    # AC-T3-20
    def test_rechazar_sin_motivo_es_datos_invalidos(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        for motivo in ("", "   ", "no"):
            with self.subTest(motivo=motivo):
                with self.assertRaises(DatosInvalidos):
                    rechazar_accion(accion.id, self.aprobador.id, motivo)
        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)

    # AC-T3-20
    def test_rechazar_con_motivo_registra_quien_cuando_y_por_que(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        resultado = rechazar_accion(
            accion.id, self.aprobador.id, "El titular no confirmó la baja."
        )

        self.assertEqual(resultado.estado, EstadoAccion.RECHAZADA)
        self.assertEqual(resultado.resuelta_por_id, self.aprobador.id)
        self.assertIsNotNone(resultado.resuelta_en)
        self.assertEqual(resultado.motivo, "El titular no confirmó la baja.")
        self.poliza.refresh_from_db()
        self.assertEqual(self.poliza.estado, EstadoPoliza.VIGENTE)

    # AC-T3-19
    def test_al_rechazar_tambien_se_avisa_al_cliente(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        rechazar_accion(accion.id, self.aprobador.id, "No corresponde.")

        aviso = Mensaje.objects.get(emisor="funcionario")
        self.assertEqual(aviso.texto, "No pudimos procesar tu solicitud. Un asesor se va a comunicar con vos.")
        self.assertEqual(aviso.estado_envio, "enviado")


class PermisosYEstadosTests(BaseAccionesTests):
    # AC-T3-21
    def test_un_operador_no_puede_aprobar_rechazar_ni_completar(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        with self.assertRaises(PermisoDenegado):
            aprobar_accion(accion.id, self.operador.id)
        with self.assertRaises(PermisoDenegado):
            rechazar_accion(accion.id, self.operador.id, "porque no")
        with self.assertRaises(PermisoDenegado):
            completar_parametros(accion.id, self.operador.id, {"detalle": "x"})

        accion.refresh_from_db()
        self.assertEqual(accion.estado, EstadoAccion.PENDIENTE)

    # AC-T3-21
    def test_una_accion_ya_resuelta_no_se_puede_volver_a_resolver(self):
        ejecutada = solicitar_accion(
            self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id
        )
        aprobar_accion(ejecutada.id, self.aprobador.id)

        otra = fabricas.crear_consulta(self.conversacion)
        rechazada = solicitar_accion(otra.id, TipoAccion.MODIFICAR_POLIZA, None, {"detalle": "x"})
        rechazar_accion(rechazada.id, self.aprobador.id, "No corresponde.")

        for accion in (ejecutada, rechazada):
            with self.subTest(accion=accion.tipo_accion):
                with self.assertRaises(EstadoInvalido):
                    aprobar_accion(accion.id, self.aprobador.id)
                with self.assertRaises(EstadoInvalido):
                    rechazar_accion(accion.id, self.aprobador.id, "otra vez")
                with self.assertRaises(EstadoInvalido):
                    completar_parametros(accion.id, self.aprobador.id, {"a": 1})

    # AC-T3-21
    def test_la_base_rechaza_un_update_directo_a_ejecutada_sin_aprobacion(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE acciones_pendientes SET estado = 'ejecutada', "
                        "resuelta_por_id = %s WHERE id = %s",
                        [self.aprobador.id, accion.id],
                    )

    # AC-T3-21
    def test_la_base_rechaza_que_resuelva_quien_no_puede_aprobar(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE acciones_pendientes SET estado = 'aprobada', "
                        "resuelta_por_id = %s WHERE id = %s",
                        [self.operador.id, accion.id],
                    )

    # AC-T3-22
    def test_completar_parametros_mezcla_y_normaliza_el_dni(self):
        accion = solicitar_accion(
            self.consulta.id,
            TipoAccion.AGREGAR_CONDUCTOR,
            self.poliza.id,
            {"nombre": "Hijo"},
        )
        resultado = completar_parametros(
            accion.id, self.aprobador.id, {"dni": "28.111.222"}
        )
        self.assertEqual(
            resultado.parametros, {"nombre": "Hijo", "dni": "28111222"}
        )

    # AC-T3-22
    def test_completar_parametros_sobre_una_no_pendiente_es_estado_invalido(self):
        accion = solicitar_accion(self.consulta.id, TipoAccion.BAJA_POLIZA, self.poliza.id)
        aprobar_accion(accion.id, self.aprobador.id)
        with self.assertRaises(EstadoInvalido):
            completar_parametros(accion.id, self.aprobador.id, {"nombre": "x"})

    # AC-T3-21
    def test_una_accion_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            aprobar_accion(999999, self.aprobador.id)


class DerivacionTests(BaseAccionesTests):
    # AC-T3-23
    def test_derivar_crea_la_derivacion_y_pasa_la_conversacion_a_humano(self):
        derivacion = derivar(
            self.consulta.id, self.aprobador.id, "urgente", "Pide hablar con alguien."
        )

        self.assertEqual(derivacion.prioridad, "urgente")
        self.assertEqual(derivacion.derivado_a_id, self.aprobador.id)
        self.conversacion.refresh_from_db()
        self.assertEqual(self.conversacion.modo, "humano")
        self.assertEqual(self.conversacion.funcionario_id, self.aprobador.id)
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.estado, EstadoConsulta.DERIVADO)
        self.assertEqual(self.consulta.funcionario_asignado_id, self.aprobador.id)

    # AC-T3-23
    def test_derivar_con_una_prioridad_invalida_es_datos_invalidos(self):
        with self.assertRaises(DatosInvalidos):
            derivar(self.consulta.id, self.aprobador.id, "altisima")
        self.assertFalse(Derivacion.objects.exists())

    # AC-T3-23
    def test_atender_derivacion_solo_la_puede_atender_su_responsable(self):
        derivacion = derivar(self.consulta.id, self.aprobador.id)

        with self.assertRaises(PermisoDenegado):
            atender_derivacion(derivacion.id, self.operador.id)

        atendida = atender_derivacion(derivacion.id, self.aprobador.id)
        self.assertIsNotNone(atendida.atendida_en)

        with self.assertRaises(EstadoInvalido):
            atender_derivacion(derivacion.id, self.aprobador.id)

    # AC-T3-23
    def test_atender_una_derivacion_inexistente_es_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            atender_derivacion(999999, self.aprobador.id)
