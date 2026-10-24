"""Administración de usuarios del panel. Solo la usa el propietario (Roberto).

Un usuario son dos filas que tienen que andar juntas: el `Funcionario` (rol,
permiso de aprobación, si está activo) y el `User` de Django con el que inicia
sesión, enlazados por el email (`sesion.funcionario_de`).

Reglas:

- Nadie se crea ni se convierte en `propietario` desde acá. Esta sección es
  del propietario; si pudiera nombrar otro, la sección dejaría de ser solo suya.
- Al propietario no se lo modifica ni se lo desactiva desde acá: un clic de
  más dejaría a la empresa sin nadie que pueda administrar usuarios.
- No se borra a nadie. El funcionario aparece en derivaciones, mensajes y
  acciones ya resueltas; se lo desactiva y no puede volver a entrar.
- El email es la identidad y no se cambia: es el usuario de inicio de sesión.
"""

from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from datos.models import Funcionario, Rol
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado

ROLES_ASIGNABLES = (Rol.ADMINISTRACION, Rol.OPERADOR)

RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def listar_usuarios():
    return Funcionario.objects.order_by("-activo", "nombre", "id")


def _usuario(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id).first()
    if funcionario is None:
        raise NoEncontrado("El usuario no existe.")
    return funcionario


def _nombre_valido(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise DatosInvalidos("El nombre es obligatorio.")
    return nombre


def _rol_valido(rol: str) -> str:
    if rol == Rol.PROPIETARIO:
        raise DatosInvalidos("No se puede asignar el rol de propietario.")
    if rol not in ROLES_ASIGNABLES:
        raise DatosInvalidos("Rol inválido.")
    return rol


def _clave_valida(clave: str, user=None) -> str:
    if not clave:
        raise DatosInvalidos("La contraseña es obligatoria.")
    try:
        validate_password(clave, user=user)
    except ValidationError as exc:
        raise DatosInvalidos(" ".join(exc.messages)) from exc
    return clave


def _no_es_propietario(funcionario: Funcionario) -> None:
    if funcionario.rol == Rol.PROPIETARIO:
        raise EstadoInvalido("El propietario no se puede modificar desde esta sección.")


def crear_usuario(
    *, nombre: str, email: str, rol: str, clave: str, puede_aprobar: bool = False
) -> Funcionario:
    nombre = _nombre_valido(nombre)
    email = (email or "").strip().lower()
    if not RE_EMAIL.match(email):
        raise DatosInvalidos("El correo no es válido.")
    rol = _rol_valido(rol)
    User = get_user_model()
    if (
        Funcionario.objects.filter(email__iexact=email).exists()
        or User.objects.filter(username__iexact=email).exists()
    ):
        raise DatosInvalidos("Ya existe un usuario con ese correo.")
    _clave_valida(clave, User(username=email, email=email, first_name=nombre))

    with transaction.atomic():
        funcionario = Funcionario.objects.create(
            nombre=nombre,
            email=email,
            rol=rol,
            puede_aprobar=bool(puede_aprobar),
            activo=True,
        )
        User.objects.create_user(
            username=email, email=email, password=clave, first_name=nombre
        )
    return funcionario


def modificar_usuario(
    funcionario_id: int,
    *,
    nombre: str | None = None,
    rol: str | None = None,
    puede_aprobar: bool | None = None,
    activo: bool | None = None,
) -> Funcionario:
    """Actualiza solo lo que venga. Desactivar también cierra el inicio de sesión."""
    funcionario = _usuario(funcionario_id)
    _no_es_propietario(funcionario)

    campos: list[str] = []
    if nombre is not None:
        funcionario.nombre = _nombre_valido(nombre)
        campos.append("nombre")
    if rol is not None:
        funcionario.rol = _rol_valido(rol)
        campos.append("rol")
    if puede_aprobar is not None:
        funcionario.puede_aprobar = bool(puede_aprobar)
        campos.append("puede_aprobar")
    if activo is not None:
        funcionario.activo = bool(activo)
        campos.append("activo")
    if not campos:
        return funcionario

    with transaction.atomic():
        funcionario.save(update_fields=campos)
        user = get_user_model().objects.filter(username__iexact=funcionario.email).first()
        if user is not None:
            user.first_name = funcionario.nombre
            user.is_active = funcionario.activo
            user.save(update_fields=["first_name", "is_active"])
    return funcionario


def cambiar_clave(funcionario_id: int, clave: str) -> Funcionario:
    """Pone una contraseña nueva. Si el usuario de Django no existía, lo crea."""
    funcionario = _usuario(funcionario_id)
    _no_es_propietario(funcionario)
    User = get_user_model()
    user = User.objects.filter(username__iexact=funcionario.email).first()
    if user is None:
        user = User(
            username=funcionario.email,
            email=funcionario.email,
            first_name=funcionario.nombre,
            is_active=funcionario.activo,
        )
    _clave_valida(clave, user)
    user.set_password(clave)
    user.save()
    return funcionario
