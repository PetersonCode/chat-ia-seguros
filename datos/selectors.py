import re
from datetime import date, datetime, time, timedelta

from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    Func,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    TextField,
    When,
    Value,
)
from django.db.models.functions import Lower, Replace
from django.utils import timezone

from datos.limpieza import normalizar_dni, normalizar_patente
from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    Compania,
    ContactoWhatsapp,
    Conversacion,
    ConsultaBot,
    Cotizacion,
    Cuota,
    Derivacion,
    EstadoAccion,
    EstadoAlerta,
    EstadoConsulta,
    EstadoEnvio,
    EstadoInteresado,
    EstadoPoliza,
    Funcionario,
    HistorialSiniestro,
    Interesado,
    InteresadoHistorial,
    Mensaje,
    Prioridad,
    Pago,
    Poliza,
    Severidad,
    Siniestro,
    TipoConsulta,
    VPolizaResumen,
    Vehiculo,
)

_ALERTAS_ABIERTAS = (EstadoAlerta.ABIERTA, EstadoAlerta.EN_REVISION)
# Un caso cerrado solo se ve en «Casos cerrados»: sus alertas y derivaciones
# salen de las listas de trabajo (alertas, contadores, bandeja, derivaciones).
# No se tocan en la base, así que si el caso se reabre vuelven a aparecer.
_CASOS_NO_CERRADOS = (
    EstadoConsulta.ABIERTO,
    EstadoConsulta.PENDIENTE_REVISION,
    EstadoConsulta.DERIVADO,
)
# Un interesado deja de estar abierto al emitirse la póliza o al perderse.
_INTERESADO_CERRADO = (EstadoInteresado.EMITIDA, EstadoInteresado.PERDIDA)


def reporte_gestion(desde, hasta) -> dict:
    """Agrega indicadores por período, usando la fecha propia de cada entidad."""
    zona = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), zona)
    fin_inclusivo = timezone.make_aware(datetime.combine(hasta, time.max), zona)

    consultas = ConsultaBot.objects.filter(
        fecha_hora__gte=inicio,
        fecha_hora__lte=fin_inclusivo,
    )
    totales_consultas = consultas.aggregate(
        total=Count("id"),
        cerradas=Count("id", filter=Q(estado=EstadoConsulta.CERRADO)),
        pendientes=Count(
            "id",
            filter=Q(
                estado__in=(
                    EstadoConsulta.ABIERTO,
                    EstadoConsulta.PENDIENTE_REVISION,
                    EstadoConsulta.DERIVADO,
                )
            ),
        ),
    )
    motivos = list(
        consultas.values(
            "tipo_consulta__codigo",
            "tipo_consulta__nombre",
        )
        .annotate(cantidad=Count("id"))
        .order_by("-cantidad", "tipo_consulta__nombre")
    )
    derivaciones_urgentes = Derivacion.objects.filter(
        prioridad=Prioridad.URGENTE,
        creada_en__gte=inicio,
        creada_en__lte=fin_inclusivo,
    ).count()
    cobros = Pago.objects.filter(fecha_pago__range=(desde, hasta)).aggregate(
        cantidad=Count("id"),
        importe_total=Sum("importe"),
    )
    return {
        "consultas": totales_consultas,
        "motivos": [
            {
                "codigo": fila["tipo_consulta__codigo"],
                "nombre": fila["tipo_consulta__nombre"],
                "cantidad": fila["cantidad"],
            }
            for fila in motivos
        ],
        "derivaciones_urgentes": derivaciones_urgentes,
        "cobros": {
            "cantidad": cobros["cantidad"],
            "importe_total": cobros["importe_total"] or 0,
        },
    }


def funcionarios_activos() -> QuerySet[Funcionario]:
    """Quién puede ser responsable de algo: los funcionarios activos, por nombre."""
    return Funcionario.objects.filter(activo=True).order_by(Lower("nombre"), "id")


def funcionario_por_email(email: str) -> Funcionario | None:
    return Funcionario.objects.filter(email__iexact=email, activo=True).first()


def funcionario_por_nombre(nombre: str) -> Funcionario | None:
    nombre_normalizado = nombre.casefold().replace(" ", "")
    return (
        Funcionario.objects.annotate(
            nombre_normalizado=Lower(
                Replace(
                    "nombre",
                    Value(" "),
                    Value(""),
                    output_field=TextField(),
                )
            )
        )
        .filter(nombre_normalizado=nombre_normalizado, activo=True)
        .first()
    )


def cliente_por_dni(dni: str) -> Cliente | None:
    return Cliente.objects.filter(dni=dni).first()


def contacto_por_numero(numero: str) -> ContactoWhatsapp | None:
    return ContactoWhatsapp.objects.filter(numero=numero).first()


def conversacion_abierta(contacto_id: int) -> Conversacion | None:
    return Conversacion.objects.filter(
        contacto_id=contacto_id,
        estado="abierta",
    ).first()


