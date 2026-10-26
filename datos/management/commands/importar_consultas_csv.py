import csv
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from datos import selectors
from datos.limpieza import normalizar_telefono, parsear_fecha_hora
from datos.models import (
    ContactoWhatsapp,
    ConsultaBot,
    Conversacion,
    Direccion,
    Emisor,
    EstadoConsulta,
    EstadoEnvio,
    Mensaje,
    TipoConsulta,
)

_COLUMNAS_REQUERIDAS = {
    "caso_id",
    "fecha_hora",
    "numero_whatsapp",
    "mensaje_usuario",
    "respuesta_bot_ia",
    "tipo_consulta_detectado",
    "estado_caso",
    "funcionario_asignado",
    "fecha_resolucion",
}
_ZONA_BUENOS_AIRES = ZoneInfo("America/Argentina/Buenos_Aires")
_ESTADOS_ALERTA = {
    "alerta_seguridad": EstadoConsulta.PENDIENTE_REVISION,
    "alerta_accion": EstadoConsulta.PENDIENTE_REVISION,
}


class Command(BaseCommand):
    help = "Importa consultas históricas desde un CSV."

    def add_arguments(self, parser):
        parser.add_argument("ruta", type=Path)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida las filas sin guardar cambios.",
        )

    def handle(self, ruta: Path, dry_run: bool = False, **options):
        if not ruta.is_file():
            raise CommandError(f"No se encuentra el archivo CSV: {ruta}")

        creadas = omitidas = con_error = 0
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            faltantes = _COLUMNAS_REQUERIDAS - set(lector.fieldnames or ())
            if faltantes:
                nombres = ", ".join(sorted(faltantes))
                raise CommandError(f"Faltan columnas requeridas en el CSV: {nombres}")

            for numero_fila, fila in enumerate(lector, start=2):
                codigo = (fila.get("caso_id") or "").strip()
                try:
                    with transaction.atomic():
                        if codigo and ConsultaBot.objects.filter(
                            codigo_caso=codigo
                        ).exists():
                            omitidas += 1
                            continue
                        self._importar_fila(fila, codigo, dry_run=dry_run)
                        creadas += 1
                except (ValueError, IntegrityError, TipoConsulta.DoesNotExist) as error:
                    identificador = codigo or "sin código"
                    self.stderr.write(
                        f"Error en fila {numero_fila} ({identificador}): {error}"
                    )
                    con_error += 1

        if dry_run:
            self.stdout.write("Dry-run: no se guardaron cambios.")
        self.stdout.write(
            f"creadas: {creadas}, omitidas: {omitidas}, con error: {con_error}"
        )

    def _importar_fila(
        self,
        fila: dict[str, str],
        codigo: str,
        *,
        dry_run: bool,
    ) -> None:
        if not codigo:
            raise ValueError("El caso_id es obligatorio.")

        fecha_raw = (fila.get("fecha_hora") or "").strip()
        if not fecha_raw:
            raise ValueError("La fecha_hora es obligatoria.")
        fecha_parseada = parsear_fecha_hora(fecha_raw)
        hora = fecha_parseada.hora or time.min
        fecha_hora = datetime.combine(
            fecha_parseada.fecha,
            hora,
            tzinfo=_ZONA_BUENOS_AIRES,
        )

        tipo_codigo = (fila.get("tipo_consulta_detectado") or "").strip().casefold()
        if not tipo_codigo:
            raise ValueError("El tipo_consulta_detectado es obligatorio.")
        tipo_consulta = selectors.tipo_consulta(tipo_codigo)

        estado_raw = (fila.get("estado_caso") or "").strip().casefold()
        estado = _ESTADOS_ALERTA.get(estado_raw)
        if estado is None:
            try:
                estado = EstadoConsulta(estado_raw)
            except ValueError as error:
                raise ValueError(f"Estado de consulta desconocido: {estado_raw!r}.") from error

        funcionario_nombre = (fila.get("funcionario_asignado") or "").strip()
        funcionario = (
            selectors.funcionario_por_nombre(funcionario_nombre)
            if funcionario_nombre
            else None
        )
        if funcionario_nombre and funcionario is None:
            raise ValueError(
                f"No se encontró el funcionario {funcionario_nombre!r}."
            )

        notas: list[str] = []
        if fecha_parseada.hora is None:
            notas.append("Hora no informada (se asumió 00:00).")

        fecha_resolucion: date | None = None
        resolucion_raw = (fila.get("fecha_resolucion") or "").strip()
        if resolucion_raw:
            fecha_resolucion = parsear_fecha_hora(resolucion_raw).fecha
            fecha_local_consulta = fecha_hora.astimezone(
                _ZONA_BUENOS_AIRES
            ).date()
            if fecha_resolucion < fecha_local_consulta:
                notas.append(
                    f"fecha_resolucion original {resolucion_raw} es anterior "
                    "a la consulta: descartada."
                )
                fecha_resolucion = None

        numero_raw = (fila.get("numero_whatsapp") or "").strip()
        numero = normalizar_telefono(numero_raw) if numero_raw else None
        if not numero_raw:
            notas.append("Mensaje sin número de WhatsApp.")

        if dry_run:
            return

        contacto = None
        conversacion = None
        if numero is not None:
            contacto, _ = ContactoWhatsapp.objects.get_or_create(
                numero=numero,
                defaults={"cliente": None},
            )
            conversacion = selectors.conversacion_abierta(contacto.pk)
            if conversacion is None:
                conversacion = Conversacion.objects.create(
                    contacto=contacto,
                    creada_en=fecha_hora,
                    ultimo_mensaje_cliente_en=fecha_hora,
                )
            else:
                actualizada = False
                if (
                    conversacion.ultimo_mensaje_cliente_en is None
                    or fecha_hora > conversacion.ultimo_mensaje_cliente_en
                ):
                    conversacion.ultimo_mensaje_cliente_en = fecha_hora
                    actualizada = True
                if fecha_hora < conversacion.creada_en:
                    conversacion.creada_en = fecha_hora
                    actualizada = True
                if actualizada:
                    conversacion.save(
                        update_fields=("creada_en", "ultimo_mensaje_cliente_en")
                    )
        consulta = ConsultaBot.objects.create(
            codigo_caso=codigo,
            fecha_hora=fecha_hora,
            contacto=contacto,
            conversacion=conversacion,
            mensaje_usuario=fila.get("mensaje_usuario") or "",
            respuesta_bot=fila.get("respuesta_bot_ia") or "",
            tipo_consulta=tipo_consulta,
            estado=estado,
            funcionario_asignado=funcionario,
            fecha_resolucion=fecha_resolucion,
            notas_importacion=" ".join(notas) or None,
            datos_origen=dict(fila),
        )

        if conversacion is None:
            return

        texto_entrante = fila.get("mensaje_usuario") or ""
        respuesta = fila.get("respuesta_bot_ia") or ""
        Mensaje.objects.create(
            conversacion=conversacion,
            consulta=consulta,
            direccion=Direccion.ENTRANTE,
            emisor=Emisor.CLIENTE,
            texto=texto_entrante,
            estado_envio=EstadoEnvio.RECIBIDO,
            fecha_hora=fecha_hora,
        )
        fecha_envio = fecha_hora + timedelta(seconds=5)
        Mensaje.objects.create(
            conversacion=conversacion,
            consulta=consulta,
            direccion=Direccion.SALIENTE,
            emisor=Emisor.BOT,
            texto=respuesta,
            estado_envio=EstadoEnvio.ENVIADO,
            fecha_hora=fecha_envio,
            enviado_en=fecha_envio,
        )
