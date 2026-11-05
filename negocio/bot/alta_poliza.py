"""Recopilación gratuita y determinista de una solicitud; nunca fija precios ni emite."""
import re
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from datos.limpieza import normalizar_dni, normalizar_patente
from datos.models import BorradorPoliza, Compania, Conversacion, Vehiculo
from negocio.bot.clasificador import normalizar, clasificar
from negocio.clientes import _nombre_validado, _email_validado
from negocio.errores import DatosInvalidos, ErrorNegocio
from negocio.vehiculos import _anio_validado, _valor_validado, _chasis_validado

PREGUNTAS = {
    'nombre_completo': '¿Cuál es tu nombre y apellido completos?',
    'dni': '¿Cuál es tu DNI? Escribilo con 7 u 8 números.',
    'patente': '¿Cuál es la patente del vehículo que querés asegurar?',
    'marca': '¿Cuál es la marca del vehículo?',
    'modelo': '¿Cuál es el modelo?',
    'anio': '¿De qué año es el vehículo?',
    'clase': '¿Es auto, moto, camioneta, utilitario o camión?',
    'uso': '¿Qué uso tiene: particular, comercial, remis/taxi o carga?',
    'chasis': '¿Cuál es el número de chasis? Si no lo tenés, escribí «omitir».',
    'valor_asegurado': '¿Cuál es el valor asegurado solicitado? Si todavía no lo sabés, escribí «omitir».',
    'compania_id': '¿Con qué compañía querés solicitar el seguro?',
    'cobertura': '¿Qué cobertura solicitás: básica, intermedia o total?',
    'fecha_inicio': '¿Desde qué fecha? Usá DD/MM/AAAA o AAAA-MM-DD.',
    'fecha_vencimiento': '¿Hasta qué fecha? Usá DD/MM/AAAA o AAAA-MM-DD.',
}
ALIAS = {normalizar(k.replace('_', ' ')): k for k in PREGUNTAS}
ALIAS.update({'nombre y apellido': 'nombre_completo', 'nombre': 'nombre_completo',
    'ano': 'anio',
    'compania': 'compania_id', 'aseguradora': 'compania_id', 'valor': 'valor_asegurado',
    'valor asegurado': 'valor_asegurado', 'inicio': 'fecha_inicio', 'fin': 'fecha_vencimiento',
    'vencimiento': 'fecha_vencimiento', 'tipo de vehiculo': 'clase', 'email': 'email'})
OMITIR = {'omitir', 'no tengo', 'no se', 'sin dato', 'no lo tengo'}


def quiere_alta(texto):
    t = normalizar(texto)
    # Pedir un precio inicia el embudo de cotizaciones, no una emisión.
    if re.search(r'\b(?:cotiza\w*|presupuesto|precio|cuanto (?:cuesta|sale|saldri[aá]))\b', t):
        return False
    return bool(re.search(r'\b(?:contratar|asegurar|(?:registrar|cargar|dar de alta|agregar) (?:un |una |mi |el |la )?(?:poliza|seguro|vehiculo)|alta (?:de |una |de una |mi )?poliza|nueva poliza)\b', t)) and not re.search(r'\b(?:hogar|vida|comercio)\b', t)


def _compania(valor):
    candidatas = list(Compania.objects.filter(activa=True).order_by('nombre'))
    buscada = normalizar(str(valor)).strip()
    elegidas = [c for c in candidatas if str(c.id) == buscada or normalizar(c.nombre) == buscada]
    if len(elegidas) != 1:
        raise DatosInvalidos('Elegí una de las compañías disponibles: ' + '; '.join(f'{c.id}: {c.nombre}' for c in candidatas))
    return elegidas[0]


