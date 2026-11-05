"""Las vistas de la API JSON.

Esta capa **no tiene reglas de negocio**: valida la entrada, llama a `negocio`
(escrituras) o a `datos.selectors` (lecturas), y traduce a JSON.

Los errores no se atrapan acá: las excepciones de `negocio.errores` suben y las
traduce `api.errores.manejar` (configurado en `EXCEPTION_HANDLER`), que es el
único lugar donde vive el mapeo código → HTTP.
"""

from __future__ import annotations

from negocio.comisiones import importe_comision

import csv
import datetime as dt
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from django.db import transaction
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
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
from api.permisos import EsAprobador, EsAprobadorParaEscribir, EsFuncionario, EsPropietario
from api.serializers import (
    ClaveSerializer,
    ClienteAltaSerializer,
    ConvertirInteresadoSerializer,
    CotizacionAltaSerializer,
    InteresadoAltaSerializer,
    InteresadoModificacionSerializer,
    MoverInteresadoSerializer,
    ClienteModificacionSerializer,
    BuscarDocumentoSerializer,
    DocumentoAltaSerializer,
    DenunciaSiniestroSerializer,
    LoginSerializer,
    MotivoSerializer,
    FinalizacionAccionSerializer,
    ParametrosSerializer,
    PagoRegistroSerializer,
    CompaniaAltaSerializer,
    CompaniaModificacionSerializer,
    PolizaAltaSerializer,
    ResponderSerializer,
    ReporteGestionFiltroSerializer,
    TextoCorregidoSerializer,
    TransicionSiniestroSerializer,
    UsuarioAltaSerializer,
    UsuarioModificacionSerializer,
    VehiculoAltaSerializer,
    VehiculoModificacionSerializer,
)
from negocio.usuarios import cambiar_clave, crear_usuario, listar_usuarios, modificar_usuario
from datos import selectors
from datos.models import (
    AccionPendiente,
    Alerta,
    Cliente,
    Compania,
    ConsultaBot,
    Conversacion,
    Derivacion,
    Cobertura,
    Cotizacion,
    EstadoAccion,
    EstadoInteresado,
    EstadoDocumento,
    DocumentoGeneral,
    EstadoEnvio,
    Interesado,
    Mensaje,
    OrigenInteresado,
    Poliza,
    EstadoSiniestro,
    Siniestro,
    TipoSeguro,
    Vehiculo,
)
from negocio.adjuntos_siniestros import (
    AdjuntoInvalido,
    abrir_adjunto,
    guardar_adjunto_panel,
)
from negocio.documentos import (
    aprobar_documento,
    buscar_fragmentos,
    crear_documento,
    retirar_documento,
)
from negocio.acciones import (
    aprobar_accion,
    atender_derivacion,
    completar_parametros,
    polizas_disponibles_para_baja,
    rechazar_accion,
    finalizar_gestion_externa,
)
from negocio.polizas import alta_poliza, proximo_numero_poliza, registrar_pago
from negocio.siniestros import registrar_denuncia, transicionar_siniestro
from negocio.clientes import (
    SIN_CAMBIO,
    alta_cliente,
    dar_de_baja_cliente,
    modificar_cliente,
    reactivar_cliente,
)
from negocio.companias import alta_compania, modificar_compania
from negocio.cotizaciones import cargar_cotizacion, elegir_cotizacion, quitar_cotizacion
from negocio.interesados import (
    actualizar_datos_interesado,
    asignar_interesado,
    convertir_en_cliente,
    crear_interesado,
    mover_interesado,
    programar_contacto,
)
from negocio.errores import DatosInvalidos, NoEncontrado, PermisoDenegado
from negocio.vehiculos import alta_vehiculo, dar_de_baja_vehiculo, modificar_vehiculo
from negocio.reglas import (
    RANGO_SEVERIDAD,
    color_por_severidad,
    severidad_por_rango,
    sin_respuesta,
    ventana_24h_abierta,
)
from negocio.sesion import funcionario_de
from negocio.supervision import (
    ESTADOS_CASO_ABIERTO,
    cerrar_casos,
    descartar_respuesta,
    devolver_al_bot,
    liberar_respuesta,
    reabrir_consulta,
    responder_como_humano,
    tomar_conversacion,
    vaciar_chat,
    vaciar_alertas,
    borrar_conversacion,
    desbloquear_numero,
)



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
    # Un paginador por llamada: guarda la página en `self`, y compartido entre
    # hilos (gunicorn gthread) dos pedidos en paralelo se pisaban el total.
    paginador = Paginador()
    page = paginador.paginate_queryset(queryset, request, view=None)
    return paginador.get_paginated_response([armar(item) for item in page or []])


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


