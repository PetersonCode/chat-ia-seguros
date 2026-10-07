"""Las vistas de la API JSON.

Esta capa **no tiene reglas de negocio**: valida la entrada, llama a `negocio`
(escrituras) o a `datos.selectors` (lecturas), y traduce a JSON.

Los errores no se atrapan acá: las excepciones de `negocio.errores` suben y las
traduce `api.errores.manejar` (configurado en `EXCEPTION_HANDLER`), que es el
único lugar donde vive el mapeo código → HTTP.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.paginacion import Paginador
from api.permisos import EsAprobador, EsAprobadorParaEscribir, EsFuncionario
from api.serializers import (
    ClienteAltaSerializer,
    ClienteModificacionSerializer,
    LoginSerializer,
    MotivoSerializer,
    ParametrosSerializer,
    ResponderSerializer,
    TextoCorregidoSerializer,
)
from datos import selectors
from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    ConsultaBot,
    Conversacion,
    Derivacion,
    EstadoEnvio,
    Mensaje,
    Poliza,
)
from negocio.acciones import (
    aprobar_accion,
    atender_derivacion,
    completar_parametros,
    rechazar_accion,
)
from negocio.clientes import (
    SIN_CAMBIO,
    alta_cliente,
    dar_de_baja_cliente,
    modificar_cliente,
    reactivar_cliente,
)
from negocio.errores import DatosInvalidos, NoEncontrado, PermisoDenegado
from negocio.reglas import (
    RANGO_SEVERIDAD,
    color_por_severidad,
    severidad_por_rango,
    sin_respuesta,
    ventana_24h_abierta,
)
from negocio.sesion import funcionario_de
from negocio.supervision import (
    descartar_respuesta,
    devolver_al_bot,
    liberar_respuesta,
    reabrir_consulta,
    responder_como_humano,
    tomar_conversacion,
)

PAGINADOR = Paginador()


# --- Traducción de tipos ---------------------------------------------------


def _iso(valor: dt.datetime | dt.date | None) -> str | None:
    """Horas en UTC con `Z`; fechas sin hora en `aaaa-mm-dd`."""
    if valor is None:
        return None
    if isinstance(valor, dt.datetime):
        if timezone.is_naive(valor):
            valor = timezone.make_aware(valor, dt.timezone.utc)
        return valor.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return valor.isoformat()


def _dinero(valor) -> str | None:
    """Siempre string con 2 decimales. Nunca número (contrato)."""
    if valor is None:
        return None
    try:
        return format(Decimal(str(valor)).quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        return None


def _pagina(queryset, request, armar):
    page = PAGINADOR.paginate_queryset(queryset, request, view=None)
    return PAGINADOR.get_paginated_response([armar(item) for item in page or []])


# --- Objetos del contrato --------------------------------------------------


def _me(funcionario) -> dict:
    return {
        "id": funcionario.id,
        "nombre": funcionario.nombre,
        "email": funcionario.email,
        "rol": funcionario.rol,
        "puede_aprobar": funcionario.puede_aprobar,
    }


def _cliente_breve(cliente: Cliente | None) -> dict | None:
    if cliente is None:
        return None
    return {"id": cliente.id, "nombre": cliente.nombre, "apellido": cliente.apellido}


def _funcionario_breve(funcionario) -> dict | None:
    if funcionario is None:
        return None
    return {"id": funcionario.id, "nombre": funcionario.nombre}


def _siniestro(siniestro) -> dict:
    return {
        "numero_siniestro": siniestro.numero_siniestro,
        "fecha_ocurrencia": _iso(siniestro.fecha_ocurrencia),
        "descripcion": siniestro.descripcion,
        "estado": siniestro.estado,
    }


def _poliza_resumen(fila) -> dict:
    """Sirve para una `Poliza` y para una fila de `v_polizas_resumen`."""
    tipo = getattr(fila, "tipo_seguro", None)
    return {
        "id": getattr(fila, "poliza_id", None) or fila.id,
        "numero_poliza": fila.numero_poliza,
        "tipo_seguro": tipo if isinstance(tipo, str) else getattr(tipo, "nombre", None),
        "cobertura": fila.cobertura,
        "estado": fila.estado,
        "fecha_vencimiento": _iso(fila.fecha_vencimiento),
        "saldo_pendiente": _dinero(getattr(fila, "saldo_pendiente", None)),
        "proximo_vencimiento_pago": _iso(
            getattr(fila, "proximo_vencimiento_pago", None)
        ),
    }


def _mensaje(mensaje: Mensaje) -> dict:
    return {
        "id": mensaje.id,
        "direccion": mensaje.direccion,
        "emisor": mensaje.emisor,
        "funcionario": _funcionario_breve(mensaje.funcionario),
        "texto": mensaje.texto,
        "estado_envio": mensaje.estado_envio,
        "fecha_hora": _iso(mensaje.fecha_hora),
        "alertas": [alerta.id for alerta in mensaje.alertas.all()],
    }


def _alerta(alerta: Alerta) -> dict:
    return {
        "id": alerta.id,
        "conversacion_id": alerta.consulta.conversacion_id,
        "consulta_id": alerta.consulta_id,
        "mensaje_id": alerta.mensaje_id,
        "tipo": alerta.tipo,
        "severidad": alerta.severidad,
        "descripcion": alerta.descripcion,
        "estado": alerta.estado,
        "creada_en": _iso(alerta.creada_en),
    }


def _conversacion_resumen(conversacion: Conversacion) -> dict:
    """Usa las anotaciones de `selectors.bandeja`; sin ellas, las deduce."""
    texto = getattr(conversacion, "ultimo_texto", None)
    emisor = getattr(conversacion, "ultimo_emisor", None)
    fecha_hora = getattr(conversacion, "ultimo_fecha_hora", None)
    ultimo = (
        {"texto": texto, "emisor": emisor, "fecha_hora": _iso(fecha_hora)}
        if emisor is not None
        else None
    )
    severidad = severidad_por_rango(getattr(conversacion, "severidad_rango", 0) or 0)
    ahora = timezone.now()
    contacto = conversacion.contacto
    return {
        "id": conversacion.id,
        "whatsapp": contacto.numero if contacto else None,
        "cliente": _cliente_breve(contacto.cliente if contacto else None),
        "estado": conversacion.estado,
        "modo": conversacion.modo,
        "atendida_por": _funcionario_breve(conversacion.funcionario),
        "ultimo_mensaje": ultimo,
        "alertas_abiertas": getattr(conversacion, "alertas_abiertas", 0) or 0,
        "severidad_maxima": severidad,
        "color": color_por_severidad(severidad),
        "respuestas_retenidas": getattr(conversacion, "retenidas", 0) or 0,
        "sin_respuesta": sin_respuesta(
            estado=conversacion.estado,
            modo=conversacion.modo,
            ultimo_emisor=emisor,
            ultimo_fecha_hora=fecha_hora,
            ahora=ahora,
        ),
        "ventana_24h_abierta": ventana_24h_abierta(
            conversacion.ultimo_mensaje_cliente_en, ahora
        ),
    }


def _conversacion_anotada(conversacion_id: int) -> Conversacion:
    """La fila de `bandeja` para una conversación. `NoEncontrado` si no está."""
    conversacion = selectors.bandeja().filter(pk=conversacion_id).first()
    if conversacion is None:
        raise NoEncontrado("La conversación no existe.")
    return conversacion


def _conversacion_detalle(conversacion_id: int) -> dict:
    payload = _conversacion_resumen(_conversacion_anotada(conversacion_id))
    conversacion = selectors.detalle_conversacion(conversacion_id)
    cliente = conversacion.contacto.cliente if conversacion.contacto else None
    payload["cliente_info"] = (
        {
            "id": cliente.id,
            "dni": cliente.dni,
            "nombre": cliente.nombre,
            "apellido": cliente.apellido,
            "polizas": [
                _poliza_resumen(fila) for fila in selectors.resumen_polizas(cliente.id)
            ],
        }
        if cliente is not None
        else None
    )
    # Para prellenar el alta cuando el contacto es desconocido: es lo único que
    # sabemos de esa persona antes de que un humano cargue sus datos reales.
    payload["nombre_perfil"] = (
        conversacion.contacto.nombre_perfil if conversacion.contacto else None
    )
    payload["alertas"] = [
        _alerta(alerta)
        for alerta in selectors.alertas_abiertas(
            conversacion_id=conversacion_id
        ).select_related("consulta")
    ]
    return payload


def _consulta_resumen(consulta: ConsultaBot) -> dict:
    abiertas = [
        alerta
        for alerta in consulta.alertas.all()
        if alerta.estado in {"abierta", "en_revision"}
    ]
    rango = max((RANGO_SEVERIDAD.get(a.severidad, 0) for a in abiertas), default=0)
    contacto = consulta.contacto
    return {
        "id": consulta.id,
        "codigo_caso": consulta.codigo_caso,
        "conversacion_id": consulta.conversacion_id,
        "cliente": _cliente_breve(contacto.cliente if contacto else None),
        "tipo_consulta": consulta.tipo_consulta.codigo,
        "estado": consulta.estado,
        "alertas_abiertas": len(abiertas),
        "severidad_maxima": severidad_por_rango(rango),
    }


def _accion(accion: AccionPendiente) -> dict:
    consulta = accion.consulta
    contacto = consulta.contacto or (
        consulta.conversacion.contacto if consulta.conversacion else None
    )
    poliza = accion.poliza
    return {
        "id": accion.id,
        "tipo_accion": accion.tipo_accion,
        "estado": accion.estado,
        "consulta_id": accion.consulta_id,
        "conversacion_id": consulta.conversacion_id,
        "cliente": _cliente_breve(contacto.cliente if contacto else None),
        "poliza": (
            {"id": poliza.id, "numero_poliza": poliza.numero_poliza}
            if poliza is not None
            else None
        ),
        "parametros": accion.parametros or {},
        "solicitada_en": _iso(accion.solicitada_en),
        "resuelta_por": _funcionario_breve(accion.resuelta_por),
        "resuelta_en": _iso(accion.resuelta_en),
        "motivo": accion.motivo,
    }


def _derivacion(derivacion: Derivacion) -> dict:
    return {
        "id": derivacion.id,
        "consulta_id": derivacion.consulta_id,
        "conversacion_id": derivacion.consulta.conversacion_id,
        "prioridad": derivacion.prioridad,
        "motivo": derivacion.motivo,
        "creada_en": _iso(derivacion.creada_en),
        "atendida_en": _iso(derivacion.atendida_en),
    }


def _cliente_resumen(cliente: Cliente) -> dict:
    return {
        "id": cliente.id,
        "dni": cliente.dni,
        "nombre": cliente.nombre,
        "apellido": cliente.apellido,
        "email": cliente.email,
        "activo": cliente.activo,
        "polizas_vigentes": getattr(cliente, "polizas_vigentes", 0) or 0,
    }


def _cliente_detalle(cliente: Cliente) -> dict:
    polizas = list(cliente.polizas.all())
    return {
        "id": cliente.id,
        "dni": cliente.dni,
        "nombre": cliente.nombre,
        "apellido": cliente.apellido,
        "email": cliente.email,
        "activo": cliente.activo,
        "contactos": [contacto.numero for contacto in cliente.contactos.all()],
        "polizas": [_poliza_resumen(poliza) for poliza in polizas],
        "siniestros": [
            _siniestro(siniestro)
            for poliza in polizas
            for siniestro in poliza.siniestros.all()
        ],
    }


def _poliza_detalle(poliza: Poliza) -> dict:
    payload = _poliza_resumen(poliza)
    payload.update(
        {
            "cliente": _cliente_breve(poliza.cliente),
            "fecha_inicio": _iso(poliza.fecha_inicio),
            "prima_mensual": _dinero(poliza.prima_mensual),
            "bien_asegurado": poliza.bien_asegurado,
            "conductores": [
                {
                    "nombre": conductor.nombre,
                    "dni": conductor.dni,
                    "relacion": conductor.relacion,
                }
                for conductor in poliza.conductores.all()
            ],
            "cuotas": [
                {
                    "periodo": _iso(cuota.periodo),
                    "importe": _dinero(cuota.importe),
                    "vencimiento": _iso(cuota.vencimiento),
                    "estado": cuota.estado,
                }
                for cuota in poliza.cuotas.all()
            ],
            "siniestros": [
                _siniestro(siniestro) for siniestro in poliza.siniestros.all()
            ],
        }
    )
    return payload


# --- Sesión ----------------------------------------------------------------


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def auth_csrf(request):
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def auth_login(request):
    datos = LoginSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    user = authenticate(
        request,
        username=datos.validated_data["email"],
        password=datos.validated_data["password"],
    )
    if user is None:
        return Response(
            {"error": {"codigo": "no_autenticado", "mensaje": "Credenciales inválidas."}},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    # Un `User` sin funcionario activo no entra: `funcionario_de` lanza
    # `PermisoDenegado` y el manejador lo traduce a 403.
    funcionario = funcionario_de(user)
    login(request, user)
    return Response(_me(funcionario))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def auth_logout(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def auth_me(request):
    return Response(_me(request.funcionario))


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def pendientes(request):
    return Response(selectors.contar_pendientes(request.funcionario.id))


# --- Supervisión -----------------------------------------------------------


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversaciones_listar(request):
    queryset = selectors.bandeja(
        estado=request.query_params.get("estado") or None,
        con_alertas=request.query_params.get("con_alertas") == "1",
        esperando_humano=request.query_params.get("esperando_humano") == "1",
        q=request.query_params.get("q") or None,
    )
    return _pagina(queryset, request, _conversacion_resumen)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversacion_detalle(request, id):
    return Response(_conversacion_detalle(id))


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def mensajes_conversacion(request, id):
    crudo = request.query_params.get("despues_de")
    despues_de = None
    if crudo not in (None, ""):
        try:
            despues_de = int(crudo)
        except (TypeError, ValueError):
            raise DatosInvalidos("`despues_de` tiene que ser un número.")
    mensajes = selectors.mensajes_de(id, despues_de)
    return Response({"mensajes": [_mensaje(mensaje) for mensaje in mensajes]})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversacion_tomar(request, id):
    tomar_conversacion(id, request.funcionario.id)
    return Response(_conversacion_detalle(id))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversacion_devolver(request, id):
    devolver_al_bot(id, request.funcionario.id)
    return Response(_conversacion_detalle(id))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversacion_responder(request, id):
    datos = ResponderSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    mensaje = responder_como_humano(
        id, request.funcionario.id, datos.validated_data["texto"]
    )
    return Response(_mensaje(mensaje), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def mensaje_liberar(request, id):
    datos = TextoCorregidoSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    mensaje = liberar_respuesta(
        id, request.funcionario.id, datos.validated_data.get("texto_corregido")
    )
    return Response(_mensaje(mensaje))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def mensaje_descartar(request, id):
    datos = MotivoSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    mensaje = descartar_respuesta(
        id, request.funcionario.id, datos.validated_data["motivo"]
    )
    return Response(_mensaje(mensaje))


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def alertas_listar(request):
    estado = request.query_params.get("estado")
    queryset = selectors.listar_alertas(
        tipo=request.query_params.get("tipo") or None,
        severidad=request.query_params.get("severidad") or None,
        estado="abierta" if estado is None else (estado or None),
    )
    return _pagina(queryset.select_related("consulta"), request, _alerta)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def consultas_cerradas_con_alertas(request):
    queryset = selectors.consultas_cerradas_con_alertas().select_related(
        "contacto__cliente", "tipo_consulta"
    ).prefetch_related("alertas")
    return _pagina(queryset, request, _consulta_resumen)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def consulta_reabrir(request, id):
    consulta = reabrir_consulta(id, request.funcionario.id)
    return Response(_consulta_resumen(consulta))


# --- Acciones y derivaciones ----------------------------------------------


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def acciones_listar(request):
    estado = request.query_params.get("estado")
    queryset = selectors.listar_acciones(
        estado="pendiente" if estado is None else (estado or None)
    )
    return _pagina(queryset, request, _accion)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def accion_detalle(request, id):
    accion = (
        AccionPendiente.objects.select_related(
            "consulta__contacto__cliente",
            "consulta__conversacion__contacto__cliente",
            "poliza",
            "resuelta_por",
        )
        .filter(pk=id)
        .first()
    )
    if accion is None:
        raise NoEncontrado("La acción no existe.")
    return Response(_accion(accion))


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def accion_parametros(request, id):
    datos = ParametrosSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    accion = completar_parametros(
        id, request.funcionario.id, datos.validated_data["parametros"]
    )
    return Response(_accion(accion))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def accion_aprobar(request, id):
    motivo = (request.data or {}).get("motivo")
    accion = aprobar_accion(id, request.funcionario.id, motivo)
    return Response(_accion(accion))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def accion_rechazar(request, id):
    datos = MotivoSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    accion = rechazar_accion(id, request.funcionario.id, datos.validated_data["motivo"])
    return Response(_accion(accion))


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def derivaciones_listar(request):
    queryset = selectors.derivaciones_de(
        request.funcionario.id,
        incluir_atendidas=request.query_params.get("atendidas") == "1",
    ).select_related("consulta")
    return _pagina(queryset, request, _derivacion)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def derivacion_atender(request, id):
    derivacion = atender_derivacion(id, request.funcionario.id)
    return Response(_derivacion(derivacion))


# --- Clientes (ABM manual) y pólizas (solo lectura) -----------------------


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
def clientes_listar_o_crear(request):
    if request.method == "POST":
        datos = ClienteAltaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        cliente = alta_cliente(**datos.validated_data)
        return Response(
            _cliente_detalle(selectors.detalle_cliente(cliente.id)),
            status=status.HTTP_201_CREATED,
        )

    queryset = selectors.buscar_clientes(request.query_params.get("q") or None)
    return _pagina(queryset, request, _cliente_resumen)


@api_view(["GET", "PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
def cliente_detalle_o_modificar(request, id):
    if request.method == "PATCH":
        datos = ClienteModificacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        # `email` ausente deja el actual; `email` vacío lo borra. Son distintos.
        campos = dict(datos.validated_data)
        campos.setdefault("email", SIN_CAMBIO)
        modificar_cliente(id, **campos)
    return Response(_cliente_detalle(selectors.detalle_cliente(id)))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def cliente_baja(request, id):
    dar_de_baja_cliente(id)
    return Response(_cliente_detalle(selectors.detalle_cliente(id)))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def cliente_reactivar(request, id):
    reactivar_cliente(id)
    return Response(_cliente_detalle(selectors.detalle_cliente(id)))


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def poliza_detalle(request, id):
    return Response(_poliza_detalle(selectors.detalle_poliza(id)))
