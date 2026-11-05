"""Recopilación gratuita y determinista de una solicitud; nunca fija precios ni emite.

El bot junta los datos de cliente, vehículo y plan, y deja una acción
`alta_poliza` lista: el asesor solo ingresa la prima y confirma o rechaza.

Lo que la gente escribe de verdad (simulación de 20 interesados) manda sobre lo
que el formulario esperaba: «ni idea» vale como «no sé», «Carla Ibáñez
38999310» trae nombre y DNI, «es del 2021» trae el año, «Pampa» es Pampa
Protección Seguros, «todo riesgo» es el plan total, «hoy» es una fecha, y una
pregunta en el medio («¿cuánto me va a salir?») se contesta sin perder el alta.
"""
import re
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from datos.limpieza import normalizar_dni, normalizar_patente
from datos.models import BorradorPoliza, Compania, Conversacion, PlanCobertura, Vehiculo
from negocio.bot.clasificador import clasificar, normalizar, normalizar_mensaje
from negocio.clientes import _email_validado, _nombre_validado
from negocio.errores import DatosInvalidos, ErrorNegocio
from negocio.vehiculos import _anio_validado, _chasis_validado, _valor_validado

PREGUNTAS = {
    'nombre_completo': '¿Cuál es tu nombre y apellido completos?',
    'dni': '¿Cuál es tu DNI? Escribilo con 7 u 8 números.',
    'patente': '¿Cuál es la patente del vehículo que querés asegurar?',
    'marca': '¿Cuál es la marca del vehículo?',
    'modelo': '¿Cuál es el modelo?',
    'anio': '¿De qué año es el vehículo?',
    'clase': '¿Es auto, moto, camioneta, utilitario o camión?',
    'uso': '¿Qué uso tiene: particular, comercial, remis/taxi o carga?',
    'chasis': '¿Cuál es el número de chasis? Si no lo tenés a mano, escribí «no sé».',
    'valor_asegurado': '¿Cuál es el valor asegurado solicitado? Si no lo sabés, escribí «no sé» y lo calcula el asesor.',
    'compania_id': '¿Con qué compañía querés solicitar el seguro?',
    'cobertura': '¿Qué plan querés?',
    'fecha_inicio': '¿Desde qué fecha querés la cobertura? Podés decir «hoy», «mañana» o una fecha (DD/MM/AAAA).',
    'fecha_vencimiento': '¿Hasta qué fecha? Usá DD/MM/AAAA.',
}
# La póliza dura un año salvo que el cliente diga otra cosa: no se pregunta el fin.
PREGUNTADOS = [c for c in PREGUNTAS if c != 'fecha_vencimiento']
OPCIONALES = frozenset({'chasis', 'valor_asegurado'})

ALIAS = {normalizar(k.replace('_', ' ')): k for k in PREGUNTAS}
ALIAS.update({'nombre y apellido': 'nombre_completo', 'nombre': 'nombre_completo',
    'ano': 'anio', 'plan': 'cobertura',
    'compania': 'compania_id', 'aseguradora': 'compania_id', 'valor': 'valor_asegurado',
    'valor asegurado': 'valor_asegurado', 'inicio': 'fecha_inicio', 'fin': 'fecha_vencimiento',
    'vencimiento': 'fecha_vencimiento', 'tipo de vehiculo': 'clase', 'email': 'email'})

# «no sé» dicho de las mil maneras en que lo dice la gente.
RE_NO_SE = re.compile(
    r'^(?:omitir|no se|nose|no lo se|ni idea|no tengo idea|no tengo|no lo tengo|desconozco|sin dato|'
    r'ninguno|no sabria|despues lo paso|despues te lo paso|-)\b.*$|^-$')
OMITIR = {'omitir', 'no tengo', 'no se', 'sin dato', 'no lo tengo'}  # compatibilidad

RE_CANCELAR = re.compile(
    r'\b(?:cancelar|cancela|cancelalo|lo pienso|lo voy a pensar|despues (?:les|te) escribo|'
    r'dejalo|deja nomas|no quiero seguir|mejor no|olvidalo)\b')

