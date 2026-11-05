from datetime import datetime,timedelta
from uuid import uuid4
from django.db import transaction
from django.utils import timezone
from django.db.models import Avg
from datos.models import Poliza,CondicionesPoliza,ConsultaBot,Siniestro,AccionPendiente
from datos.gestion_models import Renovacion,PerfilCliente,Encuesta,AvisoGestion
from negocio.errores import NoEncontrado,EstadoInvalido,DatosInvalidos
from negocio.polizas import alta_poliza
from negocio.documentos import crear_documento,aprobar_documento
from negocio.coberturas import vincular_documento
from negocio.seguridad import registrar
from negocio.comisiones import reporte_comisiones

@transaction.atomic
def renovar(id,f,prima,fin,conservar=True):
    p=Poliza.objects.select_for_update().filter(pk=id).first()
    if p is None:raise NoEncontrado('La póliza no existe.')
    if p.estado not in ('vigente','vencida') or Renovacion.objects.filter(origen=p).exists():raise EstadoInvalido('La póliza ya se renovó o no admite renovación.')
    if not p.vehiculo_id or not p.compania_id:raise DatosInvalidos('Completá vehículo y compañía antes de renovar.')
    inicio=p.fecha_vencimiento+timedelta(days=1)
    nueva=alta_poliza(p.cliente_id,tipo_seguro='automotor',cobertura=p.cobertura,fecha_inicio=inicio,fecha_vencimiento=fin,prima_mensual=prima,vehiculo_id=p.vehiculo_id,compania_id=p.compania_id)
    Renovacion.objects.create(origen=p,nueva=nueva,responsable=f)
    condiciones=CondicionesPoliza.objects.filter(poliza=p,documento__estado='aprobado').select_related('documento','plan').first()
    if conservar and condiciones and condiciones.plan_id and condiciones.plan.compania_id!=p.compania_id:raise DatosInvalidos('Revisá las condiciones: el plan anterior no coincide con la compañía actual.')
    if conservar and condiciones:
        contenido=' '.join(condiciones.documento.fragmentos.order_by('orden').values_list('texto',flat=True))
        doc=crear_documento(titulo=f'Condiciones cargadas en póliza {nueva.numero_poliza}',version=uuid4().hex,referencia='Condiciones revisadas al registrar la renovación.',contenido=contenido,funcionario_id=f.id)
        aprobar_documento(doc.id,f.id);vincular_documento(nueva.numero_poliza,doc.id,f.id)
        CondicionesPoliza.objects.create(poliza=nueva,documento=doc,actualizado_por=f,plan_id=condiciones.plan_id,plan_version=condiciones.plan_version,**{k:getattr(condiciones,k) for k in ('cubre','no_cubre','limites','asistencia')})
    for c in p.cliente.contactos.filter(acepta_avisos=True):
        AvisoGestion.objects.get_or_create(clave=f'renovada/{nueva.id}/{c.id}',defaults={'tipo':'renovacion_confirmada','contacto':c,'poliza':nueva})
    from django.contrib.auth import get_user_model
    usuario=get_user_model().objects.filter(username__iexact=f.email).values_list('id',flat=True).first()
    registrar('registrar_renovacion',f'poliza/{p.id}/nueva/{nueva.id}',usuario_id=usuario)
    return nueva

def extras(hoy):
    for perfil in PerfilCliente.objects.filter(comerciales=True,cliente__activo=True,nacimiento__month=hoy.month,nacimiento__day=hoy.day).select_related('cliente'):
        for c in perfil.cliente.contactos.filter(acepta_avisos=True):yield dict(clave=f'cumpleanos/{c.id}/{hoy.year}',tipo='cumpleanos',contacto=c)

