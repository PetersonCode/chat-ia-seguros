"""Endpoint del panel de métricas (`/panel/metricas/`)."""

from __future__ import annotations

import csv
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.response import Response

from api.permisos import EsFuncionario
from api.views import _celda_csv_segura
from datos import selectors


class MetricasFiltroSerializer(serializers.Serializer):
    periodo = serializers.ChoiceField(
        choices=("hoy", "7dias", "mes"), required=False, default="7dias"
    )
    formato = serializers.ChoiceField(
        choices=("json", "csv"), required=False, default="json"
    )


def rango_del_periodo(periodo: str, hoy=None):
    """(desde, hasta) del filtro, en fecha local. `hasta` es siempre hoy."""
    hoy = hoy or timezone.localdate()
    if periodo == "hoy":
        return hoy, hoy
    if periodo == "mes":
        return hoy.replace(day=1), hoy
    return hoy - timedelta(days=6), hoy


def _numero(valor) -> str:
    return "" if valor is None else str(valor)


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([EsFuncionario])
def metricas_panel(request):
    filtros = MetricasFiltroSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    periodo = filtros.validated_data["periodo"]
    desde, hasta = rango_del_periodo(periodo)
    datos = selectors.metricas_panel(desde, hasta)

    if filtros.validated_data["formato"] == "csv":
        respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="metricas-{desde.isoformat()}-{hasta.isoformat()}.csv"'
        )
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        escritor = csv.writer(respuesta)
        escritor.writerow(("Desde", desde.isoformat()))
        escritor.writerow(("Hasta", hasta.isoformat()))
        escritor.writerow(("Indicador", "Detalle", "Cantidad", "Porcentaje"))
        escritor.writerow(("Consultas", "Total", datos["consultas"]["total"], ""))
        escritor.writerow(
            ("Consultas", "Variación vs período anterior (%)", "",
             _numero(datos["consultas"]["variacion_pct"]))
        )
        escritor.writerow(("Efectividad del bot", "Sin derivación", "",
                           _numero(datos["efectividad_pct"])))
        escritor.writerow(("Derivadas a humano", "Consultas derivadas",
                           datos["derivadas"], ""))
        escritor.writerow(("Tiempo de respuesta", "Promedio (min)",
                           _numero(datos["tiempo_respuesta_min"]), ""))
        for ramo in datos["ramos"]:
            escritor.writerow(("Ramo", _celda_csv_segura(ramo["nombre"]),
                               ramo["cantidad"], ramo["porcentaje"]))
        for motivo in datos["motivos_derivacion"]:
            escritor.writerow(("Motivo de derivación", _celda_csv_segura(motivo["motivo"]),
                               motivo["cantidad"], motivo["porcentaje"]))
        return respuesta

    return Response(
        {
            "periodo": {"nombre": periodo, "desde": desde.isoformat(), "hasta": hasta.isoformat()},
            **datos,
        }
    )