def _siniestro_expediente(
    siniestro: Siniestro, *, incluir_adjuntos: bool = True
) -> dict:
    return {
        "id": siniestro.id,
        "numero_siniestro": siniestro.numero_siniestro,
        "cliente": _cliente_breve(siniestro.poliza.cliente),
        "poliza": {
            "id": siniestro.poliza_id,
            "numero_poliza": siniestro.poliza.numero_poliza,
        },
        "fecha_ocurrencia": _iso(siniestro.fecha_ocurrencia),
        "descripcion": siniestro.descripcion,
        "estado": siniestro.estado,
        "creado_en": _iso(siniestro.creado_en),
        "historial": [
            {
                "estado_anterior": entrada.estado_anterior,
                "estado_nuevo": entrada.estado_nuevo,
                "motivo": entrada.motivo,
                "responsable": _funcionario_breve(entrada.responsable),
                "fecha": _iso(entrada.fecha),
            }
            for entrada in siniestro.historial.all()
        ],
        "adjuntos": (
            [
                {
                    "id": adjunto.id,
                    "content_type": adjunto.content_type,
                    "tamano": adjunto.tamano,
                    "origen": adjunto.origen,
                    "creado_en": _iso(adjunto.creado_en),
                    "descarga_url": (
                        f"/api/siniestros/{siniestro.id}/adjuntos/{adjunto.id}/"
                    ),
                }
                for adjunto in siniestro.adjuntos.order_by("creado_en", "id")
            ]
            if incluir_adjuntos
            else []
        ),
        "aclaracion_decision": (
            "Las decisiones del expediente son internas y no confirman ni "
            "prometen una indemnización de la aseguradora."
        ),
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
    derivacion_urgente = bool(
        getattr(conversacion, "derivacion_urgente", False)
    )
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
        "derivacion_urgente": derivacion_urgente,
        "color": "rojo" if derivacion_urgente else color_por_severidad(severidad),
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
    from negocio.bot.orquestador import bloqueado_hasta

    payload = _conversacion_resumen(_conversacion_anotada(conversacion_id))
    conversacion = selectors.detalle_conversacion(conversacion_id)

    contacto_id = conversacion.contacto_id
    payload["bloqueado_hasta"] = _iso(bloqueado_hasta(contacto_id))

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
    payload['contacto_reconocido'] = bool(conversacion.contacto.cliente_id and conversacion.contacto.cliente.activo)
    from negocio.interesados import interesado_abierto_de
    interesado_chat = interesado_abierto_de(contacto_id)
    payload['interesado'] = ({'id':interesado_chat.id,'nombre':interesado_chat.nombre,
        'apellido':interesado_chat.apellido,'datos':interesado_chat.datos or {}} if interesado_chat else None)
    payload["nombre_perfil"] = (
        conversacion.contacto.nombre_perfil if conversacion.contacto else None
    )
    payload["alertas"] = [
        _alerta(alerta)
        for alerta in selectors.alertas_abiertas(
            conversacion_id=conversacion_id
        ).select_related("consulta")
    ]
    # Con esto el panel sabe si hay algo que cerrar y cuántos casos son.
    payload["casos_abiertos"] = [
        {
            "id": caso.id,
            "codigo_caso": caso.codigo_caso,
            "estado": caso.estado,
            "acciones_pendientes": [
                {
                    "id": accion.id,
                    "tipo_accion": accion.get_tipo_accion_display(),
                    "estado": accion.estado,
                }
                for accion in caso.acciones.filter(
                    estado__in=(EstadoAccion.PENDIENTE, EstadoAccion.APROBADA)
                ).order_by("id")
            ],
        }
        for caso in ConsultaBot.objects.filter(
            conversacion_id=conversacion_id, estado__in=ESTADOS_CASO_ABIERTO
        ).order_by("id")
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
    finalizacion = getattr(accion, "finalizacion", None)
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
        "finalizacion": (
            {
                "funcionario": _funcionario_breve(finalizacion.funcionario),
                "fecha": _iso(finalizacion.fecha),
                "referencia": finalizacion.referencia,
                "motivo": finalizacion.motivo,
            } if finalizacion is not None else None
        ),
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


def _vehiculo(vehiculo: Vehiculo | None) -> dict | None:
    if vehiculo is None:
        return None
    return {
        "id": vehiculo.id,
        "cliente": vehiculo.cliente_id,
        "patente": vehiculo.patente,
        "marca": vehiculo.marca,
        "modelo": vehiculo.modelo,
        "anio": vehiculo.anio,
        "uso": vehiculo.uso,
        "clase": vehiculo.clase,
        "chasis": vehiculo.chasis,
        "valor_asegurado": _dinero(vehiculo.valor_asegurado),
        "activo": vehiculo.activo,
    }


def _comision(valor, ver_comision: bool) -> str | None:
    """La comisión es información del dueño: un operador la recibe en `null`."""
    if not ver_comision or valor is None:
        return None
    return _dinero(valor)


def _compania(compania: Compania | None, ver_comision: bool) -> dict | None:
    if compania is None:
        return None
    return {
        "id": compania.id,
        "nombre": compania.nombre,
        "comision_pct": _comision(compania.comision_pct, ver_comision),
        "activa": compania.activa,
    }


def _ve_comision(request) -> bool:
    return bool(request.funcionario.puede_aprobar)


def _poliza_con_bien(poliza: Poliza, ver_comision: bool) -> dict:
    """`poliza_resumen` + vehículo, compañía y comisión (esta última, solo si se ve)."""
    payload = _poliza_resumen(poliza)
    payload.update(
        {
            "vehiculo": _vehiculo(poliza.vehiculo),
            "compania": _compania(poliza.compania, ver_comision),
            "comision_pct": _comision(poliza.comision_pct, ver_comision),
            "comision_mensual_estimada": _comision(
                importe_comision(poliza.prima_mensual, poliza.comision_pct), ver_comision),
        }
    )
    return payload


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


def _cliente_detalle(cliente: Cliente, ver_comision: bool = False) -> dict:
    polizas = list(cliente.polizas.all())
    return {
        "id": cliente.id,
        "dni": cliente.dni,
        "nombre": cliente.nombre,
        "apellido": cliente.apellido,
        "email": cliente.email,
        "activo": cliente.activo,
        "contactos": [contacto.numero for contacto in cliente.contactos.all()],
        "polizas": [_poliza_con_bien(poliza, ver_comision) for poliza in polizas],
        "vehiculos": [
            _vehiculo(vehiculo) for vehiculo in cliente.vehiculos.all() if vehiculo.activo
        ],
        "siniestros": [
            _siniestro(siniestro)
            for poliza in polizas
            for siniestro in poliza.siniestros.all()
        ],
    }


def _poliza_detalle(poliza: Poliza, ver_comision: bool = False) -> dict:
    payload = _poliza_con_bien(poliza, ver_comision)
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


@csrf_protect
@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def auth_login(request):
    datos = LoginSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    from negocio.seguridad import admitir
    email = datos.validated_data["email"].strip().lower()
    ip = request.META.get("REMOTE_ADDR", "")
    # No confiar en X-Forwarded-For que puede falsificar un cliente.
    if not admitir("login-ip:" + ip, 60) or not admitir("login-cuenta:" + email, 10):
        return Response({"error": {"codigo": "limite_acceso", "mensaje": "Demasiados intentos. Volvé a intentar en 15 minutos."}}, status=429, headers={"Retry-After": "900"})
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


auth_login.csrf_exempt = False


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
    if request.query_params.get('agrupada') == '1':
        qs, cantidades = selectors.bandeja_contactos(
            vista=request.query_params.get('vista','atencion'),
            con_alertas=request.query_params.get('con_alertas')=='1',
            esperando_humano=request.query_params.get('esperando_humano')=='1',
            q=request.query_params.get('q') or None,
        )
        respuesta = _pagina(qs, request, _conversacion_resumen)
        respuesta.data['clientes'] = cantidades
        return respuesta
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
@permission_classes([EsAprobador])
def conversacion_desbloquear(request, id):
    desbloquear_numero(id, request.funcionario.id)
    return Response(_conversacion_detalle(id))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversacion_cerrar_casos(request, id):
    """Cierra los casos abiertos de la conversación; el chat sigue abierto."""
    cerrar_casos(id, request.funcionario.id)
    return Response(_conversacion_detalle(id))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def conversacion_vaciar(request, id):
    """Cierra la conversación para que el bot arranque sin contexto."""
    vaciar_chat(id, request.funcionario.id)
    return Response(_conversacion_detalle(id))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def conversacion_vaciar_alertas(request, id):
    """Descarta las alertas abiertas de la conversación; devuelve el detalle."""
    vaciar_alertas(id, request.funcionario.id)
    return Response(_conversacion_detalle(id))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def conversacion_borrar(request, id):
    """Borra la conversación entera. 409 si hay expedientes que dependen de ella."""
    borrados = borrar_conversacion(id, request.funcionario.id)
    return Response({"id": id, "borrados": borrados})


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


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def reporte_gestion(request):
    filtros = ReporteGestionFiltroSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    desde = filtros.validated_data["desde"]
    hasta = filtros.validated_data["hasta"]
    datos = selectors.reporte_gestion(desde, hasta)
    definiciones = {
        "consultas": "Consultas cuyo fecha_hora cae dentro del período, en hora local.",
        "cerradas": "Consultas cuyo estado actual es cerrado, contadas por fecha_hora.",
        "pendientes": (
            "Consultas en estado abierto, pendiente_revision o derivado, "
            "contadas por fecha_hora."
        ),
        "motivos": (
            "Consultas agrupadas por el nombre del tipo_consulta, contadas por fecha_hora."
        ),
        "derivaciones_urgentes": (
            "Derivaciones con prioridad urgente, contadas por creada_en."
        ),
        "cobros": (
            "Movimientos de Pago registrados, contados y sumados por fecha_pago; "
            "no se infieren desde el estado de las cuotas."
        ),
    }
    if filtros.validated_data["formato"] == "csv":
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="reporte-gestion-{desde.isoformat()}-'
            f'{hasta.isoformat()}.csv"'
        )
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        escritor = csv.writer(respuesta)
        escritor.writerow(("Desde", desde.isoformat()))
        escritor.writerow(("Hasta", hasta.isoformat()))
        escritor.writerow(("Indicador", "Definición", "Detalle", "Cantidad", "Importe"))
        escritor.writerow(
            ("Consultas", definiciones["consultas"], "Total", datos["consultas"]["total"], "")
        )
        escritor.writerow(
            ("Consultas", definiciones["cerradas"], "Cerradas", datos["consultas"]["cerradas"], "")
        )
        escritor.writerow(
            ("Consultas", definiciones["pendientes"], "Pendientes", datos["consultas"]["pendientes"], "")
        )
        for motivo in datos["motivos"]:
            escritor.writerow(
                (
                    "Motivo",
                    definiciones["motivos"],
                    _celda_csv_segura(motivo["nombre"]),
                    motivo["cantidad"],
                    "",
                )
            )
        escritor.writerow(
            (
                "Derivaciones",
                definiciones["derivaciones_urgentes"],
                "Urgentes",
                datos["derivaciones_urgentes"],
                "",
            )
        )
        escritor.writerow(
            (
                "Cobros",
                definiciones["cobros"],
                "Movimientos registrados",
                datos["cobros"]["cantidad"],
                "",
            )
        )
        escritor.writerow(
            (
                "Cobros",
                definiciones["cobros"],
                "Importe total registrado",
                "",
                _dinero(datos["cobros"]["importe_total"]),
            )
        )
        return respuesta

    return Response(
        {
            "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
            "definiciones": definiciones,
            **datos,
            "cobros": {
                **datos["cobros"],
                "importe_total": _dinero(datos["cobros"]["importe_total"]),
            },
        }
    )


def _celda_csv_segura(valor: str) -> str:
    texto = str(valor)
    if texto.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + texto
    return texto


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
    payload = _accion(accion)
    if (
        accion.tipo_accion == "baja_poliza"
        and accion.estado == "pendiente"
        and accion.poliza_id is None
    ):
        try:
            polizas = polizas_disponibles_para_baja(accion.id)
        except DatosInvalidos as error:
            payload["polizas_disponibles"] = []
            payload["poliza_no_disponible"] = error.mensaje
        else:
            payload["polizas_disponibles"] = [
                {
                    "id": poliza.id,
                    "numero_poliza": poliza.numero_poliza,
                    "estado": poliza.estado,
                    "bien_asegurado": poliza.bien_asegurado,
                }
                for poliza in polizas
            ]
            if not polizas:
                payload["poliza_no_disponible"] = (
                    "El cliente vinculado no tiene pólizas para seleccionar."
                )
    return Response(payload)


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
    from api.serializers import AprobacionSerializer
    datos = AprobacionSerializer(data=request.data or {})
    datos.is_valid(raise_exception=True)
    accion = aprobar_accion(id, request.funcionario.id, **datos.validated_data)
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
            _cliente_detalle(
                selectors.detalle_cliente(cliente.id), _ve_comision(request)
            ),
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
    return Response(
        _cliente_detalle(selectors.detalle_cliente(id), _ve_comision(request))
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def cliente_baja(request, id):
    dar_de_baja_cliente(id)
    return Response(
        _cliente_detalle(selectors.detalle_cliente(id), _ve_comision(request))
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def cliente_reactivar(request, id):
    reactivar_cliente(id)
    return Response(
        _cliente_detalle(selectors.detalle_cliente(id), _ve_comision(request))
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def poliza_detalle(request, id):
    return Response(
        _poliza_detalle(selectors.detalle_poliza(id), _ve_comision(request))
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def poliza_opciones(request):
    """Lo que el formulario de alta necesita para armarse, en una sola llamada.

    El número sugerido es el próximo libre y viaja como propuesta, no como
    reserva: entre que se abre el formulario y se guarda puede aparecer otra
    póliza, y por eso `alta_poliza` lo vuelve a resolver con el lock tomado.
    """
    return Response(
        {
            "numero_sugerido": proximo_numero_poliza(),
            "tipos_seguro": [
                {"codigo": tipo.codigo, "nombre": tipo.nombre}
                for tipo in TipoSeguro.objects.filter(codigo="automotor").order_by("nombre")
            ],
            "coberturas": list(Cobertura.values),
        }
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def documentos_buscar(request):
    consulta = BuscarDocumentoSerializer(data=request.query_params)
    consulta.is_valid(raise_exception=True)
    return Response(buscar_fragmentos(consulta.validated_data["q"]))


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
@transaction.atomic
def documento_crear(request):
    if request.method == "GET":
        documentos = _documentos_visibles(request)
        estado_documento = request.query_params.get("estado", "")
        if estado_documento:
            if estado_documento not in EstadoDocumento.values:
                raise DatosInvalidos("El estado del documento no es válido.")
            documentos = documentos.filter(estado=estado_documento)
        return _pagina(documentos.order_by("-creado_en", "-id"), request, _documento)
    datos = DocumentoAltaSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    numero_poliza = request.data.get("numero_poliza", "")
    # Validar antes de crear para no dejar un borrador huérfano por un typo.
    if numero_poliza and (not isinstance(numero_poliza, str) or not Poliza.objects.filter(numero_poliza=numero_poliza.strip()).exists()):
        raise DatosInvalidos("La póliza indicada no existe.")
    documento = crear_documento(
        **datos.validated_data,
        funcionario_id=request.funcionario.id,
    )
    if numero_poliza:
        from negocio.coberturas import vincular_documento
        vincular_documento(numero_poliza, documento.id, request.funcionario.id)
    return Response(
        {
            "id": documento.id,
            "titulo": documento.titulo,
            "version": documento.version,
            "referencia": documento.referencia,
            "estado": documento.estado,
        },
        status=status.HTTP_201_CREATED,
    )


def _documento(documento):
    return {
        "id": documento.id, "titulo": documento.titulo,
        "version": documento.version, "referencia": documento.referencia,
        "estado": documento.estado, "creado_en": _iso(documento.creado_en),
        "creado_por": _funcionario_breve(documento.creado_por),
        "aprobado_por": _funcionario_breve(documento.aprobado_por),
        "aprobado_en": _iso(documento.aprobado_en),
        "retirado_en": _iso(documento.retirado_en),
    }


def _documentos_visibles(request):
    documentos = DocumentoGeneral.objects.select_related("creado_por", "aprobado_por")
    if not request.funcionario.puede_aprobar:
        documentos = documentos.filter(estado=EstadoDocumento.APROBADO)
    return documentos


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def documento_detalle(request, id):
    documento = _documentos_visibles(request).filter(pk=id).first()
    if documento is None:
        raise NoEncontrado("El documento no existe o no está disponible.")
    respuesta = _documento(documento)
    respuesta["contenido"] = "".join(documento.fragmentos.order_by("orden").values_list("texto", flat=True))
    return Response(respuesta)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def accion_finalizar(request, id):
    datos = FinalizacionAccionSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    accion = finalizar_gestion_externa(id, request.funcionario.id, **datos.validated_data)
    return Response(_accion(accion))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def documento_aprobar(request, id):
    documento = aprobar_documento(id, request.funcionario.id)
    return Response(
        {
            "id": documento.id,
            "titulo": documento.titulo,
            "version": documento.version,
            "estado": documento.estado,
            "aprobado_en": _iso(documento.aprobado_en),
        }
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def documento_retirar(request, id):
    documento = retirar_documento(id, request.funcionario.id)
    return Response(
        {
            "id": documento.id,
            "titulo": documento.titulo,
            "version": documento.version,
            "estado": documento.estado,
            "retirado_en": _iso(documento.retirado_en),
        }
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def poliza_pago(request, id):
    """Registra un cobro completo con referencia de comprobante.

    Pide permiso de aprobación: toca plata y cambia el saldo que el bot le
    contesta al cliente.
    """
    datos = PagoRegistroSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    pago = registrar_pago(
        id,
        referencia=datos.validated_data["referencia"],
        importe=datos.validated_data["importe"],
        funcionario_id=request.funcionario.id,
    )
    respuesta = _poliza_detalle(selectors.detalle_poliza(id), _ve_comision(request))
    respuesta["pago"] = {
        "id": pago.id,
        "referencia": pago.referencia,
        "cuota_id": pago.cuota_id,
        "importe": _dinero(pago.importe),
        "fecha_pago": _iso(pago.fecha_pago),
        "responsable": _funcionario_breve(pago.responsable),
    }
    return Response(respuesta)


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def siniestros_listar_o_crear(request):
    if request.method == "POST":
        datos = DenunciaSiniestroSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        siniestro = registrar_denuncia(
            **datos.validated_data,
            funcionario_id=request.funcionario.id,
        )
        return Response(
            _siniestro_expediente(selectors.detalle_siniestro(siniestro.id)),
            status=status.HTTP_201_CREATED,
        )

    estado = request.query_params.get("estado") or None
    if estado is not None and estado not in EstadoSiniestro.values:
        raise DatosInvalidos("El filtro de estado no es válido.")
    return _pagina(
        selectors.siniestros(estado),
        request,
        lambda siniestro: _siniestro_expediente(
            siniestro, incluir_adjuntos=False
        ),
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def siniestro_detalle(request, id):
    return Response(_siniestro_expediente(selectors.detalle_siniestro(id)))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def siniestro_adjunto_subir(request, id):
    siniestro = selectors.detalle_siniestro(id)
    archivo = request.FILES.get("archivo")
    if archivo is None:
        raise DatosInvalidos("Seleccioná una imagen para adjuntar.")
    try:
        guardar_adjunto_panel(siniestro, archivo, request.funcionario.id)
    except AdjuntoInvalido as error:
        raise DatosInvalidos(str(error)) from error
    return Response(
        _siniestro_expediente(selectors.detalle_siniestro(id)),
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def siniestro_adjunto_descargar(request, id, adjunto_id):
    adjunto, archivo = abrir_adjunto(id, adjunto_id)
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[
        adjunto.content_type
    ]
    respuesta = FileResponse(
        archivo,
        as_attachment=True,
        filename=f"{adjunto.siniestro.numero_siniestro}-{adjunto.id}.{extension}",
        content_type=adjunto.content_type,
    )
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def siniestro_transicionar(request, id):
    datos = TransicionSiniestroSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    transicionar_siniestro(
        id,
        **datos.validated_data,
        funcionario_id=request.funcionario.id,
    )
    return Response(_siniestro_expediente(selectors.detalle_siniestro(id)))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def poliza_crear(request, id):
    """Alta de una póliza para el cliente `id`, con su plan de cuotas."""
    datos = PolizaAltaSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    poliza = alta_poliza(id, **datos.validated_data)
    return Response(
        _poliza_detalle(selectors.detalle_poliza(poliza.id), _ve_comision(request)),
        status=status.HTTP_201_CREATED,
    )


# --- Vehículos y compañías (P1) --------------------------------------------


def _cliente_de_la_consulta(request) -> int:
    crudo = request.query_params.get("cliente")
    if crudo is None or crudo == "":
        raise DatosInvalidos("Indicá el cliente (?cliente=N).")
    try:
        cliente_id = int(crudo)
    except ValueError as error:
        raise DatosInvalidos("El cliente tiene que ser un número.") from error
    if cliente_id < 1:
        raise DatosInvalidos("El cliente tiene que ser un número positivo.")
    return cliente_id


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
def vehiculos_listar_o_crear(request):
    if request.method == "POST":
        datos = VehiculoAltaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        campos = dict(datos.validated_data)
        vehiculo = alta_vehiculo(
            campos.pop("cliente"), funcionario_id=request.funcionario.id, **campos
        )
        return Response(_vehiculo(vehiculo), status=status.HTTP_201_CREATED)

    vehiculos = selectors.vehiculos_de(_cliente_de_la_consulta(request))
    return Response({"resultados": [_vehiculo(vehiculo) for vehiculo in vehiculos]})


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
def vehiculo_modificar(request, id):
    datos = VehiculoModificacionSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    # Ausente deja el valor actual; presente pero vacío lo borra. Son distintos.
    campos = dict(datos.validated_data)
    campos.setdefault("chasis", SIN_CAMBIO)
    campos.setdefault("valor_asegurado", SIN_CAMBIO)
    vehiculo = modificar_vehiculo(id, funcionario_id=request.funcionario.id, **campos)
    return Response(_vehiculo(vehiculo))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def vehiculo_baja(request, id):
    vehiculo = dar_de_baja_vehiculo(id, funcionario_id=request.funcionario.id)
    return Response(_vehiculo(vehiculo))


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
def companias_listar_o_crear(request):
    ver_comision = _ve_comision(request)
    if request.method == "POST":
        datos = CompaniaAltaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        compania = alta_compania(
            funcionario_id=request.funcionario.id, **datos.validated_data
        )
        return Response(
            _compania(compania, ver_comision), status=status.HTTP_201_CREATED
        )

    solo_activas = request.query_params.get("activas") in ("1", "true")
    companias = selectors.listar_companias(solo_activas=solo_activas)
    return Response(
        {"resultados": [_compania(compania, ver_comision) for compania in companias]}
    )


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobadorParaEscribir])
def compania_modificar(request, id):
    datos = CompaniaModificacionSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    compania = modificar_compania(
        id, funcionario_id=request.funcionario.id, **datos.validated_data
    )
    return Response(_compania(compania, _ve_comision(request)))


# --- Usuarios (solo el propietario) ----------------------------------------


def _usuario(funcionario) -> dict:
    return {
        "id": funcionario.id,
        "nombre": funcionario.nombre,
        "email": funcionario.email,
        "rol": funcionario.rol,
        "puede_aprobar": funcionario.puede_aprobar,
        "activo": funcionario.activo,
        "creado_en": _iso(funcionario.creado_en),
    }


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsPropietario])
def usuarios_listar_o_crear(request):
    if request.method == "POST":
        datos = UsuarioAltaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        usuario = crear_usuario(**datos.validated_data)
        return Response(_usuario(usuario), status=status.HTTP_201_CREATED)
    return Response({"resultados": [_usuario(f) for f in listar_usuarios()]})


@api_view(["PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsPropietario])
def usuario_modificar(request, id):
    datos = UsuarioModificacionSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    return Response(_usuario(modificar_usuario(id, **datos.validated_data)))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsPropietario])
def usuario_cambiar_clave(request, id):
    datos = ClaveSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    return Response(_usuario(cambiar_clave(id, datos.validated_data["clave"])))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def poliza_vincular_documento(request, id):
    from negocio.coberturas import vincular_documento
    documento_id = request.data.get('documento_id')
    if not isinstance(documento_id, int) or isinstance(documento_id, bool) or documento_id <= 0:
        raise DatosInvalidos('Indicá un documento_id entero positivo.')
    poliza = Poliza.objects.filter(pk=id).first()
    if poliza is None:
        raise NoEncontrado('La póliza no existe.')
    vinculo = vincular_documento(poliza.numero_poliza, documento_id, request.funcionario.id)
    return Response({'id': vinculo.id, 'poliza_id': id, 'documento_id': documento_id})


# --- Embudo de interesados y cotizaciones (P5) ------------------------------


def _contacto_breve(contacto) -> dict | None:
    if contacto is None:
        return None
    return {
        "id": contacto.id,
        "whatsapp": contacto.numero,
        "nombre_perfil": contacto.nombre_perfil,
        "cliente_id": contacto.cliente_id,
    }


def _interesado_item(interesado: Interesado) -> dict:
    """Lo que muestra una tarjeta del tablero. `seguimiento_vencido` lo decide el servidor."""
    vencido = (
        interesado.proximo_contacto is not None
        and interesado.proximo_contacto < timezone.localdate()
        and interesado.estado not in (EstadoInteresado.EMITIDA, EstadoInteresado.PERDIDA)
    )
    return {
        "id": interesado.id,
        "nombre": interesado.nombre,
        "apellido": interesado.apellido,
        "origen": interesado.origen,
        "estado": interesado.estado,
        "responsable": _funcionario_breve(interesado.responsable),
        "proximo_contacto": _iso(interesado.proximo_contacto),
        "seguimiento_vencido": vencido,
        "motivo_perdida": interesado.motivo_perdida,
        "datos": interesado.datos or {},
        "cliente_id": interesado.cliente_id,
        "contacto": _contacto_breve(interesado.contacto),
        "creado_en": _iso(interesado.creado_en),
        "actualizado_en": _iso(interesado.actualizado_en),
    }


def _linea_historial(linea) -> dict:
    return {
        "id": linea.id,
        "estado_anterior": linea.estado_anterior,
        "estado_nuevo": linea.estado_nuevo,
        "nota": linea.nota or None,
        "funcionario": _funcionario_breve(linea.funcionario),
        "fecha": _iso(linea.fecha),
    }


def _cotizacion_item(cotizacion: Cotizacion, ver_comision: bool) -> dict:
    return {
        "id": cotizacion.id,
        "interesado": cotizacion.interesado_id,
        "poliza": cotizacion.poliza_id,
        "compania": _compania(cotizacion.compania, ver_comision),
        "cobertura": cotizacion.cobertura,
        "prima_mensual": _dinero(cotizacion.prima_mensual),
        "vigencia_hasta": _iso(cotizacion.vigencia_hasta),
        "elegida": cotizacion.elegida,
        "notas": cotizacion.notas,
        "creada_por": _funcionario_breve(cotizacion.creada_por),
        "creada_en": _iso(cotizacion.creada_en),
    }


def _interesado_detalle(interesado: Interesado, ver_comision: bool) -> dict:
    """La ficha: la tarjeta más el historial, las cotizaciones (de la más barata) y el cliente."""
    payload = _interesado_item(interesado)
    payload['conversacion_id'] = (
        Conversacion.objects.filter(contacto_id=interesado.contacto_id)
        .order_by('-creada_en', '-id').values_list('id', flat=True).first()
        if interesado.contacto_id else None
    )
    payload.update(
        {
            "cliente": _cliente_breve(interesado.cliente),
            "historial": [_linea_historial(linea) for linea in interesado.historial.all()],
            "cotizaciones": [
                _cotizacion_item(cotizacion, ver_comision)
                for cotizacion in interesado.cotizaciones.all()
            ],
        }
    )
    return payload


def _responsable_de_la_consulta(request) -> int | None:
    """`?responsable=N` o `?responsable=me`. Vacío o ausente = todos."""
    crudo = (request.query_params.get("responsable") or "").strip()
    if not crudo:
        return None
    if crudo == "me":
        return request.funcionario.id
    try:
        responsable_id = int(crudo)
    except ValueError as error:
        raise DatosInvalidos("El responsable tiene que ser un número o «me».") from error
    if responsable_id < 1:
        raise DatosInvalidos("El responsable tiene que ser un número positivo.")
    return responsable_id


def _entero_de_la_consulta(request, nombre: str) -> int | None:
    crudo = (request.query_params.get(nombre) or "").strip()
    if not crudo:
        return None
    try:
        valor = int(crudo)
    except ValueError as error:
        raise DatosInvalidos(f"El parámetro {nombre} tiene que ser un número.") from error
    if valor < 1:
        raise DatosInvalidos(f"El parámetro {nombre} tiene que ser un número positivo.")
    return valor


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def funcionarios_listar(request):
    """Los funcionarios activos, para elegir un responsable. Solo id, nombre y rol:
    el correo y los permisos son del propietario (`/api/usuarios/`)."""
    return Response(
        {
            "resultados": [
                {"id": f.id, "nombre": f.nombre, "rol": f.rol}
                for f in selectors.funcionarios_activos()
            ]
        }
    )


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def interesados_listar_o_crear(request):
    ver_comision = _ve_comision(request)
    if request.method == "POST":
        datos = InteresadoAltaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        interesado = crear_interesado(request.funcionario.id, **datos.validated_data)
        # Si el número ya tenía un interesado abierto, se devuelve ese: no es un alta.
        ya_existia = bool(getattr(interesado, '_ya_existia', False))
        payload = _interesado_detalle(selectors.detalle_interesado(interesado.id), ver_comision)
        payload["ya_existia"] = ya_existia
        return Response(
            payload,
            status=status.HTTP_200_OK if ya_existia else status.HTTP_201_CREATED,
        )

    estado = request.query_params.get("estado") or None
    if estado is not None and estado not in EstadoInteresado.values:
        raise DatosInvalidos("La etapa tiene que ser una de: " + ", ".join(EstadoInteresado.values) + ".")
    origen = request.query_params.get("origen") or None
    if origen is not None and origen not in OrigenInteresado.values:
        raise DatosInvalidos("El origen tiene que ser uno de: " + ", ".join(OrigenInteresado.values) + ".")
    queryset = selectors.listar_interesados(
        estado=estado,
        responsable_id=_responsable_de_la_consulta(request),
        origen=origen,
        q=request.query_params.get("q") or None,
        seguimiento_vencido=request.query_params.get("seguimiento_vencido") in ("1", "true"),
    )
    return _pagina(queryset, request, _interesado_item)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def interesados_embudo(request):
    responsable_id = _responsable_de_la_consulta(request)
    return Response(
        {
            "conteos": selectors.contar_por_estado(responsable_id),
            **selectors.cierres_del_mes(responsable_id),
        }
    )


@api_view(["GET", "PATCH"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def interesado_detalle_o_modificar(request, id):
    if request.method == "PATCH":
        datos = InteresadoModificacionSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        cambios = datos.validated_data
        funcionario_id = request.funcionario.id
        # Todo o nada: si el segundo cambio falla, el primero no queda hecho.
        with transaction.atomic():
            if "responsable_id" in cambios:
                asignar_interesado(id, cambios["responsable_id"], funcionario_id)
            if "proximo_contacto" in cambios:
                programar_contacto(id, cambios["proximo_contacto"], funcionario_id)
            if "datos" in cambios:
                actualizar_datos_interesado(id, cambios["datos"], funcionario_id)
    return Response(
        _interesado_detalle(selectors.detalle_interesado(id), _ve_comision(request))
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def interesado_mover(request, id):
    datos = MoverInteresadoSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    campos = datos.validated_data
    mover_interesado(
        id,
        campos["estado"],
        request.funcionario.id,
        nota=campos.get("nota"),
        motivo_perdida=campos.get("motivo_perdida"),
    )
    return Response(
        _interesado_detalle(selectors.detalle_interesado(id), _ve_comision(request))
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def interesado_convertir(request, id):
    datos = ConvertirInteresadoSerializer(data=request.data)
    datos.is_valid(raise_exception=True)
    convertir_en_cliente(id, request.funcionario.id, **datos.validated_data)
    return Response(
        _interesado_detalle(selectors.detalle_interesado(id), _ve_comision(request))
    )


@api_view(["GET", "POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def cotizaciones_listar_o_crear(request):
    ver_comision = _ve_comision(request)
    if request.method == "POST":
        datos = CotizacionAltaSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        cotizacion = cargar_cotizacion(request.funcionario.id, **datos.validated_data)
        cotizacion = selectors.cotizaciones_de(
            interesado_id=cotizacion.interesado_id, poliza_id=cotizacion.poliza_id
        ).get(pk=cotizacion.id)
        return Response(
            _cotizacion_item(cotizacion, ver_comision), status=status.HTTP_201_CREATED
        )

    interesado_id = _entero_de_la_consulta(request, "interesado")
    poliza_id = _entero_de_la_consulta(request, "poliza")
    if (interesado_id is None) == (poliza_id is None):
        raise DatosInvalidos("Indicá ?interesado=N o ?poliza=N, uno solo.")
    cotizaciones = selectors.cotizaciones_de(interesado_id=interesado_id, poliza_id=poliza_id)
    return Response(
        {"resultados": [_cotizacion_item(c, ver_comision) for c in cotizaciones]}
    )


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def cotizacion_elegir(request, id):
    elegir_cotizacion(id, request.funcionario.id)
    cotizacion = Cotizacion.objects.select_related("compania", "creada_por").get(pk=id)
    return Response(_cotizacion_item(cotizacion, _ve_comision(request)))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def cotizacion_quitar(request, id):
    quitar_cotizacion(id, request.funcionario.id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAprobador])
def interesado_registrar_poliza(request,id):
    from rest_framework import serializers
    from negocio.cotizaciones import registrar_poliza_elegida
    if not Interesado.objects.filter(pk=id).exists():raise NoEncontrado('El interesado no existe.')
    inicio=serializers.DateField().run_validation(request.data.get('fecha_inicio'))
    fin=serializers.DateField().run_validation(request.data.get('fecha_vencimiento'))
    registrar_poliza_elegida(id,request.funcionario.id,inicio,fin)
    return Response(_interesado_detalle(selectors.detalle_interesado(id),_ve_comision(request)),status=201)