# «Patente BBB111», «mi dni es 4633…», «año 2011»: el cliente adelanta un dato con
# su rótulo sin escribir los dos puntos. Sin esto se tomaba como respuesta al paso
# pendiente (en la conversación 43, «Marca Ford» quedó como nombre y apellido).
ROTULOS = {
    'patente': 'patente', 'dominio': 'patente', 'marca': 'marca', 'modelo': 'modelo',
    'anio': 'anio', 'ano': 'anio', 'uso': 'uso', 'clase': 'clase', 'chasis': 'chasis',
    'dni': 'dni', 'documento': 'dni', 'email': 'email', 'correo': 'email',
    'apellido': 'apellido_solo', 'nombre': 'nombre_solo',
}
RE_ROTULADO = re.compile(
    r'^(?:mi |el |la )?(' + '|'.join(sorted(ROTULOS, key=len, reverse=True)) + r')(?:\s+(?:es|son))?\s*[:=]?\s+(\S.*)$')
RE_ME_LLAMO = re.compile(
    r'^(?:me llamo|mi nombre es|mi nombre completo es|nombre y apellido(?: es)?|soy(?! de\b| del\b| el\b| la\b| un\b| una\b))'
    r'\s*:?\s+(\S.*)$')
RE_DNI_SUELTO = re.compile(r'\b\d{1,2}\.?\d{3}\.?\d{3}\b')
RE_ANIO = re.compile(r'\b(19[5-9]\d|20\d\d)\b')

ALIAS_MARCAS = {'vw': 'Volkswagen', 'volkswagen': 'Volkswagen', 'chevrolet': 'Chevrolet', 'chevy': 'Chevrolet',
                'citroen': 'Citroën', 'mercedes': 'Mercedes-Benz'}
CLASES = {'auto': 'auto', 'autito': 'auto', 'coche': 'auto', 'automovil': 'auto', 'moto': 'moto',
          'motito': 'moto', 'motocicleta': 'moto', 'camioneta': 'camioneta', 'pickup': 'camioneta',
          'utilitario': 'utilitario', 'camion': 'camion'}
NIVEL_POR_PALABRA = (
    (r'todo riesgo|\btotal\b|completa\b|la mas completa|\bfull\b|la mejor', 'total'),
    (r'terceros completo|intermedi|\bmedia\b|la del medio', 'intermedia'),
    (r'responsabilidad civil|\brc\b|basic|la mas barata|minima|obligatori', 'basica'),
)
ETIQUETA_NIVEL = {'basica': 'básica', 'intermedia': 'intermedia', 'total': 'total'}


PARTICULAS = frozenset({'de', 'del', 'la', 'las', 'los', 'y'})


def _prolijo(texto, siglas=False):
    """«nico ferreyra», «ROBERTO SOSA», «gol trend» → como lo vería el asesor en una ficha.

    Solo toca lo que vino todo en minúsculas o todo en mayúsculas: «McDonald»
    o «C3» se respetan. Las siglas cortas en mayúsculas («CB 190») también.
    """
    texto = ' '.join(str(texto).split())
    if not (texto.islower() or texto.isupper()):
        return texto
    palabras = []
    for i, palabra in enumerate(texto.split()):
        if any(c.isdigit() for c in palabra) or (palabra.isupper() and len(palabra) <= 3 and (i > 0 or siglas)):
            palabras.append(palabra.upper())
        elif i > 0 and palabra.lower() in PARTICULAS:
            palabras.append(palabra.lower())
        else:
            palabras.append(palabra.lower().capitalize())
    return ' '.join(palabras)


def quiere_alta(texto):
    t = normalizar_mensaje(texto)
    # Pedir un precio inicia el embudo de cotizaciones, no una emisión.
    if re.search(r'\b(?:cotiza\w*|presupuesto|precio|cuanto (?:me |nos |te |le )?(?:cuesta|sale|saldri[aá]))\b', t):
        return False
    return bool(re.search(
        r'\b(?:contratar(?:lo|la)?|asegurar(?:lo|la)?|(?:registrar|cargar|dar de alta|agregar) (?:un |una |mi |el |la )?(?:poliza|seguro|vehiculo)'
        r'|alta (?:de |una |de una |mi )?poliza|nueva poliza'
        r'|(?:sacar|hacer|hacerme|necesito|quiero|busco) (?:un |el )?seguro'
        r'|seguro (?:para|a) (?:mi|el|la|una|un))\b', t)) and not re.search(r'\b(?:hogar|vida|comercio)\b', t)


