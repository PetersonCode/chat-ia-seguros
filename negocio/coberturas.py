"""Coberturas del cliente reconocido: selección temporal y fuentes explícitas."""
import re
from datetime import timedelta
from django.db import transaction
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from datos.models import (ContextoCobertura, Conversacion, DocumentoPoliza,
    DocumentoGeneral, EstadoDocumento, Poliza, FragmentoDocumento, CondicionesPoliza)
from negocio.documentos import _aprobador, _normalizar, _terminos, buscar_fragmentos, puntuar_fragmento
from negocio.errores import DatosInvalidos, NoEncontrado, EstadoInvalido
from negocio.seguridad import registrar

SIN_CLIENTE = 'No tengo una póliza automotor vinculada a este número. Puedo darte información general o registrar tu consulta; no envíes DNI ni contraseñas por el chat.'
SIN_POLIZA = 'No encuentro una póliza automotor vigente tuya que coincida. Un asesor debe revisar la consulta.'
SIN_CONDICIONES = 'La póliza seleccionada no tiene condiciones aprobadas vinculadas. Un asesor debe revisarlas; no puedo confirmar coberturas con documentos generales.'
SIN_PASAJE = 'No encuentro un pasaje suficiente en las condiciones de tu póliza. Un asesor debe confirmar esa consulta.'
AVISOS_COBERTURA = (SIN_CLIENTE, SIN_POLIZA, SIN_CONDICIONES, SIN_PASAJE)

# Se quita la formulación de la pregunta, no el tema del contrato. Así
# «cubre inundación» exige un pasaje sobre inundación, no la palabra «cubre».
FORMULACION = frozenset('''cobertura automotor plan contratada contratado tiene
    estoy esta ante contra frente pasa pasaria puede podria ser tener entrada entra
    dano danos daño daños danio danios pagan paga pagado cae caen delantero trasero
    mostrame mostra mostrar contame contar explica explicame saber queria favor
    hola buenas buen dia amigo denunciar nada solo dice lo al me prestacion
    tu tus esa ese del vehicular tipo tipos cuales son
    consultar consulto pregunta preguntar quisiera queria seria cuanto cuanta cuantos
    tambien porque mio mia ustedes uds hay tienen cubren cubre eso esto ahi che ok dale
    gracias por favor mi'''.split())


def _tema_consultado(texto, excluir=frozenset()):
    """Los conceptos que la respuesta tiene que respaldar, sin relleno.

    `excluir`: palabras que identifican la póliza y no son un riesgo (marca,
    modelo, patente): «¿q me cubre el seguro del c3?» pregunta por la cobertura,
    no por la palabra «c3».
    """
    from negocio.bot.clasificador import normalizar_mensaje

    return _terminos(normalizar_mensaje(texto)) - FORMULACION - set(excluir)


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
    return bool(re.search(r'\b(mi|mis|tengo|me cubre|me ampara|me pagan|estoy cubiert[oa]|estoy asegurad[oa]|pol-\d+)\b', _normalizar(texto)))


def es_seleccion(texto, conversacion):
    contexto = contexto_vigente(conversacion)
    if not contexto or not contexto.pregunta:
        return False
    # Solo respuestas breves que parecen una selección; no intercepta urgencias.
    if len(texto) > 100:
        return False
    if re.search(r'\b(auto|automotor|coche|hogar|casa|moto|vida|comercio|pol-\d+)\b', _normalizar(texto)):
        return True
    propias = Poliza.objects.filter(cliente_id=contexto.cliente_id).select_related('vehiculo')
    return _por_vehiculo(texto, propias) is not None


def _por_vehiculo(texto, polizas):
    """Referencias explícitas al vehículo; solo compara con pólizas del titular."""
    from datos.limpieza import normalizar_patente
    patentes = re.findall(r'\b(?:[A-Z]{2}[ -]?\d{3}[ -]?[A-Z]{2}|[A-Z]{3}[ -]?\d{3}|[A-Z][ -]?\d{3}[ -]?[A-Z]{3}|\d{3}[ -]?[A-Z]{3})\b', texto.upper())
    if patentes:
        buscadas = {normalizar_patente(p) for p in patentes}
        return [p for p in polizas if p.vehiculo and p.vehiculo.patente in buscadas]
    normalizado = _normalizar(texto)
    coincidencias = []
    for poliza in polizas:
        if not poliza.vehiculo:
            continue
        v = poliza.vehiculo
        etiquetas = [v.marca, v.modelo]
        if v.clase != 'sin_especificar':
            etiquetas.append(v.clase)
        if any(re.search(r'\b' + re.escape(_normalizar(e)) + r'\b', normalizado) for e in etiquetas if e):
            coincidencias.append(poliza)
    return coincidencias or None


