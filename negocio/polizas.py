"""Alta de pólizas desde el panel (ABM manual), con su plan de cuotas.

Como el ABM de clientes, acá no hay automatismos: todo lo dispara una persona
desde la ficha del cliente. Lo que este módulo agrega sobre un `save()` son las
validaciones y el plan de cuotas, y el motivo es el mismo: la cartera es la
fuente de verdad de la que el bot saca saldos y vencimientos (R12). Una póliza
sin cuotas hace que el bot conteste "no tenés saldo pendiente" a alguien que sí
debe, y una con fechas al revés no la acepta ni la base.

Las cuotas se generan en el alta y no después porque `v_polizas_resumen` calcula
el saldo sumando cuotas: sin ellas la póliza existe pero es invisible para toda
la lógica de cobranza del bot.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import connection, transaction
from django.utils import timezone

from datos.models import (
    Cliente,
    Cobertura,
    Cuota,
    EstadoCuota,
    EstadoPoliza,
    Poliza,
    TipoSeguro,
)
from negocio.errores import DatosInvalidos, EstadoInvalido, NoEncontrado

# Llave del advisory lock que serializa la numeración, como `LOCK_CODIGO_CASO`
# hace con los `CASO-###`: sin esto, dos altas a la vez proponen el mismo
# número y la segunda choca contra el UNIQUE de la base.
LOCK_NUMERO_POLIZA = 4243

RE_NUMERO_POLIZA = re.compile(r"^POL-\d{5}$")
NUMERO_MAXIMO = 99999

# Día del mes en que vence cada cuota. Es la convención del seed (período el 1,
# vencimiento el 15) y la base solo exige que el período sea el primer día.
DIA_VENCIMIENTO_CUOTA = 15


# Lo que todavía se le debe a la póliza: `v_polizas_resumen` suma estos dos
# estados para el saldo, así que cobrar es pasar la más vieja a `pagada`.
CUOTAS_IMPAGAS = (EstadoCuota.PENDIENTE, EstadoCuota.VENCIDA)


def _cliente(cliente_id: int) -> Cliente:
    cliente = Cliente.objects.filter(pk=cliente_id).first()
    if cliente is None:
        raise NoEncontrado("El cliente no existe.")
    return cliente


def proximo_numero_poliza() -> str:
    """El siguiente `POL-#####` libre: el mayor que haya más uno.

    Mismo criterio que la numeración de casos del bot. El lock es de
    transacción: llamada suelta se suelta enseguida, y dentro de `alta_poliza`
    queda tomado hasta el commit, que es cuando el número ya existe.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_NUMERO_POLIZA])
        cursor.execute(
            """
            SELECT COALESCE(MAX(SUBSTRING(numero_poliza FROM 'POL-([0-9]{5})$')::int), 0)
            FROM polizas
            WHERE numero_poliza ~ '^POL-[0-9]{5}$'
            """
        )
        maximo = cursor.fetchone()[0] or 0
    if maximo >= NUMERO_MAXIMO:
        raise EstadoInvalido(
            "Se agotaron los números de póliza con el formato POL-#####."
        )
    return f"POL-{maximo + 1:05d}"


def _numero_validado(valor: str | None) -> str:
    """El número que mandaron, o el próximo libre si no mandaron ninguno."""
    texto = (valor or "").strip().upper()
    if not texto:
        return proximo_numero_poliza()
    if not RE_NUMERO_POLIZA.match(texto):
        raise DatosInvalidos(
            "El número de póliza tiene que ser POL- seguido de 5 dígitos, "
            "por ejemplo POL-00109."
        )
    if Poliza.objects.filter(numero_poliza=texto).exists():
        raise DatosInvalidos(f"Ya existe una póliza con el número {texto}.")
    return texto


def _tipo_validado(codigo: str) -> TipoSeguro:
    tipo = TipoSeguro.objects.filter(codigo=(codigo or "").strip().lower()).first()
    if tipo is None:
        disponibles = ", ".join(
            TipoSeguro.objects.order_by("id").values_list("codigo", flat=True)
        )
        raise DatosInvalidos(
            f"El tipo de seguro no existe. Los tipos disponibles son: {disponibles}."
        )
    return tipo


def _cobertura_validada(valor: str) -> str:
    cobertura = (valor or "").strip().lower()
    if cobertura not in Cobertura.values:
        raise DatosInvalidos(
            "La cobertura tiene que ser una de: " + ", ".join(Cobertura.values) + "."
        )
    return cobertura


def _prima_validada(valor) -> Decimal:
    try:
        prima = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError) as error:
        raise DatosInvalidos("La prima mensual tiene que ser un número.") from error
    if prima < 0:
        raise DatosInvalidos("La prima mensual no puede ser negativa.")
    return prima.quantize(Decimal("0.01"))


def _fechas_validadas(inicio, vencimiento) -> tuple[date, date]:
    if not isinstance(inicio, date) or not isinstance(vencimiento, date):
        raise DatosInvalidos("Las fechas de inicio y vencimiento son obligatorias.")
    if vencimiento <= inicio:
        raise DatosInvalidos(
            "El vencimiento de la póliza tiene que ser posterior al inicio."
        )
    return inicio, vencimiento