def _validar(campo, valor, datos, contacto):
    texto = str(valor).strip()
    n = normalizar(texto)
    if campo == 'nombre_completo':
        partes = texto.split(maxsplit=1)
        if len(partes) != 2:
            raise DatosInvalidos('Necesito nombre y apellido completos para dejar el alta lista.')
        datos.update(nombre=_nombre_validado(partes[0], 'nombre'), apellido=_nombre_validado(partes[1], 'apellido'))
    elif campo == 'dni':
        datos[campo] = normalizar_dni(texto)
    elif campo == 'patente':
        patente = normalizar_patente(texto)
        v = Vehiculo.objects.filter(patente=patente).first()
        if v and (v.cliente_id != contacto.cliente_id or not v.activo):
            raise DatosInvalidos('No puedo usar esa patente para este número. Revisala o pedí un asesor.')
        datos[campo] = patente
        if v:
            datos.update({k: getattr(v, k) for k in ('marca','modelo','anio','clase','uso','chasis')})
            datos['valor_asegurado'] = str(v.valor_asegurado) if v.valor_asegurado is not None else None
    elif campo in ('marca', 'modelo'):
        if not texto or len(texto) > 100:
            raise DatosInvalidos('Indicá un texto de hasta 100 caracteres.')
        datos[campo] = texto
    elif campo == 'anio':
        datos[campo] = _anio_validado(texto)
    elif campo == 'clase':
        n = {'coche':'auto', 'automovil':'auto', 'pickup':'camioneta','motocicleta':'moto'}.get(n, n)
        if n not in ('auto', 'moto', 'camioneta', 'utilitario', 'camion'):
            raise DatosInvalidos('Para este alta trabajamos con auto, moto, camioneta, utilitario o camión.')
        datos[campo] = n
    elif campo == 'uso':
        n = {'remis/taxi':'remis_taxi', 'remis':'remis_taxi', 'taxi':'remis_taxi'}.get(n, n)
        if n not in ('particular','comercial','remis_taxi','carga'):
            raise DatosInvalidos('Indicá particular, comercial, remis/taxi o carga.')
        datos[campo] = n
    elif campo == 'chasis':
        datos[campo] = None if n in OMITIR else _chasis_validado(texto)
    elif campo == 'valor_asegurado':
        valor = None if n in OMITIR else _valor_validado(texto)
        datos[campo] = str(valor) if valor is not None else None
    elif campo == 'email':
        datos[campo] = _email_validado(texto)
    elif campo == 'compania_id':
        c = _compania(texto)
        datos.update(compania_id=c.id, compania_nombre=c.nombre)
    elif campo == 'cobertura':
        if n not in ('basica','intermedia','total'):
            raise DatosInvalidos('Elegí básica, intermedia o total.')
        datos[campo] = n
    elif campo in ('fecha_inicio','fecha_vencimiento'):
        fecha = None
        for formato in ('%d/%m/%Y','%Y-%m-%d'):
            try:
                fecha = datetime.strptime(texto, formato).date()
                break
            except ValueError:
                pass
        if fecha is None:
            raise DatosInvalidos('La fecha no es válida. Usá DD/MM/AAAA o AAAA-MM-DD.')
        otra = datos.get('fecha_inicio' if campo == 'fecha_vencimiento' else 'fecha_vencimiento')
        if otra and ((campo == 'fecha_vencimiento' and fecha.isoformat() <= otra) or
                     (campo == 'fecha_inicio' and fecha.isoformat() >= otra)):
            raise DatosInvalidos('El vencimiento debe ser posterior al inicio.')
        datos[campo] = fecha.isoformat()