def mensajes_de(
    conversacion_id: int, despues_de: int | None = None
) -> QuerySet[Mensaje]:
    mensajes = Mensaje.objects.filter(conversacion_id=conversacion_id)
    if despues_de is not None:
        mensajes = mensajes.filter(id__gt=despues_de)
    return mensajes.select_related("adjunto_chat").prefetch_related("alertas").order_by("fecha_hora", "id")


def historial_reciente(
    conversacion_id: int, limite: int = 6
) -> list[Mensaje]:
    if limite <= 0:
        return []
    recientes = mensajes_de(conversacion_id).order_by(
        "-fecha_hora", "-id"
    )[:limite]
    return list(reversed(recientes))


def tipo_consulta(codigo: str) -> TipoConsulta:
    return TipoConsulta.objects.get(codigo=codigo)


def poliza_por_numero(numero: str) -> Poliza | None:
    return Poliza.objects.filter(numero_poliza=numero).first()


def siniestro_por_numero(numero: str) -> Siniestro | None:
    return Siniestro.objects.filter(numero_siniestro=numero).first()


def siniestros(estado: str | None = None, q: str | None = None) -> QuerySet[Siniestro]:
    historial = HistorialSiniestro.objects.select_related("responsable").order_by(
        "fecha", "id"
    )
    siniestros = Siniestro.objects.select_related("poliza__cliente")
    siniestros = siniestros.prefetch_related(
        Prefetch("historial", queryset=historial)
    )
    if estado:
        siniestros = siniestros.filter(estado=estado)
    if q and q.strip():
        siniestros = filtrar_cartera(siniestros, q, (
            "numero_siniestro", "descripcion", "poliza__numero_poliza",
            "poliza__cliente__nombre", "poliza__cliente__apellido", "poliza__cliente__dni",
            "poliza__vehiculo__patente", "poliza__vehiculo__marca", "poliza__vehiculo__modelo",
        ))
    return siniestros.order_by("-creado_en", "-id")


def detalle_siniestro(siniestro_id: int) -> Siniestro:
    return siniestros().get(pk=siniestro_id)


def polizas_vigentes(cliente_id: int) -> QuerySet[Poliza]:
    hoy = timezone.localdate()
    return Poliza.objects.filter(
        cliente_id=cliente_id,
        estado=EstadoPoliza.VIGENTE,
        fecha_inicio__lte=hoy,
        fecha_vencimiento__gte=hoy,
    )


def bienes_asegurados(cliente_id: int) -> dict[str, str | None]:
    """Qué asegura cada póliza del cliente, por número de póliza.

    `v_polizas_resumen` no trae `bien_asegurado`, y el listado de pólizas lo
    necesita para contestar por el vehículo y no solo por el número.
    """
    from negocio.polizas import descripcion_de_vehiculo
    return {p.numero_poliza: descripcion_de_vehiculo(p.vehiculo) if p.vehiculo else p.bien_asegurado
            for p in Poliza.objects.filter(cliente_id=cliente_id).select_related('vehiculo')}


def resumen_polizas(cliente_id: int) -> QuerySet[VPolizaResumen]:
    return VPolizaResumen.objects.filter(
        poliza__cliente_id=cliente_id
    ).order_by("fecha_vencimiento", "poliza_id")


def alertas_abiertas(
    *,
    consulta_id: int | None = None,
    conversacion_id: int | None = None,
    mensaje_id: int | None = None,
) -> QuerySet[Alerta]:
    alertas = Alerta.objects.filter(estado__in=_ALERTAS_ABIERTAS)
    if consulta_id is not None:
        alertas = alertas.filter(consulta_id=consulta_id)
    if conversacion_id is not None:
        alertas = alertas.filter(consulta__conversacion_id=conversacion_id)
    if mensaje_id is not None:
        alertas = alertas.filter(mensaje_id=mensaje_id)
    return alertas


def bandeja_contactos(*, vista='atencion', **filtros):
    """Una conversación representativa por contacto, sin mezclar expedientes históricos."""
    ultima = Conversacion.objects.filter(contacto_id=OuterRef('contacto_id')).annotate(
        abierta_primero=Case(When(estado='abierta', then=Value(0)), default=Value(1))
    ).order_by('abierta_primero','-creada_en','-id').values('id')[:1]
    base = bandeja(**filtros).filter(pk=Subquery(ultima)).annotate(
        derivacion_pendiente=Exists(Derivacion.objects.filter(consulta__conversacion_id=OuterRef('pk'),atendida_en__isnull=True,
            consulta__estado__in=_CASOS_NO_CERRADOS))
    )
    necesita = Q(estado='abierta') & (Q(retenidas__gt=0) | (Q(ultimo_emisor_atencion='cliente',modo='humano')) | (Q(derivacion_pendiente=True) & ~Q(ultimo_emisor_atencion='funcionario')))
    grupos = {
        'atencion': necesita,
        'bot': Q(estado='abierta',modo='bot') & ~necesita,
        'esperando': Q(estado='abierta',modo='humano') & ~necesita,
        'resueltas': Q(estado='cerrada'),
        'todas': Q(),
    }
    if vista not in grupos:
        from negocio.errores import DatosInvalidos
        raise DatosInvalidos('La vista de bandeja no es válida.')
    cantidades = {k:base.filter(v).count() for k,v in grupos.items() if k!='todas'}
    return base.filter(grupos[vista]).order_by('prioridad_bandeja',F('ultimo_fecha_hora').asc(nulls_last=True),'id'), cantidades


