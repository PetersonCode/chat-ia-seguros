from django.db.models import (
    Case,
    Count,
    F,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    TextField,
    When,
    Value,
)
from django.db.models.functions import Lower, Replace

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
    Mensaje,
    Prioridad,
    Poliza,
    Severidad,
    Siniestro,
    TipoConsulta,
    VPolizaResumen,
)

_ALERTAS_ABIERTAS = (EstadoAlerta.ABIERTA, EstadoAlerta.EN_REVISION)


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


def polizas_vigentes(cliente_id: int) -> QuerySet[Poliza]:
    return Poliza.objects.filter(
        cliente_id=cliente_id,
        estado=EstadoPoliza.VIGENTE,
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
        conversaciones = conversaciones.filter(
            Q(contacto__numero__icontains=q)
            | Q(contacto__cliente__nombre__icontains=q)
            | Q(contacto__cliente__apellido__icontains=q)
        )

    return conversaciones.annotate(
        prioridad_bandeja=Case(
            When(
                Q(retenidas__gt=0) | Q(severidad_rango=4),
                then=Value(0),
            ),
            default=Value(1),
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
    clientes = Cliente.objects.annotate(
        polizas_vigentes=Count(
            "polizas",
            filter=Q(polizas__estado=EstadoPoliza.VIGENTE),
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
    cuotas = Cuota.objects.order_by("-periodo", "-id")
    return (
        Poliza.objects.select_related("cliente", "tipo_seguro")
        .prefetch_related(
            Prefetch("cuotas", queryset=cuotas),
            "conductores",
            "siniestros",
        )
        .get(pk=poliza_id)
    )


def contar_pendientes(funcionario_id: int) -> dict[str, int]:
    return {
        "acciones": AccionPendiente.objects.filter(
            estado=EstadoAccion.PENDIENTE
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
