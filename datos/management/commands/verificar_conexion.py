from django.core.management.base import BaseCommand
from django.db import connection, transaction

from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    ContactoWhatsapp,
    ConductorPoliza,
    Conversacion,
    ConsultaBot,
    Cuota,
    Derivacion,
    Funcionario,
    Mensaje,
    Poliza,
    Siniestro,
    TipoConsulta,
    TipoSeguro,
)

_MODELOS_TABLAS = (
    Funcionario,
    TipoSeguro,
    TipoConsulta,
    Cliente,
    ContactoWhatsapp,
    Poliza,
    ConductorPoliza,
    Cuota,
    Siniestro,
    Conversacion,
    Mensaje,
    ConsultaBot,
    Alerta,
    Derivacion,
    AccionPendiente,
)


class Command(BaseCommand):
    help = "Verifica la conexión y cuenta filas sin modificar la base."

    def handle(self, **options):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                self.stdout.write(version)

                for model in _MODELOS_TABLAS:
                    tabla = connection.ops.quote_name(model._meta.db_table)
                    cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
                    cantidad = cursor.fetchone()[0]
                    self.stdout.write(f"{model._meta.db_table}: {cantidad}")
