"""Cartera ficticia para el trabajo: 5 compañías, 15 planes y 20 clientes con pólizas.

    python manage.py cargar_cartera_demo

Todo pasa por las funciones de negocio (igual que desde el panel): las pólizas
generan sus cuotas, el plan define el nivel y copia sus condiciones, y cada
póliza queda con el documento aprobado que el bot cita al responder.

Datos ficticios: compañías inventadas, teléfonos de asistencia 0800 inventados,
y números de WhatsApp `+54911000002NN`, que no existen en Argentina: el bot nunca
le escribe a una persona real. Se niega si ya hay compañías cargadas.
"""
from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from datos.models import Compania, Cuota, Funcionario, PlanCobertura, Rol
from negocio.clientes import alta_cliente
from negocio.companias import alta_compania
from negocio.condiciones_poliza import guardar_condiciones, plan_para_poliza
from negocio.polizas import alta_poliza, registrar_pago
from negocio.vehiculos import alta_vehiculo

# nombre, comisión, teléfono de asistencia, km de remolque, límite de RC (millones),
# franquicia todo riesgo ($), días de auto sustituto
COMPANIAS = [
    ("Aseguradora Río de la Plata", "15.00", "0800-555-0101", 100, 300, 450_000, 10),
    ("Cóndor Seguros", "12.50", "0800-555-0202", 150, 350, 380_000, 15),
    ("Pampa Protección Seguros", "14.00", "0800-555-0303", 200, 400, 520_000, 7),
    ("Litoral Seguros Generales", "11.00", "0800-555-0404", 120, 300, 400_000, 10),
    ("Andina Compañía de Seguros", "16.00", "0800-555-0505", 250, 500, 600_000, 20),
]

CLIENTES = [
    ("30111201", "Lucía", "Fernández"), ("30111202", "Martín", "Gómez"),
    ("30111203", "Sofía", "Rodríguez"), ("30111204", "Juan Pablo", "López"),
    ("30111205", "Valentina", "Martínez"), ("30111206", "Tomás", "García"),
    ("30111207", "Camila", "Pérez"), ("30111208", "Nicolás", "Sánchez"),
    ("30111209", "Martina", "Romero"), ("30111210", "Federico", "Díaz"),
    ("30111211", "Agustina", "Álvarez"), ("30111212", "Diego", "Torres"),
    ("30111213", "Florencia", "Ruiz"), ("30111214", "Matías", "Ramírez"),
    ("30111215", "Julieta", "Flores"), ("30111216", "Santiago", "Acosta"),
    ("30111217", "Carolina", "Benítez"), ("30111218", "Lucas", "Medina"),
    ("30111219", "Paula", "Herrera"), ("30111220", "Gonzalo", "Suárez"),
]

# marca, modelo, clase, valor asegurado aproximado ($)
VEHICULOS = [
    ("Ford", "Fiesta", "auto", 14_000_000), ("Ford", "EcoSport", "camioneta", 21_000_000),
    ("Chevrolet", "Onix", "auto", 19_000_000), ("Chevrolet", "Cruze", "auto", 27_000_000),
    ("Volkswagen", "Gol Trend", "auto", 12_000_000), ("Volkswagen", "Amarok", "camioneta", 45_000_000),
    ("Fiat", "Cronos", "auto", 18_000_000), ("Fiat", "Fiorino", "utilitario", 16_000_000),
    ("Renault", "Sandero", "auto", 15_000_000), ("Renault", "Kangoo", "utilitario", 19_000_000),
    ("Peugeot", "208", "auto", 22_000_000), ("Peugeot", "2008", "camioneta", 28_000_000),
    ("Toyota", "Etios", "auto", 17_000_000), ("Toyota", "Hilux", "camioneta", 52_000_000),
    ("Toyota", "Corolla", "auto", 33_000_000), ("Citroën", "C3", "auto", 16_000_000),
    ("Honda", "HR-V", "camioneta", 36_000_000), ("Nissan", "Kicks", "camioneta", 31_000_000),
]

PRIMA = {"basica": (18_000, 28_000), "intermedia": (38_000, 58_000), "total": (72_000, 125_000)}


def _millones(n: int) -> str:
    return f"${n:,}".replace(",", ".")


