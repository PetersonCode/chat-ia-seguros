from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from datos.models import Funcionario


class Command(BaseCommand):
    help = "Crea o actualiza usuarios Django para los funcionarios activos."

    def add_arguments(self, parser):
        parser.add_argument("--clave", dest="clave", required=True, help="Clave para todos los usuarios creados/actualizados.")

    def handle(self, *args, **options):
        clave = options["clave"]
        if not clave:
            raise CommandError("La opción --clave es obligatoria.")
        User = get_user_model()
        total = 0
        for funcionario in Funcionario.objects.filter(activo=True).order_by("id"):
            usuario, _ = User.objects.update_or_create(
                username=funcionario.email,
                defaults={
                    "email": funcionario.email,
                    "first_name": funcionario.nombre,
                    "is_active": True,
                },
            )
            usuario.set_password(clave)
            usuario.save(update_fields=["email", "first_name", "password", "is_active"])
            total += 1
        self.stdout.write(self.style.SUCCESS(f"Usuarios sincronizados: {total}"))
