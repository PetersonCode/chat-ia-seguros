"""Ejecución de una solicitud del chat, siempre dentro de la aprobación humana."""
from datetime import date
from datos.models import Vehiculo, PlanCobertura
from negocio.clientes import alta_cliente
from negocio.errores import DatosInvalidos
from negocio.polizas import alta_poliza
from negocio.vehiculos import alta_vehiculo


def ejecutar_alta_poliza(accion, funcionario):
    p = accion.parametros or {}
    contacto = accion.consulta.contacto or (accion.consulta.conversacion.contacto if accion.consulta.conversacion_id else None)
    if contacto is None:
        raise DatosInvalidos('El alta necesita el contacto que originó la solicitud.')
    if accion.consulta.conversacion_id and contacto.id != accion.consulta.conversacion.contacto_id:
        raise DatosInvalidos('El contacto de la solicitud no coincide con el del chat.')
    cliente = contacto.cliente
    if cliente is None:
        cliente = alta_cliente(dni=p.get('dni', ''), nombre=p.get('nombre', ''),
            apellido=p.get('apellido', ''), telefono=contacto.numero, email=p.get('email'))
    elif p.get('cliente_id') not in (None, cliente.id) or (p.get('dni') and p['dni'] != cliente.dni):
        raise DatosInvalidos('El cliente asociado cambió: hay que revisar la solicitud.')
    vehiculo = Vehiculo.objects.select_for_update().filter(patente=p['patente']).first()
    if vehiculo:
        if vehiculo.cliente_id != cliente.id or not vehiculo.activo:
            raise DatosInvalidos('La patente no está disponible para este cliente.')
    else:
        vehiculo = alta_vehiculo(cliente.id, patente=p['patente'], marca=p['marca'], modelo=p['modelo'],
            anio=p['anio'], clase=p['clase'], uso=p['uso'], chasis=p.get('chasis'),
            valor_asegurado=p.get('valor_asegurado'), funcionario_id=funcionario.id)
    try:
        inicio, fin = date.fromisoformat(p['fecha_inicio']), date.fromisoformat(p['fecha_vencimiento'])
    except (ValueError, TypeError) as error:
        raise DatosInvalidos('Las fechas de la solicitud no son válidas.') from error
    poliza = alta_poliza(cliente.id, tipo_seguro='automotor', cobertura=p['cobertura'],
        fecha_inicio=inicio, fecha_vencimiento=fin, prima_mensual=p['prima_mensual'],
        vehiculo_id=vehiculo.id, compania_id=p['compania_id'])
    if p.get('plan_id'):
        # El plan que eligió en el chat: mismas condiciones (y documento para el
        # bot) que una póliza cargada desde el panel.
        from negocio.condiciones_poliza import guardar_condiciones, plan_para_poliza
        if p.get('plan_version') and p.get('plan_condiciones'):
            plan = PlanCobertura.objects.select_for_update().select_related('compania').filter(pk=p['plan_id']).first()
            if not plan or plan.compania_id != poliza.compania_id or not plan.activo or not plan.compania.activa:
                raise DatosInvalidos('El plan solicitado ya no está disponible. Revisá la solicitud antes de aprobar.')
            version = p['plan_version']
            campos = p['plan_condiciones']
            if (not isinstance(version, int) or version < 1 or version > plan.version or
                    not isinstance(campos, dict) or not all(isinstance(campos.get(k), str) for k in ('cubre', 'no_cubre', 'limites', 'asistencia'))):
                raise DatosInvalidos('La copia de condiciones solicitadas no es válida.')
        else:  # solicitudes anteriores al registro de la versión
            plan, version, campos = plan_para_poliza(poliza, p['plan_id'], None)
        guardar_condiciones(poliza, plan=plan, plan_version=version, campos=campos,
                            funcionario=funcionario, plan_nombre=p.get('plan_nombre'))
    from negocio.interesados import finalizar_interesado_por_alta_chat
    finalizar_interesado_por_alta_chat(contacto, poliza, funcionario.id)
    accion.poliza = poliza
    accion.parametros = {**p, 'cliente_id': cliente.id}
