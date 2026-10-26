from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from datos.models import EstadoSiniestro
from negocio.documentos import MAXIMO_CONTENIDO


class BuscarDocumentoSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=1, max_length=300, trim_whitespace=True)


class DocumentoAltaSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=300)
    version = serializers.CharField(max_length=100)
    referencia = serializers.CharField(max_length=1000)
    contenido = serializers.CharField(
        max_length=MAXIMO_CONTENIDO,
        trim_whitespace=False,
    )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class ResponderSerializer(serializers.Serializer):
    texto = serializers.CharField(trim_whitespace=False)


class MotivoSerializer(serializers.Serializer):
    motivo = serializers.CharField(trim_whitespace=False)


class FinalizacionAccionSerializer(serializers.Serializer):
    referencia = serializers.CharField(min_length=3, max_length=100)
    motivo = serializers.CharField(min_length=3)


class TextoCorregidoSerializer(serializers.Serializer):
    texto_corregido = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)


class ParametrosSerializer(serializers.Serializer):
    parametros = serializers.DictField(required=True)


class ConsultaFiltroSerializer(serializers.Serializer):
    estado = serializers.CharField(required=False, allow_blank=True)
    con_alertas = serializers.BooleanField(required=False)
    esperando_humano = serializers.BooleanField(required=False)
    q = serializers.CharField(required=False, allow_blank=True)
    pagina = serializers.IntegerField(required=False, min_value=1)


class AccionFiltroSerializer(serializers.Serializer):
    estado = serializers.CharField(required=False, allow_blank=True)
    pagina = serializers.IntegerField(required=False, min_value=1)


class UsuarioAltaSerializer(serializers.Serializer):
    """El contenido se valida en `negocio.usuarios`; acá solo la forma."""

    nombre = serializers.CharField()
    email = serializers.CharField()
    rol = serializers.CharField()
    clave = serializers.CharField(trim_whitespace=False)
    puede_aprobar = serializers.BooleanField(required=False, default=False)


class UsuarioModificacionSerializer(serializers.Serializer):
    """Todos opcionales: se actualiza solo lo que venga."""

    nombre = serializers.CharField(required=False)
    rol = serializers.CharField(required=False)
    puede_aprobar = serializers.BooleanField(required=False)
    activo = serializers.BooleanField(required=False)


class ClaveSerializer(serializers.Serializer):
    clave = serializers.CharField(trim_whitespace=False)


class ClienteAltaSerializer(serializers.Serializer):
    """El contenido se valida en `negocio.clientes`; acá solo la forma."""

    dni = serializers.CharField()
    nombre = serializers.CharField()
    apellido = serializers.CharField()
    telefono = serializers.CharField()
    email = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PolizaAltaSerializer(serializers.Serializer):
    """El contenido se valida en `negocio.polizas`; acá solo la forma.

    `numero_poliza` vacío o ausente significa "poneme el próximo libre", así
    que se admite en blanco en vez de exigirlo.
    """

    tipo_seguro = serializers.CharField()
    cobertura = serializers.CharField()
    fecha_inicio = serializers.DateField()
    fecha_vencimiento = serializers.DateField()
    prima_mensual = serializers.CharField()
    bien_asegurado = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    numero_poliza = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


class PagoRegistroSerializer(serializers.Serializer):
    referencia = serializers.CharField(max_length=100, trim_whitespace=True)
    importe = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class ReporteGestionFiltroSerializer(serializers.Serializer):
    desde = serializers.DateField()
    hasta = serializers.DateField()
    formato = serializers.ChoiceField(
        choices=("json", "csv"),
        required=False,
        default="json",
    )

    def validate(self, attrs):
        if attrs["hasta"] < attrs["desde"]:
            raise serializers.ValidationError(
                {"hasta": "La fecha final debe ser igual o posterior a la inicial."}
            )
        return attrs


class DenunciaSiniestroSerializer(serializers.Serializer):
    cliente_id = serializers.IntegerField(min_value=1)
    poliza_id = serializers.IntegerField(min_value=1)
    fecha_ocurrencia = serializers.DateField()
    descripcion = serializers.CharField(trim_whitespace=True)


class TransicionSiniestroSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=EstadoSiniestro.choices)
    motivo = serializers.CharField(trim_whitespace=True, min_length=3)


class ClienteModificacionSerializer(serializers.Serializer):
    """Todos opcionales: se actualiza solo lo que venga."""

    dni = serializers.CharField(required=False)
    nombre = serializers.CharField(required=False)
    apellido = serializers.CharField(required=False)
    telefono = serializers.CharField(required=False)
    email = serializers.CharField(required=False, allow_blank=True, allow_null=True)
