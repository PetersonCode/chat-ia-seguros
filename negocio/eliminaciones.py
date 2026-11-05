"""Borrado físico de pólizas, planes y compañías (solo rol administrador).

Existe para el trabajo de pruebas: rehacer la cartera de cero sin dejar rastro.
No hay marcas ni estados: son DELETE reales, de las hojas hacia la raíz, porque
la base no cascadea.

Qué se lleva cada uno:
- Póliza: cuotas, pagos, conductores, condiciones y sus documentos generados,
  vínculos con documentos generales (el documento general queda), acciones y
  sus borradores, avisos, recordatorios, renovaciones, contextos del bot y
  cotizaciones de renovación. El cliente y su vehículo quedan.
- Plan: el plan. Las pólizas que lo usaban conservan su copia de condiciones
  como «condiciones particulares» (sin plan).
- Compañía: todas sus pólizas (como arriba; los clientes quedan sin esa
  póliza), sus planes y sus cotizaciones.

Sin límites: también se llevan los siniestros (con su historial y sus fotos,
incluidos los archivos del disco) y las acciones finalizadas. Esos registros son
inmutables para el uso normal; el borrado total lo habilita dentro de su
transacción con `habilitar_borrado_total` (SQL 35).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import connection, transaction

from datos.models import Funcionario, Rol
from negocio.errores import EstadoInvalido, NoEncontrado, PermisoDenegado

logger = logging.getLogger(__name__)

PREFIJO_DOCUMENTO_CONDICIONES = "Condiciones cargadas en póliza "


def exigir_administrador(funcionario_id: int) -> Funcionario:
    funcionario = Funcionario.objects.filter(pk=funcionario_id, activo=True).first()
    if funcionario is None or funcionario.rol != Rol.ADMINISTRADOR:
        raise PermisoDenegado("Solo el administrador puede borrar definitivamente.")
    return funcionario


def _ids(cursor, sql, params) -> list[int]:
    cursor.execute(sql, params)
    return [fila[0] for fila in cursor.fetchall()]


def _contar(cursor, sql, params) -> int:
    cursor.execute(sql, params)
    return cursor.fetchone()[0]


def habilitar_borrado_total(cursor) -> None:
    """Deja borrar, solo en esta transacción, lo que la base declara inmutable."""
    cursor.execute("SELECT set_config('app.borrado_total', 'on', true)")


def borrar_siniestros(cursor, *, poliza_ids=(), consulta_ids=(), mensaje_ids=()) -> int:
    """DELETE de siniestros (por póliza o por caso) con historial y fotos, y de las
    fotos que vinieron por esos mensajes. Los archivos se quitan del disco al confirmar."""
    habilitar_borrado_total(cursor)
    siniestros = _ids(
        cursor,
        "SELECT id FROM siniestros WHERE poliza_id = ANY(%s) OR consulta_id = ANY(%s)",
        [list(poliza_ids), list(consulta_ids)],
    )
    claves = _ids(
        cursor,
        "SELECT clave_almacenamiento FROM siniestro_adjuntos "
        "WHERE siniestro_id = ANY(%s) OR mensaje_origen_id = ANY(%s)",
        [siniestros, list(mensaje_ids)],
    )
    cursor.execute(
        "DELETE FROM siniestro_adjuntos WHERE siniestro_id = ANY(%s) OR mensaje_origen_id = ANY(%s)",
        [siniestros, list(mensaje_ids)],
    )
    cursor.execute("DELETE FROM siniestro_historial WHERE siniestro_id = ANY(%s)", [siniestros])
    cursor.execute("DELETE FROM siniestros WHERE id = ANY(%s)", [siniestros])
    if claves:
        transaction.on_commit(lambda: _borrar_archivos(claves))
    return len(siniestros)


def borrar_finalizaciones(cursor, accion_ids) -> None:
    habilitar_borrado_total(cursor)
    cursor.execute("DELETE FROM acciones_finalizaciones WHERE accion_id = ANY(%s)", [list(accion_ids)])


def _borrar_archivos(claves) -> None:
    storage = FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)
    for clave in claves:
        try:
            storage.delete(clave)
        except OSError:
            logger.warning("No se pudo borrar el archivo %s.", clave)


def borrar_polizas(poliza_ids: list[int]) -> dict[str, int]:
    """DELETE de las pólizas y todo lo que cuelga de ellas, siniestros incluidos. Sin
    permisos ni chequeos: quien llama ya verificó administrador, dentro de una transacción."""
    if not poliza_ids:
        return {"polizas": 0, "cuotas": 0, "siniestros": 0}
    with connection.cursor() as c:
        numeros = _ids(c, "SELECT numero_poliza FROM polizas WHERE id = ANY(%s)", [poliza_ids])
        cuotas = _ids(c, "SELECT id FROM cuotas WHERE poliza_id = ANY(%s)", [poliza_ids])
        acciones = _ids(c, "SELECT id FROM acciones_pendientes WHERE poliza_id = ANY(%s)", [poliza_ids])
        # Los documentos que generó la carga de condiciones (todas sus versiones)
        # son de esta póliza y de nadie más. Los documentos generales vinculados
        # (p. ej. el PDF de la compañía) se desvinculan y quedan.
        documentos = _ids(
            c,
            "SELECT id FROM documentos_generales WHERE titulo = ANY(%s)",
            [[PREFIJO_DOCUMENTO_CONDICIONES + n for n in numeros]],
        )

        siniestros = borrar_siniestros(c, poliza_ids=poliza_ids)
        borrar_finalizaciones(c, acciones)
        c.execute("DELETE FROM borradores_poliza WHERE accion_id = ANY(%s)", [acciones])
        c.execute("DELETE FROM acciones_pendientes WHERE id = ANY(%s)", [acciones])
        c.execute("DELETE FROM contextos_cobertura WHERE poliza_id = ANY(%s)", [poliza_ids])
        c.execute(
            "DELETE FROM gestion_avisos WHERE poliza_id = ANY(%s) OR cuota_id = ANY(%s)",
            [poliza_ids, cuotas],
        )
        c.execute("DELETE FROM recordatorios_polizas WHERE poliza_id = ANY(%s)", [poliza_ids])
        c.execute(
            "DELETE FROM gestion_renovaciones WHERE origen_id = ANY(%s) OR nueva_id = ANY(%s)",
            [poliza_ids, poliza_ids],
        )
        c.execute("DELETE FROM cotizaciones WHERE poliza_id = ANY(%s)", [poliza_ids])
        c.execute("DELETE FROM documentos_polizas WHERE poliza_id = ANY(%s)", [poliza_ids])
        c.execute("DELETE FROM condiciones_poliza WHERE poliza_id = ANY(%s)", [poliza_ids])
        # Solo los documentos generados que ya nadie más referencia.
        c.execute(
            "DELETE FROM documentos_generales_fragmentos WHERE documento_id = ANY(%s) "
            "AND documento_id NOT IN (SELECT documento_id FROM documentos_polizas) "
            "AND documento_id NOT IN (SELECT documento_id FROM condiciones_poliza WHERE documento_id IS NOT NULL)",
            [documentos],
        )
        c.execute(
            "DELETE FROM documentos_generales WHERE id = ANY(%s) "
            "AND id NOT IN (SELECT documento_id FROM documentos_polizas) "
            "AND id NOT IN (SELECT documento_id FROM condiciones_poliza WHERE documento_id IS NOT NULL)",
            [documentos],
        )
        c.execute("DELETE FROM conductores_poliza WHERE poliza_id = ANY(%s)", [poliza_ids])
        c.execute("DELETE FROM pagos WHERE cuota_id = ANY(%s)", [cuotas])
        c.execute("DELETE FROM cuotas WHERE id = ANY(%s)", [cuotas])
        c.execute("DELETE FROM polizas WHERE id = ANY(%s)", [poliza_ids])
    return {"polizas": len(poliza_ids), "cuotas": len(cuotas), "siniestros": siniestros}


@transaction.atomic
def eliminar_poliza(poliza_id: int, funcionario_id: int) -> dict[str, int]:
    exigir_administrador(funcionario_id)
    with connection.cursor() as c:
        if not _ids(c, "SELECT id FROM polizas WHERE id = %s FOR UPDATE", [poliza_id]):
            raise NoEncontrado("La póliza no existe.")
    return borrar_polizas([poliza_id])


@transaction.atomic
def eliminar_plan(plan_id: int, funcionario_id: int) -> dict[str, int]:
    exigir_administrador(funcionario_id)
    with connection.cursor() as c:
        if not _ids(c, "SELECT id FROM planes_cobertura WHERE id = %s FOR UPDATE", [plan_id]):
            raise NoEncontrado("El plan no existe.")
        # Las pólizas conservan su copia de condiciones, ahora sin plan.
        c.execute(
            "UPDATE condiciones_poliza SET plan_id = NULL, plan_version = NULL WHERE plan_id = %s",
            [plan_id],
        )
        polizas_con_copia = c.rowcount
        c.execute("DELETE FROM planes_cobertura WHERE id = %s", [plan_id])
    return {"planes": 1, "polizas_con_condiciones_particulares": polizas_con_copia}


@transaction.atomic
def eliminar_compania(compania_id: int, funcionario_id: int) -> dict[str, int]:
    exigir_administrador(funcionario_id)
    with connection.cursor() as c:
        if not _ids(c, "SELECT id FROM companias WHERE id = %s FOR UPDATE", [compania_id]):
            raise NoEncontrado("La compañía no existe.")
        polizas = _ids(c, "SELECT id FROM polizas WHERE compania_id = %s", [compania_id])
    resumen = borrar_polizas(polizas)
    with connection.cursor() as c:
        c.execute("DELETE FROM cotizaciones WHERE compania_id = %s", [compania_id])
        cotizaciones = c.rowcount
        c.execute(
            "UPDATE condiciones_poliza SET plan_id = NULL, plan_version = NULL "
            "WHERE plan_id IN (SELECT id FROM planes_cobertura WHERE compania_id = %s)",
            [compania_id],
        )
        c.execute("DELETE FROM planes_cobertura WHERE compania_id = %s", [compania_id])
        planes = c.rowcount
        c.execute("DELETE FROM companias WHERE id = %s", [compania_id])
    return {**resumen, "planes": planes, "cotizaciones": cotizaciones}
