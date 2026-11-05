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

Se niega, sin borrar nada, si hay siniestros, fotos de siniestro o acciones
finalizadas: la base los declara inmutables por trigger.
"""
from __future__ import annotations

from django.db import connection, transaction

from datos.models import Funcionario, Rol
from negocio.errores import EstadoInvalido, NoEncontrado, PermisoDenegado

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


def verificar_polizas_borrables(poliza_ids: list[int], que: str = "las pólizas") -> None:
    """Niega el borrado si algo inmutable cuelga de estas pólizas."""
    if not poliza_ids:
        return
    with connection.cursor() as c:
        bloqueos = []
        n = _contar(c, "SELECT count(*) FROM siniestros WHERE poliza_id = ANY(%s)", [poliza_ids])
        if n:
            bloqueos.append(f"{n} siniestro(s)")
        n = _contar(
            c,
            "SELECT count(*) FROM siniestro_adjuntos a JOIN siniestros s ON s.id = a.siniestro_id "
            "WHERE s.poliza_id = ANY(%s)",
            [poliza_ids],
        )
        if n:
            bloqueos.append(f"{n} foto(s) de siniestro")
        n = _contar(
            c,
            "SELECT count(*) FROM acciones_finalizaciones f JOIN acciones_pendientes a "
            "ON a.id = f.accion_id WHERE a.poliza_id = ANY(%s)",
            [poliza_ids],
        )
        if n:
            bloqueos.append(f"{n} acción(es) finalizada(s)")
    if bloqueos:
        raise EstadoInvalido(
            f"No se puede borrar {que}: hay " + ", ".join(bloqueos)
            + ", que la base declara inmutables. No se borró nada."
        )


def borrar_polizas(poliza_ids: list[int]) -> dict[str, int]:
    """DELETE de las pólizas y todo lo que cuelga de ellas. Sin permisos ni chequeos:
    quien llama ya verificó administrador e inmutables, dentro de una transacción."""
    if not poliza_ids:
        return {"polizas": 0, "cuotas": 0}
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
    return {"polizas": len(poliza_ids), "cuotas": len(cuotas)}


@transaction.atomic
def eliminar_poliza(poliza_id: int, funcionario_id: int) -> dict[str, int]:
    exigir_administrador(funcionario_id)
    with connection.cursor() as c:
        if not _ids(c, "SELECT id FROM polizas WHERE id = %s FOR UPDATE", [poliza_id]):
            raise NoEncontrado("La póliza no existe.")
    verificar_polizas_borrables([poliza_id], "la póliza")
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
    verificar_polizas_borrables(polizas, "la compañía")
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
