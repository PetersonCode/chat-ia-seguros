from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from datos import fabricas
from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    ContactoWhatsapp,
    Conversacion,
    Cuota,
    Derivacion,
    Funcionario,
    Mensaje,
    Poliza,
    TipoConsulta,
    TipoSeguro,
)


class RunnerTests(TestCase):
    # AC-T4-10
    def test_schema_runner_usa_base_de_test_vacia(self):
        self.assertTrue(connection.settings_dict["NAME"].startswith("test_"))
        self.assertEqual(Funcionario.objects.count(), 0)
        self.assertEqual(TipoSeguro.objects.count(), 0)


class FabricasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fabricas.crear_catalogos()

    # AC-T4-11
    def test_catalogos_creados_con_politicas_del_seed_sin_duplicados(self):
        seguros_esperados = {
            ("automotor", "Automotor"),
            ("hogar", "Hogar"),
            ("vida", "Vida"),
            ("comercio", "Comercio"),
            ("moto", "Moto"),
        }
        consultas_esperadas = {
            ("saludo", "Saludo", "bot_responde"),
            ("saldo", "Saldo pendiente", "bot_responde"),
            ("vencimiento", "Vencimiento de póliza", "bot_responde"),
            ("siniestro", "Denuncia de siniestro", "bot_responde"),
            ("siniestro_urgente", "Siniestro urgente", "derivar_humano"),
            ("cotizacion", "Cotización", "derivar_humano"),
            ("consulta_cobertura", "Consulta de cobertura", "derivar_humano"),
            ("reclamo", "Reclamo", "derivar_humano"),
            ("baja", "Baja de póliza", "requiere_aprobacion"),
            ("modificacion", "Modificación de póliza", "requiere_aprobacion"),
            ("prompt_injection", "Intento de manipulación del bot", "seguridad"),
            ("otro", "Otra consulta", "derivar_humano"),
        }

        fabricas.crear_catalogos()
        self.assertEqual(
            set(TipoSeguro.objects.values_list("codigo", "nombre")),
            seguros_esperados,
        )
        self.assertEqual(
            set(
                TipoConsulta.objects.values_list(
                    "codigo", "nombre", "politica"
                )
            ),
            consultas_esperadas,
        )
        self.assertEqual(TipoSeguro.objects.count(), 5)
        self.assertEqual(TipoConsulta.objects.count(), 12)

    # AC-T4-11
    def test_fabricas_crean_registros_validos_con_defaults_unicos(self):
        funcionario = fabricas.crear_funcionario()
        segundo_funcionario = fabricas.crear_funcionario()
        usuario = get_user_model().objects.get(email=funcionario.email)
        self.assertEqual(usuario.email, funcionario.email)
        self.assertNotEqual(funcionario.email, segundo_funcionario.email)

        cliente = fabricas.crear_cliente()
        otro_cliente = fabricas.crear_cliente()
        contacto = fabricas.crear_contacto(cliente=cliente)
        otro_contacto = fabricas.crear_contacto()
        poliza = fabricas.crear_poliza(cliente=cliente)
        otra_poliza = fabricas.crear_poliza(cliente=otro_cliente)
        cuota = fabricas.crear_cuota(poliza)
        otra_cuota = fabricas.crear_cuota(otra_poliza)
        conversacion = fabricas.crear_conversacion(contacto)
        otra_conversacion = fabricas.crear_conversacion(otro_contacto)
        mensaje = fabricas.crear_mensaje(conversacion)
        otro_mensaje = fabricas.crear_mensaje(otra_conversacion)
        consulta = fabricas.crear_consulta(conversacion)
        otra_consulta = fabricas.crear_consulta(otra_conversacion)
        alerta = fabricas.crear_alerta(consulta)
        otra_alerta = fabricas.crear_alerta(otra_consulta)
        accion = fabricas.crear_accion(consulta)
        otra_accion = fabricas.crear_accion(otra_consulta)
        derivacion = fabricas.crear_derivacion(consulta, funcionario)
        otra_derivacion = fabricas.crear_derivacion(otra_consulta, segundo_funcionario)

        self.assertNotEqual(cliente.dni, otro_cliente.dni)
        self.assertNotEqual(contacto.numero, otro_contacto.numero)
        self.assertNotEqual(poliza.numero_poliza, otra_poliza.numero_poliza)
        self.assertNotEqual(cuota.periodo, otra_cuota.periodo)
        self.assertNotEqual(mensaje.wa_message_id, otro_mensaje.wa_message_id)
        self.assertNotEqual(consulta.codigo_caso, otra_consulta.codigo_caso)
        self.assertNotEqual(alerta.pk, otra_alerta.pk)
        self.assertNotEqual(accion.pk, otra_accion.pk)
        self.assertNotEqual(derivacion.pk, otra_derivacion.pk)

        self.assertEqual(poliza.tipo_seguro.codigo, "automotor")
        self.assertEqual(poliza.estado, "vigente")
        self.assertEqual(cuota.estado, "pendiente")
        self.assertEqual(conversacion.estado, "abierta")
        self.assertEqual(conversacion.modo, "bot")
        self.assertEqual(mensaje.direccion, "entrante")
        self.assertEqual(mensaje.emisor, "cliente")
        self.assertEqual(mensaje.estado_envio, "recibido")
        self.assertEqual(alerta.tipo, "dato_inventado")
        self.assertEqual(alerta.severidad, "alta")
        self.assertEqual(alerta.estado, "abierta")
        self.assertEqual(accion.tipo_accion, "baja_poliza")
        self.assertEqual(accion.estado, "pendiente")
        self.assertEqual(derivacion.derivado_a, funcionario)

        self.assertTrue(
            all(
                objeto.pk is not None
                for objeto in (
                    cliente,
                    otro_cliente,
                    contacto,
                    otro_contacto,
                    poliza,
                    otra_poliza,
                    cuota,
                    otra_cuota,
                    conversacion,
                    otra_conversacion,
                    mensaje,
                    otro_mensaje,
                    consulta,
                    otra_consulta,
                    alerta,
                    otra_alerta,
                    accion,
                    otra_accion,
                    derivacion,
                    otra_derivacion,
                )
            )
        )

        self.assertEqual(Cliente.objects.count(), 2)
        self.assertEqual(ContactoWhatsapp.objects.count(), 2)
        self.assertEqual(Poliza.objects.count(), 2)
        self.assertEqual(Cuota.objects.count(), 2)
        self.assertEqual(Conversacion.objects.count(), 2)
        self.assertEqual(Mensaje.objects.count(), 2)
        self.assertEqual(Alerta.objects.count(), 2)
        self.assertEqual(AccionPendiente.objects.count(), 2)
        self.assertEqual(Derivacion.objects.count(), 2)

    # AC-T4-09
    def test_fabricas_solo_requieren_los_campos_sin_default(self):
        funcionario = fabricas.crear_funcionario()
        cliente = fabricas.crear_cliente()
        contacto = fabricas.crear_contacto()
        poliza = fabricas.crear_poliza()
        cuota = fabricas.crear_cuota(poliza)
        conversacion = fabricas.crear_conversacion()
        mensaje = fabricas.crear_mensaje(conversacion)
        consulta = fabricas.crear_consulta()
        alerta = fabricas.crear_alerta(consulta)
        accion = fabricas.crear_accion(consulta)
        derivacion = fabricas.crear_derivacion(consulta, funcionario)

        self.assertTrue(
            all(
                objeto.pk is not None
                for objeto in (
                    funcionario,
                    cliente,
                    contacto,
                    poliza,
                    cuota,
                    conversacion,
                    mensaje,
                    consulta,
                    alerta,
                    accion,
                    derivacion,
                )
            )
        )
