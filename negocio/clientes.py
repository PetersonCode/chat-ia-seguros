"""Alta, modificación y baja de clientes desde el panel (ABM manual).

Acá no hay automatismos: todo lo dispara una persona desde la página. Lo único
que este módulo agrega sobre un `save()` son las validaciones, y la razón es que
la cartera de clientes es la fuente de verdad de la que el bot saca saldos y
vencimientos (R12). Un DNI repetido o un teléfono mal cargado no quedan en un
listado feo: se convierten en una respuesta equivocada a un cliente real, o en
que el bot no reconozca a alguien que sí es cliente y lo derive sin necesidad.

La baja es lógica (`activo = False`). Borrar la fila no es una opción: las
pólizas, los contactos, las conversaciones y los siniestros apuntan al cliente,
y una aseguradora necesita conservar ese historial.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from datos.limpieza import normalizar_dni, normalizar_telefono
from datos.models import Cliente, ContactoWhatsapp, EstadoPoliza, Poliza
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado

# Un nombre con dígitos es casi siempre un error de carga (un DNI pegado en el
# campo equivocado, un número de póliza). No se intenta adivinar: se rechaza.
_TIENE_DIGITOS = re.compile(r"\d")

# Centinela para distinguir "no mandaron el campo" de "lo mandaron vacío", que
# en el email significan cosas distintas: dejarlo como está, o borrarlo.
SIN_CAMBIO = object()


def _cliente(cliente_id: int) -> Cliente:
    cliente = Cliente.objects.filter(pk=cliente_id).first()
    if cliente is None:
        raise NoEncontrado("El cliente no existe.")
    return cliente


def _nombre_validado(valor: str, campo: str) -> str:
    texto = (valor or "").strip()
    if not texto:
        raise DatosInvalidos(f"El {campo} es obligatorio.")
    if _TIENE_DIGITOS.search(texto):
        raise DatosInvalidos(f"El {campo} no puede contener números.")
    return texto


def _dni_validado(valor: str, excluir_id: int | None = None) -> str:
    try:
        dni = normalizar_dni(valor or "")
    except ValueError as error:
        raise DatosInvalidos(str(error)) from error
    repetidos = Cliente.objects.filter(dni=dni)
    if excluir_id is not None:
        repetidos = repetidos.exclude(pk=excluir_id)
    if repetidos.exists():
        raise DatosInvalidos(f"Ya existe un cliente con el DNI {dni}.")
    return dni


def _numero_validado(valor: str) -> str:
    try:
        return normalizar_telefono(valor or "")
    except ValueError as error:
        raise DatosInvalidos(str(error)) from error


def _contacto_libre(numero: str, cliente_id: int | None = None) -> ContactoWhatsapp | None:
    """La fila que ya tiene ese número, si se puede usar. Lanza si es de otro.

    Un número puede existir sin cliente: lo crea `registrar_entrante` cuando
    alguien desconocido le escribe al bot. Ese contacto **se adopta**, no se
    rechaza: es el caso del prospecto que después se da de alta como cliente, y
    reusarlo conserva la conversación previa en vez de duplicar el número.
    """
    contacto = ContactoWhatsapp.objects.filter(numero=numero).first()
    if contacto is None:
        return None
    if contacto.cliente_id not in (None, cliente_id):
        raise DatosInvalidos(f"El teléfono {numero} ya pertenece a otro cliente.")
    return contacto


def _email_validado(valor: str | None) -> str | None:
    """Vacío se guarda como `NULL`, nunca como cadena vacía."""
    texto = (valor or "").strip()
    if not texto:
        return None
    try:
        validate_email(texto)
    except ValidationError as error:
        raise DatosInvalidos("El email no tiene un formato válido.") from error
    return texto


@transaction.atomic
def alta_cliente(
    dni: str,
    nombre: str,
    apellido: str,
    telefono: str,
    email: str | None = None,
) -> Cliente:
    """Crea el cliente y su contacto de WhatsApp, o no crea nada.

    El teléfono se pide en el alta a propósito: sin un contacto vinculado, el
    bot no reconoce a la persona cuando escribe y la deriva a un asesor con la
    plantilla `SIN_CLIENTE`, que es justo lo que este ABM viene a evitar.
    """
    datos = {
        "dni": _dni_validado(dni),
        "nombre": _nombre_validado(nombre, "nombre"),
        "apellido": _nombre_validado(apellido, "apellido"),
        "email": _email_validado(email),
    }
    numero = _numero_validado(telefono)
    contacto = _contacto_libre(numero)

    cliente = Cliente.objects.create(activo=True, **datos)
    if contacto is None:
        ContactoWhatsapp.objects.create(numero=numero, cliente=cliente)
    else:
        contacto.cliente = cliente
        contacto.save(update_fields=["cliente"])
    return cliente


@transaction.atomic
def modificar_cliente(
    cliente_id: int,
    *,
    dni: str | None = None,
    nombre: str | None = None,
    apellido: str | None = None,
    telefono: str | None = None,
    email: str | object | None = SIN_CAMBIO,
) -> Cliente:
    """Actualiza solo los campos que vengan. Valida igual que el alta."""
    cliente = _cliente(cliente_id)
    campos: list[str] = []

    if dni is not None:
        cliente.dni = _dni_validado(dni, excluir_id=cliente.id)
        campos.append("dni")
    if nombre is not None:
        cliente.nombre = _nombre_validado(nombre, "nombre")
        campos.append("nombre")
    if apellido is not None:
        cliente.apellido = _nombre_validado(apellido, "apellido")
        campos.append("apellido")
    if email is not SIN_CAMBIO:
        cliente.email = _email_validado(email)  # type: ignore[arg-type]
        campos.append("email")

    if telefono is not None:
        numero = _numero_validado(telefono)
        ocupado = _contacto_libre(numero, cliente_id=cliente.id)
        if ocupado is None:
            # Número libre: se renombra el contacto del cliente, para no dejarle
            # dos números cuando lo que quiso hacer fue corregir uno.
            propio = (
                ContactoWhatsapp.objects.filter(cliente=cliente).order_by("id").first()
            )
            if propio is None:
                ContactoWhatsapp.objects.create(numero=numero, cliente=cliente)
            else:
                propio.numero = numero
                propio.save(update_fields=["numero"])
        elif ocupado.cliente_id is None:
            ocupado.cliente = cliente
            ocupado.save(update_fields=["cliente"])

    if campos:
        cliente.save(update_fields=campos)
    return cliente


@transaction.atomic
def dar_de_baja_cliente(cliente_id: int) -> Cliente:
    """Baja lógica. Se niega si el cliente todavía tiene cobertura vigente."""
    cliente = _cliente(cliente_id)
    if not cliente.activo:
        raise EstadoInvalido("El cliente ya está dado de baja.")

    vigentes = Poliza.objects.filter(
        cliente=cliente, estado=EstadoPoliza.VIGENTE
    ).count()
    if vigentes:
        raise EstadoInvalido(
            f"El cliente tiene {vigentes} póliza(s) vigente(s). "
            "Hay que darlas de baja antes."
        )

    cliente.activo = False
    cliente.save(update_fields=["activo"])
    return cliente


@transaction.atomic
def reactivar_cliente(cliente_id: int) -> Cliente:
    cliente = _cliente(cliente_id)
    if cliente.activo:
        raise EstadoInvalido("El cliente ya está activo.")
    cliente.activo = True
    cliente.save(update_fields=["activo"])
    return cliente