@transaction.atomic
def preparar_turno(texto, conversacion, mensaje_id):
    """Devuelve respuesta/acción preparadas o None cuando el turno es otra consulta."""
    # La relectura bajo lock evita que dos workers avancen dos veces una respuesta.
    Conversacion.objects.select_for_update().get(pk=conversacion.id)
    borrador = BorradorPoliza.objects.select_for_update().filter(conversacion=conversacion).first()
    empieza = quiere_alta(texto)
    if not empieza and (not borrador or not borrador.activo):
        return None
    if borrador and borrador.ultimo_mensaje_id == mensaje_id:
        return borrador.respuesta
    if borrador and borrador.accion_id:
        if not empieza:
            return None
        if borrador.accion.estado == 'pendiente':
            return {'texto': 'Tu solicitud ya está preparada. Un asesor ingresará la prima mensual y confirmará o rechazará el alta; te avisaremos por este chat.', 'accion': None}
        borrador.delete()
        borrador = None
    if not borrador:
        borrador = BorradorPoliza.objects.create(conversacion=conversacion)
    contacto = conversacion.contacto
    if contacto.cliente_id and not contacto.cliente.activo:
        return {'texto': 'Tu registro está inactivo. Un asesor debe revisar la solicitud antes de preparar otra póliza.', 'accion': None, 'derivar': True}
    datos = dict(borrador.datos)
    datos['cliente_id'] = contacto.cliente_id
    datos['telefono'] = contacto.numero
    if normalizar(texto).strip() in ('cancelar', 'cancelar alta', 'cancelar solicitud', 'salir'):
        borrador.activo = False
        borrador.save(update_fields=['activo'])
        return {'texto': 'Cancelé la preparación de esta solicitud. No se creó ninguna póliza.', 'accion': None}
    entradas = {}
    for linea in re.split(r'[;\n]+', texto):
        if ':' in linea:
            etiqueta, valor = linea.split(':', 1)
            if (clave := ALIAS.get(normalizar(etiqueta).strip())):
                entradas[clave] = valor.strip()
    if not entradas and borrador.campo and not empieza:
        if '?' in texto or '¿' in texto or clasificar(texto) in {
            'saldo','vencimiento','asistencia','consulta_cobertura','pago','saludo','agradecimiento','ajeno'}:
            return None
        entradas[borrador.campo] = texto
    error = ''
    for campo, valor in entradas.items():
        try:
            _validar(campo, valor, datos, contacto)
        except (ErrorNegocio, ValueError) as exc:
            error = str(exc)
            break
    campos = ([] if contacto.cliente_id else ['nombre_completo', 'dni']) + list(PREGUNTAS)[2:]
    if datos.get('nombre') and datos.get('apellido'):
        datos['nombre_completo'] = datos['nombre'] + ' ' + datos['apellido']
    faltantes = [k for k in campos if k not in datos]
    if error:
        respuesta = {'texto': error + ' ' + PREGUNTAS.get(campo, ''), 'accion': None}
        borrador.campo = campo
    elif faltantes:
        campo = faltantes[0]
        pregunta = PREGUNTAS[campo]
        if campo == 'compania_id':
            companias = list(Compania.objects.filter(activa=True).order_by('nombre'))
            if not companias:
                return {'texto': 'Un asesor debe configurar las compañías disponibles antes de preparar el alta.', 'accion': None, 'derivar': True}
            pregunta += '\n' + '\n'.join(f'{c.id}: {c.nombre}' for c in companias)
        prefijo = ('Voy a preparar la solicitud. El asesor ingresará el importe mensual y confirmará; no hay cobertura nueva hasta esa confirmación. Podés responder cada pregunta o enviar varios datos como «Patente: ...; Marca: ...».\n' if empieza else '')
        respuesta = {'texto': prefijo + pregunta, 'accion': None}
        borrador.campo = campo
    else:
        # El cliente no puede fijar prima ni comisión. Solo el aprobador ingresa la prima.
        parametros = {k:v for k,v in datos.items() if k != 'nombre_completo'}
        parametros['borrador_alta_id'] = borrador.id
        respuesta = {'texto': 'Ya preparé tu solicitud con los datos del cliente y del vehículo. El asesor solo debe ingresar la prima mensual y confirmar. Te avisaremos por este chat cuando termine. Todavía no se emitió una póliza.',
                     'accion': ['alta_poliza', None, parametros]}
        borrador.campo = ''
    borrador.datos = datos
    borrador.ultimo_mensaje_id = mensaje_id
    borrador.respuesta = respuesta
    borrador.actualizado_en = timezone.now()
    borrador.save()
    return respuesta
