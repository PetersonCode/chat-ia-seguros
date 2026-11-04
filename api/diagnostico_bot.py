from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from api.permisos import EsFuncionario
from datos.models import Poliza, DocumentoPoliza, DocumentoGeneral, ContactoWhatsapp, CondicionesPoliza
from negocio.errores import NoEncontrado


@api_view(['GET'])
@permission_classes([EsFuncionario])
def diagnostico(request,id):
    poliza=Poliza.objects.select_related('cliente').filter(pk=id).first()
    if poliza is None: raise NoEncontrado('La póliza no existe.')
    hoy=timezone.localdate()
    vinculos=list(DocumentoPoliza.objects.filter(poliza=poliza).select_related('documento').order_by('id'))
    documentos=[{'id':v.documento_id,'titulo':v.documento.titulo,'estado':v.documento.estado,
                 'fragmentos':v.documento.fragmentos.count()} for v in vinculos]
    problemas=[]
    condiciones=CondicionesPoliza.objects.filter(poliza=poliza).select_related('plan').first()
    if condiciones and condiciones.plan_id and condiciones.plan.compania_id != poliza.compania_id:
        problemas.append('Cambió la compañía de la póliza: seleccioná un plan de esa compañía y revisá sus condiciones.')
    if not poliza.cliente.activo: problemas.append('El cliente está inactivo.')
    if not ContactoWhatsapp.objects.filter(cliente=poliza.cliente).exists():
        problemas.append('No hay un número de WhatsApp vinculado a este cliente.')
    if poliza.estado!='vigente' or not poliza.fecha_inicio<=hoy<=poliza.fecha_vencimiento:
        problemas.append('La póliza no tiene vigencia actual; el bot no debe presentarla como cobertura activa.')
    if not documentos: problemas.append('Falta vincular las condiciones a esta póliza. Asignarle un vehículo no vincula documentos.')
    elif not any(d['estado']=='aprobado' and d['fragmentos'] for d in documentos):
        problemas.append('No hay condiciones aprobadas con contenido para esta póliza.')
    return Response({'numero_poliza':poliza.numero_poliza,'listo':not problemas,
        'problemas':problemas,'documentos':documentos,
        'disponibles':[{'id':d.id,'titulo':d.titulo,'version':d.version} for d in
            DocumentoGeneral.objects.filter(estado='aprobado').order_by('titulo','id')[:100]]})
