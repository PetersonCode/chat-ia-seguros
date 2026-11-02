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

import calendar
import hashlib
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
    Funcionario,
    Pago,
    Poliza,
    TipoSeguro,
)
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)

# Llave del advisory lock que serializa la numeración, como `LOCK_CODIGO_CASO`
# hace con los `CASO-###`: sin esto, dos altas a la vez proponen el mismo
# número y la segunda choca contra el UNIQUE de la base.
LOCK_NUMERO_POLIZA = 4243

RE_NUMERO_POLIZA = re.compile(r"^POL-\d{5}$")
NUMERO_MAXIMO = 99999

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
    if not prima.is_finite():
        raise DatosInvalidos("La prima mensual debe ser un número finito.")
    if prima < 0:
        raise DatosInvalidos("La prima mensual no puede ser negativa.")
    if prima > Decimal("9999999999.99"):
        raise DatosInvalidos("La prima mensual está fuera del rango permitido.")
    try:
        centavos = prima.quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise DatosInvalidos("La prima mensual está fuera del rango permitido.") from error
    if centavos != prima:
        raise DatosInvalidos("La prima mensual admite como máximo dos decimales.")
    return centavos


def _fechas_validadas(inicio, vencimiento) -> tuple[date, date]:
    if not isinstance(inicio, date) or not isinstance(vencimiento, date):
        raise DatosInvalidos("Las fechas de inicio y vencimiento son obligatorias.")
    if vencimiento <= inicio:
        raise DatosInvalidos(
            "El vencimiento de la póliza tiene que ser posterior al inicio."
        )
    return inicio, vencimiento


def _aniversario_mensual(inicio: date, meses: int) -> date:
    """Calcula aniversarios anclados al día original, acotando meses cortos."""
    total = inicio.month - 1 + meses
    anio = inicio.year + total // 12
    mes = total % 12 + 1
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(inicio.day, ultimo_dia))


def meses_de_cobertura(inicio: date, vencimiento: date) -> int:
    """Cuenta ciclos mensuales desde el inicio, cobrando completo el último.

    El día original se conserva como ancla cuando un mes no tiene ese día:
    después de que enero 31 cae en febrero 28, marzo vuelve al 31. Si el
    vencimiento es un aniversario exacto no se agrega otro ciclo.
    """
    meses = (vencimiento.year - inicio.year) * 12 + (vencimiento.month - inicio.month)
    if _aniversario_mensual(inicio, meses) < vencimiento:
        meses += 1
    return max(1, meses)


def plan_de_cuotas(poliza: Poliza) -> list[Cuota]:
    """Una cuota por ciclo mensual desde el inicio, todas pendientes.

    Quedan `pendiente` aunque el vencimiento ya haya pasado: pasarlas a
    `vencida` es trabajo de la cobranza, y para el saldo del bot da igual
    —`v_polizas_resumen` suma los dos estados—. `periodo` sigue identificando
    el mes calendario del ciclo para cumplir la restricción de la base.
    """
    # Una prima gratuita no genera deuda ni un pago ficticio por cero.
    if poliza.prima_mensual == 0:
        return []
    cuotas = []
    for indice in range(meses_de_cobertura(poliza.fecha_inicio, poliza.fecha_vencimiento)):
        inicio_ciclo = _aniversario_mensual(poliza.fecha_inicio, indice)
        cuotas.append(
            Cuota(
                poliza=poliza,
                periodo=inicio_ciclo.replace(day=1),
                importe=poliza.prima_mensual,
                vencimiento=inicio_ciclo,
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
        # La fecha de vencimiento es inclusiva, igual que en
        # `selectors.polizas_vigentes`.
        estado=(
            EstadoPoliza.VIGENTE
            if vencimiento >= timezone.localdate()
            else EstadoPoliza.VENCIDA
        ),
        fecha_inicio=inicio,
        fecha_vencimiento=vencimiento,
        prima_mensual=_prima_validada(prima_mensual),
        bien_asegurado=(bien_asegurado or "").strip() or None,
    )
    Cuota.objects.bulk_create(plan_de_cuotas(poliza))
    return poliza


def _importe_pago_validado(valor) -> Decimal:
    try:
        importe = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError) as error:
        raise DatosInvalidos("El importe del pago tiene que ser un número.") from error
    if not importe.is_finite() or importe <= 0:
        raise DatosInvalidos("El importe del pago tiene que ser mayor que cero.")
    try:
        importe_centavos = importe.quantize(Decimal("0.01"))
    except InvalidOperation as error:
        raise DatosInvalidos("El importe del pago está fuera del rango permitido.") from error
    if importe != importe_centavos:
        raise DatosInvalidos("El importe del pago admite como máximo dos decimales.")
    return importe_centavos


def _referencia_pago_validada(referencia: str) -> str:
    texto = (referencia or "").strip()
    if not texto:
        raise DatosInvalidos("La referencia del comprobante es obligatoria.")
    if len(texto) > 100:
        raise DatosInvalidos(
            "La referencia del comprobante no puede superar 100 caracteres."
        )
    return texto


def _lock_referencia_pago(referencia: str) -> None:
    """Serializa referencias iguales aun si llegan para pólizas distintas."""
    llave = int.from_bytes(
        hashlib.sha256(referencia.encode("utf-8")).digest()[:8], "big"
    )
    if llave >= 2**63:
        llave -= 2**64
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [llave])


@transaction.atomic
def registrar_pago(
    poliza_id: int,
    *,
    referencia: str,
    importe,
    funcionario_id: int,
) -> Pago:
    """Registra un cobro completo e idempotente de la cuota impaga más vieja."""
    referencia = _referencia_pago_validada(referencia)
    importe = _importe_pago_validado(importe)
    funcionario = Funcionario.objects.filter(
        pk=funcionario_id, activo=True, puede_aprobar=True
    ).first()
    if funcionario is None:
        raise PermisoDenegado(
            "Hace falta un funcionario activo con permiso de aprobación para registrar pagos."
        )

    _lock_referencia_pago(referencia)
    existente = Pago.objects.select_related("cuota__poliza").filter(
        referencia=referencia
    ).first()
    if existente is not None:
        if existente.cuota.poliza_id != poliza_id or existente.importe != importe:
            raise EstadoInvalido(
                "La referencia del comprobante ya se usó con otra póliza o importe."
            )
        return existente

    poliza = Poliza.objects.select_for_update().filter(pk=poliza_id).first()
    if poliza is None:
        raise NoEncontrado("La póliza no existe.")

    cuota = (
        Cuota.objects.select_for_update()
        .filter(poliza_id=poliza_id, estado__in=CUOTAS_IMPAGAS)
        .order_by("periodo", "id")
        .first()
    )
    if cuota is None:
        raise EstadoInvalido("La póliza no tiene cuotas pendientes de pago.")
    if importe != cuota.importe:
        raise DatosInvalidos(
            "Solo se admiten pagos completos: el importe debe coincidir con el de la cuota."
        )

    pago = Pago.objects.create(
        referencia=referencia,
        cuota=cuota,
        importe=importe,
        fecha_pago=timezone.localdate(),
        responsable=funcionario,
    )
    pago.refresh_from_db()
    return pago
