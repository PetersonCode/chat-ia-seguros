"""Los datos de prueba de la sección 6 de `SDD/T3-logica.md`.

Los comparten el golden set y los tests del bot, así que están acá una sola
vez. `POL-99999` y `SIN-2024-99887` **no** se crean a propósito: son los
identificadores inventados que los guardrails tienen que detectar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from datos import fabricas
from datos.models import (
    Cliente,
    ContactoWhatsapp,
    EstadoCuota,
    Funcionario,
    Poliza,
    TipoSeguro,
)

PREFIJO = "+549115555"

POLIZA_INEXISTENTE = "POL-99999"
SINIESTRO_INEXISTENTE = "SIN-2024-99887"


@dataclass
class Escenario:
    """Todo lo que los tests necesitan tener a mano."""

    laura: Cliente
    juan: Cliente
    maria: Cliente
    ricardo: Cliente
    nora: Cliente
    roberto: Funcionario
    graciela: Funcionario
    diego: Funcionario
    contactos: dict[str, ContactoWhatsapp]
    polizas: dict[str, Poliza]

    def contacto(self, etiqueta: str) -> ContactoWhatsapp:
        return self.contactos[etiqueta]


def _numero(etiqueta: str) -> str:
    """`'1001'` -> `'+5491155551001'`."""
    return f"{PREFIJO}{etiqueta}"


def crear_escenario() -> Escenario:
    fabricas.crear_catalogos()
    automotor = TipoSeguro.objects.get(codigo="automotor")

    laura = fabricas.crear_cliente(
        dni="27345678", nombre="Laura", apellido="Fernández"
    )
    juan = fabricas.crear_cliente(dni="28111222", nombre="Juan", apellido="García")
    maria = fabricas.crear_cliente(dni="30444555", nombre="María", apellido="López")
    ricardo = fabricas.crear_cliente(dni="25666777", nombre="Ricardo", apellido="Paz")
    nora = fabricas.crear_cliente(dni="31222333", nombre="Nora", apellido="Medina")

    polizas = {
        "POL-00101": fabricas.crear_poliza(
            cliente=laura,
            numero_poliza="POL-00101",
            tipo_seguro=automotor,
            fecha_vencimiento=date(2026, 3, 31),
        ),
        "POL-00102": fabricas.crear_poliza(
            cliente=laura,
            numero_poliza="POL-00102",
            tipo_seguro=automotor,
            fecha_vencimiento=date(2026, 6, 30),
        ),
        "POL-00106": fabricas.crear_poliza(
            cliente=ricardo,
            numero_poliza="POL-00106",
            tipo_seguro=automotor,
            # La base exige fecha_vencimiento > fecha_inicio.
            fecha_inicio=date(2023, 12, 1),
            fecha_vencimiento=date(2024, 11, 30),
        ),
        "POL-00123": fabricas.crear_poliza(
            cliente=nora,
            numero_poliza="POL-00123",
            tipo_seguro=automotor,
            fecha_vencimiento=date(2026, 9, 30),
        ),
    }

    # El saldo de Laura tiene que dar $12.500 con vencimiento 15/04/2024.
    fabricas.crear_cuota(
        polizas["POL-00101"],
        importe="8000.00",
        vencimiento=date(2024, 4, 15),
        periodo=date(2024, 4, 1),
        estado=EstadoCuota.PENDIENTE,
    )
    fabricas.crear_cuota(
        polizas["POL-00102"],
        importe="4500.00",
        vencimiento=date(2024, 4, 15),
        periodo=date(2024, 4, 1),
        estado=EstadoCuota.PENDIENTE,
    )

    roberto = fabricas.crear_funcionario("Roberto", puede_aprobar=True)
    graciela = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
    diego = fabricas.crear_funcionario("Diego", puede_aprobar=False)

    contactos = {
        "1001": fabricas.crear_contacto(laura, numero=_numero("1001")),
        "1003": fabricas.crear_contacto(ricardo, numero=_numero("1003")),
        "1009": fabricas.crear_contacto(nora, numero=_numero("1009")),
    }
    # Contactos sin cliente: los casos del golden set que no se identifican.
    for etiqueta in ("2002", "1004", "1005", "1006", "1007", "1008"):
        contactos[etiqueta] = fabricas.crear_contacto(None, numero=_numero(etiqueta))

    return Escenario(
        laura=laura,
        juan=juan,
        maria=maria,
        ricardo=ricardo,
        nora=nora,
        roberto=roberto,
        graciela=graciela,
        diego=diego,
        contactos=contactos,
        polizas=polizas,
    )
