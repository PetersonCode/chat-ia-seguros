from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
import csv
from django.http import HttpResponse

from api.permisos import EsAprobador
from api.serializers import ReporteGestionFiltroSerializer
from negocio.cartera import completar_cartera
from negocio.comisiones import reporte_comisiones


class CarteraSerializer(serializers.Serializer):
    vehiculo_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    compania_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    comision_pct = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def validate_comision_pct(self, valor):
        return (valor or '').strip() or None


@api_view(['PATCH'])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def poliza_cartera(request, id):
    from api.views import _poliza_con_bien
    datos = CarteraSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    poliza = completar_cartera(id, funcionario_id=request.funcionario.id, **datos.validated_data)
    return Response(_poliza_con_bien(poliza, True))


@api_view(['GET'])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def comisiones(request):
    filtros = ReporteGestionFiltroSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    desde, hasta = filtros.validated_data['desde'], filtros.validated_data['hasta']
    datos = reporte_comisiones(desde, hasta)
    if filtros.validated_data['formato'] == 'csv':
        from api.views import _celda_csv_segura
        respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
        respuesta['Content-Disposition'] = f'attachment; filename="comisiones-{desde}-{hasta}.csv"'
        escritor = csv.writer(respuesta)
        escritor.writerow(('Desde', str(desde), 'Hasta', str(hasta)))
        escritor.writerow(('Agrupación', 'Nombre', 'Base cuotas ARS', 'Comisión estimada ARS',
                           'Base cobros ARS', 'Comisión sobre cobros ARS', 'Pólizas sin porcentaje'))
        for clave, etiqueta in [('por_compania', 'Compañía'), ('por_cliente', 'Cliente')]:
            for fila in datos[clave]:
                escritor.writerow((etiqueta, _celda_csv_segura(fila['nombre']), fila['base_cuotas'],
                    fila['estimada'], fila['base_cobros'], fila['sobre_cobros'], fila['sin_porcentaje']))
        return respuesta
    return Response(datos)
