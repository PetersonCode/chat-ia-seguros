"""Ejecución de una solicitud del chat, siempre dentro de la aprobación humana."""
from datetime import date
from datos.models import Vehiculo
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
    accion.poliza = poliza
    accion.parametros = {**p, 'cliente_id': cliente.id}
