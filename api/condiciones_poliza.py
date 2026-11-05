import re
from django.db import transaction
from rest_framework import serializers
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from api.permisos import EsAprobadorParaEscribir
from api.paginacion import Paginador
from datos.models import Poliza,CondicionesPoliza
from datos.selectors import filtrar_cartera
from negocio.errores import NoEncontrado
from negocio.condiciones_poliza import guardar_condiciones, plan_para_poliza


class Campos(serializers.Serializer):
    cubre=serializers.CharField(max_length=10000,trim_whitespace=True)
    no_cubre=serializers.CharField(max_length=10000,allow_blank=True,default='')
    limites=serializers.CharField(max_length=10000,allow_blank=True,default='')
    asistencia=serializers.CharField(max_length=100,allow_blank=True,default='')

    def validate_asistencia(self, valor):
        if valor and (not re.fullmatch(r'\+?[\d\s()\-]+',valor) or not 7 <= len(re.sub(r'\D','',valor)) <= 18):
            raise serializers.ValidationError('Ingresá un teléfono con 7 a 18 dígitos, sin instrucciones ni enlaces.')
        return valor


class SeleccionPlan(serializers.Serializer):
    plan_id=serializers.IntegerField(min_value=1,required=False,allow_null=True)
    plan_version=serializers.IntegerField(min_value=1,required=False,allow_null=True)


@api_view(['GET','PATCH'])
@permission_classes([EsAprobadorParaEscribir])
@transaction.atomic
def condiciones(request,id):
    poliza=Poliza.objects.select_for_update().filter(pk=id).first()
    if not poliza:raise NoEncontrado('La póliza no existe.')
    info=CondicionesPoliza.objects.filter(poliza=poliza).select_related('documento').first()
    if request.method=='PATCH':
        selector=SeleccionPlan(data=request.data);selector.is_valid(raise_exception=True)
        plan_id=selector.validated_data.get('plan_id',info.plan_id if info else None)
        version=selector.validated_data.get('plan_version',info.plan_version if info and info.plan_id==plan_id else None)
        plan,version,anteriores=plan_para_poliza(poliza,plan_id,version,info)
        s=Campos(data={**anteriores,**{k:request.data[k] for k in request.data}});s.is_valid(raise_exception=True)
        info=guardar_condiciones(poliza,plan=plan,plan_version=version,campos=s.validated_data,funcionario=request.funcionario)
    return Response({'poliza':poliza.numero_poliza,**{k:getattr(info,k,'') for k in ('cubre','no_cubre','limites','asistencia')},
        'plan_id':info.plan_id if info else None,'plan_version':info.plan_version if info else None,
        'lista':bool(info and info.documento_id and info.documento.estado=='aprobado')})


@api_view(['GET'])
@permission_classes([EsAprobadorParaEscribir])
def listar(request):
    qs=Poliza.objects.select_related('cliente','vehiculo','compania').order_by('-id')
    q=request.query_params.get('q','').strip()[:100]
    if q:qs=filtrar_cartera(qs,q,('numero_poliza','cliente__nombre','cliente__apellido','vehiculo__patente','vehiculo__modelo','compania__nombre'))
    p=Paginador(); filas=p.paginate_queryset(qs,request)
    return p.get_paginated_response([{'id':x.id,'numero':x.numero_poliza,'cliente_id':x.cliente_id,
        'cliente':f'{x.cliente.nombre} {x.cliente.apellido}','patente':x.vehiculo.patente if x.vehiculo else '',
        'compania':x.compania.nombre if x.compania else 'Sin asignar','compania_id':x.compania_id,'estado':x.estado} for x in filas])
