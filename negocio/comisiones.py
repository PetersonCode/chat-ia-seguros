"""Comisión estimada sobre cuotas y calculada sobre cobros. Sin liquidaciones ficticias."""
from decimal import Decimal, ROUND_HALF_UP

from datos.models import Cuota, Pago


def importe_comision(base, porcentaje):
    if porcentaje is None:
        return None
    return (base * porcentaje / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def reporte_comisiones(desde, hasta):
    companias, clientes = {}, {}
    total = {'base_cuotas': Decimal('0'), 'estimada': Decimal('0'),
             'base_cobros': Decimal('0'), 'sobre_cobros': Decimal('0')}
    pendientes = set()

    def grupo(destino, clave, nombre):
        return destino.setdefault(clave, {'id': clave, 'nombre': nombre, 'sin_porcentaje': 0,
                                          **{k: Decimal('0') for k in total}})

    # Consultas separadas: no se multiplican cuotas al unirlas con los pagos.
    cuotas = Cuota.objects.filter(vencimiento__range=(desde, hasta)).exclude(
        poliza__estado='dada_de_baja').select_related('poliza__compania', 'poliza__cliente')
    pagos = Pago.objects.filter(fecha_pago__range=(desde, hasta)).select_related(
        'cuota__poliza__compania', 'cuota__poliza__cliente')
    for registros, es_cobro in ((cuotas, False), (pagos, True)):
        for registro in registros.iterator():
            poliza = registro.cuota.poliza if es_cobro else registro.poliza
            base = registro.importe
            calculada = importe_comision(base, poliza.comision_pct)
            nuevo_pendiente = calculada is None and poliza.id not in pendientes
            compania = grupo(companias, poliza.compania_id,
                             poliza.compania.nombre if poliza.compania else 'Sin compañía asignada')
            cliente = grupo(clientes, poliza.cliente_id,
                            f'{poliza.cliente.apellido}, {poliza.cliente.nombre}')
            if nuevo_pendiente:
                pendientes.add(poliza.id)
                compania['sin_porcentaje'] += 1
                cliente['sin_porcentaje'] += 1
            clave_base, clave_comision = ('base_cobros', 'sobre_cobros') if es_cobro else ('base_cuotas', 'estimada')
            for fila in (total, compania, cliente):
                fila[clave_base] += base
                fila[clave_comision] += calculada if calculada is not None else Decimal('0')

    def dinero(fila):
        return {k: f'{v:.2f}' if isinstance(v, Decimal) else v for k, v in fila.items()}

    return {'periodo': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()},
            'totales': dinero(total), 'sin_porcentaje': len(pendientes),
            'por_compania': [dinero(f) for f in sorted(companias.values(), key=lambda f: f['nombre'].casefold())],
            'por_cliente': [dinero(f) for f in sorted(clientes.values(), key=lambda f: f['nombre'].casefold())]}
