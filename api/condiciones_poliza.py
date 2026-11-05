from uuid import uuid4
import re
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from api.permisos import EsAprobadorParaEscribir
from api.paginacion import Paginador
from datos.models import Poliza,CondicionesPoliza,PlanCobertura
from datos.selectors import filtrar_cartera
from negocio.errores import NoEncontrado,DatosInvalidos
from negocio.documentos import crear_documento,aprobar_documento,retirar_documento
from negocio.coberturas import vincular_documento


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
        anteriores={k:getattr(info,k) for k in ('cubre','no_cubre','limites','asistencia')} if info else {}
        if plan_id:
            plan=PlanCobertura.objects.select_for_update().filter(pk=plan_id).first()
            if not plan or plan.compania_id!=poliza.compania_id:
                raise DatosInvalidos('El plan debe pertenecer a la compañía de esta póliza.')
            misma_copia=bool(info and info.plan_id==plan.id and info.plan_version==version)
            if not misma_copia:
                if not plan.activo or not plan.compania.activa:
                    raise DatosInvalidos('El plan o su compañía están inactivos.')
                if version is not None and version!=plan.version:
                    raise DatosInvalidos('El plan cambió mientras editabas. Volvé a seleccionarlo antes de guardar.')
                anteriores={k:getattr(plan,k) for k in ('cubre','no_cubre','limites','asistencia')}
                version=plan.version
        else:
            version=None
        s=Campos(data={**anteriores,**{k:request.data[k] for k in request.data}});s.is_valid(raise_exception=True)
        d=s.validated_data
        titulo=f'Condiciones cargadas en póliza {poliza.numero_poliza}'
        if info and info.documento_id and info.documento.estado=='aprobado':
            retirar_documento(info.documento_id,request.funcionario.id)
        contenido=('Cobertura informada: '+d['cubre']+'\nExclusiones: '+(d['no_cubre'] or 'No informadas.')+
            '\nLímites y franquicia: '+(d['limites'] or 'No informados.')+
            '\nTeléfono de asistencia: '+(d['asistencia'] or 'No informado.'))
        doc=crear_documento(titulo=titulo,version=uuid4().hex,referencia='Datos ingresados en la ficha de esta póliza por un aprobador.',
            contenido=contenido,funcionario_id=request.funcionario.id)
        aprobar_documento(doc.id,request.funcionario.id)
        vincular_documento(poliza.numero_poliza,doc.id,request.funcionario.id)
        info,_=CondicionesPoliza.objects.update_or_create(poliza=poliza,defaults={**d,'documento':doc,
            'plan_id':plan_id,'plan_version':version,
            'actualizado_por':request.funcionario,'actualizado_en':timezone.now()})
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
