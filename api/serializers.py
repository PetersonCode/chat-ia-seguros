from __future__ import annotations

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class ResponderSerializer(serializers.Serializer):
    texto = serializers.CharField(trim_whitespace=False)


class MotivoSerializer(serializers.Serializer):
    motivo = serializers.CharField(trim_whitespace=False)


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


class ClienteAltaSerializer(serializers.Serializer):
    """El contenido se valida en `negocio.clientes`; acá solo la forma."""

    dni = serializers.CharField()
    nombre = serializers.CharField()
    apellido = serializers.CharField()
    telefono = serializers.CharField()
    email = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ClienteModificacionSerializer(serializers.Serializer):
    """Todos opcionales: se actualiza solo lo que venga."""

    dni = serializers.CharField(required=False)
    nombre = serializers.CharField(required=False)
    apellido = serializers.CharField(required=False)
    telefono = serializers.CharField(required=False)
    email = serializers.CharField(required=False, allow_blank=True, allow_null=True)
