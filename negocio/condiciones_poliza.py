"""Condiciones de cobertura de una póliza: una sola lógica para todos los caminos.

La usan la página Pólizas («Ver / cargar cobertura») y el alta de póliza desde
la ficha del cliente cuando se elige un plan. Antes la lógica vivía dentro de
la vista de Pólizas y el alta solo podía fijar el nivel básica/intermedia/total,
así que cobertura y plan se cargaban por separado y podían contradecirse.

Reglas:
- El plan tiene que ser de la compañía de la póliza.
- Elegir un plan copia sus campos (versión congelada): cambiar el plan después
  no reescribe contratos existentes.
- Si el plan tiene `nivel`, la póliza toma ese nivel: no hay dos fuentes.
- Cada guardado genera el documento aprobado que el bot cita, y retira el
  anterior.
"""
from __future__ import annotations

from uuid import uuid4

from django.utils import timezone

from datos.models import CondicionesPoliza, PlanCobertura
from negocio.coberturas import vincular_documento
from negocio.documentos import aprobar_documento, crear_documento, retirar_documento
from negocio.errores import DatosInvalidos

CAMPOS = ("cubre", "no_cubre", "limites", "asistencia")


def plan_para_poliza(poliza, plan_id, version, info=None):
    """(plan | None, versión, campos de partida) para aplicar a la póliza.

    Con el mismo plan y versión que ya tiene la póliza, parte de su copia (que
    pudo haberse ajustado a mano). Con otro plan, de los campos del plan.
    """
    if not plan_id:
        return None, None, ({k: getattr(info, k) for k in CAMPOS} if info else {})
    plan = (
        PlanCobertura.objects.select_for_update()
        .select_related("compania")
        .filter(pk=plan_id)
        .first()
    )
    if not plan or plan.compania_id != poliza.compania_id:
        raise DatosInvalidos("El plan debe pertenecer a la compañía de esta póliza.")
    if info and info.plan_id == plan.id and info.plan_version == version:
        return plan, version, {k: getattr(info, k) for k in CAMPOS}
    if not plan.activo or not plan.compania.activa:
        raise DatosInvalidos("El plan o su compañía están inactivos.")
    if version is not None and version != plan.version:
        raise DatosInvalidos(
            "El plan cambió mientras editabas. Volvé a seleccionarlo antes de guardar."
        )
    return plan, plan.version, {k: getattr(plan, k) for k in CAMPOS}


def guardar_condiciones(poliza, *, plan, plan_version, campos, funcionario, plan_nombre=None):
    """Guarda la copia de condiciones, su documento para el bot y sincroniza el nivel."""
    info = (
        CondicionesPoliza.objects.filter(poliza=poliza).select_related("documento").first()
    )
    if info and info.documento_id and info.documento.estado == "aprobado":
        retirar_documento(info.documento_id, funcionario.id)
    contenido = (
        "Cobertura informada: " + campos["cubre"]
        + "\nExclusiones: " + (campos["no_cubre"] or "No informadas.")
        + "\nLímites y franquicia: " + (campos["limites"] or "No informados.")
        + "\nTeléfono de asistencia: " + (campos["asistencia"] or "No informado.")
    )
    documento = crear_documento(
        titulo=f"Condiciones cargadas en póliza {poliza.numero_poliza}",
        version=uuid4().hex,
        referencia="Datos ingresados en la ficha de esta póliza por un aprobador.",
        contenido=contenido,
        funcionario_id=funcionario.id,
    )
    aprobar_documento(documento.id, funcionario.id)
    vincular_documento(poliza.numero_poliza, documento.id, funcionario.id)
    info, _ = CondicionesPoliza.objects.update_or_create(
        poliza=poliza,
        defaults={
            **{k: campos[k] for k in CAMPOS},
            "documento": documento,
            "plan_id": plan.id if plan else None,
            "plan_version": plan_version if plan else None,
            "plan_nombre": (plan_nombre if plan_nombre is not None else plan.nombre if plan_version == plan.version else
                            info.nombre_plan_confirmado if info else '') if plan else '',
            "actualizado_por": funcionario,
            "actualizado_en": timezone.now(),
        },
    )
    # Una sola fuente: el nivel de la póliza es el del plan, si el plan lo dice.
    if (plan is not None and plan_version == plan.version and plan.nivel
            and poliza.cobertura != plan.nivel):
        poliza.cobertura = plan.nivel
        poliza.save(update_fields=["cobertura"])
    return info
