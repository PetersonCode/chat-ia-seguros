"""Alta y mantenimiento de compañías aseguradoras (P1).

Una compañía dice quién emite la póliza y cuánta comisión deja. La comisión es
información del dueño: por eso todo lo que escribe acá exige un aprobador. Una
compañía **no se borra**: se desactiva, y las pólizas que ya la usan no se
tocan (siguen mostrando su compañía y la comisión con la que se emitieron).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from datos.models import Compania, Funcionario
from negocio.errores import DatosInvalidos, NoEncontrado, PermisoDenegado

MAXIMO_NOMBRE = 120


def _aprobador(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id).first()
    if funcionario is None:
        raise NoEncontrado("El funcionario no existe.")
    if not funcionario.activo or not funcionario.puede_aprobar:
        raise PermisoDenegado("Administrar compañías requiere un aprobador activo.")
    return funcionario


def _compania(compania_id: int) -> Compania:
    compania = Compania.objects.filter(pk=compania_id).first()
    if compania is None:
        raise NoEncontrado("La compañía no existe.")
    return compania


def _clave(nombre: str) -> str:
    """Sin mayúsculas ni espacios: «La  Caja» y «lacaja» son la misma compañía."""
    return re.sub(r"\s+", "", nombre).casefold()


def _nombre_validado(valor: str, excluir_id: int | None = None) -> str:
    nombre = " ".join((valor or "").split())
    if not nombre:
        raise DatosInvalidos("El nombre de la compañía es obligatorio.")
    if len(nombre) > MAXIMO_NOMBRE:
        raise DatosInvalidos(
            f"El nombre de la compañía no puede superar {MAXIMO_NOMBRE} caracteres."
        )
    clave = _clave(nombre)
    otras = Compania.objects.all()
    if excluir_id is not None:
        otras = otras.exclude(pk=excluir_id)
    if any(_clave(otra.nombre) == clave for otra in otras):
        raise DatosInvalidos(f"Ya existe la compañía {nombre}.")
    return nombre


def porcentaje_validado(valor, campo: str = "La comisión") -> Decimal:
    """Un porcentaje de 0 a 100 con hasta dos decimales (acepta coma decimal)."""
    if isinstance(valor, bool):
        raise DatosInvalidos(f"{campo} tiene que ser un número.")
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError) as error:
        raise DatosInvalidos(f"{campo} tiene que ser un número.") from error
    if not numero.is_finite():
        raise DatosInvalidos(f"{campo} tiene que ser un número finito.")
    if numero < 0 or numero > 100:
        raise DatosInvalidos(f"{campo} tiene que estar entre 0 y 100.")
    centesimas = numero.quantize(Decimal("0.01"))
    if centesimas != numero:
        raise DatosInvalidos(f"{campo} admite como máximo dos decimales.")
    return centesimas


@transaction.atomic
def alta_compania(nombre: str, comision_pct, *, funcionario_id: int) -> Compania:
    _aprobador(funcionario_id)
    datos = {
        "nombre": _nombre_validado(nombre),
        "comision_pct": porcentaje_validado(comision_pct),
    }
    try:
        with transaction.atomic():
            return Compania.objects.create(activa=True, **datos)
    except IntegrityError as error:  # carrera: otra alta con el mismo nombre
        raise DatosInvalidos(f"Ya existe la compañía {datos['nombre']}.") from error


@transaction.atomic
def modificar_compania(
    compania_id: int,
    *,
    funcionario_id: int,
    nombre: str | None = None,
    comision_pct=None,
    activa: bool | None = None,
) -> Compania:
    """Actualiza solo lo recibido. `activa` permite también reactivarla.

    Cambiar la comisión no reescribe las pólizas ya emitidas: cada una guarda la
    que tenía la compañía al emitirse.
    """
    _aprobador(funcionario_id)
    compania = _compania(compania_id)
    campos: list[str] = []
    if nombre is not None:
        compania.nombre = _nombre_validado(nombre, excluir_id=compania.id)
        campos.append("nombre")
    if comision_pct is not None:
        compania.comision_pct = porcentaje_validado(comision_pct)
        campos.append("comision_pct")
    if activa is not None:
        if not isinstance(activa, bool):
            raise DatosInvalidos("El estado de la compañía tiene que ser verdadero o falso.")
        compania.activa = activa
        campos.append("activa")
    if campos:
        try:
            with transaction.atomic():
                compania.save(update_fields=campos)
        except IntegrityError as error:
            raise DatosInvalidos(f"Ya existe la compañía {compania.nombre}.") from error
    return compania


def desactivar_compania(compania_id: int, *, funcionario_id: int) -> Compania:
    """La compañía deja de ofrecerse para pólizas nuevas; las existentes no se tocan."""
    return modificar_compania(compania_id, funcionario_id=funcionario_id, activa=False)
