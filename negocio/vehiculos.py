"""Alta, modificación y baja de vehículos (P1).

El bien asegurado deja de ser un texto libre: la patente identifica al vehículo,
es única en toda la cartera y permite buscar «la camioneta de Pérez». Todo lo que
escribe acá lo hace un aprobador; leer es de cualquier funcionario (eso lo
resuelve la API).

La baja es lógica, como la del cliente: las pólizas viejas siguen apuntando al
vehículo y el historial se conserva.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from datos.limpieza import normalizar_patente
from datos.models import (
    Cliente,
    EstadoPoliza,
    Funcionario,
    Poliza,
    UsoVehiculo,
    Vehiculo,
)
from negocio.clientes import SIN_CAMBIO
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)

ANIO_MINIMO = 1950
VALOR_MAXIMO = Decimal("9999999999.99")
MARCA_OBLIGATORIA = "La marca es obligatoria."
MODELO_OBLIGATORIO = "El modelo es obligatorio."


def _aprobador(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id).first()
    if funcionario is None:
        raise NoEncontrado("El funcionario no existe.")
    if not funcionario.activo or not funcionario.puede_aprobar:
        raise PermisoDenegado("Administrar vehículos requiere un aprobador activo.")
    return funcionario


def _vehiculo(vehiculo_id: int) -> Vehiculo:
    vehiculo = Vehiculo.objects.filter(pk=vehiculo_id).first()
    if vehiculo is None:
        raise NoEncontrado("El vehículo no existe.")
    return vehiculo


def _patente_validada(valor: str, excluir_id: int | None = None) -> str:
    try:
        patente = normalizar_patente(valor or "")
    except ValueError as error:
        raise DatosInvalidos(str(error)) from error
    repetidas = Vehiculo.objects.filter(patente=patente)
    if excluir_id is not None:
        repetidas = repetidas.exclude(pk=excluir_id)
    if repetidas.exists():
        raise DatosInvalidos(f"Ya existe un vehículo con la patente {patente}.")
    return patente


def _texto_obligatorio(valor: str, mensaje: str) -> str:
    texto = " ".join((valor or "").split())
    if not texto:
        raise DatosInvalidos(mensaje)
    return texto


def _anio_validado(valor) -> int:
    if isinstance(valor, bool):
        raise DatosInvalidos("El año tiene que ser un número.")
    try:
        anio = int(str(valor).strip())
    except (TypeError, ValueError) as error:
        raise DatosInvalidos("El año tiene que ser un número.") from error
    maximo = timezone.localdate().year + 1
    if not ANIO_MINIMO <= anio <= maximo:
        raise DatosInvalidos(f"El año tiene que estar entre {ANIO_MINIMO} y {maximo}.")
    return anio


def _uso_validado(valor: str) -> str:
    uso = (valor or "").strip().lower()
    if uso not in UsoVehiculo.values:
        raise DatosInvalidos("El uso tiene que ser uno de: " + ", ".join(UsoVehiculo.values) + ".")
    return uso


def _valor_validado(valor) -> Decimal | None:
    """`None` o vacío = sin valor asegurado. Si viene, tiene que ser mayor que cero."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool):
        raise DatosInvalidos("El valor asegurado tiene que ser un número.")
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError) as error:
        raise DatosInvalidos("El valor asegurado tiene que ser un número.") from error
    if not numero.is_finite():
        raise DatosInvalidos("El valor asegurado tiene que ser un número finito.")
    if numero <= 0:
        raise DatosInvalidos("El valor asegurado tiene que ser mayor que cero.")
    if numero > VALOR_MAXIMO:
        raise DatosInvalidos("El valor asegurado está fuera del rango permitido.")
    centavos = numero.quantize(Decimal("0.01"))
    if centavos != numero:
        raise DatosInvalidos("El valor asegurado admite como máximo dos decimales.")
    return centavos


def _chasis_validado(valor: str | None) -> str | None:
    texto = (valor or "").strip()
    return texto or None


def _guardar(vehiculo: Vehiculo, campos: list[str] | None = None) -> None:
    # `update_fields=None` guarda todo (alta); una lista, solo esas columnas.
    """Guarda convirtiendo la carrera de dos patentes iguales en un error de datos."""
    try:
        with transaction.atomic():
            vehiculo.save(update_fields=campos)
    except IntegrityError as error:
        raise DatosInvalidos(
            f"Ya existe un vehículo con la patente {vehiculo.patente}."
        ) from error


