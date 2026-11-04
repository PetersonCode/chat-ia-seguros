from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from api.permisos import EsFuncionario
from api.paginacion import Paginador
from datos.models import RecordatorioPoliza
from negocio.recordatorios import (polizas_por_vencer, preparar_recordatorio,
    conversacion_disponible, enviar_recordatorio)


class Filtros(serializers.Serializer):
    dias = serializers.IntegerField(required=False,min_value=1,max_value=3650)
    incluir_vencidas = serializers.BooleanField(required=False,default=False)
    q = serializers.CharField(required=False,allow_blank=True,max_length=100)
    pagina = serializers.IntegerField(required=False,min_value=1)


class Envio(serializers.Serializer):
    contacto_id = serializers.IntegerField(min_value=1)
    canal = serializers.ChoiceField(choices=['api','manual'],default='api')


def aviso_json(aviso):
    return {'id':aviso.pk,'canal':aviso.canal,'texto':aviso.texto,
        'creado_en':aviso.creado_en.isoformat(),'funcionario':aviso.funcionario.nombre,
        'estado':aviso.mensaje.estado_envio if aviso.mensaje else ('enviado_manual' if aviso.canal=='manual' else 'sin_mensaje'),
        'error':aviso.mensaje.error if aviso.mensaje else None}


@api_view(['GET'])
@permission_classes([EsFuncionario])
def vencimientos(request):
    s=Filtros(data=request.query_params);s.is_valid(raise_exception=True)
    datos=dict(s.validated_data);datos.pop('pagina',None)
    p=Paginador();pagina=p.paginate_queryset(polizas_por_vencer(**datos),request)
    return p.get_paginated_response([{'id':poliza.pk,'numero_poliza':poliza.numero_poliza,
        'cliente':{'id':poliza.cliente_id,'nombre':poliza.cliente.nombre,'apellido':poliza.cliente.apellido},
        'vehiculo':poliza.bien_asegurado,'estado':poliza.estado,
        'fecha_vencimiento':poliza.fecha_vencimiento.isoformat(),
        'dias_restantes':(poliza.fecha_vencimiento-timezone.localdate()).days,
        'saldo_pendiente':str(poliza.saldo or 0),
        'saldo_vencido':str(poliza.saldo_vencido),
        'primera_cuota_vencida':poliza.primera_cuota_vencida.isoformat() if poliza.primera_cuota_vencida else None,
        'proxima_cuota':poliza.proxima_cuota.isoformat() if poliza.proxima_cuota else None,
        'ultimo_recordatorio':poliza.ultimo_recordatorio.isoformat() if poliza.ultimo_recordatorio else None,
    } for poliza in pagina])


@api_view(['GET','POST'])
@permission_classes([EsFuncionario])
def recordatorio(request,id):
    if request.method=='POST':
        s=Envio(data=request.data);s.is_valid(raise_exception=True)
        aviso,nuevo=enviar_recordatorio(id,funcionario_id=request.funcionario.id,**s.validated_data)
        aviso=RecordatorioPoliza.objects.select_related('mensaje','funcionario').get(pk=aviso.pk)
        return Response({'recordatorio':aviso_json(aviso),'nuevo':nuevo},status=201 if nuevo else 200)
    s=serializers.IntegerField(min_value=1,required=False)
    contacto_id=s.run_validation(request.query_params['contacto_id']) if 'contacto_id' in request.query_params else None
    poliza,contactos,contacto,texto,_,anterior=preparar_recordatorio(id,contacto_id)
    historia=RecordatorioPoliza.objects.filter(poliza=poliza).select_related('mensaje','funcionario').order_by('-creado_en','-id')[:5]
    return Response({'poliza':poliza.numero_poliza,'texto':texto,'contacto_id':contacto.pk if contacto else None,
        'contactos':[{'id':c.pk,'numero':c.numero} for c in contactos],
        'puede_enviar':bool(contacto and conversacion_disponible(contacto)),
        'ya_enviado_hoy':aviso_json(anterior) if anterior else None,
        'historial':[aviso_json(a) for a in historia]})