def _companias():
    return list(Compania.objects.filter(activa=True).order_by('id'))


def _compania(valor):
    candidatas = _companias()
    buscada = normalizar(str(valor)).strip()
    elegidas = [c for c in candidatas if str(c.id) == buscada or normalizar(c.nombre) == buscada]
    if not elegidas and len(buscada) >= 3:
        # «Pampa», «la de Cóndor»: alcanza con una parte del nombre si es única.
        palabras = [p for p in re.findall(r'[a-z]+', buscada)
                    if len(p) >= 3 and p not in {'las', 'los', 'del', 'seguros', 'seguro', 'compania', 'quiero', 'con'}]
        elegidas = [c for c in candidatas if palabras and all(p in normalizar(c.nombre) for p in palabras)]
    if len(elegidas) != 1:
        raise DatosInvalidos('Elegí una de las compañías disponibles: ' + '; '.join(f'{c.id}: {c.nombre}' for c in candidatas))
    return elegidas[0]


def _planes(compania_id):
    return list(PlanCobertura.objects.filter(compania_id=compania_id, activo=True).order_by('nivel', 'id'))


def _nivel_en(texto):
    n = normalizar_mensaje(texto)
    for patron, nivel in NIVEL_POR_PALABRA:
        if re.search(patron, n):
            return nivel
    return None


def _elegir_plan(valor, datos):
    """Plan de la compañía elegida por número, nombre o nivel («todo riesgo», «la básica»)."""
    planes = _planes(datos.get('compania_id')) if datos.get('compania_id') else []
    n = normalizar_mensaje(str(valor))
    if planes:
        elegido = None
        if (m := re.fullmatch(r'(?:el |la |plan )?(\d{1,2})', n)) and 1 <= int(m.group(1)) <= len(planes):
            elegido = planes[int(m.group(1)) - 1]
        if elegido is None:
            elegido = next((p for p in planes if normalizar(p.nombre) in n), None)
        if elegido is None and (nivel := _nivel_en(valor)):
            elegido = next((p for p in planes if p.nivel == nivel), None)
        if elegido is None:
            raise DatosInvalidos('Elegí uno de los planes por su número o su nombre.')
        datos.update(plan_id=elegido.id, plan_nombre=elegido.nombre)
        if elegido.nivel:
            datos['cobertura'] = elegido.nivel
            return
    nivel = _nivel_en(valor)
    if nivel is None:
        raise DatosInvalidos('Elegí básica, intermedia o total.')
    datos['cobertura'] = nivel