def planes_de(nombre, telefono, km, rc, franquicia, sustituto):
    """Los tres planes de una compañía, con riesgos nombrados uno por uno: el bot
    responde «¿me cubre el granizo?» solo si el pasaje nombra el granizo."""
    rc_texto = f"{_millones(rc * 1_000_000)}"
    return [
        ("basica", "Responsabilidad Civil", (
            "Responsabilidad civil frente a terceros: daños a personas y a bienes de terceros "
            "causados con el vehículo asegurado, incluido el transporte de pasajeros. Defensa legal "
            f"y costas judiciales. Asistencia mecánica y remolque con grúa hasta {km} km."
        ), (
            "No cubre daños al propio vehículo por choque o accidente. No cubre robo ni hurto. "
            "No cubre incendio. No cubre granizo ni inundación. No cubre rotura de cristales, "
            "parabrisas ni luneta. No cubre cerraduras."
        ), f"Responsabilidad civil hasta {rc_texto} por evento. Sin franquicia."),
        ("intermedia", "Terceros Completo", (
            f"Responsabilidad civil frente a terceros hasta {rc_texto}. Robo y hurto total y parcial. "
            "Incendio total y parcial. Destrucción total por accidente. Rotura de cristales, "
            "parabrisas y luneta sin franquicia. Granizo. Reposición de cerraduras. Asistencia "
            f"mecánica y remolque con grúa hasta {km} km."
        ), (
            "No cubre daños parciales al propio vehículo por choque o accidente. No cubre inundación. "
            "No cubre conducción bajo efectos del alcohol, competencias ni conductor sin licencia."
        ), (
            "Granizo hasta el 10 % de la suma asegurada por evento. Cristales: una reposición por "
            f"vigencia. Responsabilidad civil hasta {rc_texto}."
        )),
        ("total", "Todo Riesgo con franquicia", (
            f"Todo lo del plan Terceros Completo más daños parciales al propio vehículo por choque o "
            "accidente, granizo sin tope, inundación, robo y hurto total y parcial, incendio, rotura "
            f"de cristales, parabrisas y luneta, y cerraduras. Auto sustituto por {sustituto} días ante "
            f"robo o reparación. Asistencia mecánica y remolque con grúa hasta {km * 2} km."
        ), (
            "No cubre desgaste ni fallas mecánicas. No cubre conducción bajo efectos del alcohol, "
            "competencias ni conductor sin licencia. No cubre objetos dejados dentro del vehículo."
        ), (
            f"Franquicia fija de {_millones(franquicia)} por evento de daño parcial. Robo e incendio sin "
            f"franquicia. Responsabilidad civil hasta {rc_texto}."
        )),
    ]


