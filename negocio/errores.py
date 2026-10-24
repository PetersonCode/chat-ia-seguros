class ErrorNegocio(Exception):
    codigo = "error_negocio"

    def __init__(self, mensaje: str, codigo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo or self.__class__.codigo


class DatosInvalidos(ErrorNegocio):
    codigo = "datos_invalidos"


class ParametrosIncompletos(ErrorNegocio):
    codigo = "parametros_incompletos"


class PermisoDenegado(ErrorNegocio):
    codigo = "permiso_denegado"


class NoEncontrado(ErrorNegocio):
    codigo = "no_encontrado"


class EstadoInvalido(ErrorNegocio):
    codigo = "estado_invalido"
