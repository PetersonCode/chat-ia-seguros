"""Completar una póliza histórica sin alterar vigencia, prima, cuotas ni saldo."""
from django.db import transaction

from datos.models import CondicionesPoliza, Poliza
from negocio.clientes import SIN_CAMBIO
from negocio.companias import porcentaje_validado
from negocio.errores import DatosInvalidos, NoEncontrado
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
            con_plan = (
                CondicionesPoliza.objects.filter(poliza=poliza, plan__isnull=False)
                .select_related("plan").first()
            )
            if con_plan is not None and con_plan.plan.compania_id != compania_id:
                # Cambiar de compañía dejaría la cobertura con un plan ajeno.
                raise DatosInvalidos(
                    f"La cobertura de esta póliza es el plan «{con_plan.plan.nombre}» de su "
                    "compañía actual. Para cambiarla de compañía, primero pasá la cobertura a "
                    "condiciones particulares en la página Pólizas."
                )
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
