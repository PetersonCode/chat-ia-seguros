"""Borrado físico de póliza, plan y compañía. Solo el rol administrador."""
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from api.permisos import EsAdministrador
from negocio.eliminaciones import eliminar_compania, eliminar_plan, eliminar_poliza


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAdministrador])
def poliza_eliminar_definitivo(request, id):
    return Response({"id": id, "borrados": eliminar_poliza(id, request.funcionario.id)})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAdministrador])
def plan_eliminar(request, id):
    return Response({"id": id, "borrados": eliminar_plan(id, request.funcionario.id)})


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsAdministrador])
def compania_eliminar_definitivo(request, id):
    return Response({"id": id, "borrados": eliminar_compania(id, request.funcionario.id)})