def responder_cobertura(texto, conversacion):
    """Devuelve texto y fragmento, o None cuando corresponde búsqueda general."""
    contexto = contexto_vigente(conversacion)
    seguimiento = bool(contexto and contexto.pregunta)
    general = bool(re.search(r'\b(?:en general|informacion general|tipos de seguros)\b', _normalizar(texto)))
    # Una pregunta breve «¿cubre granizo?» puede omitir «mi». Las preguntas
    # generales («qué documentación necesito», «el seguro cubre...») conservan
    # la biblioteca general sin asumir un contrato del cliente.
    implicita = bool(cliente_reconocido(conversacion) and re.match(r'^[¿\s]*(?:cubre|incluye|protege)\b', _normalizar(texto)))
    if general or (not implicita and not es_personal(texto) and not seguimiento and not (contexto and contexto.poliza_id)):
        return None
    if contexto is None:
        contexto = contexto_automatico(conversacion)
    if contexto is None:
        return (SIN_CLIENTE, None)
    hoy = timezone.localdate()
    polizas = list(Poliza.objects.filter(cliente_id=contexto.cliente_id, tipo_seguro__codigo='automotor', estado='vigente',
        fecha_inicio__lte=hoy, fecha_vencimiento__gte=hoy).select_related('tipo_seguro', 'vehiculo', 'compania').order_by('id'))
    texto_norm = _normalizar(texto)
    numeros = re.findall(r'POL-\d+', texto.upper())
    tipos = {'auto': 'automotor', 'coche': 'automotor', 'vehiculo': 'automotor', 'automotor': 'automotor',
             'hogar': 'hogar', 'casa': 'hogar', 'moto': 'moto', 'vida': 'vida', 'comercio': 'comercio'}
    tipos_pedidos = {valor for palabra, valor in tipos.items() if re.search(r'\b'+palabra+r'\b', texto_norm)}
    opciones = polizas
    if numeros:
        opciones = [p for p in opciones if p.numero_poliza in numeros]
    elif (por_vehiculo := _por_vehiculo(texto, opciones)) is not None:
        opciones = por_vehiculo
    elif tipos_pedidos:
        opciones = [p for p in opciones if p.tipo_seguro.codigo in tipos_pedidos]
    elif contexto.poliza_id and not seguimiento:
        opciones = [p for p in opciones if p.pk == contexto.poliza_id]
    if not opciones:
        return (SIN_POLIZA, None)
    if len(opciones) != 1:
        contexto.pregunta = (contexto.pregunta or texto)[:300]
        contexto.save(update_fields=['pregunta'])
        from negocio.polizas import descripcion_de_vehiculo
        listado = '\n'.join(f'• {p.numero_poliza}: ' + (
            descripcion_de_vehiculo(p.vehiculo) if p.vehiculo else p.bien_asegurado or p.tipo_seguro.nombre
        ) for p in opciones)
        return (f'Tenés varias pólizas automotor. ¿Cuál querés consultar? Respondé con la patente, el vehículo o el número:\n{listado}', None)
    poliza = opciones[0]
    pregunta = contexto.pregunta or texto
    contexto.poliza = poliza
    contexto.pregunta = ''
    contexto.save(update_fields=['poliza', 'pregunta'])
    ids = list(DocumentoPoliza.objects.filter(poliza=poliza,
        documento__estado=EstadoDocumento.APROBADO).values_list('documento_id', flat=True))
    directas = CondicionesPoliza.objects.filter(poliza=poliza,documento__estado=EstadoDocumento.APROBADO).select_related('plan').first()
    if directas and directas.plan_id and directas.plan.compania_id != poliza.compania_id:
        return (SIN_CONDICIONES, None)
    if directas and directas.documento_id in ids:
        ids = [directas.documento_id]
    if not ids:
        return (SIN_CONDICIONES, None)
    # La pregunta general pide un extracto; nunca se usa una fuente ajena.
    # El número identifica el contrato; no es un término de sus coberturas.
    consulta = re.sub(r'\bPOL-\d+\b', '', pregunta, flags=re.I)
    identificadores = set()
    for p in polizas:
        if p.vehiculo:
            identificadores |= _terminos(f"{p.vehiculo.marca} {p.vehiculo.modelo} {p.vehiculo.patente}")
    temas = _tema_consultado(consulta, identificadores)
    resumen = not temas
    consulta = ' '.join(sorted(temas)) if temas else 'cobertura'
    encontrado = buscar_fragmentos(consulta, documentos_ids=ids, incluir_vinculados=True,
        exigir_todos=not resumen)
    if not resumen:
        # Todos los conceptos específicos deben estar respaldados. Un pasaje
        # parecido sobre otro riesgo no responde esta consulta particular.
        resultados = [r for r in encontrado['resultados']
            if puntuar_fragmento(consulta,r['pasaje'])[0] == len(temas)]
        encontrado = {**encontrado,'resultados':resultados,'respaldo_suficiente':bool(resultados)}
    if resumen and not encontrado['respaldo_suficiente'] and len(set(ids)) == 1:
        # Un resumen explícito puede mostrar las condiciones de su único documento
        # aunque no contengan la palabra «cobertura». No aplica a preguntas específicas.
        f = FragmentoDocumento.objects.filter(documento_id=ids[0], documento__estado=EstadoDocumento.APROBADO).select_related('documento').order_by('orden','id').first()
        if f:
            encontrado = {'respaldo_suficiente': True, 'resultados': [{'titulo':f.documento.titulo,
                'version':f.documento.version,'pasaje':f.texto,'fragmento_id':f.id}]}
    if not encontrado['respaldo_suficiente']:
        return (SIN_PASAJE, None)
    fuente = encontrado['resultados'][0]
    if directas and fuente.get('fragmento_id'):
        compania = f' — {poliza.compania.nombre}' if poliza.compania else ''
        return (f'Tu póliza {poliza.numero_poliza}{compania}. Condiciones registradas por la agencia:\n“{fuente["pasaje"]}”\nEste es un extracto; aplican los límites y exclusiones indicados.', fuente['fragmento_id'])
    return (f'Condiciones vinculadas a tu póliza {poliza.numero_poliza}. Fuente: {fuente["titulo"]}, versión {fuente["version"]}.\n“{fuente["pasaje"]}”\nEste es un extracto de tus condiciones. Aplican los límites y exclusiones indicados; si querés denunciar un hecho, contame qué ocurrió.', fuente['fragmento_id'])
