from datetime import timedelta

from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import EstadoSiniestro, HistorialSiniestro, Siniestro
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado, PermisoDenegado
from negocio.siniestros import registrar_denuncia, transicionar_siniestro


class ExpedienteSiniestrosTests(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        hoy = timezone.localdate()
        self.cliente = fabricas.crear_cliente()
        self.poliza = fabricas.crear_poliza(
            self.cliente,
            fecha_inicio=hoy - timedelta(days=90),
            fecha_vencimiento=hoy + timedelta(days=180),
        )
        self.aprobador = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
        self.operador = fabricas.crear_funcionario("Diego", puede_aprobar=False)

    def _denunciar(self, **campos):
        datos = {
            "cliente_id": self.cliente.id,
            "poliza_id": self.poliza.id,
            "fecha_ocurrencia": timezone.localdate(),
            "descripcion": "Daño por granizo en el vehículo.",
            "funcionario_id": self.aprobador.id,
        }
        datos.update(campos)
        return registrar_denuncia(**datos)

    # AC-T3-56
    def test_registra_denuncia_y_audita_responsable_y_fecha(self):
        siniestro = self._denunciar()

        self.assertRegex(siniestro.numero_siniestro, r"^SIN-\d{4}-\d{5}$")
        self.assertEqual(siniestro.estado, EstadoSiniestro.DENUNCIADO)
        entrada = HistorialSiniestro.objects.get(siniestro=siniestro)
        self.assertIsNone(entrada.estado_anterior)
        self.assertEqual(entrada.estado_nuevo, EstadoSiniestro.DENUNCIADO)
        self.assertEqual(entrada.responsable_id, self.aprobador.id)
        self.assertIsNotNone(entrada.fecha)

    # AC-T3-56
    def test_denuncia_requiere_poliza_del_cliente_y_fecha_en_vigencia(self):
        otro_cliente = fabricas.crear_cliente()
        otro_poliza = fabricas.crear_poliza(otro_cliente)
        with self.assertRaises(DatosInvalidos):
            self._denunciar(poliza_id=otro_poliza.id)
        with self.assertRaises(DatosInvalidos):
            self._denunciar(
                fecha_ocurrencia=self.poliza.fecha_inicio - timedelta(days=1)
            )
        with self.assertRaises(DatosInvalidos):
            self._denunciar(fecha_ocurrencia=timezone.localdate() + timedelta(days=1))
        self.assertFalse(Siniestro.objects.exists())

    # AC-T3-56
    def test_registro_requiere_funcionario_activo_pero_no_aprobador(self):
        siniestro = self._denunciar(funcionario_id=self.operador.id)
        entrada = HistorialSiniestro.objects.get(siniestro=siniestro)
        self.assertEqual(entrada.responsable_id, self.operador.id)

        self.aprobador.activo = False
        self.aprobador.save(update_fields=["activo"])
        with self.assertRaises(PermisoDenegado):
            self._denunciar()
        self.assertEqual(Siniestro.objects.count(), 1)

    # AC-T3-56
    def test_transiciones_secuenciales_registran_motivo_responsable_y_fecha(self):
        siniestro = self._denunciar()
        siniestro = transicionar_siniestro(
            siniestro.id,
            estado=EstadoSiniestro.EN_EVALUACION,
            motivo="Inicia la revisión documental.",
            funcionario_id=self.aprobador.id,
        )
        siniestro = transicionar_siniestro(
            siniestro.id,
            estado=EstadoSiniestro.APROBADO,
            motivo="La documentación interna está completa.",
            funcionario_id=self.aprobador.id,
        )
        siniestro = transicionar_siniestro(
            siniestro.id,
            estado=EstadoSiniestro.CERRADO,
            motivo="Se cerró la gestión interna.",
            funcionario_id=self.aprobador.id,
        )

        self.assertEqual(siniestro.estado, EstadoSiniestro.CERRADO)
        historial = list(
            HistorialSiniestro.objects.filter(siniestro=siniestro).order_by("id")
        )
        self.assertEqual(
            [entrada.estado_nuevo for entrada in historial],
            [
                EstadoSiniestro.DENUNCIADO,
                EstadoSiniestro.EN_EVALUACION,
                EstadoSiniestro.APROBADO,
                EstadoSiniestro.CERRADO,
            ],
        )
        self.assertEqual(
            [entrada.responsable_id for entrada in historial],
            [self.aprobador.id] * 4,
        )
        self.assertTrue(all(entrada.motivo.strip() for entrada in historial))
        self.assertTrue(all(entrada.fecha for entrada in historial))

    # AC-T3-56
    def test_no_permite_saltar_estados_motivo_vacio_ni_cambiar_un_cerrado(self):
        siniestro = self._denunciar()
        with self.assertRaises(EstadoInvalido):
            transicionar_siniestro(
                siniestro.id,
                estado=EstadoSiniestro.APROBADO,
                motivo="Salto de estado.",
                funcionario_id=self.aprobador.id,
            )
        with self.assertRaises(DatosInvalidos):
            transicionar_siniestro(
                siniestro.id,
                estado=EstadoSiniestro.EN_EVALUACION,
                motivo="  ",
                funcionario_id=self.aprobador.id,
            )
        transicionar_siniestro(
            siniestro.id,
            estado=EstadoSiniestro.EN_EVALUACION,
            motivo="Comienza la evaluación.",
            funcionario_id=self.aprobador.id,
        )
        transicionar_siniestro(
            siniestro.id,
            estado=EstadoSiniestro.RECHAZADO,
            motivo="No cumple los criterios internos.",
            funcionario_id=self.aprobador.id,
        )
        siniestro = transicionar_siniestro(
            siniestro.id,
            estado=EstadoSiniestro.CERRADO,
            motivo="Se cierra la gestión.",
            funcionario_id=self.aprobador.id,
        )
        with self.assertRaises(EstadoInvalido):
            transicionar_siniestro(
                siniestro.id,
                estado=EstadoSiniestro.APROBADO,
                motivo="No se permite reabrir.",
                funcionario_id=self.aprobador.id,
            )

    # AC-T3-56
    def test_no_aprobador_no_puede_tomar_una_decision(self):
        siniestro = self._denunciar()
        with self.assertRaises(PermisoDenegado):
            transicionar_siniestro(
                siniestro.id,
                estado=EstadoSiniestro.EN_EVALUACION,
                motivo="Comienza la evaluación.",
                funcionario_id=self.operador.id,
            )

    # AC-T3-56
    def test_un_siniestro_inexistente_da_no_encontrado(self):
        with self.assertRaises(NoEncontrado):
            transicionar_siniestro(
                999999,
                estado=EstadoSiniestro.EN_EVALUACION,
                motivo="Comienza la evaluación.",
                funcionario_id=self.aprobador.id,
            )

    # AC-T3-56
    def test_base_rechaza_cambio_de_estado_sin_historial_y_edicion_del_historial(self):
        siniestro = self._denunciar()
        historial = HistorialSiniestro.objects.get(siniestro=siniestro)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                Siniestro.objects.filter(pk=siniestro.id).update(
                    estado=EstadoSiniestro.APROBADO
                )
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                HistorialSiniestro.objects.filter(pk=historial.id).update(
                    motivo="Alterado"
                )
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                HistorialSiniestro.objects.filter(pk=historial.id).delete()
