from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from api.permisos import EsFuncionario,EsAprobador
from datos.models import Cliente,Interesado,Funcionario,ContactoWhatsapp
from datos.gestion_models import Tarea,NotaInterna,AvisoGestion,ConfigGestion
from negocio.gestion_diaria import resumen,texto,procesar
from negocio.errores import NoEncontrado,DatosInvalidos,PermisoDenegado,EstadoInvalido

class TareaDatos(serializers.Serializer):
    titulo=serializers.CharField(min_length=3,max_length=200)
    detalle=serializers.CharField(max_length=2000,allow_blank=True,default='')
    asignada_a=serializers.PrimaryKeyRelatedField(queryset=Funcionario.objects.filter(activo=True))
    cliente=serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.filter(activo=True),required=False,allow_null=True)
    interesado=serializers.PrimaryKeyRelatedField(queryset=Interesado.objects.all(),required=False,allow_null=True)
    vence=serializers.DateField()

def tarea(t):
    return {'id':t.id,'titulo':t.titulo,'detalle':t.detalle,'asignada_a':t.asignada_a_id,'creada_por':t.creada_por_id,'responsable':t.asignada_a.nombre,'cliente':t.cliente_id,'interesado':t.interesado_id,'vence':t.vence,'estado':t.estado}

@api_view(['GET'])
@permission_classes([EsFuncionario])
def inicio(request):return Response(resumen())

@api_view(['GET','POST'])
@permission_classes([EsFuncionario])
def tareas(request):
    if request.method=='POST':
        s=TareaDatos(data=request.data);s.is_valid(raise_exception=True)
        d=s.validated_data
        if d.get('cliente') and d.get('interesado') and d['interesado'].cliente_id not in (None,d['cliente'].id):raise DatosInvalidos('El interesado y el cliente no coinciden.')
        t=Tarea.objects.create(**d,creada_por=request.funcionario)
        return Response(tarea(t),status=201)
    qs=Tarea.objects.filter(estado='pendiente').select_related('asignada_a').order_by('vence','id')
    if request.query_params.get('mias')=='1':qs=qs.filter(asignada_a=request.funcionario)
    return Response({'resultados':[tarea(t) for t in qs[:200]],'total':qs.count()})

@api_view(['PATCH'])
@permission_classes([EsFuncionario])
@transaction.atomic
def tarea_cambiar(request,id):
    t=Tarea.objects.select_for_update().filter(pk=id).first()
    if t is None:raise NoEncontrado('La tarea no existe.')
    if request.funcionario.id not in (t.asignada_a_id,t.creada_por_id) and not request.funcionario.puede_aprobar:raise PermisoDenegado('La tarea está a cargo de otro integrante.')
    if t.estado!='pendiente':raise EstadoInvalido('La tarea ya fue resuelta.')
    op=serializers.ChoiceField(choices=['hecha','cancelada','reasignar']).run_validation(request.data.get('accion'))
    if op=='reasignar':t.asignada_a=serializers.PrimaryKeyRelatedField(queryset=Funcionario.objects.filter(activo=True)).run_validation(request.data.get('asignada_a'))
    else:t.estado=op;t.completada_en=timezone.now() if op=='hecha' else None
    t.save();return Response(tarea(t))

@api_view(['GET','POST'])
@permission_classes([EsFuncionario])
def notas(request,id):
    if not Cliente.objects.filter(pk=id).exists():raise NoEncontrado('El cliente no existe.')
    if request.method=='POST':
        valor=serializers.CharField(min_length=3,max_length=2000).run_validation(request.data.get('texto'))
        NotaInterna.objects.create(cliente_id=id,autor=request.funcionario,texto=valor)
    qs=NotaInterna.objects.filter(cliente_id=id).select_related('autor').order_by('-id')
    return Response({'resultados':[{'id':n.id,'texto':n.texto,'autor':n.autor.nombre,'fecha':n.creada_en} for n in qs[:100]]})

@api_view(['GET'])
@permission_classes([EsFuncionario])
def avisos(request):
    qs=AvisoGestion.objects.filter(estado__in=['pendiente','preparado']).select_related('contacto','poliza__cliente','cuota__poliza__cliente','interesado','mensaje').order_by('id')
    filas=[]
    for a in qs[:200]:
        t=texto(a)
        if t:filas.append({'id':a.id,'tipo':a.tipo,'numero':a.contacto.numero,'texto':t,'estado':a.mensaje.estado_envio if a.mensaje_id else 'para_contactar'})
    return Response({'resultados':filas,'total':qs.count()})

@api_view(['POST'])
@permission_classes([EsFuncionario])
@transaction.atomic
def aviso_resolver(request,id):
    a=AvisoGestion.objects.select_for_update().filter(pk=id).first()
    if a is None:raise NoEncontrado('El aviso no existe.')
    if a.estado!='pendiente':raise EstadoInvalido('Este aviso ya se preparó o resolvió.')
    a.estado=serializers.ChoiceField(choices=['manual','cancelado']).run_validation(request.data.get('estado'))
    if a.estado=='manual' and not texto(a):raise EstadoInvalido('El aviso ya no corresponde; cancelalo.')
    a.resuelto_por=request.funcionario;a.resuelto_en=timezone.now();a.save()
    return Response({'estado':a.estado})

@api_view(['PATCH'])
@permission_classes([EsAprobador])
def configurar(request):
    activo=serializers.BooleanField().run_validation(request.data.get('automaticos'))
    ConfigGestion.objects.filter(pk=1).update(automaticos=activo)
    return Response({'automaticos':activo})

@api_view(['POST'])
@permission_classes([EsFuncionario])
def actualizar(request):return Response(procesar())

@api_view(['PATCH'])
@permission_classes([EsAprobador])
@transaction.atomic
def preferencia(request,id):
    c=ContactoWhatsapp.objects.filter(pk=id).first()
    if c is None:raise NoEncontrado('El contacto no existe.')
    c.acepta_avisos=serializers.BooleanField().run_validation(request.data.get('acepta_avisos'))
    if not c.acepta_avisos:
        from negocio.gestion_diaria import desactivar_avisos
        desactivar_avisos(c.id)
    else:c.save(update_fields=['acepta_avisos'])
    return Response({'acepta_avisos':c.acepta_avisos})
