"""El embudo de venta nueva (P5): de «cuánto sale asegurar mi auto» a una póliza.

Un **interesado** es alguien que pidió precio o información y todavía no es
cliente (o lo es y pide otro seguro: venta cruzada). Tiene un responsable, una
etapa y un próximo contacto, y cada cambio deja una línea en su historial con
quién lo hizo y cuándo.

Etapas: `consulta → cotizando → documentacion → emitida`, de una en una, y se
puede volver **una** etapa atrás (si el cliente pide otra cotización, de
`documentacion` a `cotizando`). Desde cualquiera abierta se puede pasar a
`perdida` (con motivo), y de `perdida` se vuelve a `consulta`. `emitida` es final.

Cualquier funcionario activo trabaja el embudo: es el mostrador. Lo único que
exige un aprobador es `convertir_en_cliente`, porque da de alta a una persona en
la cartera. Nada acá contacta al cliente: lo que se le dice sale por el motor de
avisos o lo manda una persona.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max, OuterRef, Subquery
from django.utils import timezone

from datos.limpieza import normalizar_dni, normalizar_patente, normalizar_telefono
from datos.models import (
    Cliente,
    ContactoWhatsapp,
    Direccion,
    Emisor,
    EstadoInteresado,
    Funcionario,
    Interesado,
    InteresadoHistorial,
    Mensaje,
    OrigenInteresado,
    Poliza,
    UsoVehiculo,
)
from datos.selectors import cliente_por_dni, interesado_abierto_de
from negocio.bot.plantillas import SEGUIMIENTO_COTIZACION, SEGUIMIENTO_COTIZACION_SIN_NOMBRE
from negocio.clientes import alta_cliente
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado, PermisoDenegado

E = EstadoInteresado

# Una etapa por vez, hacia adelante o hacia atrás; perder se puede desde cualquier
# etapa abierta. No se vuelve de `emitida`: la póliza ya existe.
TRANSICIONES: dict[str, frozenset[str]] = {
    E.CONSULTA: frozenset({E.COTIZANDO, E.PERDIDA}),
    E.COTIZANDO: frozenset({E.CONSULTA, E.DOCUMENTACION, E.PERDIDA}),
    E.DOCUMENTACION: frozenset({E.COTIZANDO, E.EMITIDA, E.PERDIDA}),
    E.EMITIDA: frozenset(),
    E.PERDIDA: frozenset({E.CONSULTA}),
}

MINIMO_MOTIVO = 3
MAXIMO_TEXTO = 300  # un dato suelto de `datos` (localidad, modelo…)
MAXIMO_NOMBRE = 120
MAXIMO_NOTA = 1000
ANIO_MINIMO = 1950

# Hitos de seguimiento de una cotización: días en `cotizando` → tipo de aviso (P2).
HITOS_SEGUIMIENTO = ((2, "seguimiento_cotizacion_2d"), (5, "seguimiento_cotizacion_5d"))
# Un aviso que nadie contactó en 7 días caduca (P2): más allá de eso no se genera.
DIAS_DE_GRACIA = 7



# --- Validaciones ------------------------------------------------------------


def _funcionario_activo(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id, activo=True).first()
    if funcionario is None:
        raise PermisoDenegado("El funcionario no existe o no está activo.")
    return funcionario


def _aprobador(funcionario_id: int) -> Funcionario:
    funcionario = _funcionario_activo(funcionario_id)
    if not funcionario.puede_aprobar:
        raise PermisoDenegado("Convertir un interesado en cliente requiere un aprobador.")
    return funcionario


def _interesado(interesado_id: int, *, bloquear: bool = False) -> Interesado:
    consulta = Interesado.objects.all()
    if bloquear:
        consulta = consulta.select_for_update()
    interesado = consulta.filter(pk=interesado_id).first()
    if interesado is None:
        raise NoEncontrado("El interesado no existe.")
    return interesado


def _texto_o_none(valor: Any, maximo: int, campo: str) -> str | None:
    texto = " ".join(str(valor).split()) if valor is not None else ""
    if not texto:
        return None
    if len(texto) > maximo:
        raise DatosInvalidos(f"{campo} no puede superar {maximo} caracteres.")
    return texto


def _etiqueta(estado: str) -> str:
    return EstadoInteresado(estado).label


def datos_normalizados(datos: dict | None) -> dict[str, Any]:
    """Limpia lo que se guarda en `Interesado.datos`.

    Valida solo lo que después usa una cotización: patente, DNI, año y uso se
    normalizan o se rechazan; el resto (marca, modelo, localidad…) son textos
    cortos. Un valor vacío o `None` significa «borrar ese dato» al mezclar.
    Los valores tienen que ser escalares: acá no entran listas ni objetos.
    """
    if datos is None:
        return {}
    if not isinstance(datos, dict):
        raise DatosInvalidos("Los datos tienen que ser un objeto.")
    limpios: dict[str, Any] = {}
    for clave, valor in datos.items():
        if not isinstance(clave, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", clave):
            raise DatosInvalidos(f"El nombre de dato «{clave}» no es válido.")
        if valor is not None and not isinstance(valor, (str, int, float, bool)):
            raise DatosInvalidos(f"El dato «{clave}» tiene que ser un texto o un número.")
        if isinstance(valor, bool):
            raise DatosInvalidos(f"El dato «{clave}» tiene que ser un texto o un número.")
        texto = _texto_o_none(valor, MAXIMO_TEXTO, f"El dato «{clave}»")
        if texto is None:
            limpios[clave] = None
        elif clave == "patente":
            try:
                limpios[clave] = normalizar_patente(texto)
            except ValueError as error:
                raise DatosInvalidos(str(error)) from error
        elif clave == "dni":
            try:
                limpios[clave] = normalizar_dni(texto)
            except ValueError as error:
                raise DatosInvalidos(str(error)) from error
        elif clave == "anio":
            limpios[clave] = _anio_validado(texto)
        elif clave == "uso":
            uso = texto.lower()
            if uso not in UsoVehiculo.values:
                raise DatosInvalidos(
                    "El uso tiene que ser uno de: " + ", ".join(UsoVehiculo.values) + "."
                )
            limpios[clave] = uso
        else:
            limpios[clave] = texto
    return limpios


def _anio_validado(texto: str) -> int:
    try:
        anio = int(texto)
    except ValueError as error:
        raise DatosInvalidos("El año tiene que ser un número.") from error
    maximo = timezone.localdate().year + 1
    if not ANIO_MINIMO <= anio <= maximo:
        raise DatosInvalidos(f"El año tiene que estar entre {ANIO_MINIMO} y {maximo}.")
    return anio


def _mezclar(actuales: dict | None, nuevos: dict[str, Any]) -> dict[str, Any]:
    """Los datos nuevos pisan a los viejos; `None` borra la clave."""
    mezcla = dict(actuales or {})
    for clave, valor in nuevos.items():
        if valor is None:
            mezcla.pop(clave, None)
        else:
            mezcla[clave] = valor
    return mezcla


def _asentar(
    interesado: Interesado,
    funcionario_id: int | None,
    nota: str,
    *,
    estado_anterior: str | None = None,
    estado_nuevo: str | None = None,
) -> None:
    """Una línea de historial. Sin estados, la gestión queda en la etapa actual."""
    InteresadoHistorial.objects.create(
        interesado=interesado,
        estado_anterior=estado_anterior if estado_nuevo else interesado.estado,
        estado_nuevo=estado_nuevo or interesado.estado,
        nota=nota,
        funcionario_id=funcionario_id,
    )


def _tocar(interesado: Interesado, *campos: str) -> None:
    interesado.actualizado_en = timezone.now()
    interesado.save(update_fields=[*campos, "actualizado_en"])


# --- Alta ------------------------------------------------------------------


def _contacto_para(telefono: str | None) -> ContactoWhatsapp | None:
    """El contacto de ese número: el que ya existe, o uno nuevo sin cliente."""
    if telefono is None or not str(telefono).strip():
        return None
    try:
        numero = normalizar_telefono(str(telefono))
    except ValueError as error:
        raise DatosInvalidos(str(error)) from error
    contacto = ContactoWhatsapp.objects.filter(numero=numero).first()
    if contacto is None:
        contacto = ContactoWhatsapp.objects.create(numero=numero, cliente=None)
    return contacto


def _cliente_activo_de(contacto: ContactoWhatsapp | None) -> Cliente | None:
    if contacto is None or contacto.cliente_id is None:
        return None
    cliente = Cliente.objects.filter(pk=contacto.cliente_id, activo=True).first()
    return cliente


@transaction.atomic
def crear_interesado(
    funcionario_id: int,
    nombre: str,
    origen: str,
    telefono: str | None = None,
    apellido: str | None = None,
    datos: dict | None = None,
) -> Interesado:
    """Alta en `consulta`, con el que la hizo como responsable.

    Si el número ya tiene un interesado abierto devuelve ese, sin duplicar. Si el
    número es de un cliente activo, el interesado nace con `cliente_id` cargado:
    es una venta cruzada, no un desconocido.
    """
    _funcionario_activo(funcionario_id)
    nombre_limpio = _texto_o_none(nombre, MAXIMO_NOMBRE, "El nombre")
    if nombre_limpio is None:
        raise DatosInvalidos("El nombre es obligatorio.")
    if origen not in OrigenInteresado.values:
        raise DatosInvalidos(
            "El origen tiene que ser uno de: " + ", ".join(OrigenInteresado.values) + "."
        )
    apellido_limpio = _texto_o_none(apellido, MAXIMO_NOMBRE, "El apellido")
    datos_limpios = {k: v for k, v in datos_normalizados(datos).items() if v is not None}
    contacto = _contacto_para(telefono)

    if contacto is not None:
        abierto = interesado_abierto_de(contacto.pk)
        if abierto is not None:
            abierto._ya_existia = True
            return abierto
    cliente = _cliente_activo_de(contacto)

    try:
        with transaction.atomic():
            interesado = Interesado.objects.create(
                nombre=nombre_limpio,
                apellido=apellido_limpio,
                contacto=contacto,
                cliente=cliente,
                origen=origen,
                estado=E.CONSULTA,
                responsable_id=funcionario_id,
                datos=datos_limpios,
            )
            _asentar(
                interesado,
                funcionario_id,
                f"Alta del interesado (origen: {OrigenInteresado(origen).label}).",
                estado_nuevo=E.CONSULTA,
            )
    except IntegrityError:
        # Otro alta del mismo número ganó la carrera: se devuelve esa.
        abierto = interesado_abierto_de(contacto.pk) if contacto is not None else None
        if abierto is None:
            raise
        abierto._ya_existia = True
        return abierto
    return interesado


@transaction.atomic
def registrar_cotizacion_del_bot(
    contacto: ContactoWhatsapp, datos: dict, *, responsable_id: int | None = None
) -> Interesado:
    """Lo que el bot juntó para cotizar, en el interesado de ese número.

    Si el número ya tiene un interesado abierto, se le suman los datos (los
    nuevos pisan a los viejos y lo vacío no borra nada); si no, se crea uno con
    origen `whatsapp`. No hay un funcionario que lo cree: el historial queda sin
    autor y el responsable es quien recibe la derivación.

    Si no tiene próximo contacto, queda para **hoy**: alguien pidió precio y
    tiene que aparecer en el tablero hasta que una persona lo atienda, en vez de
    esperar a que alguien se acuerde. Uno que ya tenía fecha la conserva.
    """
    datos_limpios = {k: v for k, v in datos_normalizados(datos).items() if v is not None}
    nota = "El cliente dejó por WhatsApp los datos para cotizar."
    existente = interesado_abierto_de(contacto.pk)
    if existente is not None:
        if datos_limpios.get('patente') and existente.datos.get('patente') and datos_limpios['patente'] != existente.datos['patente']:
            existente.datos = {k:v for k,v in existente.datos.items() if k not in {'patente','marca','modelo','anio','uso','localidad'}}
        existente.datos = _mezclar(existente.datos, datos_limpios)
        campos = ["datos"]
        if existente.proximo_contacto is None:
            existente.proximo_contacto = timezone.localdate()
            campos.append("proximo_contacto")
        if existente.responsable_id is None and responsable_id is not None:
            existente.responsable_id = responsable_id
            campos.append("responsable")
        _tocar(existente, *campos)
        _asentar(existente, None, nota)
        return existente

    cliente = _cliente_activo_de(contacto)
    if cliente is not None:
        nombre, apellido = cliente.nombre, cliente.apellido
    else:
        nombre = (contacto.nombre_perfil or "").strip() or contacto.numero
        apellido = None
    interesado = Interesado.objects.create(
        nombre=nombre,
        apellido=apellido,
        contacto=contacto,
        cliente=cliente,
        origen=OrigenInteresado.WHATSAPP,
        estado=E.CONSULTA,
        responsable_id=responsable_id,
        proximo_contacto=timezone.localdate(),
        datos=datos_limpios,
    )
    _asentar(interesado, None, nota, estado_nuevo=E.CONSULTA)
    return interesado


# --- Etapas ----------------------------------------------------------------


@transaction.atomic
def mover_interesado(
    interesado_id: int,
    estado_nuevo: str,
    funcionario_id: int,
    nota: str | None = None,
    motivo_perdida: str | None = None,
) -> Interesado:
    """Cambia de etapa si la transición es válida y deja el historial."""
    _funcionario_activo(funcionario_id)
    if estado_nuevo not in EstadoInteresado.values:
        raise DatosInvalidos(
            "La etapa tiene que ser una de: " + ", ".join(EstadoInteresado.values) + "."
        )
    interesado = _interesado(interesado_id, bloquear=True)
    anterior = interesado.estado
    if estado_nuevo not in TRANSICIONES[anterior]:
        if anterior == E.EMITIDA:
            raise EstadoInvalido("Un interesado emitido es final: no se puede cambiar de etapa.")
        raise EstadoInvalido(
            f"No se puede pasar de «{_etiqueta(anterior)}» a «{_etiqueta(estado_nuevo)}»."
        )

    texto_nota = _texto_o_none(nota, MAXIMO_NOTA, "La nota")
    motivo = None
    if estado_nuevo == E.PERDIDA:
        motivo = " ".join((motivo_perdida or "").split())
        if len(motivo) < MINIMO_MOTIVO:
            raise DatosInvalidos(
                f"Indicá el motivo por el que se perdió ({MINIMO_MOTIVO} caracteres como mínimo)."
            )
        texto_nota = f"Motivo: {motivo}" + (f". {texto_nota}" if texto_nota else "")
    elif estado_nuevo == E.EMITIDA:
        _exigir_poliza_emitida(interesado)

    interesado.estado = estado_nuevo
    interesado.motivo_perdida = motivo  # volver a `consulta` limpia el motivo
    try:
        with transaction.atomic():
            _tocar(interesado, "estado", "motivo_perdida")
    except IntegrityError as error:
        # Reabrir una perdida cuando el mismo número ya tiene otro interesado abierto.
        raise EstadoInvalido(
            "Ese número ya tiene otro interesado abierto. Trabajá ese en lugar de reabrir éste."
        ) from error
    _asentar(
        interesado,
        funcionario_id,
        texto_nota or "",
        estado_anterior=anterior,
        estado_nuevo=estado_nuevo,
    )
    return interesado


def _exigir_poliza_emitida(interesado: Interesado) -> None:
    """Emitida es cuando existe la póliza: el cliente tiene una creada después del interesado."""
    if interesado.cliente_id is None:
        raise EstadoInvalido(
            "Para marcarlo como emitido primero hay que convertirlo en cliente."
        )
    hay_poliza = Poliza.objects.filter(
        cliente_id=interesado.cliente_id, creado_en__gt=interesado.creado_en
    ).exists()
    if not hay_poliza:
        raise EstadoInvalido(
            "Para marcarlo como emitido el cliente tiene que tener una póliza cargada "
            "después de que se creó el interesado."
        )


@transaction.atomic
def convertir_en_cliente(
    interesado_id: int,
    funcionario_id: int,
    dni: str,
    nombre: str,
    apellido: str,
    email: str | None = None,
    telefono: str | None = None,
) -> Interesado:
    """Da de alta al cliente (o reutiliza al que ya tiene ese DNI) y lo liga al interesado.

    Solo un aprobador, y solo con el interesado en `documentacion`. No cambia la
    etapa: pasar a `emitida` es `mover_interesado`, cuando la póliza ya existe.
    `telefono` se usa solo si el interesado no tiene contacto de WhatsApp.
    """
    _aprobador(funcionario_id)
    interesado = _interesado(interesado_id, bloquear=True)
    if interesado.estado != E.DOCUMENTACION:
        raise EstadoInvalido(
            "Solo se puede convertir en cliente un interesado en «Documentación»."
        )
    try:
        dni_normalizado = normalizar_dni(dni or "")
    except ValueError as error:
        raise DatosInvalidos(str(error)) from error

    contacto = (
        ContactoWhatsapp.objects.filter(pk=interesado.contacto_id).first()
        if interesado.contacto_id
        else None
    )
    existente = cliente_por_dni(dni_normalizado)
    if existente is not None:
        cliente = existente
        _vincular_contacto(contacto, cliente)
    else:
        numero = contacto.numero if contacto is not None else telefono
        if not numero or not str(numero).strip():
            raise DatosInvalidos(
                "Falta el teléfono: el interesado no tiene WhatsApp y el alta de cliente lo necesita."
            )
        cliente = alta_cliente(dni_normalizado, nombre, apellido, numero, email)
        if contacto is None:
            contacto = ContactoWhatsapp.objects.get(numero=normalizar_telefono(str(numero)))

    interesado.cliente = cliente
    guardar_vehiculo_del_interesado(interesado, cliente, funcionario_id)
    interesado.contacto = contacto
    interesado.datos = _mezclar(interesado.datos, {"dni": dni_normalizado})
    _tocar(interesado, "cliente", "contacto", "datos")
    _asentar(
        interesado,
        funcionario_id,
        f"Convertido en cliente: {cliente.nombre} {cliente.apellido} (DNI {cliente.dni}).",
    )
    return interesado


def guardar_vehiculo_del_interesado(interesado, cliente, funcionario_id):
    """Conservar el vehículo confirmado al convertir, sin duplicar ni reasignar patentes."""
    from datos.models import Vehiculo
    from negocio.vehiculos import alta_vehiculo
    datos = interesado.datos or {}
    if not all(datos.get(k) for k in ('patente','marca','modelo','anio')):
        return None
    patente = normalizar_patente(datos['patente'])
    existente = Vehiculo.objects.select_for_update().filter(patente=patente).first()
    if existente:
        if existente.cliente_id != cliente.id:
            raise DatosInvalidos('La patente pertenece a otro cliente. Revisá el vehículo antes de convertir.')
        return existente
    return alta_vehiculo(cliente.id,patente,datos['marca'],datos['modelo'],datos['anio'],
                         datos.get('uso') or 'particular',funcionario_id=funcionario_id)


def _vincular_contacto(contacto: ContactoWhatsapp | None, cliente: Cliente) -> None:
    """Al reutilizar un cliente, el WhatsApp del interesado pasa a ser suyo (si estaba libre)."""
    if contacto is None or contacto.cliente_id == cliente.pk:
        return
    if contacto.cliente_id is not None:
        raise DatosInvalidos(f"El teléfono {contacto.numero} ya pertenece a otro cliente.")
    contacto.cliente = cliente
    contacto.save(update_fields=["cliente"])


# --- Gestión del día a día -------------------------------------------------


@transaction.atomic
def asignar_interesado(
    interesado_id: int, responsable_id: int, funcionario_id: int
) -> Interesado:
    _funcionario_activo(funcionario_id)
    responsable = Funcionario.objects.filter(pk=responsable_id, activo=True).first()
    if responsable is None:
        raise DatosInvalidos("El responsable no existe o no está activo.")
    interesado = _interesado(interesado_id, bloquear=True)
    interesado.responsable = responsable
    _tocar(interesado, "responsable")
    _asentar(interesado, funcionario_id, f"Asignado a {responsable.nombre}.")
    return interesado


def _fecha_de_contacto(fecha) -> dt.date | None:
    if fecha is None or (isinstance(fecha, str) and not fecha.strip()):
        return None
    if isinstance(fecha, dt.datetime):
        fecha = fecha.date()
    elif not isinstance(fecha, dt.date):
        try:
            fecha = dt.date.fromisoformat(str(fecha).strip())
        except ValueError as error:
            raise DatosInvalidos("La fecha tiene que tener el formato aaaa-mm-dd.") from error
    if fecha < timezone.localdate():
        raise DatosInvalidos("El próximo contacto no puede ser una fecha pasada.")
    return fecha


@transaction.atomic
def programar_contacto(interesado_id: int, fecha, funcionario_id: int) -> Interesado:
    """Fija cuándo hay que volver a llamar (hoy o después). Una fecha vacía lo borra."""
    _funcionario_activo(funcionario_id)
    nueva = _fecha_de_contacto(fecha)
    interesado = _interesado(interesado_id, bloquear=True)
    interesado.proximo_contacto = nueva
    _tocar(interesado, "proximo_contacto")
    _asentar(
        interesado,
        funcionario_id,
        f"Próximo contacto: {nueva.strftime('%d/%m/%Y')}." if nueva else "Se quitó el próximo contacto.",
    )
    return interesado


@transaction.atomic
def actualizar_datos_interesado(
    interesado_id: int, datos: dict, funcionario_id: int
) -> Interesado:
    """Mezcla los datos con los que ya hay, normalizando patente y DNI."""
    _funcionario_activo(funcionario_id)
    nuevos = datos_normalizados(datos)
    interesado = _interesado(interesado_id, bloquear=True)
    interesado.datos = _mezclar(interesado.datos, nuevos)
    _tocar(interesado, "datos")
    cambiados = ", ".join(sorted(nuevos)) or "sin cambios"
    _asentar(interesado, funcionario_id, f"Datos actualizados: {cambiados}.")
    return interesado


# --- Seguimiento automático (se engancha al motor de avisos, P2) -------------


def seguimiento_interesados(hoy: dt.date) -> list[dict[str, Any]]:
    """Qué avisos de seguimiento corresponde programar hoy.

    Un interesado que lleva 2 días en `cotizando` (y otro hito a los 5) recibe un
    recordatorio **si el contacto no escribió desde que entró a esa etapa**: si ya
    contestó, la conversación sigue por otro lado. La referencia lleva el hito y la
    fecha de entrada, así que correrlo todos los días no duplica nada, y volver a
    `cotizando` más adelante abre un seguimiento nuevo.

    Devuelve, para cada aviso, lo que P2 espera de un generador: `tipo`,
    `contacto_id`, `referencia`, `datos` (solo ids, el texto se arma al enviar),
    y `asignado_a_id` (el responsable: casi siempre le toca como tarea manual).
    Un hito se genera desde su día hasta que el siguiente toma la posta; el
    último, hasta que caduca. Así una caída del servicio un día no pierde el
    aviso. El filtro por `acepta_avisos` lo aplica el motor al programar.
    """
    entrada = (
        InteresadoHistorial.objects.filter(
            interesado_id=OuterRef("pk"), estado_nuevo=E.COTIZANDO
        )
        .exclude(estado_anterior=E.COTIZANDO)
        .order_by("-fecha", "-id")
        .values("fecha")[:1]
    )
    ultimo_mensaje_del_cliente = (
        Mensaje.objects.filter(
            conversacion__contacto_id=OuterRef("contacto_id"),
            direccion=Direccion.ENTRANTE,
            emisor=Emisor.CLIENTE,
        )
        .values("conversacion__contacto_id")
        .annotate(ultimo=Max("fecha_hora"))
        .values("ultimo")[:1]
    )
    candidatos = (
        Interesado.objects.filter(estado=E.COTIZANDO, contacto__isnull=False)
        .annotate(
            entro_en=Subquery(entrada),
            cliente_escribio_en=Subquery(ultimo_mensaje_del_cliente),
        )
        .exclude(entro_en__isnull=True)
    )

    avisos: list[dict[str, Any]] = []
    for interesado in candidatos:
        # Si el contacto escribió después de la cotización, ya hay conversación.
        if (
            interesado.cliente_escribio_en is not None
            and interesado.cliente_escribio_en > interesado.entro_en
        ):
            continue
        entro_el = timezone.localtime(interesado.entro_en).date()
        dias = (hoy - entro_el).days
        for posicion, (hito, tipo) in enumerate(HITOS_SEGUIMIENTO):
            hasta = (
                HITOS_SEGUIMIENTO[posicion + 1][0]
                if posicion + 1 < len(HITOS_SEGUIMIENTO)
                else hito + DIAS_DE_GRACIA
            )
            if hito <= dias < hasta:
                avisos.append(
                    {
                        "tipo": tipo,
                        "contacto_id": interesado.contacto_id,
                        "referencia": f"interesado:{interesado.pk}:{hito}d:{entro_el.isoformat()}",
                        "datos": {"interesado_id": interesado.pk},
                        "asignado_a_id": interesado.responsable_id,
                    }
                )
    return avisos


def texto_seguimiento_cotizacion(datos: dict) -> tuple[str, frozenset[str]]:
    """El texto del aviso de seguimiento, con el nombre de la base (R12).

    Es lo que P2 registra en `TEXTOS_AVISO` para los dos tipos de seguimiento.
    """
    interesado = Interesado.objects.filter(pk=datos.get("interesado_id")).first()
    if interesado is None:
        raise NoEncontrado("El interesado no existe.")
    if not any(caracter.isalpha() for caracter in interesado.nombre):
        return SEGUIMIENTO_COTIZACION_SIN_NOMBRE, frozenset()
    return SEGUIMIENTO_COTIZACION.format(nombre=interesado.nombre), frozenset()
