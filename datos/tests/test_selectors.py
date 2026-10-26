from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from datos import fabricas, selectors
from datos.models import (
    AccionPendiente,
    Alerta,
    EstadoAccion,
    EstadoAlerta,
    EstadoConversacion,
    EstadoCuota,
    EstadoEnvio,
    EstadoPoliza,
    Siniestro,
    TipoAlerta,
    TipoConsulta,
)


class SelectorsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fabricas.crear_catalogos()

    # AC-T4-12
    def test_consultas_de_identidad(self):
        funcionario = fabricas.crear_funcionario(
            nombre="Roberto",
            email="roberto@example.test",
        )
        inactivo = fabricas.crear_funcionario(
            nombre="Inactivo",
            email="inactivo@example.test",
            activo=False,
        )
        cliente = fabricas.crear_cliente(dni="28111222")
        contacto = fabricas.crear_contacto(
            cliente=cliente,
            numero="+5491155551001",
        )
        conversacion = fabricas.crear_conversacion(contacto)
        poliza = fabricas.crear_poliza(
            cliente=cliente,
            numero_poliza="POL-10001",
        )
        siniestro = Siniestro.objects.create(
            numero_siniestro="SIN-2025-10001",
            poliza=poliza,
            fecha_ocurrencia=date(2025, 1, 2),
            descripcion="Choque de prueba",
        )

        self.assertEqual(
            selectors.funcionario_por_email("ROBERTO@EXAMPLE.TEST"),
            funcionario,
        )
        self.assertIsNone(selectors.funcionario_por_email(inactivo.email))
        self.assertIsNone(selectors.funcionario_por_nombre(inactivo.nombre))
        self.assertEqual(selectors.funcionario_por_nombre(" R o b e r t o "), funcionario)
        self.assertEqual(selectors.cliente_por_dni(cliente.dni), cliente)
        self.assertIsNone(selectors.cliente_por_dni("00000000"))
        self.assertEqual(selectors.contacto_por_numero(contacto.numero), contacto)
        self.assertEqual(
            selectors.conversacion_abierta(contacto.pk),
            conversacion,
        )
        self.assertEqual(selectors.poliza_por_numero(poliza.numero_poliza), poliza)
        self.assertEqual(
            selectors.siniestro_por_numero(siniestro.numero_siniestro),
            siniestro,
        )
        self.assertEqual(
            selectors.tipo_consulta("saludo"),
            TipoConsulta.objects.get(codigo="saludo"),
        )
        with self.assertRaises(TipoConsulta.DoesNotExist):
            selectors.tipo_consulta("no-existe")

    # AC-T4-13
    def test_mensajes_ordenados_filtrados_y_historial_limitado(self):
        conversacion = fabricas.crear_conversacion()
        base = timezone.now()
        mensaje_mas_reciente = fabricas.crear_mensaje(
            conversacion,
            fecha_hora=base + timedelta(minutes=2),
        )
        mensaje_mas_antiguo = fabricas.crear_mensaje(
            conversacion,
            fecha_hora=base,
        )
        mensaje_intermedio = fabricas.crear_mensaje(
            conversacion,
            fecha_hora=base + timedelta(minutes=1),
        )

        self.assertEqual(
            list(selectors.mensajes_de(conversacion.pk)),
            [mensaje_mas_antiguo, mensaje_intermedio, mensaje_mas_reciente],
        )
        # `despues_de` filtra por id, no por fecha: los mensajes se crearon
        # desordenados, asi que el unico id mayor es el del intermedio.
        self.assertEqual(
            list(
                selectors.mensajes_de(
                    conversacion.pk,
                    despues_de=mensaje_mas_antiguo.pk,
                )
            ),
            [mensaje_intermedio],
        )
        self.assertEqual(
            selectors.historial_reciente(conversacion.pk, limite=2),
            [mensaje_intermedio, mensaje_mas_reciente],
        )
        self.assertEqual(selectors.historial_reciente(conversacion.pk, limite=0), [])

    # AC-T4-14
    def test_polizas_vigentes_y_resumen_de_cuotas(self):
        cliente = fabricas.crear_cliente()
        vigente = fabricas.crear_poliza(cliente=cliente)
        fabricas.crear_poliza(
            cliente=cliente,
            estado=EstadoPoliza.VENCIDA,
        )
        fabricas.crear_poliza(
            cliente=cliente,
            estado=EstadoPoliza.DADA_DE_BAJA,
        )
        fabricas.crear_cuota(
            vigente,
            periodo=date(2025, 1, 1),
            vencimiento=date(2025, 1, 15),
            importe=Decimal("1000.00"),
            estado=EstadoCuota.PENDIENTE,
        )
        fabricas.crear_cuota(
            vigente,
            periodo=date(2025, 2, 1),
            vencimiento=date(2025, 2, 15),
            importe=Decimal("1500.00"),
            estado=EstadoCuota.VENCIDA,
        )
        fabricas.crear_cuota(
            vigente,
            periodo=date(2025, 3, 1),
            vencimiento=date(2025, 3, 15),
            importe=Decimal("700.00"),
            estado=EstadoCuota.PAGADA,
            fecha_pago=date(2025, 3, 10),
            importe_pagado=Decimal("700.00"),
        )

        self.assertEqual(
            list(selectors.polizas_vigentes(cliente.pk)),
            [vigente],
        )
        resumen = selectors.resumen_polizas(cliente.pk).get(poliza_id=vigente.pk)
        self.assertEqual(resumen.saldo_pendiente, Decimal("2500.00"))
        self.assertEqual(resumen.proximo_vencimiento_pago, date(2025, 1, 15))

    # AC-T4-15
    def test_alertas_abiertas_filtradas_por_consulta_conversacion_y_mensaje(self):
        conversacion = fabricas.crear_conversacion()
        consulta = fabricas.crear_consulta(conversacion)
        mensaje = fabricas.crear_mensaje(conversacion)
        alerta = fabricas.crear_alerta(
            consulta,
            mensaje=mensaje,
            estado=EstadoAlerta.ABIERTA,
        )
        en_revision = fabricas.crear_alerta(
            consulta,
            estado=EstadoAlerta.EN_REVISION,
        )
        resolvedor = fabricas.crear_funcionario()
        fabricas.crear_alerta(
            consulta,
            estado=EstadoAlerta.RESUELTA,
            resuelta_por=resolvedor,
            resuelta_en=timezone.now(),
        )
        otra_conversacion = fabricas.crear_conversacion()
        otra_consulta = fabricas.crear_consulta(otra_conversacion)
        otra_alerta = fabricas.crear_alerta(otra_consulta)

        self.assertCountEqual(
            selectors.alertas_abiertas(consulta_id=consulta.pk),
            [alerta, en_revision],
        )
        self.assertCountEqual(
            selectors.alertas_abiertas(conversacion_id=conversacion.pk),
            [alerta, en_revision],
        )
        self.assertEqual(
            list(selectors.alertas_abiertas(mensaje_id=mensaje.pk)),
            [alerta],
        )
        self.assertCountEqual(
            selectors.alertas_abiertas(),
            [alerta, en_revision, otra_alerta],
        )

    # AC-T4-16
    def test_bandeja_anotaciones_filtros_y_orden(self):
        cliente = fabricas.crear_cliente(apellido="Fernández", nombre="Laura")
        contacto = fabricas.crear_contacto(
            cliente=cliente,
            numero="+5491155551999",
        )
        retenida = fabricas.crear_conversacion(contacto)
        consulta_retenida = fabricas.crear_consulta(retenida)
        fabricas.crear_mensaje(
            retenida,
            direccion="saliente",
            emisor="bot",
            estado_envio=EstadoEnvio.RETENIDO,
            texto="Respuesta retenida",
            fecha_hora=timezone.now() - timedelta(days=1),
        )

        critica = fabricas.crear_conversacion()
        consulta_critica = fabricas.crear_consulta(critica)
        fabricas.crear_alerta(
            consulta_critica,
            tipo=TipoAlerta.DATO_INCONSISTENTE,
            severidad="critica",
        )
        mensaje_critico = fabricas.crear_mensaje(
            critica,
            fecha_hora=timezone.now(),
        )

        normal = fabricas.crear_conversacion()
        consulta_normal = fabricas.crear_consulta(normal)
        mensaje_normal = fabricas.crear_mensaje(
            normal,
            fecha_hora=timezone.now() + timedelta(minutes=1),
        )

        humana = fabricas.crear_conversacion(
            modo="humano",
            funcionario=fabricas.crear_funcionario(),
        )
        cerrada = fabricas.crear_conversacion(
            estado=EstadoConversacion.CERRADA,
            cerrada_en=timezone.now(),
        )

        bandeja = list(selectors.bandeja())
        self.assertEqual(bandeja[0], critica)
        self.assertEqual(bandeja[1], retenida)
        by_id = {conversacion.pk: conversacion for conversacion in bandeja}
        self.assertEqual(by_id[critica.pk].alertas_abiertas, 1)
        self.assertEqual(by_id[critica.pk].severidad_rango, 4)
        self.assertEqual(by_id[critica.pk].retenidas, 0)
        self.assertEqual(by_id[critica.pk].ultimo_texto, mensaje_critico.texto)
        self.assertEqual(by_id[critica.pk].ultimo_emisor, mensaje_critico.emisor)
        self.assertEqual(
            by_id[critica.pk].ultimo_fecha_hora,
            mensaje_critico.fecha_hora,
        )
        self.assertEqual(by_id[retenida.pk].alertas_abiertas, 0)
        self.assertEqual(by_id[retenida.pk].retenidas, 1)
        self.assertEqual(by_id[normal.pk].ultimo_texto, mensaje_normal.texto)
        self.assertEqual(
            set(selectors.bandeja(con_alertas=True)),
            {critica},
        )
        self.assertEqual(
            set(selectors.bandeja(esperando_humano=True)),
            {humana},
        )
        self.assertEqual(
            set(selectors.bandeja(estado=EstadoConversacion.CERRADA)),
            {cerrada},
        )
        self.assertEqual(
            set(selectors.bandeja(q="FERNÁNDEZ")),
            {retenida},
        )
        self.assertEqual(
            set(selectors.bandeja(q="+5491155551999")),
            {retenida},
        )
        self.assertEqual(consulta_retenida.conversacion_id, retenida.pk)
        self.assertEqual(consulta_normal.conversacion_id, normal.pk)

    # AC-T4-17
    def test_listar_alertas_y_consultas_cerradas_con_alertas(self):
        conversacion = fabricas.crear_conversacion()
        consulta_cerrada = fabricas.crear_consulta(
            conversacion,
            estado="cerrado",
        )
        critica_abierta = fabricas.crear_alerta(
            consulta_cerrada,
            tipo=TipoAlerta.PROMPT_INJECTION,
            severidad="critica",
        )
        fabricas.crear_alerta(
            consulta_cerrada,
            severidad="baja",
            estado=EstadoAlerta.EN_REVISION,
        )
        fabricas.crear_alerta(
            consulta_cerrada,
            severidad="critica",
            estado=EstadoAlerta.RESUELTA,
            resuelta_por=fabricas.crear_funcionario(),
            resuelta_en=timezone.now(),
        )
        otra_consulta = fabricas.crear_consulta(
            fabricas.crear_conversacion(),
            estado="abierto",
        )
        fabricas.crear_alerta(
            otra_consulta,
            severidad="critica",
        )

        self.assertEqual(
            list(
                selectors.listar_alertas(
                    tipo=TipoAlerta.PROMPT_INJECTION,
                    severidad="critica",
                    estado=EstadoAlerta.ABIERTA,
                )
            ),
            [critica_abierta],
        )
        self.assertEqual(
            list(selectors.listar_alertas(estado=None)),
            list(Alerta.objects.order_by("-creada_en", "-id")),
        )
        self.assertEqual(
            list(selectors.consultas_cerradas_con_alertas()),
            [consulta_cerrada],
        )

    # AC-T4-18
    def test_acciones_pendientes_y_derivaciones_priorizadas(self):
        funcionario = fabricas.crear_funcionario()
        consulta = fabricas.crear_consulta()
        primera_accion = fabricas.crear_accion(
            consulta,
            solicitada_en=timezone.now() - timedelta(days=2),
        )
        segunda_accion = fabricas.crear_accion(
            consulta,
            solicitada_en=timezone.now() - timedelta(days=1),
        )
        # La base exige que toda accion nazca `pendiente` y recien despues
        # pase a resuelta (trigger acciones_pendientes_control).
        resuelta = fabricas.crear_accion(consulta)
        resuelta.estado = EstadoAccion.APROBADA
        resuelta.resuelta_por = funcionario
        resuelta.resuelta_en = timezone.now()
        resuelta.save()
        self.assertEqual(
            list(selectors.listar_acciones()),
            [primera_accion, segunda_accion],
        )
        self.assertEqual(
            list(selectors.listar_acciones(estado=None)),
            list(
                AccionPendiente.objects.order_by("solicitada_en", "id")
            ),
        )

        urgente = fabricas.crear_derivacion(
            consulta,
            funcionario,
            prioridad="urgente",
        )
        normal = fabricas.crear_derivacion(consulta, funcionario)
        atendida = fabricas.crear_derivacion(
            consulta,
            funcionario,
            prioridad="urgente",
            atendida_en=timezone.now(),
        )
        ajena = fabricas.crear_derivacion(
            consulta,
            fabricas.crear_funcionario(),
            prioridad="urgente",
        )
        self.assertEqual(
            list(selectors.derivaciones_de(funcionario.pk)),
            [urgente, normal],
        )
        self.assertEqual(
            list(
                selectors.derivaciones_de(
                    funcionario.pk,
                    incluir_atendidas=True,
                )
            ),
            [urgente, atendida, normal],
        )
        self.assertNotIn(ajena, selectors.derivaciones_de(funcionario.pk))

    # AC-T4-19
    def test_busqueda_y_detalles_cargan_relaciones_en_hasta_cinco_consultas(self):
        cliente = fabricas.crear_cliente(
            dni="28111222",
            nombre="Laura",
            apellido="Fernández",
        )
        contacto = fabricas.crear_contacto(cliente)
        poliza = fabricas.crear_poliza(cliente)
        fabricas.crear_cuota(poliza)
        fabricas.crear_conversacion(contacto)
        consulta = fabricas.crear_consulta()
        Siniestro.objects.create(
            numero_siniestro="SIN-2025-10002",
            poliza=poliza,
            consulta=consulta,
            fecha_ocurrencia=date(2025, 1, 2),
            descripcion="Siniestro de prueba",
        )

        por_dni = selectors.buscar_clientes("28.111.222").get()
        por_nombre = selectors.buscar_clientes("fernández").get()
        self.assertEqual(por_dni, cliente)
        self.assertEqual(por_nombre, cliente)
        self.assertEqual(por_dni.polizas_vigentes, 1)

        with self.assertNumQueries(4):
            detalle = selectors.detalle_cliente(cliente.pk)
            contactos = list(detalle.contactos.all())
            polizas = list(detalle.polizas.all())
            siniestros = [
                siniestro
                for poliza_detalle in polizas
                for siniestro in poliza_detalle.siniestros.all()
            ]
            tipos = [poliza_detalle.tipo_seguro for poliza_detalle in polizas]
        self.assertEqual(contactos, [contacto])
        self.assertEqual(len(siniestros), 1)
        self.assertEqual(len(tipos), 1)

        with self.assertNumQueries(4):
            detalle = selectors.detalle_poliza(poliza.pk)
            cuotas = list(detalle.cuotas.all())
            conductores = list(detalle.conductores.all())
            siniestros = list(detalle.siniestros.all())
            cliente_detalle = detalle.cliente
            tipo_seguro = detalle.tipo_seguro
        self.assertEqual(len(cuotas), 1)
        self.assertEqual(conductores, [])
        self.assertEqual(len(siniestros), 1)
        self.assertEqual(cliente_detalle, cliente)
        self.assertEqual(tipo_seguro.codigo, "automotor")

    # AC-T4-20
    def test_contar_pendientes_separa_acciones_derivaciones_y_alertas_criticas(self):
        funcionario = fabricas.crear_funcionario()
        otro_funcionario = fabricas.crear_funcionario()
        consulta = fabricas.crear_consulta()
        for _ in range(2):
            fabricas.crear_accion(consulta)
        fabricas.crear_derivacion(consulta, funcionario)
        fabricas.crear_derivacion(consulta, otro_funcionario)
        for _ in range(3):
            fabricas.crear_alerta(consulta, severidad="critica")
        fabricas.crear_alerta(
            consulta,
            severidad="critica",
            estado=EstadoAlerta.RESUELTA,
            resuelta_por=funcionario,
            resuelta_en=timezone.now(),
        )

        self.assertEqual(
            selectors.contar_pendientes(funcionario.pk),
            {"acciones": 2, "derivaciones": 1, "alertas_criticas": 3},
        )
