"""Completar una póliza histórica sin alterar vigencia, prima, cuotas ni saldo."""
from django.db import transaction

from datos.models import Poliza
from negocio.clientes import SIN_CAMBIO
from negocio.companias import porcentaje_validado
from negocio.errores import NoEncontrado
from negocio.polizas import (
    _compania_activa, _vehiculo_del_cliente, validar_solapamiento,
)
from negocio.vehiculos import _aprobador


@transaction.atomic
def completar_cartera(poliza_id, *, funcionario_id, vehiculo_id=SIN_CAMBIO,
                      compania_id=SIN_CAMBIO, comision_pct=SIN_CAMBIO):
    _aprobador(funcionario_id)
    poliza = Poliza.objects.select_for_update().filter(pk=poliza_id).first()
    if poliza is None:
        raise NoEncontrado('La póliza no existe.')
    campos = []
    if vehiculo_id is not SIN_CAMBIO:
        vehiculo = _vehiculo_del_cliente(vehiculo_id, poliza.cliente)
        validar_solapamiento(vehiculo, poliza.fecha_inicio, poliza.fecha_vencimiento,
                             excluir_id=poliza.id, estado=poliza.estado)
        poliza.vehiculo = vehiculo
        campos.append('vehiculo')
    if compania_id is not SIN_CAMBIO:
        compania = _compania_activa(compania_id)
        if poliza.compania_id != compania_id:
            poliza.compania = compania
            # Nueva compañía: nuevo porcentaje explícito o su valor actual.
            poliza.comision_pct = compania.comision_pct if compania else None
            campos.extend(['compania', 'comision_pct'])
    if comision_pct is not SIN_CAMBIO:
        # Vacío restaura el porcentaje de la compañía; cero es una comisión real.
        poliza.comision_pct = (porcentaje_validado(comision_pct) if comision_pct is not None
                              else poliza.compania.comision_pct if poliza.compania else None)
        campos.append('comision_pct')
    if campos:
        poliza.save(update_fields=list(set(campos)))
    return poliza
