"""Arnés de conexiones: unidades con TestCase e integración con commits reales."""
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase


def conservar_conexion_del_test(caso):
    # TestCase envuelve todo en una transacción. Un worker de producción vive
    # fuera de ella; sus cierres se verifican aparte en PruebaConTransacciones.
    for nombre in (
        "negocio.management.commands.reprocesar_pendientes.close_old_connections",
        "negocio.bot.orquestador.close_old_connections",
    ):
        parche = patch(nombre)
        parche.start()
        caso.addCleanup(parche.stop)


class PruebaConTransacciones(TransactionTestCase):
    def _fixture_teardown(self):
        # Django no limpia las tablas managed=False por sí solo. Esta base
        # siempre la crea el runner de tests; nunca se aplica a una base real.
        assert connection.settings_dict["NAME"] == connection.settings_dict["TEST"]["NAME"]
        with connection.cursor() as cursor:
            tablas = [t for t in connection.introspection.table_names(cursor) if t != "django_migrations"]
            cursor.execute("TRUNCATE " + ", ".join(connection.ops.quote_name(t) for t in tablas) + " RESTART IDENTITY CASCADE")
        super()._fixture_teardown()
