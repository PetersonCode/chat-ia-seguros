"""Agenda operativa y avisos; no emite pólizas ni modifica saldos."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.db import transaction
from django.db.models import Q, Sum, Max, F, Min
from django.db.models.functions import Greatest, Coalesce
from django.utils import timezone
from datos.models import Poliza, Cuota, Interesado, Siniestro, Conversacion, Mensaje, ContactoWhatsapp, RecordatorioPoliza
from datos.gestion_models import AvisoGestion, ConfigGestion, Tarea
from datos.selectors import bandeja
from negocio.recordatorios import texto_recordatorio
from negocio.bot.plantillas import formatear_monto, formatear_fecha
from negocio.reglas import ventana_24h_abierta
from negocio.whatsapp import enviar_pendientes

def pendientes():
    return Interesado.objects.exclude(estado__in=['emitida','perdida']).filter(Q(proximo_contacto__lte=timezone.localdate())|Q(proximo_contacto__isnull=True)).select_related('responsable','contacto','cliente').order_by(F('proximo_contacto').asc(nulls_first=True),'id')

def resumen():
    hoy=timezone.localdate()
    renovaciones=Poliza.objects.filter(cliente__activo=True,tipo_seguro__codigo='automotor',estado='vigente',gestion_renovada__isnull=True,fecha_vencimiento__range=(hoy,hoy+timedelta(days=30))).select_related('cliente','vehiculo').order_by('fecha_vencimiento','id')
    morosos=Cuota.objects.filter(estado__in=['pendiente','vencida'],vencimiento__lt=hoy,poliza__cliente__activo=True,poliza__tipo_seguro__codigo='automotor').exclude(poliza__estado='dada_de_baja').values('poliza_id','poliza__numero_poliza','poliza__cliente_id','poliza__cliente__nombre','poliza__cliente__apellido').annotate(importe=Sum('importe'),desde=Min('vencimiento')).order_by('desde','poliza_id')
    siniestros=Siniestro.objects.exclude(estado__in=['cerrado','rechazado']).annotate(ultima=Greatest('creado_en',Coalesce(Max('historial__fecha'),F('creado_en')),Coalesce(Max('adjuntos__creado_en'),F('creado_en')))).filter(ultima__lte=timezone.now()-timedelta(days=7)).order_by('ultima','id')
    chats=bandeja(estado='abierta').filter(ultimo_emisor_atencion='cliente',ultima_atencion_en__lte=timezone.now()-timedelta(hours=2))
    leads=pendientes()
    return {'fecha':str(hoy),'automaticos':ConfigGestion.objects.get(pk=1).automaticos,
      'cantidades':{'renovaciones':renovaciones.count(),'morosos':morosos.count(),'interesados':leads.count(),'siniestros':siniestros.count(),'sin_respuesta':chats.count()},
      'renovaciones':[{'id':p.id,'cliente_id':p.cliente_id,'numero':p.numero_poliza,'cliente':f'{p.cliente.nombre} {p.cliente.apellido}','vence':str(p.fecha_vencimiento),'patente':p.vehiculo.patente if p.vehiculo else ''} for p in renovaciones[:20]],
      'morosos':list(morosos[:20]),
      'interesados':[{'id':i.id,'nombre':f'{i.cliente.nombre} {i.cliente.apellido}' if i.cliente_id else f'{i.nombre} {i.apellido or ""}'.strip(),'fecha':str(i.proximo_contacto or hoy),'responsable':i.responsable.nombre if i.responsable else 'Sin asignar'} for i in leads[:20]],
      'siniestros':[{'id':s.id,'numero':s.numero_siniestro,'desde':s.ultima.isoformat()} for s in siniestros[:20]],
      'sin_respuesta':[{'id':c.id,'numero':c.contacto.numero,'desde':c.ultima_atencion_en.isoformat()} for c in chats[:20]]}

def candidatos(hoy):
    from negocio.fidelizacion import extras
    yield from extras(hoy)
    polizas=Poliza.objects.filter(cliente__activo=True,tipo_seguro__codigo='automotor',estado='vigente',gestion_renovada__isnull=True,fecha_vencimiento__in=[hoy+timedelta(days=n) for n in (30,7,1,0)])
    for p in polizas:
        for c in p.cliente.contactos.filter(acepta_avisos=True):
            yield dict(clave=f'renovacion/{p.id}/{p.fecha_vencimiento}/{hoy}',tipo='renovacion',contacto=c,poliza=p)
    cuotas=Cuota.objects.filter(estado__in=['pendiente','vencida'],poliza__cliente__activo=True,poliza__tipo_seguro__codigo='automotor',vencimiento__in=[hoy+timedelta(days=n) for n in (3,0,-3,-7,-14)]).exclude(poliza__estado='dada_de_baja')
    for q in cuotas.select_related('poliza__cliente'):
        for c in q.poliza.cliente.contactos.filter(acepta_avisos=True):
            yield dict(clave=f'cuota/{q.id}/{hoy}',tipo='cuota',contacto=c,poliza=q.poliza,cuota=q)
    for i in pendientes().filter(contacto__acepta_avisos=True,proximo_contacto__isnull=False):
        yield dict(clave=f'seguimiento/{i.id}/{i.proximo_contacto}',tipo='seguimiento',contacto=i.contacto,interesado=i)

def texto(aviso):
    if not aviso.contacto.acepta_avisos:return None
    if aviso.contacto.cliente_id and not aviso.contacto.cliente.activo:return None
    if aviso.tipo=='cumpleanos':
        from datos.gestion_models import PerfilCliente
        p=PerfilCliente.objects.filter(cliente_id=aviso.contacto.cliente_id,comerciales=True,cliente__activo=True).first()
        if not p or not p.nacimiento or (p.nacimiento.month,p.nacimiento.day)!=(timezone.localdate().month,timezone.localdate().day):return None
        return f'¡Feliz cumpleaños, {p.cliente.nombre}! Te saludamos de parte de todo el equipo de Seguros Castaño.'
    if aviso.tipo=='encuesta':
        if aviso.encuesta.puntaje is not None:return None
        if aviso.encuesta.cliente_id and aviso.encuesta.cliente_id!=aviso.contacto.cliente_id:return None
        return '¿Cómo fue tu atención en Seguros Castaño? Respondé «Encuesta 1» (muy mala) a «Encuesta 5» (muy buena). Es opcional. ¡Gracias!'
    if aviso.poliza_id and (not aviso.poliza.cliente.activo or aviso.poliza.estado=='dada_de_baja' or aviso.contacto.cliente_id!=aviso.poliza.cliente_id):return None
    if aviso.tipo=='renovacion_confirmada':
        r=aviso.poliza.gestion_origen
        gracias=' ¡Gracias por renovar a tiempo!' if timezone.localtime(r.creada_en).date()<=r.origen.fecha_vencimiento else ''
        return f'Registramos la renovación: póliza {aviso.poliza.numero_poliza}, vigencia del {formatear_fecha(aviso.poliza.fecha_inicio)} al {formatear_fecha(aviso.poliza.fecha_vencimiento)}.{gracias} Seguros Castaño.'
    if aviso.tipo=='renovacion':
        from datos.gestion_models import Renovacion
        if Renovacion.objects.filter(origen_id=aviso.poliza_id).exists():return None
        if aviso.poliza.fecha_vencimiento<timezone.localdate():return None
        return texto_recordatorio(aviso.poliza)[0]
    if aviso.tipo=='cuota':
        q=aviso.cuota
        if q.estado=='pagada' or hasattr(q,'pago'):return None
        verbo='venció' if q.vencimiento<timezone.localdate() else 'vence'
        return f'Hola {q.poliza.cliente.nombre}, tu cuota de la póliza {q.poliza.numero_poliza} {verbo} el {formatear_fecha(q.vencimiento)}. Importe pendiente de esta cuota: {formatear_monto(q.importe)}. Si ya pagaste, escribinos para revisar el comprobante. Seguros Castaño.'
    i=aviso.interesado
    if i.estado in ('emitida','perdida') or i.contacto_id!=aviso.contacto_id or i.proximo_contacto is None or i.proximo_contacto>timezone.localdate():return None
    if aviso.clave!=f'seguimiento/{i.id}/{i.proximo_contacto}':return None
    return f'Hola {i.nombre}, te escribimos de Seguros Castaño para continuar tu consulta por el seguro de tu vehículo. ¿Querés que avancemos con la cotización?'

@transaction.atomic
def procesar(ahora=None,dry_run=False):
    ahora=ahora or timezone.now(); hoy=ahora.astimezone(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    nuevos=list(candidatos(hoy))
    if dry_run:return {'candidatos':len(nuevos),'escrituras':0}
    from negocio.fidelizacion import programar_encuestas
    programar_encuestas()
    for d in nuevos:AvisoGestion.objects.get_or_create(clave=d['clave'],defaults=d)
    config=ConfigGestion.objects.get(pk=1)
    contadores={'candidatos':len(nuevos),'preparados':0,'cancelados':0}
    avisos=AvisoGestion.objects.select_for_update(of=('self',)).filter(estado='pendiente').select_related('contacto','poliza__cliente','cuota__poliza__cliente','interesado').order_by('id')
    for a in avisos:
        t=texto(a)
        if not t or a.creado_en<ahora-timedelta(days=7):
            a.estado='cancelado';a.save(update_fields=['estado']);contadores['cancelados']+=1;continue
        if not config.automaticos or not 9<=ahora.astimezone(ZoneInfo('America/Argentina/Buenos_Aires')).hour<20:continue
        # Serializa todos los avisos de este contacto y limita a uno por día.
        ContactoWhatsapp.objects.select_for_update().get(pk=a.contacto_id)
        if AvisoGestion.objects.filter(contacto_id=a.contacto_id,resuelto_en__date=hoy,estado__in=['preparado','manual']).exists() or RecordatorioPoliza.objects.filter(contacto_id=a.contacto_id,fecha_aviso=hoy).exists():continue
        c=Conversacion.objects.select_for_update().filter(contacto_id=a.contacto_id,estado='abierta',modo='bot').first()
        if not c or not ventana_24h_abierta(c.ultimo_mensaje_cliente_en,ahora):continue
        a.mensaje=Mensaje.objects.create(conversacion=c,direccion='saliente',emisor='bot',texto=t,estado_envio='pendiente_envio',payload={'aviso_gestion_id':a.id})
        a.estado='preparado';a.resuelto_en=ahora;a.save(update_fields=['mensaje','estado','resuelto_en'])
        contadores['preparados']+=1
        transaction.on_commit(lambda id=c.id:enviar_pendientes(id),robust=True)
    return contadores

@transaction.atomic
def desactivar_avisos(contacto_id):
    avisos=list(AvisoGestion.objects.select_for_update().filter(contacto_id=contacto_id,estado__in=['pendiente','preparado']).order_by('id'))
    Mensaje.objects.filter(pk__in=[a.mensaje_id for a in avisos if a.mensaje_id],estado_envio='pendiente_envio').update(estado_envio='descartado')
    AvisoGestion.objects.filter(pk__in=[a.id for a in avisos]).update(estado='cancelado')
    ContactoWhatsapp.objects.filter(pk=contacto_id).update(acepta_avisos=False)

def validar_antes_de_enviar(mensaje):
    """También se controla al reintentar: no se manda un saldo que ya cambió."""
    id=(mensaje.payload or {}).get('aviso_gestion_id')
    a=AvisoGestion.objects.filter(pk=id,mensaje=mensaje,estado='preparado',contacto_id=mensaje.conversacion.contacto_id).first()
    if not a:
        mensaje.estado_envio='descartado';mensaje.save(update_fields=['estado_envio']);return False
    t=texto(a)
    if not t:
        mensaje.estado_envio='descartado';mensaje.save(update_fields=['estado_envio']);return False
    if not ConfigGestion.objects.get(pk=1).automaticos or not 9<=timezone.localtime().hour<20:return False
    if mensaje.texto!=t:mensaje.texto=t;mensaje.save(update_fields=['texto'])
    return True