def _fecha(texto):
    n = normalizar_mensaje(texto)
    hoy = timezone.localdate()
    for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(texto.strip(), formato).date()
        except ValueError:
            pass
    if re.search(r'\bpasado manana\b', n):
        return hoy + timedelta(days=2)
    if re.search(r'\bmanana\b', n):
        return hoy + timedelta(days=1)
    if re.search(r'\b(?:hoy|ya|ahora|cuanto antes|lo antes posible|inmediato)\b', n):
        return hoy
    if m := re.search(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b', n):
        anio = int(m.group(3)) if m.group(3) else hoy.year
        anio += 2000 if anio < 100 else 0
        try:
            return date(anio, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def _validar(campo, valor, datos, contacto):
    texto = str(valor).strip()
    n = normalizar(texto)
    if campo in OPCIONALES and RE_NO_SE.match(normalizar_mensaje(texto)):
        datos[campo] = None
        return
    if campo == 'nombre_completo':
        partes = texto.split(maxsplit=1)
        if partes and normalizar(partes[0]) in ROTULOS:
            raise DatosInvalidos('Eso parece otro dato. Necesito tu nombre y apellido, por ejemplo «Juan Pérez».')
        if len(partes) != 2:
            raise DatosInvalidos('Necesito nombre y apellido completos para dejar el alta lista.')
        datos.update(nombre=_nombre_validado(_prolijo(partes[0]), 'nombre'),
                     apellido=_nombre_validado(_prolijo(partes[1]), 'apellido'))
    elif campo == 'nombre_solo':
        datos['nombre'] = _nombre_validado(_prolijo(texto), 'nombre')
    elif campo == 'apellido_solo':
        datos['apellido'] = _nombre_validado(_prolijo(texto), 'apellido')
    elif campo == 'dni':
        datos[campo] = normalizar_dni(texto)
    elif campo == 'patente':
        patente = normalizar_patente(texto)
        v = Vehiculo.objects.filter(patente=patente).first()
        if v and (v.cliente_id != contacto.cliente_id or not v.activo):
            raise DatosInvalidos('No puedo usar esa patente para este número. Revisala o pedí un asesor.')
        datos[campo] = patente
        if v:
            datos.update({k: getattr(v, k) for k in ('marca', 'modelo', 'anio', 'clase', 'uso', 'chasis')})
            datos['valor_asegurado'] = str(v.valor_asegurado) if v.valor_asegurado is not None else None
    elif campo in ('marca', 'modelo'):
        if not texto or len(texto) > 100:
            raise DatosInvalidos('Indicá un texto de hasta 100 caracteres.')
        if campo == 'marca' and len(texto.split()) >= 2 and 'modelo' not in datos:
            # «Chevrolet Onix»: la marca y el modelo en la misma respuesta.
            marca, modelo = texto.split(maxsplit=1)
            datos['marca'] = ALIAS_MARCAS.get(normalizar(marca), _prolijo(marca))
            datos['modelo'] = _prolijo(modelo, siglas=True)
        else:
            datos[campo] = ALIAS_MARCAS.get(n, _prolijo(texto)) if campo == 'marca' else _prolijo(texto, siglas=True)
    elif campo == 'anio':
        encontrado = RE_ANIO.search(texto)
        datos[campo] = _anio_validado(encontrado.group(1) if encontrado else texto)
    elif campo == 'clase':
        clase = next((CLASES[p] for p in re.findall(r'[a-z]+', n) if p in CLASES), None)
        if clase is None:
            raise DatosInvalidos('Para este alta trabajamos con auto, moto, camioneta, utilitario o camión.')
        datos[campo] = clase
    elif campo == 'uso':
        n = {'remis/taxi': 'remis_taxi', 'remis': 'remis_taxi', 'taxi': 'remis_taxi'}.get(n, n)
        uso = next((u for u in ('particular', 'comercial', 'remis_taxi', 'carga') if u in n), None)
        if uso is None and re.search(r'\b(?:trabajo|laburo|laburar|reparto)\b', n):
            uso = 'comercial'
        if uso is None:
            raise DatosInvalidos('Indicá particular, comercial, remis/taxi o carga.')
        datos[campo] = uso
    elif campo == 'chasis':
        datos[campo] = _chasis_validado(texto)
    elif campo == 'valor_asegurado':
        datos[campo] = str(_valor_validado(re.sub(r'[^\d.,]', '', texto) or texto))
    elif campo == 'email':
        datos[campo] = _email_validado(texto)
    elif campo == 'compania_id':
        c = _compania(texto)
        if datos.get('compania_id') != c.id:
            datos.pop('plan_id', None)
            datos.pop('plan_nombre', None)
        datos.update(compania_id=c.id, compania_nombre=c.nombre)
    elif campo == 'cobertura':
        _elegir_plan(texto, datos)
    elif campo in ('fecha_inicio', 'fecha_vencimiento'):
        fecha = _fecha(texto)
        if fecha is None:
            raise DatosInvalidos('No entendí la fecha. Podés decir «hoy», «mañana» o escribirla como DD/MM/AAAA.')
        otra = datos.get('fecha_inicio' if campo == 'fecha_vencimiento' else 'fecha_vencimiento')
        if otra and ((campo == 'fecha_vencimiento' and fecha.isoformat() <= otra) or
                     (campo == 'fecha_inicio' and fecha.isoformat() >= otra)):
            raise DatosInvalidos('El vencimiento debe ser posterior al inicio.')
        datos[campo] = fecha.isoformat()


def _datos_libres(texto, empieza, datos):
    """Lo que se lee con certeza en un texto sin rótulos: marca + modelo + año,
    la patente, la clase de vehículo. Solo completa lo que todavía falta."""
    from negocio.bot.cotizacion import MARCAS_CONOCIDAS, _patente_en

    entradas = {}
    n = normalizar_mensaje(texto)
    palabras = re.findall(r'[a-z0-9]+', n)
    for i, palabra in enumerate(palabras):
        marca = ALIAS_MARCAS.get(palabra) or (palabra.title() if palabra in MARCAS_CONOCIDAS else None)
        if not marca or 'marca' in datos:
            continue
        entradas['marca'] = marca
        modelo = []
        for siguiente in palabras[i + 1:i + 3]:
            if RE_ANIO.fullmatch(siguiente) or siguiente in {'del', 'de', 'modelo', 'ano', 'patente', 'dni'}:
                break
            modelo.append(siguiente)
        if modelo and 'modelo' not in datos:
            original = re.search(r'\b' + r'\W+'.join(re.escape(m) for m in modelo) + r'\b', texto, re.I)
            entradas['modelo'] = original.group(0) if original else ' '.join(modelo)
        if (anio := RE_ANIO.search(' '.join(palabras[i:i + 5]))) and 'anio' not in datos:
            entradas['anio'] = anio.group(1)
        break
    if 'patente' not in datos:
        for segmento in re.split(r'[,;\n]', texto):
            if hallada := _patente_en(segmento):
                entradas['patente'] = hallada[0]
                break
    if empieza and 'clase' not in datos:
        if clase := next((CLASES[p] for p in palabras if p in CLASES), None):
            entradas['clase'] = clase
    return entradas


def _pregunta(campo, datos=None):
    datos = datos or {}
    pregunta = PREGUNTAS[campo]
    if campo == 'compania_id':
        pregunta += '\n' + '\n'.join(f'{c.id}: {c.nombre}' for c in _companias())
    if campo == 'cobertura':
        planes = _planes(datos.get('compania_id')) if datos.get('compania_id') else []
        if planes:
            pregunta = (f'¿Qué plan de {datos.get("compania_nombre", "la compañía")} querés? Respondé con el número:\n'
                        + '\n'.join(f'{i}: {p.nombre}' + (f' (cobertura {ETIQUETA_NIVEL[p.nivel]})' if p.nivel else '')
                                    for i, p in enumerate(planes, start=1)))
        else:
            pregunta = '¿Qué cobertura querés: básica, intermedia o total?'
    return pregunta


def _respuesta_a_una_duda(texto, borrador):
    """Una pregunta en medio del alta, contestada sin abandonar la solicitud."""
    n = normalizar_mensaje(texto)
    seguir = '\n\nSigamos con la solicitud. ' + _pregunta(borrador.campo, borrador.datos)
    if re.search(r'\b(?:cuanto|precio|sale|cuesta|cuota|por mes|mensual)\b', n):
        return ('El importe mensual lo calcula el asesor con estos datos y te lo confirma antes de emitir la póliza: '
                'no se emite nada sin tu acuerdo.' + seguir)
    if re.search(r'\b(?:plan|planes|diferencia|cubre|cobertura|basica|intermedia|total|todo riesgo|terceros)\b', n):
        return ('En general: la cobertura básica es responsabilidad civil (daños a terceros); la intermedia (terceros completo) '
                'suma robo, incendio, granizo y cristales; la total (todo riesgo) suma además los daños a tu propio vehículo, '
                'con franquicia. Cuando elijas la compañía te muestro sus planes.' + seguir)
    return 'Esa consulta la ve el asesor cuando revise tu solicitud.' + seguir


def _entradas_rotuladas(texto):
    """Los datos que el cliente dio con su rótulo, en cualquier momento del alta."""
    entradas = {}
    for trozo in re.split(r'[;\n,!?]+|\.\s+', texto):
        original = trozo.strip()
        n = normalizar(original)
        if (m := RE_ME_LLAMO.match(n)):
            valor = original[len(original) - len(m.group(1)):].strip()
            if RE_DNI_SUELTO.search(valor) or RE_ANIO.search(valor):
                continue
            entradas['nombre_completo' if len(valor.split()) >= 2 else 'nombre_solo'] = valor
        elif (m := RE_ROTULADO.match(n)):
            valor = original[len(original) - len(m.group(2)):].strip()
            clave = ROTULOS[m.group(1)]
            if clave == 'nombre_solo' and len(valor.split()) >= 2:
                clave = 'nombre_completo'  # «Nombre: Andrés Molina» trae también el apellido
            entradas[clave] = valor
    return entradas


RE_ACEPTA = re.compile(
    r'^(?:si|sii+|dale|de una|ok|okey|bueno|listo|joya|perfecto|claro|me interesa|quiero|lo quiero|'
    r'vamos|hagamoslo|avanza|avancemos)\b')


def acepta_oferta(texto, conversacion):
    """«Sí» / «dale» justo después de la oferta de contratar que cierra una cotización."""
    n = normalizar_mensaje(texto)
    if '?' in texto or len(n.split()) > 6 or not RE_ACEPTA.match(n):
        return False
    from datos.models import Mensaje
    from negocio.bot import plantillas

    ultimo = (Mensaje.objects.filter(conversacion=conversacion, direccion='saliente', emisor='bot')
              .exclude(estado_envio__in=('retenido', 'descartado')).order_by('-id').first())
    return bool(ultimo and plantillas.COTIZACION_REGISTRADA in (ultimo.texto or ''))


def _datos_de_la_cotizacion(contacto, datos):
    """Lo que el interesado ya dio al cotizar (patente, vehículo, año, uso): no se repregunta."""
    from datos.selectors import interesado_abierto_de

    interesado = interesado_abierto_de(contacto.id)
    previos = (interesado.datos if interesado else {}) or {}
    for campo in ('patente', 'marca', 'modelo', 'anio', 'uso'):
        if previos.get(campo) and campo not in datos:
            try:
                _validar(campo, previos[campo], datos, contacto)
            except (ErrorNegocio, ValueError):
                pass  # un dato que no valida se pregunta, no se arrastra


@transaction.atomic
def preparar_turno(texto, conversacion, mensaje_id):
    """Devuelve respuesta/acción preparadas o None cuando el turno es otra consulta."""
    # La relectura bajo lock evita que dos workers avancen dos veces una respuesta.
    Conversacion.objects.select_for_update().get(pk=conversacion.id)
    borrador = BorradorPoliza.objects.select_for_update().filter(conversacion=conversacion).first()
    empieza = quiere_alta(texto) or acepta_oferta(texto, conversacion)
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
    if empieza and not borrador.campo:
        _datos_de_la_cotizacion(contacto, datos)
    normalizado = normalizar(texto).strip()
    if normalizado in ('cancelar', 'cancelar alta', 'cancelar solicitud', 'salir') or (
            borrador.campo and not empieza and RE_CANCELAR.search(normalizar_mensaje(texto))):
        borrador.activo = False
        borrador.save(update_fields=['activo'])
        return {'texto': 'Listo, cancelé la solicitud y no se creó ninguna póliza. Cuando quieras retomarla, '
                         'escribime «quiero asegurar mi auto».', 'accion': None}
    entradas = {}
    for linea in re.split(r'[;\n]+', texto):
        if ':' in linea:
            etiqueta, valor = linea.split(':', 1)
            if (clave := ALIAS.get(normalizar(etiqueta).strip())):
                entradas[clave] = valor.strip()
    for clave, valor in _entradas_rotuladas(texto).items():
        entradas.setdefault(clave, valor)
    if not entradas and borrador.campo and not empieza:
        es_pregunta = '?' in texto or '¿' in texto
        tipo = clasificar(texto)
        if tipo == 'consulta_cobertura' or (es_pregunta and not contacto.cliente_id):
            # Una duda no saca a la persona del alta ni le vuelve a pedir nombre y DNI.
            return {'texto': _respuesta_a_una_duda(texto, borrador), 'accion': None}
        if es_pregunta or tipo in {'saldo', 'vencimiento', 'asistencia', 'pago', 'saludo', 'agradecimiento', 'ajeno'}:
            return None
        if borrador.campo == 'nombre_completo' and (dni := RE_DNI_SUELTO.search(texto)):
            # «Carla Ibáñez 38999310»: nombre y DNI en la misma respuesta.
            entradas['dni'] = dni.group(0)
            resto = (texto[:dni.start()] + texto[dni.end():]).strip(' ,-')
            if resto:
                entradas['nombre_completo'] = resto
        else:
            entradas[borrador.campo] = texto
    for clave, valor in _datos_libres(texto, empieza, datos).items():
        if clave not in entradas and clave not in datos:
            entradas[clave] = valor
    error = ''
    campo = borrador.campo
    for campo, valor in entradas.items():
        try:
            _validar(campo, valor, datos, contacto)
        except (ErrorNegocio, ValueError) as exc:
            error = str(exc)
            break
    if error and campo in OPCIONALES:
        # Un dato opcional que no sale después de dos intentos no traba el alta.
        intentos = datos.setdefault('_intentos', {})
        intentos[campo] = intentos.get(campo, 0) + 1
        if intentos[campo] >= 2:
            datos[campo] = None
            error = ''
    if 'fecha_inicio' in datos and 'fecha_vencimiento' not in datos:
        inicio = date.fromisoformat(datos['fecha_inicio'])
        try:
            datos['fecha_vencimiento'] = inicio.replace(year=inicio.year + 1).isoformat()
        except ValueError:  # 29 de febrero
            datos['fecha_vencimiento'] = (inicio + timedelta(days=365)).isoformat()
    campos = ([] if contacto.cliente_id else ['nombre_completo', 'dni']) + PREGUNTADOS[2:]
    if datos.get('nombre') and datos.get('apellido'):
        datos['nombre_completo'] = datos['nombre'] + ' ' + datos['apellido']
    faltantes = [k for k in campos if k not in datos]
    prefijo = ('Voy a preparar tu solicitud: te hago unas preguntas cortas y el asesor solo tiene que '
               'confirmar el precio. No hay cobertura nueva hasta esa confirmación. Si querés, podés mandarme '
               'varios datos juntos.\n' if empieza else '')
    if error:
        respuesta = {'texto': error + ' ' + _pregunta(campo, datos), 'accion': None}
        borrador.campo = campo
    elif faltantes:
        campo = faltantes[0]
        if campo == 'compania_id' and not _companias():
            return {'texto': 'Un asesor debe configurar las compañías disponibles antes de preparar el alta.', 'accion': None, 'derivar': True}
        respuesta = {'texto': prefijo + _pregunta(campo, datos), 'accion': None}
        borrador.campo = campo
    else:
        # El cliente no puede fijar prima ni comisión. Solo el aprobador ingresa la prima.
        parametros = {k: v for k, v in datos.items() if k != 'nombre_completo' and not k.startswith('_')}
        parametros['borrador_alta_id'] = borrador.id
        plan = f' ({datos["plan_nombre"]})' if datos.get('plan_nombre') else ''
        respuesta = {'texto': f'¡Listo! Preparé tu solicitud{plan} con tus datos y los del vehículo. '
                              'El asesor solo tiene que ingresar el importe mensual y confirmarla; te avisamos por este chat. '
                              'Todavía no se emitió ninguna póliza.',
                     'accion': ['alta_poliza', None, parametros]}
        borrador.campo = ''
    borrador.datos = datos
    borrador.ultimo_mensaje_id = mensaje_id
    borrador.respuesta = respuesta
    borrador.actualizado_en = timezone.now()
    borrador.save()
    return respuesta
