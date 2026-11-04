"""Coberturas del cliente reconocido: selección temporal y fuentes explícitas."""
import re
from datetime import timedelta
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from datos.models import (ContextoCobertura, Conversacion, DocumentoPoliza,
                          DocumentoGeneral, EstadoDocumento, Poliza)
from negocio.documentos import _aprobador, _normalizar, buscar_fragmentos
from negocio.errores import DatosInvalidos, NoEncontrado, EstadoInvalido
from negocio.seguridad import registrar


@transaction.atomic
def vincular_documento(numero, documento_id, funcionario_id):
    funcionario = _aprobador(funcionario_id)
    poliza = Poliza.objects.filter(numero_poliza=numero.strip()).first()
    if poliza is None:
        raise NoEncontrado('La póliza indicada no existe.')
    if not DocumentoGeneral.objects.filter(pk=documento_id).exists():
        raise NoEncontrado('El documento no existe.')
    vinculo, _ = DocumentoPoliza.objects.get_or_create(poliza=poliza, documento_id=documento_id,
                                                    defaults={'vinculado_por': funcionario})
    usuario_id = get_user_model().objects.filter(username__iexact=funcionario.email).values_list('id',flat=True).first()
    registrar('vincular_documento', f'funcionario/{funcionario.pk}/poliza/{poliza.id}/documento/{documento_id}', usuario_id=usuario_id)
    return vinculo


def cliente_reconocido(conversacion):
    cliente = conversacion.contacto.cliente
    return cliente if cliente and cliente.activo and conversacion.estado == 'abierta' else None


def contexto_vigente(conversacion):
    cliente = cliente_reconocido(conversacion)
    if cliente is None:
        return None
    return ContextoCobertura.objects.filter(conversacion=conversacion, cliente=cliente,
        expira_en__gt=timezone.now()).first()


@transaction.atomic
def contexto_automatico(conversacion):
    # La asociación número-cliente viene de la cartera, no de un DNI enviado por chat.
    cliente = cliente_reconocido(conversacion)
    if cliente is None:
        return None
    contexto = contexto_vigente(conversacion)
    if contexto:
        return contexto
    ahora = timezone.now()
    contexto, _ = ContextoCobertura.objects.update_or_create(conversacion=conversacion, defaults={
        'cliente': cliente, 'creado_en': ahora, 'expira_en': ahora+timedelta(hours=4),
        'poliza': None, 'pregunta': '',
    })
    return contexto


def es_personal(texto):
    return bool(re.search(r'\b(mi|mis|tengo|me cubre|estoy asegurad[oa]|pol-\d+)\b', _normalizar(texto)))


def es_seleccion(texto, conversacion):
    contexto = contexto_vigente(conversacion)
    if not contexto or not contexto.pregunta:
        return False
    # Solo respuestas breves que parecen una selección; no intercepta urgencias.
    return len(texto) <= 100 and bool(re.search(r'\b(auto|automotor|coche|hogar|casa|moto|vida|comercio|pol-\d+)\b', _normalizar(texto)))


def responder_cobertura(texto, conversacion):
    """Devuelve texto y fragmento, o None cuando corresponde búsqueda general."""
    contexto = contexto_vigente(conversacion)
    seguimiento = bool(contexto and contexto.pregunta)
    general = bool(re.search(r'\b(?:en general|informacion general|tipos de seguros)\b', _normalizar(texto)))
    if general or (not es_personal(texto) and not seguimiento and not (contexto and contexto.poliza_id)):
        return None
    if contexto is None:
        contexto = contexto_automatico(conversacion)
    if contexto is None:
        return ('No tengo una póliza automotor vinculada a este número. Puedo darte información general o registrar tu consulta; no envíes DNI ni contraseñas por el chat.', None)
    hoy = timezone.localdate()
    polizas = list(Poliza.objects.filter(cliente_id=contexto.cliente_id, tipo_seguro__codigo='automotor', estado='vigente',
        fecha_inicio__lte=hoy, fecha_vencimiento__gte=hoy).select_related('tipo_seguro').order_by('id'))
    texto_norm = _normalizar(texto)
    numeros = re.findall(r'POL-\d+', texto.upper())
    tipos = {'auto': 'automotor', 'coche': 'automotor', 'vehiculo': 'automotor', 'automotor': 'automotor',
             'hogar': 'hogar', 'casa': 'hogar', 'moto': 'moto', 'vida': 'vida', 'comercio': 'comercio'}
    tipos_pedidos = {valor for palabra, valor in tipos.items() if re.search(r'\b'+palabra+r'\b', texto_norm)}
    opciones = polizas
    if numeros:
        opciones = [p for p in opciones if p.numero_poliza in numeros]
    elif tipos_pedidos:
        opciones = [p for p in opciones if p.tipo_seguro.codigo in tipos_pedidos]
    elif contexto.poliza_id and not seguimiento:
        opciones = [p for p in opciones if p.pk == contexto.poliza_id]
    if not opciones:
        return ('No encuentro una póliza automotor vigente tuya que coincida. Un asesor debe revisar la consulta.', None)
    if len(opciones) != 1:
        contexto.pregunta = (contexto.pregunta or texto)[:300]
        contexto.save(update_fields=['pregunta'])
        listado = '\n'.join(f'• {p.numero_poliza}: {p.tipo_seguro.nombre}' for p in opciones)
        return (f'Tenés varias pólizas automotor. ¿Cuál querés consultar? Respondé con el tipo o el número:\n{listado}', None)
    poliza = opciones[0]
    pregunta = contexto.pregunta or texto
    contexto.poliza = poliza
    contexto.pregunta = ''
    contexto.save(update_fields=['poliza', 'pregunta'])
    ids = list(DocumentoPoliza.objects.filter(poliza=poliza,
        documento__estado=EstadoDocumento.APROBADO).values_list('documento_id', flat=True))
    if not ids:
        return ('La póliza seleccionada no tiene condiciones aprobadas vinculadas. Un asesor debe revisarlas; no puedo confirmar coberturas con documentos generales.', None)
    # La pregunta general pide un extracto; nunca se usa una fuente ajena.
    consulta = pregunta
    if re.fullmatch(r'(?:que (?:cubre|incluye|protege) (?:mi |el |la )?(?:poliza|seguro|cobertura)|cual es mi cobertura|mi cobertura)[?¿ ]*', _normalizar(pregunta).lstrip('¿')):
        consulta = 'cobertura'
    encontrado = buscar_fragmentos(consulta, documentos_ids=ids, incluir_vinculados=True)
    if not encontrado['respaldo_suficiente']:
        return ('No encuentro un pasaje suficiente en las condiciones de tu póliza. Un asesor debe confirmar esa consulta.', None)
    fuente = encontrado['resultados'][0]
    return (f'Condiciones vinculadas a tu póliza {poliza.numero_poliza}. Fuente: {fuente["titulo"]}, versión {fuente["version"]}.\n“{fuente["pasaje"]}”\nEste es un extracto de tus condiciones. Aplican los límites y exclusiones indicados; si querés denunciar un hecho, contame qué ocurrió.', fuente['fragmento_id'])
