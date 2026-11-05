from datetime import timedelta
from decimal import Decimal
import re
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import escape
from rest_framework import serializers
from rest_framework.decorators import api_view,permission_classes
from rest_framework.response import Response
from api.permisos import EsFuncionario,EsAprobador,EsAprobadorParaEscribir
from datos.models import Cliente,Poliza,CondicionesPoliza
from datos.gestion_models import PerfilCliente,Referido,Encuesta
from negocio.errores import NoEncontrado,DatosInvalidos,EstadoInvalido
from negocio.fidelizacion import renovar,mensual

class PerfilDatos(serializers.Serializer):
    nacimiento=serializers.DateField(allow_null=True,required=False)
    comerciales=serializers.BooleanField(required=False)
    def validate_nacimiento(self,v):
        if v and (v>timezone.localdate() or v.year<1900):raise serializers.ValidationError('La fecha de nacimiento no es válida.')
        return v

@api_view(['GET','PATCH'])
@permission_classes([EsAprobadorParaEscribir])
def perfil(request,id):
    if not Cliente.objects.filter(pk=id).exists():raise NoEncontrado('El cliente no existe.')
    p=PerfilCliente.objects.filter(cliente_id=id).first()
    if request.method=='PATCH':
        s=PerfilDatos(data=request.data);s.is_valid(raise_exception=True)
        p,_=PerfilCliente.objects.update_or_create(cliente_id=id,defaults=s.validated_data)
    referidos=Referido.objects.filter(referente_id=id).select_related('referido').order_by('-id')
    return Response({'nacimiento':p.nacimiento if p else None,'comerciales':p.comerciales if p else False,
        'referidos':[{'id':r.id,'cliente':f'{r.referido.nombre} {r.referido.apellido}','estado':r.estado,'beneficio':r.beneficio} for r in referidos[:100]]})

@api_view(['POST'])
@permission_classes([EsAprobador])
@transaction.atomic
def referido_crear(request,id):
    c=Cliente.objects.filter(pk=id,activo=True).first()
    if c is None:raise NoEncontrado('El referente no existe o está inactivo.')
    r=serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.filter(activo=True)).run_validation(request.data.get('referido'))
    if r.id==id:raise DatosInvalidos('El referente y el referido deben ser distintos.')
    # Serializa por cliente referido para impedir dos beneficios por la misma persona.
    list(Cliente.objects.select_for_update().filter(pk__in=[c.id,r.id]).order_by('id'))
    if Referido.objects.filter(referido=r).exists():raise EstadoInvalido('Este cliente ya está registrado como referido.')
    obj=Referido.objects.create(referente=c,referido=r,responsable=request.funcionario)
    return Response({'id':obj.id,'estado':obj.estado},status=201)

@api_view(['PATCH'])
@permission_classes([EsAprobador])
@transaction.atomic
def referido_resolver(request,id):
    r=Referido.objects.select_for_update().filter(pk=id).first()
    if not r:raise NoEncontrado('El referido no existe.')
    if r.estado!='pendiente':raise EstadoInvalido('El beneficio ya fue resuelto.')
    r.estado=serializers.ChoiceField(choices=['otorgado','cancelado']).run_validation(request.data.get('estado'))
    r.beneficio=serializers.CharField(min_length=3,max_length=1000).run_validation(request.data.get('beneficio'))
    r.responsable=request.funcionario;r.save()
    return Response({'estado':r.estado})

class RenovarDatos(serializers.Serializer):
    prima_mensual=serializers.DecimalField(max_digits=12,decimal_places=2,min_value=Decimal('0.01'))
    fecha_vencimiento=serializers.DateField()
    conservar_condiciones=serializers.BooleanField()

@api_view(['POST'])
@permission_classes([EsAprobador])
def poliza_renovar(request,id):
    s=RenovarDatos(data=request.data);s.is_valid(raise_exception=True)
    d=s.validated_data
    p=renovar(id,request.funcionario,d['prima_mensual'],d['fecha_vencimiento'],d['conservar_condiciones'])
    return Response({'id':p.id,'numero':p.numero_poliza,'cliente_id':p.cliente_id},status=201)

@api_view(['GET'])
@permission_classes([EsFuncionario])
def reporte(request):return Response(mensual(request.query_params.get('mes',timezone.localdate().strftime('%Y-%m')),request.funcionario.puede_aprobar))

@api_view(['GET'])
@permission_classes([EsFuncionario])
def credencial(request,id):
    p=Poliza.objects.select_related('cliente','vehiculo','compania').filter(pk=id).first()
    if not p:raise NoEncontrado('La póliza no existe.')
    c=CondicionesPoliza.objects.filter(poliza=p,documento__estado='aprobado').select_related('plan').first()
    if c and c.plan_id and c.plan.compania_id!=p.compania_id:c=None
    filas={'Póliza':p.numero_poliza,'Titular':f'{p.cliente.nombre} {p.cliente.apellido}',
        'Patente':p.vehiculo.patente if p.vehiculo else 'No informada','Compañía':p.compania.nombre if p.compania else 'No informada',
        'Vigencia':f'{p.fecha_inicio:%d/%m/%Y} a {p.fecha_vencimiento:%d/%m/%Y}',
        'Estado registrado':p.estado,'Asistencia':c.asistencia if c and c.asistencia else 'No informada'}
    if request.query_params.get('formato')=='png':
        from negocio.credenciales import imagen_credencial
        r=HttpResponse(imagen_credencial(filas,timezone.localdate()),content_type='image/png')
        r['Content-Disposition']=f'attachment; filename="credencial-{p.numero_poliza}.png"';r['Cache-Control']='no-store';return r
    contenido=''
    for k,v in filas.items():
        valor=escape(str(v))
        if k=='Asistencia' and v!='No informada':valor=f'<a style="color:#cfe0f7" href="tel:{re.sub(r"[^+0-9]","",str(v))}">{valor}</a>'
        contenido+=f'<dt>{escape(k)}</dt><dd>{valor}</dd>'
    html=f'<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Credencial de contacto</title><style>body{{background:#0a2342;color:#eef3fa;font:18px system-ui;padding:20px}}main{{max-width:440px;margin:auto;background:#12315c;padding:24px;border-radius:18px}}dt{{color:#a9b8cf;font-size:14px}}dd{{margin:4px 0 18px}}small{{color:#a9b8cf}}</style><main><h1>Seguros Castaño</h1><h2>Credencial de contacto</h2><dl>{contenido}</dl><small>Datos de contacto y referencia del contrato. Consultá el certificado de cobertura emitido por tu compañía para la documentación del seguro. Generada el {timezone.localdate():%d/%m/%Y}.</small></main></html>'
    r=HttpResponse(html,content_type='text/html; charset=utf-8');r['Content-Disposition']=f'attachment; filename="credencial-{p.numero_poliza}.html"';r['Cache-Control']='no-store';return r

@api_view(['GET'])
@permission_classes([EsFuncionario])
def encuestas(request):
    qs=Encuesta.objects.filter(puntaje__isnull=False).select_related('contacto','cliente').order_by('-respondida_en')
    return Response({'resultados':[{'id':e.id,'cliente':f'{e.cliente.nombre} {e.cliente.apellido}' if e.cliente_id else e.contacto.numero,'cliente_id':e.cliente_id,'numero':e.contacto.numero,'puntaje':e.puntaje,'fecha':e.respondida_en} for e in qs[:100]],'total':qs.count()})
