import re

from django.db import models as django_models
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from datos import models


TABLAS = (
    (models.Funcionario, "funcionarios"),
    (models.TipoSeguro, "tipos_seguro"),
    (models.TipoConsulta, "tipos_consulta"),
    (models.Cliente, "clientes"),
    (models.ContactoWhatsapp, "contactos_whatsapp"),
    (models.Poliza, "polizas"),
    (models.ConductorPoliza, "conductores_poliza"),
    (models.Cuota, "cuotas"),
    (models.Siniestro, "siniestros"),
    (models.Conversacion, "conversaciones"),
    (models.Mensaje, "mensajes"),
    (models.ConsultaBot, "consultas_bot"),
    (models.Alerta, "alertas"),
    (models.Derivacion, "derivaciones"),
    (models.AccionPendiente, "acciones_pendientes"),
)

VISTAS = (
    (models.VPolizaResumen, "v_polizas_resumen"),
    (models.VConsultaSupervision, "v_consultas_supervision"),
    (models.VBandejaConversacion, "v_bandeja_conversaciones"),
)

CHOICES_BD = (
    (models.Funcionario, "rol", models.Rol),
    (models.TipoConsulta, "politica", models.Politica),
    (models.Poliza, "cobertura", models.Cobertura),
    (models.Poliza, "estado", models.EstadoPoliza),
    (models.ConductorPoliza, "relacion", models.Relacion),
    (models.Cuota, "estado", models.EstadoCuota),
    (models.Siniestro, "estado", models.EstadoSiniestro),
    (models.Conversacion, "estado", models.EstadoConversacion),
    (models.Conversacion, "modo", models.ModoConversacion),
    (models.Mensaje, "direccion", models.Direccion),
    (models.Mensaje, "emisor", models.Emisor),
    (models.Mensaje, "estado_envio", models.EstadoEnvio),
    (models.ConsultaBot, "estado", models.EstadoConsulta),
    (models.Alerta, "tipo", models.TipoAlerta),
    (models.Alerta, "severidad", models.Severidad),
    (models.Alerta, "origen", models.OrigenAlerta),
    (models.Alerta, "estado", models.EstadoAlerta),
    (models.Derivacion, "prioridad", models.Prioridad),
    (models.AccionPendiente, "tipo_accion", models.TipoAccion),
    (models.AccionPendiente, "estado", models.EstadoAccion),
)


class ModelDefinitionTests(SimpleTestCase):
    # AC-T4-05
    def test_modelos_de_tabla_mapean_las_tablas_no_administradas(self):
        self.assertEqual(len(TABLAS), 15)
        for model, table in TABLAS:
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.db_table, table)
                self.assertFalse(model._meta.managed)
                self.assertIsNotNone(model._meta.pk)

        for model in (models.TipoSeguro, models.TipoConsulta):
            with self.subTest(model=model.__name__):
                self.assertIsInstance(model._meta.pk, django_models.SmallAutoField)

        relaciones = (
            (models.ContactoWhatsapp, "cliente", "contactos"),
            (models.Poliza, "cliente", "polizas"),
            (models.ConductorPoliza, "poliza", "conductores"),
            (models.Cuota, "poliza", "cuotas"),
            (models.Siniestro, "poliza", "siniestros"),
            (models.Conversacion, "contacto", "conversaciones"),
            (models.Conversacion, "funcionario", "+"),
            (models.Mensaje, "conversacion", "mensajes"),
            (models.Mensaje, "consulta", "mensajes"),
            (models.Mensaje, "funcionario", "+"),
            (models.ConsultaBot, "conversacion", "consultas"),
            (models.ConsultaBot, "funcionario_asignado", "+"),
            (models.ConsultaBot, "revisado_por", "+"),
            (models.Alerta, "consulta", "alertas"),
            (models.Alerta, "mensaje", "alertas"),
            (models.Alerta, "resuelta_por", "+"),
            (models.Derivacion, "derivado_a", "derivaciones"),
            (models.AccionPendiente, "consulta", "acciones"),
            (models.AccionPendiente, "resuelta_por", "+"),
        )
        for model, name, related_name in relaciones:
            with self.subTest(model=model.__name__, field=name):
                field = model._meta.get_field(name)
                self.assertIsInstance(field, django_models.ForeignKey)
                self.assertEqual(field.remote_field.related_name, related_name)
                self.assertIs(field.remote_field.on_delete, django_models.DO_NOTHING)

    # AC-T4-06
    def test_vistas_son_de_solo_lectura(self):
        for model, table in VISTAS:
            with self.subTest(model=model.__name__):
                self.assertEqual(model._meta.db_table, table)
                self.assertFalse(model._meta.managed)
                objeto = model()
                with self.assertRaisesRegex(TypeError, "^Es una vista de solo lectura$"):
                    objeto.save()
                with self.assertRaisesRegex(TypeError, "^Es una vista de solo lectura$"):
                    objeto.delete()

        self.assertEqual(models.VPolizaResumen._meta.pk.name, "poliza")
        self.assertIsInstance(
            models.VPolizaResumen._meta.pk, django_models.OneToOneField
        )
        self.assertEqual(models.VConsultaSupervision._meta.pk.name, "id")
        self.assertEqual(models.VBandejaConversacion._meta.pk.name, "conversacion_id")

    # AC-T4-09
    def test_campos_con_default_declarados_en_los_modelos(self):
        defaults = (
            (models.Funcionario, "puede_aprobar", False),
            (models.Funcionario, "activo", True),
            (models.Funcionario, "creado_en", timezone.now),
            (models.Cliente, "activo", True),
            (models.Cliente, "creado_en", timezone.now),
            (models.ContactoWhatsapp, "creado_en", timezone.now),
            (models.Poliza, "estado", models.EstadoPoliza.VIGENTE),
            (models.Poliza, "creado_en", timezone.now),
            (models.ConductorPoliza, "activo", True),
            (models.Cuota, "estado", models.EstadoCuota.PENDIENTE),
            (models.ConsultaBot, "estado", models.EstadoConsulta.PENDIENTE_REVISION),
            (models.ConsultaBot, "creado_en", timezone.now),
            (models.Alerta, "origen", models.OrigenAlerta.AUTOMATICA),
            (models.Alerta, "estado", models.EstadoAlerta.ABIERTA),
            (models.Alerta, "creada_en", timezone.now),
            (models.Derivacion, "prioridad", models.Prioridad.NORMAL),
            (models.Derivacion, "creada_en", timezone.now),
            (models.Siniestro, "estado", models.EstadoSiniestro.DENUNCIADO),
            (models.Siniestro, "creado_en", timezone.now),
            (models.AccionPendiente, "parametros", dict),
            (models.AccionPendiente, "estado", models.EstadoAccion.PENDIENTE),
            (models.AccionPendiente, "solicitada_en", timezone.now),
            (models.Conversacion, "estado", models.EstadoConversacion.ABIERTA),
            (models.Conversacion, "modo", models.ModoConversacion.BOT),
            (models.Conversacion, "creada_en", timezone.now),
            (models.Mensaje, "fecha_hora", timezone.now),
        )
        for model, name, expected in defaults:
            with self.subTest(model=model.__name__, field=name):
                self.assertIs(model._meta.get_field(name).default, expected)


