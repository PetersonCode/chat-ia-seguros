from datetime import datetime, time

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

from datos.limpieza import normalizar_dni
from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    ContactoWhatsapp,
    Conversacion,
    ConsultaBot,
    Cuota,
    Derivacion,
    EstadoAccion,
    EstadoAlerta,
    EstadoConsulta,
    EstadoEnvio,
    EstadoPoliza,
    Funcionario,
    HistorialSiniestro,
    Mensaje,
    Prioridad,
    Pago,
    Poliza,
    Severidad,
    Siniestro,
    TipoConsulta,
    VPolizaResumen,
)

_ALERTAS_ABIERTAS = (EstadoAlerta.ABIERTA, EstadoAlerta.EN_REVISION)


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
    return mensajes.prefetch_related("alertas").order_by("fecha_hora", "id")


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


def siniestros(estado: str | None = None) -> QuerySet[Siniestro]:
    historial = HistorialSiniestro.objects.select_related("responsable").order_by(
        "fecha", "id"
    )
    siniestros = Siniestro.objects.select_related("poliza__cliente")
    siniestros = siniestros.prefetch_related(
        Prefetch("historial", queryset=historial)
    )
    if estado:
        siniestros = siniestros.filter(estado=estado)
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
    return dict(
        Poliza.objects.filter(cliente_id=cliente_id).values_list(
            "numero_poliza", "bien_asegurado"
        )
    )


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
    conversaciones = Conversacion.objects.annotate(
        derivacion_urgente=Exists(
            Derivacion.objects.filter(
                consulta__conversacion_id=OuterRef("pk"),
                prioridad=Prioridad.URGENTE,
                atendida_en__isnull=True,
            )
        ),
        alertas_abiertas=Count(
            "consultas__alertas",
            filter=Q(consultas__alertas__estado__in=_ALERTAS_ABIERTAS),
            distinct=True,
        ),
        severidad_rango=Max(
            Case(
                When(
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.CRITICA,
                    then=Value(4),
                ),
                When(
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.ALTA,
                    then=Value(3),
                ),
                When(
                    consultas__alertas__estado__in=_ALERTAS_ABIERTAS,
                    consultas__alertas__severidad=Severidad.MEDIA,
                    then=Value(2),
                ),
                When(
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
    alertas = Alerta.objects.select_related("consulta")
    if tipo is not None:
        alertas = alertas.filter(tipo=tipo)
    if severidad is not None:
        alertas = alertas.filter(severidad=severidad)
    if estado is not None:
        alertas = alertas.filter(estado=estado)
    return alertas.order_by("-creada_en", "-id")


def consultas_cerradas_con_alertas() -> QuerySet[ConsultaBot]:
    return ConsultaBot.objects.filter(
        estado=EstadoConsulta.CERRADO,
        alertas__estado__in=_ALERTAS_ABIERTAS,
    ).distinct()


def listar_acciones(
    *, estado: str | None = EstadoAccion.PENDIENTE
) -> QuerySet[AccionPendiente]:
    acciones = AccionPendiente.objects.select_related(
        "poliza",
        "consulta__conversacion__contacto__cliente",
        "resuelta_por",
    )
    if estado is not None:
        acciones = acciones.filter(estado=estado)
    return acciones.order_by("solicitada_en", "id")


def derivaciones_de(
    funcionario_id: int, *, incluir_atendidas: bool = False
) -> QuerySet[Derivacion]:
    derivaciones = Derivacion.objects.filter(derivado_a_id=funcionario_id)
    if not incluir_atendidas:
        derivaciones = derivaciones.filter(atendida_en__isnull=True)
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
        )
    )
    if q and q.strip():
        try:
            dni = normalizar_dni(q.strip())
        except ValueError:
            clientes = clientes.filter(
                Q(nombre__icontains=q.strip())
                | Q(apellido__icontains=q.strip())
            )
        else:
            clientes = clientes.filter(dni=dni)
    return clientes.order_by("apellido", "nombre", "id")


def detalle_cliente(cliente_id: int) -> Cliente:
    polizas = Poliza.objects.select_related("tipo_seguro").prefetch_related(
        "siniestros"
    )
    return Cliente.objects.prefetch_related(
        "contactos",
        Prefetch("polizas", queryset=polizas),
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
        Poliza.objects.select_related("cliente", "tipo_seguro", "vpolizaresumen")
        .prefetch_related(
            Prefetch("cuotas", queryset=cuotas),
            "conductores",
            "siniestros",
        )
        .get(pk=poliza_id)
    )
    resumen = getattr(poliza, "vpolizaresumen", None)
    poliza.saldo_pendiente = resumen.saldo_pendiente if resumen else None
    poliza.proximo_vencimiento_pago = (
        resumen.proximo_vencimiento_pago if resumen else None
    )
    return poliza


def contar_pendientes(funcionario_id: int) -> dict[str, int]:
    return {
        "acciones": AccionPendiente.objects.filter(
            estado__in=(EstadoAccion.PENDIENTE, EstadoAccion.APROBADA)
        ).count(),
        "derivaciones": Derivacion.objects.filter(
            derivado_a_id=funcionario_id,
            atendida_en__isnull=True,
        ).count(),
        "alertas_criticas": Alerta.objects.filter(
            estado__in=_ALERTAS_ABIERTAS,
            severidad=Severidad.CRITICA,
        ).count(),
    }