@transaction.atomic
def alta_vehiculo(
    cliente_id: int,
    patente: str,
    marca: str,
    modelo: str,
    anio,
    uso: str = "particular",
    chasis: str | None = None,
    valor_asegurado=None,
    *,
    funcionario_id: int,
) -> Vehiculo:
    """Crea el vehículo con la patente normalizada, o no crea nada."""
    _aprobador(funcionario_id)
    cliente = Cliente.objects.filter(pk=cliente_id).first()
    if cliente is None:
        raise NoEncontrado("El cliente no existe.")
    if not cliente.activo:
        raise DatosInvalidos("El cliente está dado de baja: no se le pueden cargar vehículos.")

    vehiculo = Vehiculo(
        cliente=cliente,
        patente=_patente_validada(patente),
        marca=_texto_obligatorio(marca, MARCA_OBLIGATORIA),
        modelo=_texto_obligatorio(modelo, MODELO_OBLIGATORIO),
        anio=_anio_validado(anio),
        uso=_uso_validado(uso),
        chasis=_chasis_validado(chasis),
        valor_asegurado=_valor_validado(valor_asegurado),
        activo=True,
    )
    _guardar(vehiculo)
    return vehiculo


@transaction.atomic
def modificar_vehiculo(
    vehiculo_id: int,
    *,
    funcionario_id: int,
    patente: str | None = None,
    marca: str | None = None,
    modelo: str | None = None,
    anio=None,
    uso: str | None = None,
    chasis: str | None | object = SIN_CAMBIO,
    valor_asegurado: object = SIN_CAMBIO,
) -> Vehiculo:
    """Actualiza solo lo recibido; `chasis` y `valor_asegurado` vacíos se borran.

    La patente propia no cuenta como repetida. El dueño no se cambia: un vehículo
    que cambia de dueño es una baja y un alta nueva.
    """
    _aprobador(funcionario_id)
    vehiculo = _vehiculo(vehiculo_id)
    campos: list[str] = []

    if patente is not None:
        vehiculo.patente = _patente_validada(patente, excluir_id=vehiculo.id)
        campos.append("patente")
    if marca is not None:
        vehiculo.marca = _texto_obligatorio(marca, MARCA_OBLIGATORIA)
        campos.append("marca")
    if modelo is not None:
        vehiculo.modelo = _texto_obligatorio(modelo, MODELO_OBLIGATORIO)
        campos.append("modelo")
    if anio is not None:
        vehiculo.anio = _anio_validado(anio)
        campos.append("anio")
    if uso is not None:
        vehiculo.uso = _uso_validado(uso)
        campos.append("uso")
    if chasis is not SIN_CAMBIO:
        vehiculo.chasis = _chasis_validado(chasis)  # type: ignore[arg-type]
        campos.append("chasis")
    if valor_asegurado is not SIN_CAMBIO:
        vehiculo.valor_asegurado = _valor_validado(valor_asegurado)
        campos.append("valor_asegurado")

    if campos:
        _guardar(vehiculo, campos)
    return vehiculo


@transaction.atomic
def dar_de_baja_vehiculo(vehiculo_id: int, *, funcionario_id: int) -> Vehiculo:
    """Baja lógica. Se niega si una póliza vigente todavía lo asegura."""
    _aprobador(funcionario_id)
    vehiculo = Vehiculo.objects.select_for_update().filter(pk=vehiculo_id).first()
    if vehiculo is None:
        raise NoEncontrado("El vehículo no existe.")
    if not vehiculo.activo:
        raise EstadoInvalido("El vehículo ya está dado de baja.")

    vigentes = Poliza.objects.filter(
        vehiculo_id=vehiculo.id,
        estado=EstadoPoliza.VIGENTE,
        fecha_vencimiento__gte=timezone.localdate(),
    ).count()
    if vigentes:
        raise EstadoInvalido(
            f"El vehículo tiene {vigentes} póliza(s) vigente(s). "
            "Hay que darlas de baja antes."
        )

    vehiculo.activo = False
    vehiculo.save(update_fields=["activo"])
    return vehiculo