def bandeja(
    *,
    estado: str | None = None,
    con_alertas: bool = False,
    esperando_humano: bool = False,
    q: str | None = None,
) -> QuerySet[Conversacion]:
    ultimo_mensaje = Mensaje.objects.filter(
        conversacion_id=OuterRef("pk")
    ).order_by("-fecha_hora", "-id")
    # Un recordatorio de cobranza y un envío fallido no contestan la consulta
    # pendiente del cliente. El último mensaje visible sigue incluyendo ambos.
    ultimo_operativo = ultimo_mensaje.exclude(payload__has_key='recordatorio_poliza_id').exclude(payload__has_key='aviso_gestion_id').exclude(
        direccion='saliente', estado_envio__in=['fallido', 'descartado', 'pendiente_envio'])
    conversaciones = Conversacion.objects.annotate(
        derivacion_urgente=Exists(
            Derivacion.objects.filter(
                consulta__conversacion_id=OuterRef("pk"),
                consulta__estado__in=_CASOS_NO_CERRADOS,
                prioridad=Prioridad.URGENTE,
                atendida_en__isnull=True,
            )
        ),
        alertas_abiertas=Count(
            "consultas__alertas",
            filter=Q(
                consultas__estado__in=_CASOS_NO_CERRADOS,
                consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
            ),
            distinct=True,
        ),
        severidad_rango=Max(
            Case(
                When(
                    consultas__estado__in=_CASOS_NO_CERRADOS,
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.CRITICA,
                    then=Value(4),
                ),
                When(
                    consultas__estado__in=_CASOS_NO_CERRADOS,
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.ALTA,
                    then=Value(3),
                ),
                When(
                    consultas__estado__in=_CASOS_NO_CERRADOS,
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.MEDIA,
                    then=Value(2),
                ),
                When(
                    consultas__estado__in=_CASOS_NO_CERRADOS,
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.BAJA,
                    then=Value(1),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            output_field=IntegerField(),
        ),
        retenidas=Count(
            "mensajes",
            filter=Q(mensajes__estado_envio=EstadoEnvio.RETENIDO),
            distinct=True,
        ),
        ultimo_texto=Subquery(ultimo_mensaje.values("texto")[:1]),
        ultimo_emisor=Subquery(ultimo_mensaje.values("emisor")[:1]),
        ultimo_emisor_atencion=Subquery(ultimo_operativo.values("emisor")[:1]),
        ultima_atencion_en=Subquery(ultimo_operativo.values("fecha_hora")[:1]),
        ultimo_fecha_hora=Subquery(ultimo_mensaje.values("fecha_hora")[:1]),
    ).select_related("contacto__cliente", "funcionario")

    if estado is not None:
        conversaciones = conversaciones.filter(estado=estado)
    if con_alertas:
        conversaciones = conversaciones.filter(alertas_abiertas__gt=0)
    if esperando_humano:
        conversaciones = conversaciones.filter(modo="humano")
    if q:
        # TRANSLATE antes de LOWER también funciona en clusters con locale C,
        # donde UPPER/LOWER no convierten todas las letras acentuadas.
        acentos = "ÁÉÍÓÚÜÑáéíóúüñ"
        simples = "AEIOUUNaeiouun"
        def texto_busqueda(campo):
            return Lower(Func(F(campo), Value(acentos), Value(simples), function="TRANSLATE", output_field=TextField()))
        buscado = q.translate(str.maketrans(acentos, simples)).lower()
        conversaciones = conversaciones.annotate(
            nombre_busqueda=texto_busqueda("contacto__cliente__nombre"),
            apellido_busqueda=texto_busqueda("contacto__cliente__apellido"),
        )
        conversaciones = conversaciones.filter(
            Q(contacto__numero__icontains=q)
            | Q(nombre_busqueda__contains=buscado)
            | Q(apellido_busqueda__contains=buscado)
        )

    return conversaciones.annotate(
        prioridad_bandeja=Case(
            When(
                derivacion_urgente=True,
                then=Value(0),
            ),
            When(
                Q(retenidas__gt=0) | Q(severidad_rango=4),
                then=Value(1),
            ),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by(
        "prioridad_bandeja",
        F("ultimo_fecha_hora").desc(nulls_last=True),
        "-id",
    )


def detalle_conversacion(conversacion_id: int) -> Conversacion:
    return Conversacion.objects.select_related(
        "contacto__cliente",
        "funcionario",
    ).get(pk=conversacion_id)


def listar_alertas(
    *,
    tipo: str | None = None,
    severidad: str | None = None,
    estado: str | None = "abierta",
) -> QuerySet[Alerta]:
    alertas = Alerta.objects.select_related("consulta").filter(
        consulta__estado__in=_CASOS_NO_CERRADOS
    )
    if tipo is not None:
        alertas = alertas.filter(tipo=tipo)
    if severidad is not None:
        alertas = alertas.filter(severidad=severidad)
    if estado is not None:
        alertas = alertas.filter(estado=estado)
    return alertas.order_by("-creada_en", "-id")


def consultas_cerradas(*, con_alertas: bool = False, q: str | None = None) -> QuerySet[ConsultaBot]:
    """Casos cerrados; con `con_alertas`, solo los que aún tienen alertas abiertas.

    `q` busca por código de caso, número, nombre, apellido o DNI del cliente,
    tipo de consulta y lo que escribió el cliente.
    """
    if not con_alertas:
        casos = ConsultaBot.objects.filter(estado=EstadoConsulta.CERRADO).order_by('-fecha_hora', '-id')
    else:
        casos = consultas_cerradas_con_alertas()
    if q and q.strip():
        casos = filtrar_cartera(casos, q, (
            'codigo_caso', 'contacto__numero', 'contacto__cliente__nombre',
            'contacto__cliente__apellido', 'contacto__cliente__dni',
            'tipo_consulta__nombre', 'mensaje_usuario',
        ))
    return casos


def consultas_cerradas_con_alertas() -> QuerySet[ConsultaBot]:
    return ConsultaBot.objects.filter(
        estado=EstadoConsulta.CERRADO,
        alertas__estado__in=_ALERTAS_ABIERTAS,
    ).distinct().order_by('-fecha_hora', '-id')


def listar_acciones(
    *,
    estado: str | None = EstadoAccion.PENDIENTE,
    q: str | None = None,
    orden: str = "antiguo",
) -> QuerySet[AccionPendiente]:
    """Acciones por estado; `q` busca (todas las palabras) y `orden` es «antiguo» o «reciente»."""
    from django.db.models import TextField
    from django.db.models.functions import Cast

    acciones = AccionPendiente.objects.select_related(
        "poliza",
        "consulta__conversacion__contacto__cliente",
        "resuelta_por",
    )
    if estado is not None:
        acciones = acciones.filter(estado=estado)
    palabras = (q or "").split()
    if palabras:
        acciones = acciones.annotate(_parametros_texto=Cast("parametros", TextField()))
        for palabra in palabras:
            acciones = acciones.filter(
                Q(tipo_accion__icontains=palabra)
                | Q(consulta__codigo_caso__icontains=palabra)
                | Q(poliza__numero_poliza__icontains=palabra)
                | Q(_parametros_texto__icontains=palabra)
                | Q(consulta__contacto__cliente__nombre__icontains=palabra)
                | Q(consulta__contacto__cliente__apellido__icontains=palabra)
                | Q(consulta__contacto__cliente__dni__icontains=palabra)
                | Q(consulta__conversacion__contacto__cliente__nombre__icontains=palabra)
                | Q(consulta__conversacion__contacto__cliente__apellido__icontains=palabra)
                | Q(consulta__conversacion__contacto__cliente__dni__icontains=palabra)
                | Q(consulta__contacto__numero__icontains=palabra)
                | Q(consulta__conversacion__contacto__numero__icontains=palabra)
            )
    if orden == "reciente":
        return acciones.order_by("-solicitada_en", "-id")
    return acciones.order_by("solicitada_en", "id")


def derivaciones_de(
    funcionario_id: int | None, *, incluir_atendidas: bool = False
) -> QuerySet[Derivacion]:
    """Derivaciones de un funcionario; con `None`, las de todos."""
    derivaciones = Derivacion.objects.all()
    if funcionario_id is not None:
        derivaciones = derivaciones.filter(derivado_a_id=funcionario_id)
    if not incluir_atendidas:
        derivaciones = derivaciones.filter(
            atendida_en__isnull=True, consulta__estado__in=_CASOS_NO_CERRADOS
        )
    return derivaciones.annotate(
        orden_prioridad=Case(
            When(prioridad=Prioridad.URGENTE, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("orden_prioridad", "creada_en", "id")


def buscar_clientes(q: str | None = None) -> QuerySet[Cliente]:
    hoy = timezone.localdate()
    clientes = Cliente.objects.annotate(
        polizas_vigentes=Count(
            "polizas",
            filter=Q(
                polizas__estado=EstadoPoliza.VIGENTE,
                polizas__fecha_inicio__lte=hoy,
                polizas__fecha_vencimiento__gte=hoy,
            ),
            distinct=True,
        ),
        # Contratadas y cargadas, pero con la cobertura todavía sin empezar.
        polizas_por_iniciar=Count(
            "polizas",
            filter=Q(
                polizas__estado=EstadoPoliza.VIGENTE,
                polizas__fecha_inicio__gt=hoy,
            ),
            distinct=True,
        ),
    )
    if q and q.strip():
        try:
            dni = normalizar_dni(q.strip())
        except ValueError:
            clientes = _filtrar_por_patente_o_nombre(clientes, q.strip())
        else:
            # Algunos chasis antiguos son numéricos de 7/8 dígitos, igual que un DNI.
            por_chasis = filtrar_cartera(Vehiculo.objects.filter(cliente_id=OuterRef('pk')),
                                        q.strip(), ('chasis',))
            clientes = clientes.filter(Q(dni=dni) | Exists(por_chasis))
    return clientes.order_by("apellido", "nombre", "id")


def _filtrar_por_patente_o_nombre(
    clientes: QuerySet[Cliente], q: str
) -> QuerySet[Cliente]:
    """Una patente exacta (con o sin espacios) gana; si nadie la tiene, nombre o apellido."""
    try:
        patente = normalizar_patente(q)
    except ValueError:
        patente = None
    if patente is not None:
        por_patente = clientes.filter(vehiculos__patente=patente)
        if por_patente.exists():
            return por_patente
    # La subconsulta mantiene los términos del vehículo en una misma fila.
    vehiculos = filtrar_cartera(Vehiculo.objects.filter(cliente_id=OuterRef('pk')), q,
                               ('cliente__nombre', 'cliente__apellido', 'patente',
                                'marca', 'modelo', 'chasis', 'clase', 'uso'))
    propios = filtrar_cartera(clientes, q, ('nombre', 'apellido'))
    return clientes.filter(Q(pk__in=propios.values('pk')) | Exists(vehiculos))


ACENTOS = "ÁÉÍÓÚÜÑáéíóúüñ"
SIMPLES = "AEIOUUNaeiouun"


def filtrar_cartera(queryset, texto, campos):
    """AND entre palabras; OR entre campos. Parámetros ORM, sin SQL interpolado."""
    normalizado = texto.translate(str.maketrans(ACENTOS, SIMPLES)).lower()
    terminos = re.findall(r'[a-z0-9]+', normalizado)
    vacias = {'el', 'la', 'los', 'las', 'de', 'del', 'un', 'una', 'y'}
    alias = {'pickup': 'camioneta', 'pickups': 'camioneta', 'camionetas': 'camioneta',
             'autos': 'auto', 'automovil': 'auto', 'camiones': 'camion', 'motos': 'moto'}
    terminos = [alias.get(t, t) for t in terminos if t not in vacias]
    if not terminos:
        return queryset.none()
    anotaciones = {f'busqueda_{i}': Lower(Func(F(campo), Value(ACENTOS), Value(SIMPLES),
                    function='TRANSLATE', output_field=TextField())) for i, campo in enumerate(campos)}
    for i, campo in enumerate(campos):
        if campo.endswith(('chasis', 'patente')):
            anotaciones[f'compacto_{i}'] = Replace(Replace(anotaciones[f'busqueda_{i}'],
                Value(' '), Value(''), output_field=TextField()),
                Value('-'), Value(''), output_field=TextField())
    queryset = queryset.alias(**anotaciones)
    for termino in terminos[:16]:
        condicion = Q()
        for alias_campo in anotaciones:
            condicion |= Q(**{alias_campo + '__contains': termino})
        queryset = queryset.filter(condicion)
    return queryset


def vehiculo_por_patente(patente: str) -> Vehiculo | None:
    """Normaliza la patente y devuelve el vehículo, o None si no existe o no es válida."""
    try:
        normalizada = normalizar_patente(patente)
    except ValueError:
        return None
    return Vehiculo.objects.select_related("cliente").filter(patente=normalizada).first()


def vehiculos_de(cliente_id: int, solo_activos: bool = True) -> QuerySet[Vehiculo]:
    vehiculos = Vehiculo.objects.filter(cliente_id=cliente_id)
    if solo_activos:
        vehiculos = vehiculos.filter(activo=True)
    return vehiculos.order_by("patente", "id")


def listar_companias(solo_activas: bool = True) -> QuerySet[Compania]:
    companias = Compania.objects.all()
    if solo_activas:
        companias = companias.filter(activa=True)
    return companias.order_by(Lower("nombre"), "id")


def _condicion_de_busqueda_de_interesado(q: str) -> Q:
    """Cada palabra tiene que aparecer en el nombre, el apellido, el teléfono o la patente.

    «juan perez» encuentra a Juan Pérez aunque el nombre y el apellido estén en
    columnas distintas. Una patente completa (con o sin espacios) también gana
    por coincidencia exacta.
    """
    condicion = Q()
    for palabra in q.translate(str.maketrans(ACENTOS, SIMPLES)).lower().split():
        por_palabra = (
            Q(nombre_busqueda__contains=palabra)
            | Q(apellido_busqueda__contains=palabra)
            | Q(nombre_cliente_busqueda__contains=palabra)
            | Q(apellido_cliente_busqueda__contains=palabra)
            | Q(datos__patente__icontains=palabra.upper())
            | Q(vehiculo__patente__icontains=palabra)
            | Q(vehiculo__chasis__icontains=palabra)
        )
        digitos = "".join(c for c in palabra if c.isdigit())
        if len(digitos) >= 3:
            por_palabra |= Q(contacto__numero__contains=digitos)
        condicion &= por_palabra
    try:
        condicion |= Q(datos__patente=normalizar_patente(q)) | Q(vehiculo__patente=normalizar_patente(q))
    except ValueError:
        pass
    # Un teléfono escrito con espacios o guiones ("11 2691-4442") son varias
    # palabras cortas: por palabra no se encontraría, así que se mira entero.
    digitos = "".join(c for c in q if c.isdigit())
    if len(digitos) >= 3 and re.fullmatch(r"[\d\s+()\-.]+", q):
        condicion |= Q(contacto__numero__contains=digitos)
    return condicion


def listar_interesados(
    estado: str | None = None,
    responsable_id: int | None = None,
    origen: str | None = None,
    q: str | None = None,
    seguimiento_vencido: bool = False,
    hoy: date | None = None,
) -> QuerySet[Interesado]:
    """El tablero de venta nueva: primero los que había que llamar y no se llamó.

    «Vencido» es un `proximo_contacto` anterior a hoy en un interesado todavía
    abierto: uno emitido o perdido ya no espera ningún llamado. Dentro de cada
    grupo, el que se tocó más recientemente va primero.
    """
    hoy = hoy or timezone.localdate()
    vencido = Q(proximo_contacto__lt=hoy) & ~Q(estado__in=_INTERESADO_CERRADO)
    interesados = Interesado.objects.select_related(
        "responsable", "contacto", "cliente", "vehiculo"
    ).annotate(
        orden_vencido=Case(
            When(vencido, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    if estado:
        interesados = interesados.filter(estado=estado)
    if responsable_id is not None:
        interesados = interesados.filter(responsable_id=responsable_id)
    if origen:
        interesados = interesados.filter(origen=origen)
    if q and q.strip():
        interesados = interesados.alias(**{
            alias: Lower(Func(F(campo), Value(ACENTOS), Value(SIMPLES),
                function='TRANSLATE', output_field=TextField()))
            for alias,campo in (('nombre_busqueda','nombre'),('apellido_busqueda','apellido'),
                ('nombre_cliente_busqueda','cliente__nombre'),('apellido_cliente_busqueda','cliente__apellido'))
        })
        interesados = interesados.filter(_condicion_de_busqueda_de_interesado(q.strip()))
    if seguimiento_vencido:
        interesados = interesados.filter(vencido)
    return interesados.order_by("orden_vencido", "-actualizado_en", "-id")


def contar_por_estado(responsable_id: int | None = None) -> dict[str, int]:
    """Cuántos interesados hay en cada etapa. Siempre trae las cinco, aunque estén en cero."""
    interesados = Interesado.objects.all()
    if responsable_id is not None:
        interesados = interesados.filter(responsable_id=responsable_id)
    conteos = {estado: 0 for estado in EstadoInteresado.values}
    for fila in interesados.values("estado").annotate(cantidad=Count("id")):
        conteos[fila["estado"]] = fila["cantidad"]
    return conteos


def cierres_del_mes(
    responsable_id: int | None = None, hoy: date | None = None
) -> dict[str, int]:
    """Cuántos interesados se emitieron y cuántos se perdieron en el mes de `hoy`.

    Cuenta interesados distintos, por el cambio de etapa que quedó en el historial:
    una gestión que no cambia la etapa (asignar, cargar datos) no suma, y uno que se
    pierde, se reabre y se pierde otra vez en el mismo mes cuenta una vez.
    """
    hoy = hoy or timezone.localdate()
    zona = timezone.get_current_timezone()
    primero = hoy.replace(day=1)
    siguiente = (primero.replace(day=28) + timedelta(days=4)).replace(day=1)
    lineas = InteresadoHistorial.objects.filter(
        fecha__gte=timezone.make_aware(datetime.combine(primero, time.min), zona),
        fecha__lt=timezone.make_aware(datetime.combine(siguiente, time.min), zona),
        estado_nuevo__in=_INTERESADO_CERRADO,
    ).exclude(estado_anterior=F("estado_nuevo"))
    if responsable_id is not None:
        lineas = lineas.filter(interesado__responsable_id=responsable_id)
    cuentas = {
        fila["estado_nuevo"]: fila["cantidad"]
        for fila in lineas.values("estado_nuevo").annotate(
            cantidad=Count("interesado_id", distinct=True)
        )
    }
    return {
        "convertidos_mes": cuentas.get(EstadoInteresado.EMITIDA, 0),
        "perdidos_mes": cuentas.get(EstadoInteresado.PERDIDA, 0),
    }


def interesado_abierto_de(contacto_id: int) -> Interesado | None:
    """El interesado de ese número que todavía no se emitió ni se perdió, si lo hay."""
    return (
        Interesado.objects.filter(contacto_id=contacto_id)
        .exclude(estado__in=_INTERESADO_CERRADO)
        .first()
    )


def cotizaciones_de(
    interesado_id: int | None = None, poliza_id: int | None = None
) -> QuerySet[Cotizacion]:
    """Las cotizaciones de un interesado o de una póliza, de la más barata a la más cara."""
    if interesado_id is None and poliza_id is None:
        return Cotizacion.objects.none()
    cotizaciones = Cotizacion.objects.select_related("compania", "creada_por")
    if interesado_id is not None:
        cotizaciones = cotizaciones.filter(interesado_id=interesado_id)
    if poliza_id is not None:
        cotizaciones = cotizaciones.filter(poliza_id=poliza_id)
    return cotizaciones.order_by("prima_mensual", "id")


def datos_actuales_interesado(interesado):
    """La cartera es la fuente de verdad después de la conversión."""
    datos = dict(interesado.datos or {})
    if interesado.vehiculo_id:
        v = interesado.vehiculo
        datos.update({k:getattr(v,k) for k in ('patente','marca','modelo','anio','uso','clase','chasis')})
        datos['valor_asegurado'] = str(v.valor_asegurado) if v.valor_asegurado is not None else None
    if interesado.cliente_id:
        datos['dni'] = interesado.cliente.dni
    return datos


def detalle_interesado(interesado_id: int) -> Interesado:
    """El interesado con su historial (viejo a nuevo), sus cotizaciones y su contacto.

    Cuatro consultas fijas: el interesado con responsable, contacto y cliente en
    el mismo JOIN, el historial con su autor, y las cotizaciones con compañía.
    """
    historial = InteresadoHistorial.objects.select_related("funcionario").order_by(
        "fecha", "id"
    )
    cotizaciones = Cotizacion.objects.select_related("compania", "creada_por").order_by(
        "prima_mensual", "id"
    )
    return (
        Interesado.objects.select_related("responsable", "contacto", "cliente", "vehiculo")
        .prefetch_related(
            Prefetch("historial", queryset=historial),
            Prefetch("cotizaciones", queryset=cotizaciones),
        )
        .get(pk=interesado_id)
    )


def detalle_cliente(cliente_id: int) -> Cliente:
    polizas = Poliza.objects.select_related(
        "tipo_seguro", "vehiculo", "compania"
    ).prefetch_related("siniestros")
    return Cliente.objects.prefetch_related(
        "contactos",
        Prefetch("polizas", queryset=polizas),
        Prefetch("vehiculos", queryset=Vehiculo.objects.order_by("patente", "id")),
    ).get(pk=cliente_id)


def detalle_poliza(poliza_id: int) -> Poliza:
    """La póliza con sus cuotas, conductores y siniestros, más su saldo.

    El saldo y el próximo vencimiento de pago no son columnas de `polizas`:
    los calcula `v_polizas_resumen` sumando cuotas. Se copian acá desde la
    vista, en vez de recalcularlos, para que el detalle de una póliza y el
    listado de la ficha digan siempre lo mismo (una sola definición de qué es
    "saldo pendiente", la de la vista).
    """
    cuotas = Cuota.objects.order_by("-periodo", "-id")
    poliza = (
        # La vista entra por el mismo JOIN: es `OneToOne` con `polizas`, así que
        # no agrega una consulta y AC-T4-19 sigue cerrando en cuatro.
        Poliza.objects.select_related(
            "cliente", "tipo_seguro", "vpolizaresumen", "vehiculo", "compania"
        )
        .prefetch_related(
            Prefetch("cuotas", queryset=cuotas),
            "conductores",
            "siniestros",
        )
        .get(pk=poliza_id)
    )
    resumen = getattr(poliza, "vpolizaresumen", None)
    poliza.saldo_pendiente = resumen.saldo_pendiente if resumen else None
    poliza.saldo_total = resumen.saldo_total if resumen else None
    poliza.proximo_vencimiento_pago = (
        resumen.proximo_vencimiento_pago if resumen else None
    )
    return poliza


def contar_pendientes(funcionario_id: int, ve_todas: bool = False) -> dict[str, int]:
    """`ve_todas`: administrador y propietario ven (y cuentan) las derivaciones de todos."""
    return {
        "acciones": AccionPendiente.objects.filter(
            estado__in=(EstadoAccion.PENDIENTE, EstadoAccion.APROBADA)
        ).count(),
        "derivaciones": derivaciones_de(None if ve_todas else funcionario_id).count(),
        "alertas_criticas": Alerta.objects.filter(
            estado__in=_ALERTAS_ABIERTAS,
            severidad=Severidad.CRITICA,
            consulta__estado__in=_CASOS_NO_CERRADOS,
        ).count(),
    }


# --- Métricas del panel ---------------------------------------------------

from django.db.models import Avg, DurationField, ExpressionWrapper  # noqa: E402
from datos.models import Direccion, Emisor  # noqa: E402


# Ramo al que se atribuye cada tipo de consulta en el panel de métricas.
# El alcance actual es solo automotor: lo que no figura acá cuenta como
# automotor. Para mover un tipo de ramo, basta con editar estos conjuntos.
TIPOS_ACCIDENTES = frozenset({"siniestro", "siniestro_urgente"})
TIPOS_OTROS = frozenset(
    {
        "saludo",
        "agradecimiento",
        "ajeno",
        "otro",
        "prompt_injection",
        "baja_avisos",
        "credencial",
        "encuesta_respuesta",
    }
)
RAMOS_METRICAS = (
    ("automotor", "Consultas de autos y motos"),
    ("accidentes", "Siniestros automotores"),
    ("otros", "Otros / Consultas Generales"),
)


def _ramo_de_tipo(codigo: str) -> str:
    if codigo in TIPOS_ACCIDENTES:
        return "accidentes"
    if codigo in TIPOS_OTROS:
        return "otros"
    return "automotor"


def _limites_del_periodo(desde, hasta):
    zona = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), zona)
    fin = timezone.make_aware(datetime.combine(hasta, time.max), zona)
    return inicio, fin


def _porcentaje(parte: int, total: int) -> float | None:
    if not total:
        return None
    return round(parte * 100 / total, 1)


def _resumen_consultas(desde, hasta) -> dict:
    inicio, fin = _limites_del_periodo(desde, hasta)
    consultas = ConsultaBot.objects.filter(fecha_hora__gte=inicio, fecha_hora__lte=fin)
    derivadas = Derivacion.objects.filter(consulta=OuterRef("pk"))
    return consultas.aggregate(
        total=Count("id"),
        derivadas=Count("id", filter=Q(Exists(derivadas))),
    )


def metricas_panel(desde, hasta) -> dict:
    """Indicadores del panel de métricas para el período [desde, hasta].

    Todo se calcula con las consultas cuya `fecha_hora` cae en el período:
    - efectividad: consultas sin ninguna derivación sobre el total.
    - derivadas: consultas con al menos una derivación a una persona.
    - tiempo de respuesta: del mensaje del cliente a la respuesta automática
      del bot (`respuesta_a`), en minutos.
    - ramos: cada tipo de consulta se atribuye a un ramo (ver `_ramo_de_tipo`).
    - motivos: texto de `Derivacion.motivo` de esas consultas, más frecuentes primero.
    La variación compara con el período inmediato anterior de igual duración.
    """
    inicio, fin = _limites_del_periodo(desde, hasta)
    actual = _resumen_consultas(desde, hasta)
    total = actual["total"]
    derivadas = actual["derivadas"]

    dias = (hasta - desde).days + 1
    hasta_anterior = desde - timedelta(days=1)
    desde_anterior = hasta_anterior - timedelta(days=dias - 1)
    total_anterior = _resumen_consultas(desde_anterior, hasta_anterior)["total"]
    variacion = (
        round((total - total_anterior) * 100 / total_anterior, 1)
        if total_anterior
        else None
    )

    demora = ExpressionWrapper(
        F("fecha_hora") - F("respuesta_a__fecha_hora"), output_field=DurationField()
    )
    promedio = (
        Mensaje.objects.filter(
            emisor=Emisor.BOT,
            direccion=Direccion.SALIENTE,
            respuesta_a__isnull=False,
            respuesta_a__fecha_hora__gte=inicio,
            respuesta_a__fecha_hora__lte=fin,
        )
        .annotate(demora=demora)
        .filter(demora__gte=timedelta(0))
        .aggregate(promedio=Avg("demora"))["promedio"]
    )

    por_tipo = (
        ConsultaBot.objects.filter(fecha_hora__gte=inicio, fecha_hora__lte=fin)
        .values("tipo_consulta__codigo")
        .annotate(cantidad=Count("id"))
    )
    por_ramo = {codigo: 0 for codigo, _ in RAMOS_METRICAS}
    for fila in por_tipo:
        por_ramo[_ramo_de_tipo(fila["tipo_consulta__codigo"])] += fila["cantidad"]

    motivos = list(
        Derivacion.objects.filter(
            consulta__fecha_hora__gte=inicio, consulta__fecha_hora__lte=fin
        )
        .values("motivo")
        .annotate(cantidad=Count("id"))
        .order_by("-cantidad", "motivo")
    )
    total_derivaciones = sum(fila["cantidad"] for fila in motivos)

    return {
        "consultas": {"total": total, "variacion_pct": variacion},
        "efectividad_pct": _porcentaje(total - derivadas, total),
        "derivadas": derivadas,
        "tiempo_respuesta_min": (
            round(promedio.total_seconds() / 60, 1) if promedio is not None else None
        ),
        "ramos": [
            {
                "codigo": codigo,
                "nombre": nombre,
                "cantidad": por_ramo[codigo],
                "porcentaje": _porcentaje(por_ramo[codigo], total) or 0,
            }
            for codigo, nombre in RAMOS_METRICAS
        ],
        "motivos_derivacion": [
            {
                "motivo": fila["motivo"],
                "cantidad": fila["cantidad"],
                "porcentaje": _porcentaje(fila["cantidad"], total_derivaciones) or 0,
            }
            for fila in motivos[:6]
        ],
    }
