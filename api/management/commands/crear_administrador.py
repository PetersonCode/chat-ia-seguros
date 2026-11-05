from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from datos.models import Funcionario, Rol


class Command(BaseCommand):
    help = (
        "Crea o actualiza el usuario con rol administrador (ELIMINACION TOTAL de chats). "
        "Sin --clave genera una y la muestra una sola vez."
    )

    def add_arguments(self, parser):
        parser.add_argument("--email", default="administrador@seguroscastano.example")
        parser.add_argument("--nombre", default="Administrador")
        parser.add_argument("--clave", default=None)

    @transaction.atomic
    def handle(self, *args, **opciones):
        email = opciones["email"].strip().lower()
        clave = opciones["clave"] or secrets.token_urlsafe(12)
        Funcionario.objects.update_or_create(
            email=email,
            defaults={
                "nombre": opciones["nombre"],
                "rol": Rol.ADMINISTRADOR,
                "puede_aprobar": True,
                "activo": True,
            },
        )
        usuario, _ = get_user_model().objects.update_or_create(
            username=email,
            defaults={"email": email, "first_name": opciones["nombre"], "is_active": True},
        )
        usuario.set_password(clave)
        usuario.save(update_fields=["password"])
        self.stdout.write(self.style.SUCCESS(f"Administrador listo: {email}"))
        if not opciones["clave"]:
            self.stdout.write(f"Clave generada: {clave}")
