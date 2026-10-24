from datos.selectors import funcionario_por_email
from negocio.errores import PermisoDenegado


def funcionario_de(user):
    if user is None:
        raise PermisoDenegado("No hay un usuario identificado.")
    email = getattr(user, "email", None)
    if not email:
        raise PermisoDenegado("El usuario no tiene email asociado.")
    funcionario = funcionario_por_email(email)
    if funcionario is None or not funcionario.activo:
        raise PermisoDenegado("El funcionario no está activo o no existe.")
    return funcionario