class DatabaseModelTests(TestCase):
    # AC-T4-07
    def test_textchoices_coinciden_con_las_restricciones_check(self):
        for model, column, choice_class in CHOICES_BD:
            with self.subTest(table=model._meta.db_table, column=column):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT pg_get_constraintdef(oid)
                        FROM pg_constraint
                        WHERE conrelid = %s::regclass AND contype = 'c'
                        """,
                        [model._meta.db_table],
                    )
                    restricciones = [
                        definicion
                        for (definicion,) in cursor.fetchall()
                        if re.search(rf"\b{re.escape(column)}\b", definicion)
                        and all(
                            f"'{valor}'" in definicion
                            for valor in choice_class.values
                        )
                    ]

                self.assertEqual(len(restricciones), 1)
                valores_bd = re.findall(r"'([^']*)'", restricciones[0])
                self.assertCountEqual(valores_bd, choice_class.values)
                self.assertEqual(len(valores_bd), len(choice_class.values))

    # AC-T4-08
    def test_columnas_y_nulabilidad_coinciden_con_el_esquema(self):
        for model, table in TABLAS:
            with self.subTest(table=table):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT column_name, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = %s
                        """,
                        [table],
                    )
                    columnas = {
                        nombre: es_nullable == "YES"
                        for nombre, es_nullable in cursor.fetchall()
                    }

                campos = {field.column: field.null for field in model._meta.local_fields}
                self.assertEqual(set(campos), set(columnas))
                for columna, nullable in campos.items():
                    with self.subTest(table=table, column=columna):
                        self.assertEqual(nullable, columnas[columna])

    # AC-T4-09
    def test_defaults_modelo_coinciden_con_los_defaults_de_la_base(self):
        esperados = {
            ("funcionarios", "puede_aprobar"): False,
            ("funcionarios", "activo"): True,
            ("funcionarios", "creado_en"): timezone.now,
            ("clientes", "activo"): True,
            ("clientes", "creado_en"): timezone.now,
            ("contactos_whatsapp", "creado_en"): timezone.now,
            ("polizas", "estado"): models.EstadoPoliza.VIGENTE,
            ("polizas", "creado_en"): timezone.now,
            ("conductores_poliza", "activo"): True,
            ("cuotas", "estado"): models.EstadoCuota.PENDIENTE,
            ("consultas_bot", "estado"): models.EstadoConsulta.PENDIENTE_REVISION,
            ("consultas_bot", "creado_en"): timezone.now,
            ("alertas", "origen"): models.OrigenAlerta.AUTOMATICA,
            ("alertas", "estado"): models.EstadoAlerta.ABIERTA,
            ("alertas", "creada_en"): timezone.now,
            ("derivaciones", "prioridad"): models.Prioridad.NORMAL,
            ("derivaciones", "creada_en"): timezone.now,
            ("siniestros", "estado"): models.EstadoSiniestro.DENUNCIADO,
            ("siniestros", "creado_en"): timezone.now,
            ("acciones_pendientes", "parametros"): dict,
            ("acciones_pendientes", "estado"): models.EstadoAccion.PENDIENTE,
            ("acciones_pendientes", "solicitada_en"): timezone.now,
            ("conversaciones", "estado"): models.EstadoConversacion.ABIERTA,
            ("conversaciones", "modo"): models.ModoConversacion.BOT,
            ("conversaciones", "creada_en"): timezone.now,
            ("mensajes", "fecha_hora"): timezone.now,
        }

        for model, table in TABLAS:
            with self.subTest(table=table):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT column_name, column_default, is_identity
                        FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = %s
                        """,
                        [table],
                    )
                    defaults_bd = {
                        nombre
                        for nombre, default, identidad in cursor.fetchall()
                        if identidad == "NO" and default is not None
                    }

                fields = {
                    field.column: field
                    for field in model._meta.local_fields
                    if field.has_default()
                }
                self.assertEqual(set(fields), defaults_bd)
                for columna in defaults_bd:
                    with self.subTest(table=table, column=columna):
                        self.assertEqual(
                            fields[columna].default,
                            esperados[(table, columna)],
                        )
