"""Plantillas reutilizables; cambiar un plan no modifica contratos existentes."""
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from api.condiciones_poliza import Campos
from api.paginacion import Paginador
from api.permisos import EsAprobadorParaEscribir
from datos.models import Compania, PlanCobertura
from negocio.errores import NoEncontrado, DatosInvalidos
from negocio.seguridad import registrar

CAMPOS = ('cubre', 'no_cubre', 'limites', 'asistencia')


class PlanSerializer(Campos):
    nombre = serializers.CharField(max_length=120)
    compania_id = serializers.IntegerField(min_value=1)
    activo = serializers.BooleanField(default=True)


def representacion(plan):
    return {k: getattr(plan, k) for k in
            ('id', 'nombre', 'compania_id', 'version', 'activo', *CAMPOS)}


def guardar(request, plan=None):
    anteriores = representacion(plan) if plan else {}
    s = PlanSerializer(data={**anteriores, **{k: request.data[k] for k in request.data}})
    s.is_valid(raise_exception=True)
    datos = s.validated_data
    if not Compania.objects.filter(pk=datos['compania_id'], activa=True).exists():
        raise DatosInvalidos('Elegí una compañía activa.')
    if plan and plan.compania_id != datos['compania_id']:
        raise DatosInvalidos('La compañía de un plan no se cambia: creá otro plan para esa empresa.')
    try:
        with transaction.atomic():
            if plan is None:
                plan = PlanCobertura.objects.create(**datos, actualizado_por=request.funcionario)
            else:
                for k, v in datos.items():
                    setattr(plan, k, v)
                plan.version += 1
                plan.actualizado_por = request.funcionario
                plan.actualizado_en = timezone.now()
                plan.save()
    except IntegrityError as exc:
        raise DatosInvalidos('Ya existe un plan con ese nombre en esta compañía.') from exc
    registrar('guardar_plan_cobertura', f'plan/{plan.id}/version/{plan.version}', usuario_id=request.user.id)
    return plan


@api_view(['GET', 'POST'])
@permission_classes([EsAprobadorParaEscribir])
@transaction.atomic
def listar_o_crear(request):
    if request.method == 'POST':
        return Response(representacion(guardar(request)), status=201)
    qs = PlanCobertura.objects.select_related('compania').order_by('compania__nombre', 'nombre', 'id')
    if request.query_params.get('compania_id'):
        filtro = serializers.IntegerField(min_value=1).run_validation(request.query_params['compania_id'])
        qs = qs.filter(compania_id=filtro)
    p = Paginador()
    return p.get_paginated_response([representacion(x) for x in p.paginate_queryset(qs, request)])


@api_view(['GET', 'PATCH'])
@permission_classes([EsAprobadorParaEscribir])
@transaction.atomic
def detalle(request, id):
    plan = PlanCobertura.objects.select_for_update().filter(pk=id).first()
    if plan is None:
        raise NoEncontrado('El plan no existe.')
    return Response(representacion(guardar(request, plan) if request.method == 'PATCH' else plan))
