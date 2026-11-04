"""Recordatorios elegidos por un asesor; no hay envíos automáticos programados."""
from decimal import Decimal
from datetime import timedelta
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, Sum, Min, Case, When, Value, IntegerField, DecimalField, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from datos.models import (Poliza, VPolizaResumen, ContactoWhatsapp, Conversacion,
                          Mensaje, RecordatorioPoliza, Cuota)
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado
from negocio.supervision import _funcionario
from negocio.reglas import ventana_24h_abierta
from negocio.bot.plantillas import formatear_fecha, formatear_monto
from negocio.whatsapp import enviar_pendientes


def polizas_por_vencer(dias=None, incluir_vencidas=False, q=''):
    hoy = timezone.localdate()
    resumen = VPolizaResumen.objects.filter(poliza_id=OuterRef('pk'))
    ultimo = RecordatorioPoliza.objects.filter(poliza_id=OuterRef('pk')).order_by('-creado_en', '-id')
    atrasos = Cuota.objects.filter(poliza_id=OuterRef('pk'), estado__in=['pendiente','vencida'],
        vencimiento__lt=hoy).values('poliza_id').annotate(total=Sum('importe'),fecha=Min('vencimiento'))
    polizas = Poliza.objects.filter(cliente__activo=True, tipo_seguro__codigo='automotor',
        estado__in=['vigente', 'vencida'] if incluir_vencidas else ['vigente'],
        fecha_vencimiento__gte=hoy-timedelta(days=30) if incluir_vencidas else hoy
    ).select_related('cliente').annotate(
        saldo=Subquery(resumen.values('saldo_pendiente')[:1]),
        proxima_cuota=Subquery(resumen.values('proximo_vencimiento_pago')[:1]),
        ultimo_recordatorio=Subquery(ultimo.values('creado_en')[:1]),
        saldo_vencido=Coalesce(Subquery(atrasos.values('total')[:1]),Value(Decimal('0')),
                              output_field=DecimalField(max_digits=12,decimal_places=2)),
        primera_cuota_vencida=Subquery(atrasos.values('fecha')[:1]),
    )
    if dias is not None:
        polizas = polizas.filter(fecha_vencimiento__lte=hoy+timedelta(days=dias))
    if q:
        polizas = polizas.filter(Q(numero_poliza__icontains=q) | Q(cliente__nombre__icontains=q)
            | Q(cliente__apellido__icontains=q) | Q(bien_asegurado__icontains=q))
    return polizas.annotate(prioridad_pago=Case(When(saldo_vencido__gt=0,then=Value(0)),
        default=Value(1),output_field=IntegerField())).order_by('prioridad_pago',
        F('primera_cuota_vencida').asc(nulls_last=True),'fecha_vencimiento','id')


def poliza_habilitada(poliza_id, bloquear=False):
    qs = Poliza.objects.select_for_update() if bloquear else Poliza.objects
    poliza = qs.filter(pk=poliza_id).first()
    if poliza is None:
        raise NoEncontrado('La póliza no existe.')
    if (not poliza.cliente.activo or poliza.tipo_seguro.codigo != 'automotor'
        or poliza.estado not in ('vigente','vencida')):
        raise EstadoInvalido('Esta póliza no admite recordatorios.')
    return poliza


def texto_recordatorio(poliza):
    dias = (poliza.fecha_vencimiento-timezone.localdate()).days
    if dias < 0:
        plazo = f'venció hace {abs(dias)} día' + ('s' if dias != -1 else '')
    elif dias == 0:
        plazo = 'vence hoy'
    elif dias == 1:
        plazo = 'vence mañana'
    else:
        plazo = f'vence en {dias} días'
    saldo = VPolizaResumen.objects.get(poliza_id=poliza.pk).saldo_pendiente or Decimal('0')
    vencido = Cuota.objects.filter(poliza=poliza,estado__in=['pendiente','vencida'],
        vencimiento__lt=timezone.localdate()).aggregate(total=Sum('importe'))['total'] or Decimal('0')
    atraso = f'De ese total, {formatear_monto(vencido)} corresponde a cuotas vencidas.\n' if vencido>0 else ''
    texto = (f'Hola {poliza.cliente.nombre}, te recordamos que tu póliza {poliza.numero_poliza} '
             f'{plazo} ({formatear_fecha(poliza.fecha_vencimiento)}).\n'
             f'Saldo pendiente de esta póliza: {formatear_monto(saldo)}.\n'
             f'{atraso}Si ya realizaste el pago o querés consultar la renovación, escribinos. Seguros Castaño.')
    return texto, saldo


def conversacion_disponible(contacto):
    conversacion = Conversacion.objects.filter(contacto=contacto, estado='abierta').first()
    if conversacion and ventana_24h_abierta(conversacion.ultimo_mensaje_cliente_en, timezone.now()):
        return conversacion
    return None


def preparar_recordatorio(poliza_id, contacto_id=None):
    poliza = poliza_habilitada(poliza_id)
    contactos = list(ContactoWhatsapp.objects.filter(cliente_id=poliza.cliente_id).order_by('id'))
    if contacto_id is None:
        contacto = contactos[0] if len(contactos)==1 else None
    else:
        contacto = next((c for c in contactos if c.pk==contacto_id), None)
        if contacto is None:
            raise DatosInvalidos('El número seleccionado no pertenece al cliente de la póliza.')
    texto, saldo = texto_recordatorio(poliza)
    anterior = RecordatorioPoliza.objects.filter(poliza=poliza, contacto=contacto,
        fecha_aviso=timezone.localdate()).select_related('mensaje').first() if contacto else None
    return poliza, contactos, contacto, texto, saldo, anterior


@transaction.atomic
def enviar_recordatorio(poliza_id, contacto_id, funcionario_id, canal='api'):
    funcionario = _funcionario(funcionario_id, aprobador=False)
    poliza = poliza_habilitada(poliza_id, bloquear=True)
    _, _, contacto, texto, saldo, anterior = preparar_recordatorio(poliza.pk, contacto_id)
    if anterior:
        return anterior, False
    if canal not in ('api','manual'):
        raise DatosInvalidos('Canal inválido.')
    conversacion = None
    if canal=='api':
        # Mismo lock que usa el envío: una toma o cambio de estado no se intercala.
        conversacion = Conversacion.objects.select_for_update().filter(
            contacto=contacto, estado='abierta').first()
        if not conversacion or not ventana_24h_abierta(conversacion.ultimo_mensaje_cliente_en, timezone.now()):
            raise EstadoInvalido('La ventana de WhatsApp está cerrada. Usá el texto preparado para contactar manualmente.',
                                 codigo='ventana_24h_cerrada')
    recordatorio = RecordatorioPoliza.objects.create(poliza=poliza, contacto=contacto,
        funcionario=funcionario, fecha_aviso=timezone.localdate(),
        fecha_vencimiento=poliza.fecha_vencimiento, saldo_pendiente=saldo, texto=texto, canal=canal)
    if canal=='api':
        mensaje = Mensaje.objects.create(conversacion=conversacion, direccion='saliente',
            emisor='funcionario', funcionario=funcionario, texto=texto, estado_envio='pendiente_envio',
            payload={'recordatorio_poliza_id':recordatorio.pk})
        recordatorio.mensaje = mensaje
        recordatorio.save(update_fields=['mensaje'])
        transaction.on_commit(lambda: enviar_pendientes(conversacion.pk))
    return recordatorio, True
