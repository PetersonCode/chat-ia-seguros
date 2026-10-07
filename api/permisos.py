from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from negocio.errores import PermisoDenegado as ErrorPermisoDenegado
from negocio.sesion import funcionario_de


class EsFuncionario(BasePermission):
    message = "Debe iniciar sesión."

    def has_permission(self, request, view):
        if not getattr(request.user, "is_authenticated", False):
            raise AuthenticationFailed("Debe iniciar sesión.")
        try:
            request.funcionario = funcionario_de(request.user)
        except ErrorPermisoDenegado as exc:
            raise PermissionDenied(str(exc.mensaje))
        return True


class EsAprobador(EsFuncionario):
    message = "No tiene permisos de aprobación."

    def has_permission(self, request, view):
        super().has_permission(request, view)
        if not request.funcionario.puede_aprobar:
            raise PermissionDenied("No tiene permisos de aprobación.")
        return True


class EsAprobadorParaEscribir(EsFuncionario):
    """Leer necesita sesión; escribir, permiso de aprobación.

    Para las rutas que mezclan ambas cosas en la misma URL, como el ABM de
    clientes: cualquier funcionario consulta la cartera, pero tocarla queda
    para quien ya puede aprobar bajas de póliza.
    """

    message = "No tiene permisos de aprobación."

    def has_permission(self, request, view):
        super().has_permission(request, view)
        if request.method not in SAFE_METHODS and not request.funcionario.puede_aprobar:
            raise PermissionDenied("No tiene permisos de aprobación.")
        return True