class Command(BaseCommand):
    help = "Carga 5 compañías ficticias con 3 planes cada una y 20 clientes con vehículos y pólizas."

    def add_arguments(self, parser):
        parser.add_argument("--semilla", type=int, default=2026)

    def handle(self, *args, **opciones):
        if Compania.objects.exists():
            raise CommandError("Ya hay compañías cargadas: este comando es para una base vacía.")
        funcionario = (
            Funcionario.objects.filter(rol=Rol.ADMINISTRADOR, activo=True).first()
            or Funcionario.objects.filter(puede_aprobar=True, activo=True).order_by("id").first()
        )
        if funcionario is None:
            raise CommandError("Hace falta un funcionario aprobador activo.")
        azar = random.Random(opciones["semilla"])
        hoy = timezone.localdate()
        with transaction.atomic():
            planes_por_compania = self._companias(funcionario)
            resumen = self._clientes(azar, hoy, funcionario, planes_por_compania)
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {len(COMPANIAS)} compañías, {len(COMPANIAS) * 3} planes, {len(CLIENTES)} clientes, "
            f"{resumen['vehiculos']} vehículos y pólizas, {resumen['pagos']} cuotas pagadas, "
            f"{resumen['morosos']} clientes con cuotas vencidas impagas."
        ))

    def _companias(self, funcionario):
        planes = {}
        for nombre, comision, telefono, km, rc, franquicia, sustituto in COMPANIAS:
            compania = alta_compania(nombre, comision, funcionario_id=funcionario.id)
            planes[compania.id] = (compania, {})
            for nivel, nombre_plan, cubre, no_cubre, limites in planes_de(
                nombre, telefono, km, rc, franquicia, sustituto
            ):
                contenido = ("Cobertura informada: " + cubre + "\nExclusiones: " + no_cubre
                             + "\nLímites y franquicia: " + limites + "\nTeléfono de asistencia: " + telefono)
                if len(contenido) > 1200:  # un solo pasaje: el bot lo cita entero
                    raise CommandError(f"El plan {nombre_plan} de {nombre} supera 1200 caracteres.")
                planes[compania.id][1][nivel] = PlanCobertura.objects.create(
                    compania=compania, nombre=nombre_plan, nivel=nivel, cubre=cubre,
                    no_cubre=no_cubre, limites=limites, asistencia=telefono,
                    actualizado_por=funcionario,
                )
        return planes

    def _clientes(self, azar, hoy, funcionario, planes_por_compania):
        companias = list(planes_por_compania.values())
        usadas: set[str] = set()
        morosos = set(azar.sample(range(len(CLIENTES)), 3))
        vehiculos = pagos = 0
        for indice, (dni, nombre, apellido) in enumerate(CLIENTES):
            correo = (f"{nombre.split()[0]}.{apellido}".lower()
                      .translate(str.maketrans("áéíóúñ", "aeioun")) + "@correo.example")
            cliente = alta_cliente(dni, nombre, apellido, f"+54911000002{indice + 1:02d}", correo)
            for _ in range(azar.choice((1, 1, 2))):
                marca, modelo, clase, valor = azar.choice(VEHICULOS)
                patente = self._patente(azar, usadas)
                anio = azar.randint(2012, hoy.year)
                vehiculo = alta_vehiculo(
                    cliente.id, patente, marca, modelo, anio,
                    uso="comercial" if clase == "utilitario" else "particular",
                    valor_asegurado=Decimal(valor - (hoy.year - anio) * 600_000),
                    funcionario_id=funcionario.id, clase=clase,
                )
                compania, planes = azar.choice(companias)
                nivel = azar.choices(("basica", "intermedia", "total"), weights=(3, 4, 3))[0]
                plan = planes[nivel]
                inicio = hoy - timedelta(days=azar.randint(10, 330))
                poliza = alta_poliza(
                    cliente.id, tipo_seguro="automotor", cobertura=nivel,
                    fecha_inicio=inicio, fecha_vencimiento=inicio.replace(year=inicio.year + 1),
                    prima_mensual=Decimal(round(azar.randint(*PRIMA[nivel]), -2)),
                    vehiculo_id=vehiculo.id, compania_id=compania.id,
                )
                plan_ok, version, campos = plan_para_poliza(poliza, plan.id, None)
                guardar_condiciones(poliza, plan=plan_ok, plan_version=version,
                                    campos=campos, funcionario=funcionario)
                pagos += self._pagar_vencidas(poliza, funcionario, deja_impagas=indice in morosos)
                vehiculos += 1
        return {"vehiculos": vehiculos, "pagos": pagos, "morosos": len(morosos)}

    @staticmethod
    def _patente(azar, usadas):
        letras = "ABCDEFGHJKLMNPRSTUVWXYZ"
        while True:
            patente = (f"A{azar.choice(letras)}{azar.randint(100, 999)}"
                       f"{azar.choice(letras)}{azar.choice(letras)}")
            if patente not in usadas:
                usadas.add(patente)
                return patente

    @staticmethod
    def _pagar_vencidas(poliza, funcionario, deja_impagas):
        """Al día salvo los morosos, que deben las dos últimas cuotas vencidas."""
        hoy = timezone.localdate()
        vencidas = list(Cuota.objects.filter(poliza=poliza, vencimiento__lte=hoy).order_by("vencimiento"))
        a_pagar = vencidas[:-2] if deja_impagas else vencidas
        for numero, cuota in enumerate(a_pagar, start=1):
            registrar_pago(poliza.id, referencia=f"DEMO-{poliza.numero_poliza}-{numero:02d}",
                           importe=cuota.importe, funcionario_id=funcionario.id)
        return len(a_pagar)