def _sumar_meses(primero_de_mes: date, meses: int) -> date:
    """Avanza meses sobre un primer día de mes, sin dependencias externas."""
    total = primero_de_mes.month - 1 + meses
    return date(primero_de_mes.year + total // 12, total % 12 + 1, 1)


def meses_de_cobertura(inicio: date, vencimiento: date) -> int:
    """Meses enteros que cubre la póliza; nunca menos de uno.

    Una póliza del 10/01 al 10/01 del año siguiente son 12 cuotas, no 13:
    contar los meses del calendario que toca daría trece. Y una de quince días
    igual lleva una cuota, porque se cobró una prima.
    """
    meses = (vencimiento.year - inicio.year) * 12 + (vencimiento.month - inicio.month)
    if vencimiento.day < inicio.day:
        meses -= 1
    return max(1, meses)


def plan_de_cuotas(poliza: Poliza) -> list[Cuota]:
    """Una cuota por mes de cobertura, todas pendientes.

    Quedan `pendiente` aunque el vencimiento ya haya pasado: pasarlas a
    `vencida` es trabajo de la cobranza, y para el saldo del bot da igual
    —`v_polizas_resumen` suma los dos estados—.
    """
    primer_periodo = poliza.fecha_inicio.replace(day=1)
    cuotas = []
    for indice in range(meses_de_cobertura(poliza.fecha_inicio, poliza.fecha_vencimiento)):
        periodo = _sumar_meses(primer_periodo, indice)
        vencimiento = periodo.replace(day=DIA_VENCIMIENTO_CUOTA)
        # Una póliza que arranca después del 15 no puede tener su primera cuota
        # vencida antes de existir.
        if vencimiento < poliza.fecha_inicio:
            vencimiento = poliza.fecha_inicio
        cuotas.append(
            Cuota(
                poliza=poliza,
                periodo=periodo,
                importe=poliza.prima_mensual,
                vencimiento=vencimiento,
                estado=EstadoCuota.PENDIENTE,
            )
        )
    return cuotas


@transaction.atomic
def alta_poliza(
    cliente_id: int,
    *,
    tipo_seguro: str,
    cobertura: str,
    fecha_inicio: date,
    fecha_vencimiento: date,
    prima_mensual,
    bien_asegurado: str | None = None,
    numero_poliza: str | None = None,
) -> Poliza:
    """Crea la póliza con su plan de cuotas, o no crea nada.

    `numero_poliza` vacío toma el próximo libre; si viene, se respeta el que
    eligió el funcionario, validando formato y que no esté repetido.
    """
    cliente = _cliente(cliente_id)
    if not cliente.activo:
        raise EstadoInvalido(
            "El cliente está dado de baja: hay que reactivarlo antes de "
            "darle una póliza nueva."
        )

    inicio, vencimiento = _fechas_validadas(fecha_inicio, fecha_vencimiento)
    poliza = Poliza.objects.create(
        numero_poliza=_numero_validado(numero_poliza),
        cliente=cliente,
        tipo_seguro=_tipo_validado(tipo_seguro),
        cobertura=_cobertura_validada(cobertura),
        # Una póliza que nace con el vencimiento pasado nace vencida: dejarla
        # `vigente` le mentiría al bot y trabaría la baja del cliente.
        estado=(
            EstadoPoliza.VIGENTE
            if vencimiento > timezone.localdate()
            else EstadoPoliza.VENCIDA
        ),
        fecha_inicio=inicio,
        fecha_vencimiento=vencimiento,
        prima_mensual=_prima_validada(prima_mensual),
        bien_asegurado=(bien_asegurado or "").strip() or None,
    )
    Cuota.objects.bulk_create(plan_de_cuotas(poliza))
    return poliza


@transaction.atomic
def registrar_pago(poliza_id: int) -> Cuota:
    """Marca pagada la cuota impaga más vieja de la póliza y la devuelve.

    Una cuota por vez, y siempre la más vieja: es como se cobra una póliza
    mensual, y deja el saldo bajando de a un mes en vez de borrar la deuda
    entera de un clic.

    `select_for_update` es por dos pantallas a la vez: sin el lock, dos
    funcionarios que aprietan el botón al mismo tiempo leen la misma cuota
    pendiente y cobran dos veces el mismo mes.
    """
    if not Poliza.objects.filter(pk=poliza_id).exists():
        raise NoEncontrado("La póliza no existe.")

    cuota = (
        Cuota.objects.select_for_update()
        .filter(poliza_id=poliza_id, estado__in=CUOTAS_IMPAGAS)
        .order_by("periodo", "id")
        .first()
    )
    if cuota is None:
        raise EstadoInvalido("La póliza no tiene cuotas pendientes de pago.")

    cuota.estado = EstadoCuota.PAGADA
    cuota.fecha_pago = timezone.localdate()
    # La base exige que una cuota pagada tenga fecha e importe, los dos o
    # ninguno. Se cobra el importe de la cuota: no hay pagos parciales acá.
    cuota.importe_pagado = cuota.importe
    cuota.save(update_fields=["estado", "fecha_pago", "importe_pagado"])
    return cuota