def programar_encuestas():
    desde=timezone.now()-timedelta(days=7)
    consultas=ConsultaBot.objects.filter(estado='cerrado',fecha_hora__gte=desde,contacto__isnull=False).exclude(tipo_consulta__codigo__in=['saludo','agradecimiento','ajeno','baja_avisos','encuesta_respuesta','prompt_injection']).select_related('contacto')
    eventos=[(c.contacto,f'consulta/{c.id}') for c in consultas]
    for s in Siniestro.objects.filter(estado='cerrado',historial__estado_nuevo='cerrado',historial__fecha__gte=desde).select_related('poliza__cliente').distinct():
        eventos.extend((c,f'siniestro/{s.id}') for c in s.poliza.cliente.contactos.all())
    for c,ref in eventos:
        if not c.acepta_avisos or Encuesta.objects.filter(contacto=c,creada_en__gte=desde).exists():continue
        e,_=Encuesta.objects.get_or_create(referencia=ref,defaults={'contacto':c,'cliente_id':c.cliente_id})
        AvisoGestion.objects.get_or_create(clave=f'encuesta/{e.id}',defaults={'tipo':'encuesta','contacto':c,'encuesta':e})

def responder_encuesta(contacto,puntaje):
    with transaction.atomic():
        e=Encuesta.objects.select_for_update().filter(contacto=contacto,puntaje__isnull=True,creada_en__gte=timezone.now()-timedelta(days=7)).order_by('-id').first()
        if not e:return 'No hay una encuesta pendiente para este número. ¿En qué te puedo ayudar?'
        if e.cliente_id and e.cliente_id!=contacto.cliente_id:return 'La encuesta anterior ya no está disponible para este contacto. ¿En qué te puedo ayudar?'
        e.puntaje=puntaje;e.respondida_en=timezone.now();e.save()
    return 'Gracias por responder. Tu opinión quedó registrada para el equipo de Seguros Castaño.'

def mensual(mes,ver_comision):
    try:
        inicio=datetime.strptime(mes,'%Y-%m').date()
        if len(mes)!=7:raise ValueError()
    except (ValueError,TypeError):raise DatosInvalidos('Usá un mes con formato AAAA-MM.')
    siguiente=(inicio.replace(day=28)+timedelta(days=4)).replace(day=1);fin=siguiente-timedelta(days=1)
    comisiones=reporte_comisiones(inicio,fin)
    return {'mes':mes,'nuevas':Poliza.objects.filter(creado_en__date__gte=inicio,creado_en__date__lt=siguiente,gestion_origen__isnull=True).count(),
        'bajas':AccionPendiente.objects.filter(tipo_accion='baja_poliza',estado='ejecutada',resuelta_en__date__range=(inicio,fin)).count(),
        'renovadas':Renovacion.objects.filter(creada_en__date__range=(inicio,fin)).count(),
        'cobrado':comisiones['totales']['base_cobros'],'comision':comisiones['totales']['sobre_cobros'] if ver_comision else None,
        'sin_porcentaje':comisiones['sin_porcentaje'],'encuestas':Encuesta.objects.filter(respondida_en__date__range=(inicio,fin)).aggregate(promedio=Avg('puntaje'))}

def credencial_chat(conversacion):
    cliente=conversacion.contacto.cliente
    if not cliente or not cliente.activo:return ('No hay pólizas vinculadas a este número para preparar una credencial de contacto.',set())
    hoy=timezone.localdate()
    polizas=Poliza.objects.filter(cliente=cliente,tipo_seguro__codigo='automotor',estado='vigente',fecha_inicio__lte=hoy,fecha_vencimiento__gte=hoy).select_related('vehiculo','compania').order_by('id')
    lineas=['Credencial de contacto · Seguros Castaño'];verificados=set()
    for p in polizas[:10]:
        c=CondicionesPoliza.objects.filter(poliza=p,documento__estado='aprobado').select_related('plan').first()
        if c and c.plan_id and c.plan.compania_id!=p.compania_id:c=None
        fecha=p.fecha_vencimiento.strftime('%d/%m/%Y');patente=p.vehiculo.patente if p.vehiculo else 'No informada'
        lineas.append(f'Póliza: {p.numero_poliza}\nPatente: {patente}\nCompañía: {p.compania.nombre if p.compania else "No informada"}\nVigencia hasta: {fecha}\nAsistencia: {c.asistencia if c and c.asistencia else "No informada"}')
        verificados.update([fecha,p.numero_poliza,patente])
    if len(lineas)==1:return ('No encuentro una póliza vigente vinculada a este número para generar la credencial.',set())
    lineas.append('Conservá también el certificado de cobertura emitido por tu compañía.')
    return ('\n\n'.join(lineas),verificados)
