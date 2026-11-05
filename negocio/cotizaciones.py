"""Cotizaciones de las compañías (P5): cargarlas, compararlas y elegir una.

Una cotización cuelga de **un** interesado (venta nueva) o de **una** póliza
(renovación), nunca de los dos ni de ninguno: lo hace cumplir la base y lo
verifica acá antes, para dar un mensaje claro. La elegida es una sola por
destino; elegir otra desmarca la anterior en la misma transacción.

Cualquier funcionario activo puede cargarlas y elegirlas: son el trabajo de todos
los días del mostrador, no una decisión contractual. Cambiar un contrato sigue
pasando por `AccionPendiente` (R11).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.db import transaction

from datos.models import Cobertura, Compania, Cotizacion, Funcionario, Interesado, Poliza
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado, PermisoDenegado

PRIMA_MAXIMA = Decimal("9999999999.99")
MAXIMO_NOTAS = 1000


def _funcionario_activo(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id, activo=True).first()
    if funcionario is None:
        raise PermisoDenegado("El funcionario no existe o no está activo.")
    return funcionario


def _prima_validada(valor) -> Decimal:
    """Un importe mayor que cero, con hasta dos decimales (acepta coma decimal)."""
    if isinstance(valor, bool) or valor is None:
        raise DatosInvalidos("La prima mensual tiene que ser un número.")
    try:
        numero = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError) as error:
        raise DatosInvalidos("La prima mensual tiene que ser un número.") from error
    if not numero.is_finite():
        raise DatosInvalidos("La prima mensual tiene que ser un número finito.")
    if numero <= 0:
        raise DatosInvalidos("La prima mensual tiene que ser mayor que cero.")
    if numero > PRIMA_MAXIMA:
        raise DatosInvalidos("La prima mensual es demasiado grande.")
    centavos = numero.quantize(Decimal("0.01"))
    if centavos != numero:
        raise DatosInvalidos("La prima mensual admite como máximo dos decimales.")
    return centavos


def _fecha_validada(valor, campo: str) -> dt.date | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    try:
        return dt.date.fromisoformat(str(valor).strip())
    except ValueError as error:
        raise DatosInvalidos(f"{campo} tiene que ser una fecha (aaaa-mm-dd).") from error


def _compania_activa(compania_id: int) -> Compania:
    compania = Compania.objects.filter(pk=compania_id).first()
    if compania is None:
        raise NoEncontrado("La compañía no existe.")
    if not compania.activa:
        raise DatosInvalidos(f"La compañía {compania.nombre} está desactivada.")
    return compania


def _cotizacion(cotizacion_id: int, *, bloquear: bool = False) -> Cotizacion:
    consulta = Cotizacion.objects.all()
    if bloquear:
        consulta = consulta.select_for_update()
    cotizacion = consulta.filter(pk=cotizacion_id).first()
    if cotizacion is None:
        raise NoEncontrado("La cotización no existe.")
    return cotizacion


@transaction.atomic
def cargar_cotizacion(
    funcionario_id: int,
    compania_id: int,
    cobertura: str,
    prima_mensual,
    interesado_id: int | None = None,
    poliza_id: int | None = None,
    vigencia_hasta=None,
    notas: str | None = None,
) -> Cotizacion:
    """Carga lo que cotiza una compañía. Exige exactamente uno de interesado o póliza."""
    funcionario = _funcionario_activo(funcionario_id)
    if (interesado_id is None) == (poliza_id is None):
        raise DatosInvalidos("La cotización es de un interesado o de una póliza, no de ambos ni de ninguno.")
    if interesado_id is not None and not Interesado.objects.filter(pk=interesado_id).exists():
        raise NoEncontrado("El interesado no existe.")
    if poliza_id is not None and not Poliza.objects.filter(pk=poliza_id).exists():
        raise NoEncontrado("La póliza no existe.")
    compania = _compania_activa(compania_id)
    if cobertura not in Cobertura.values:
        raise DatosInvalidos(
            "La cobertura tiene que ser una de: " + ", ".join(Cobertura.values) + "."
        )
    texto_notas = (notas or "").strip() or None
    if texto_notas is not None and len(texto_notas) > MAXIMO_NOTAS:
        raise DatosInvalidos(f"Las notas no pueden superar {MAXIMO_NOTAS} caracteres.")

    return Cotizacion.objects.create(
        interesado_id=interesado_id,
        poliza_id=poliza_id,
        compania=compania,
        cobertura=cobertura,
        prima_mensual=_prima_validada(prima_mensual),
        vigencia_hasta=_fecha_validada(vigencia_hasta, "La vigencia"),
        notas=texto_notas,
        creada_por=funcionario,
    )


@transaction.atomic
def elegir_cotizacion(cotizacion_id: int, funcionario_id: int) -> Cotizacion:
    """Marca la elegida y desmarca la anterior del mismo destino, todo o nada."""
    _funcionario_activo(funcionario_id)
    cotizacion = _cotizacion(cotizacion_id, bloquear=True)
    if cotizacion.elegida:
        return cotizacion

    # Primero se baja la anterior: el índice único parcial no admite dos elegidas
    # ni siquiera un instante.
    Cotizacion.objects.filter(
        interesado_id=cotizacion.interesado_id,
        poliza_id=cotizacion.poliza_id,
        elegida=True,
    ).update(elegida=False)
    cotizacion.elegida = True
    cotizacion.save(update_fields=["elegida"])
    return cotizacion


@transaction.atomic
def quitar_cotizacion(cotizacion_id: int, funcionario_id: int) -> None:
    """Borra una cotización que no es la elegida. La elegida hay que cambiarla antes."""
    _funcionario_activo(funcionario_id)
    cotizacion = _cotizacion(cotizacion_id, bloquear=True)
    if cotizacion.elegida:
        raise EstadoInvalido(
            "Esa es la cotización elegida. Elegí otra antes de quitarla."
        )
    cotizacion.delete()


def variacion_renovacion(poliza_id: int) -> Decimal | None:
    """Cuánto cambia el precio al renovar, en %: de la prima de la póliza a la cotización elegida.

    Positivo es un aumento; negativo, una baja. `None` si no hay cotización
    elegida para la póliza (o si la prima actual no permite comparar).
    """
    poliza = Poliza.objects.filter(pk=poliza_id).first()
    if poliza is None:
        raise NoEncontrado("La póliza no existe.")
    elegida = Cotizacion.objects.filter(poliza_id=poliza_id, elegida=True).first()
    if elegida is None or poliza.prima_mensual <= 0:
        return None
    variacion = (elegida.prima_mensual - poliza.prima_mensual) * 100 / poliza.prima_mensual
    return variacion.quantize(Decimal("0.01"))


@transaction.atomic
def registrar_poliza_elegida(interesado_id, funcionario_id, inicio, vencimiento):
    from negocio.interesados import _aprobador, guardar_vehiculo_del_interesado, mover_interesado
    from negocio.polizas import alta_poliza
    from django.utils import timezone
    _aprobador(funcionario_id)
    i=Interesado.objects.select_for_update().get(pk=interesado_id)
    if i.estado!='documentacion' or not i.cliente_id:
        raise EstadoInvalido('Primero completá Documentación y convertí al interesado en cliente. Si ya está emitido, no se registra otra póliza.')
    c=Cotizacion.objects.select_for_update().filter(interesado=i,elegida=True).first()
    if not c:raise DatosInvalidos('Falta elegir una cotización.')
    if c.vigencia_hasta and c.vigencia_hasta<timezone.localdate():raise DatosInvalidos('La cotización venció: actualizá la propuesta antes de confirmar.')
    v=guardar_vehiculo_del_interesado(i,i.cliente,funcionario_id)
    if not v:raise DatosInvalidos('Completá patente, marca, modelo y año del vehículo.')
    p=alta_poliza(i.cliente_id,tipo_seguro='automotor',cobertura=c.cobertura,fecha_inicio=inicio,fecha_vencimiento=vencimiento,prima_mensual=c.prima_mensual,vehiculo_id=v.id,compania_id=c.compania_id)
    mover_interesado(i.id,'emitida',funcionario_id,nota=f'Póliza {p.numero_poliza} registrada desde cotización elegida #{c.id}.')
    return p
