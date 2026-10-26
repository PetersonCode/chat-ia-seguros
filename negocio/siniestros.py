"""Registro y seguimiento del expediente operativo de siniestros."""

from __future__ import annotations

from datetime import date, datetime

from django.db import connection, transaction
from django.utils import timezone

from datos.models import (
    EstadoSiniestro,
    Funcionario,
    HistorialSiniestro,
    Poliza,
    Siniestro,
)
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado, PermisoDenegado

LOCK_NUMERO_SINIESTRO = 4243
MOTIVO_MINIMO = 3

TRANSICIONES_SINIESTRO = {
    EstadoSiniestro.DENUNCIADO: (EstadoSiniestro.EN_EVALUACION,),
    EstadoSiniestro.EN_EVALUACION: (
        EstadoSiniestro.APROBADO,
        EstadoSiniestro.RECHAZADO,
    ),
    EstadoSiniestro.APROBADO: (EstadoSiniestro.CERRADO,),
    EstadoSiniestro.RECHAZADO: (EstadoSiniestro.CERRADO,),
    EstadoSiniestro.CERRADO: (),
}


def _funcionario_activo(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.select_for_update().filter(pk=funcionario_id).first()
    if funcionario is None:
        raise NoEncontrado("El funcionario no existe.")
    if not funcionario.activo:
        raise PermisoDenegado("Hace falta un funcionario activo.")
    return funcionario


def _aprobador(funcionario_id: int) -> Funcionario:
    funcionario = _funcionario_activo(funcionario_id)
    if not funcionario.puede_aprobar:
        raise PermisoDenegado(
            "Hace falta un funcionario activo con permiso de aprobación."
        )
    return funcionario


def _fecha_ocurrencia_validada(valor, poliza: Poliza) -> date:
    try:
        fecha = date.fromisoformat(valor) if isinstance(valor, str) else valor
    except ValueError as error:
        raise DatosInvalidos("La fecha de ocurrencia no es válida.") from error
    if not isinstance(fecha, date) or isinstance(fecha, datetime):
        raise DatosInvalidos("La fecha de ocurrencia es obligatoria.")
    if fecha > timezone.localdate():
        raise DatosInvalidos("La fecha de ocurrencia no puede ser futura.")
    if not poliza.fecha_inicio <= fecha <= poliza.fecha_vencimiento:
        raise DatosInvalidos(
            "La fecha de ocurrencia debe estar dentro de la vigencia de la póliza."
        )
    return fecha


def _descripcion_validada(descripcion: str) -> str:
    texto = descripcion.strip() if isinstance(descripcion, str) else ""
    if not texto:
        raise DatosInvalidos("La descripción de la denuncia es obligatoria.")
    return texto


def _motivo_validado(motivo: str) -> str:
    texto = motivo.strip() if isinstance(motivo, str) else ""
    if len(texto) < MOTIVO_MINIMO:
        raise DatosInvalidos("El motivo debe tener al menos 3 caracteres.")
    return texto


def _proximo_numero_siniestro() -> str:
    """Asigna números secuenciales bajo el mismo lock de la rama del bot."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_NUMERO_SINIESTRO])
        anio = timezone.localdate().year
        cursor.execute(
            """
            SELECT COALESCE(MAX(SUBSTRING(numero_siniestro FROM 'SIN-[0-9]{4}-([0-9]+)$')::int), 0)
            FROM siniestros
            WHERE numero_siniestro ~ %s
            """,
            [rf"^SIN-{anio}-[0-9]+$"],
        )
        maximo = cursor.fetchone()[0] or 0
    if maximo >= 99999:
        raise EstadoInvalido("Se agotaron los números de siniestro para este año.")
    return f"SIN-{anio}-{maximo + 1:05d}"


def _crear_denuncia(
    *,
    poliza: Poliza,
    fecha_ocurrencia: date,
    descripcion: str,
    responsable: Funcionario,
    consulta_id: int | None = None,
) -> Siniestro:
    siniestro = Siniestro.objects.create(
        numero_siniestro=_proximo_numero_siniestro(),
        poliza=poliza,
        consulta_id=consulta_id,
        fecha_ocurrencia=fecha_ocurrencia,
        descripcion=descripcion,
        estado=EstadoSiniestro.DENUNCIADO,
    )
    HistorialSiniestro.objects.create(
        siniestro=siniestro,
        estado_anterior=None,
        estado_nuevo=EstadoSiniestro.DENUNCIADO,
        motivo="Denuncia registrada",
        responsable=responsable,
        fecha=timezone.now(),
    )
    return siniestro


@transaction.atomic
def registrar_denuncia(
    *,
    cliente_id: int,
    poliza_id: int,
    fecha_ocurrencia,
    descripcion: str,
    funcionario_id: int,
) -> Siniestro:
    funcionario = _funcionario_activo(funcionario_id)
    poliza = (
        Poliza.objects.select_for_update()
        .select_related("cliente")
        .filter(pk=poliza_id)
        .first()
    )
    if poliza is None:
        raise NoEncontrado("La póliza no existe.")
    if poliza.cliente_id != cliente_id:
        raise DatosInvalidos("La póliza seleccionada no pertenece al cliente.")
    fecha = _fecha_ocurrencia_validada(fecha_ocurrencia, poliza)
    return _crear_denuncia(
        poliza=poliza,
        fecha_ocurrencia=fecha,
        descripcion=_descripcion_validada(descripcion),
        responsable=funcionario,
    )


@transaction.atomic
def registrar_denuncia_desde_accion(
    *,
    cliente_id: int,
    poliza_id: int,
    consulta_id: int,
    fecha_ocurrencia,
    descripcion: str,
    funcionario_id: int,
) -> Siniestro:
    """Comparte la creación del expediente con la aprobación del bot."""
    funcionario = _aprobador(funcionario_id)
    poliza = Poliza.objects.select_for_update().filter(pk=poliza_id).first()
    if poliza is None:
        raise NoEncontrado("La póliza asociada a la denuncia no existe.")
    if poliza.cliente_id != cliente_id:
        raise DatosInvalidos(
            "La póliza de la denuncia no pertenece al cliente vinculado."
        )
    fecha = _fecha_ocurrencia_validada(fecha_ocurrencia, poliza)
    return _crear_denuncia(
        poliza=poliza,
        fecha_ocurrencia=fecha,
        descripcion=_descripcion_validada(descripcion),
        responsable=funcionario,
        consulta_id=consulta_id,
    )


@transaction.atomic
def transicionar_siniestro(
    siniestro_id: int,
    *,
    estado: str,
    motivo: str,
    funcionario_id: int,
) -> Siniestro:
    funcionario = _aprobador(funcionario_id)
    if estado not in EstadoSiniestro.values:
        raise DatosInvalidos("El estado del siniestro no es válido.")
    motivo = _motivo_validado(motivo)
    siniestro = Siniestro.objects.select_for_update().filter(pk=siniestro_id).first()
    if siniestro is None:
        raise NoEncontrado("El siniestro no existe.")
    if estado not in TRANSICIONES_SINIESTRO[siniestro.estado]:
        permitidos = TRANSICIONES_SINIESTRO[siniestro.estado]
        nombres = ", ".join(permitidos) if permitidos else "ninguno"
        raise EstadoInvalido(
            f"No se puede pasar de {siniestro.estado} a {estado}; "
            f"estados siguientes permitidos: {nombres}."
        )

    estado_anterior = siniestro.estado
    HistorialSiniestro.objects.create(
        siniestro=siniestro,
        estado_anterior=estado_anterior,
        estado_nuevo=estado,
        motivo=motivo,
        responsable=funcionario,
        fecha=timezone.now(),
    )
    siniestro.estado = estado
    return siniestro
