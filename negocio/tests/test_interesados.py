"""P5 · el embudo de interesados (AC-T3-81 a AC-T3-84 y AC-T3-86)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as tz
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from datos import fabricas
from datos.models import (
    Cliente,
    ContactoWhatsapp,
    Interesado,
    InteresadoHistorial,
)
from negocio import interesados
from negocio.errores import (
    DatosInvalidos,
    EstadoInvalido,
    NoEncontrado,
    PermisoDenegado,
)


class BaseInteresadosTests(TestCase):
    def setUp(self):
        fabricas.crear_catalogos()
        self.graciela = fabricas.crear_funcionario("Graciela", puede_aprobar=True)
        self.diego = fabricas.crear_funcionario("Diego", puede_aprobar=False)

    def _crear(self, **campos):
        argumentos = {"nombre": "Marta", "origen": "web"}
        argumentos.update(campos)
        return interesados.crear_interesado(self.diego.id, **argumentos)

    def _en(self, interesado, *etapas, por=None):
        """Lleva al interesado por las etapas dadas, como lo haría el mostrador."""
        for etapa in etapas:
            interesado = interesados.mover_interesado(
                interesado.pk, etapa, (por or self.diego).id
            )
        return interesado


class CrearInteresadoTests(BaseInteresadosTests):
    # AC-T3-81
    def test_nace_en_consulta_con_responsable_y_primer_historial(self):
        interesado = interesados.crear_interesado(
            self.diego.id, "  Marta ", "recomendacion", apellido=" Gómez ", telefono="11 5555-0001"
        )

        interesado.refresh_from_db()
        self.assertEqual(interesado.nombre, "Marta")
        self.assertEqual(interesado.apellido, "Gómez")
        self.assertEqual(interesado.estado, "consulta")
        self.assertEqual(interesado.origen, "recomendacion")
        self.assertEqual(interesado.responsable_id, self.diego.id)
        self.assertEqual(interesado.datos, {})
        historial = interesado.historial.get()
        self.assertIsNone(historial.estado_anterior)
        self.assertEqual(historial.estado_nuevo, "consulta")
        self.assertEqual(historial.funcionario_id, self.diego.id)

    # AC-T3-81
    def test_el_telefono_se_normaliza_y_crea_un_contacto_sin_cliente(self):
        interesado = self._crear(telefono="011 5555-0002")

        self.assertEqual(interesado.contacto.numero, "+5491155550002")
        self.assertIsNone(interesado.contacto.cliente_id)
        self.assertIsNone(interesado.cliente_id)

    # AC-T3-81
    def test_reutiliza_el_contacto_de_whatsapp_que_ya_existe(self):
        contacto = fabricas.crear_contacto(numero="+5491155550003")

        interesado = self._crear(telefono="+54 9 11 5555-0003")

        self.assertEqual(interesado.contacto_id, contacto.pk)
        self.assertEqual(ContactoWhatsapp.objects.filter(numero="+5491155550003").count(), 1)

    # AC-T3-81
    def test_sin_telefono_no_hay_contacto(self):
        for vacio in (None, "", "   "):
            with self.subTest(telefono=vacio):
                self.assertIsNone(self._crear(telefono=vacio).contacto_id)

    # AC-T3-81
    def test_origen_invalido_nombre_vacio_o_telefono_invalido_son_datos_invalidos(self):
        casos = (
            {"origen": "paloma"},
            {"nombre": ""},
            {"nombre": "   "},
            {"nombre": None},
            {"telefono": "no es un número"},
            {"telefono": "123"},
        )
        for campos in casos:
            with self.subTest(campos=campos):
                with self.assertRaises(DatosInvalidos):
                    self._crear(**campos)
        self.assertFalse(Interesado.objects.exists())
        self.assertFalse(ContactoWhatsapp.objects.exists())

    # AC-T3-81
    def test_si_el_numero_ya_tiene_un_interesado_abierto_devuelve_ese(self):
        primero = self._crear(nombre="Marta", telefono="1155550004")

        segundo = interesados.crear_interesado(
            self.graciela.id, "Otra Persona", "llamado", telefono="+54911 5555 0004"
        )

        self.assertEqual(segundo.pk, primero.pk)
        self.assertEqual(Interesado.objects.count(), 1)
        self.assertEqual(InteresadoHistorial.objects.count(), 1)
        segundo.refresh_from_db()
        self.assertEqual(segundo.nombre, "Marta")  # no se pisa nada

    # AC-T3-81
    def test_un_interesado_perdido_no_impide_uno_nuevo(self):
        primero = self._crear(telefono="1155550005")
        interesados.mover_interesado(
            primero.pk, "perdida", self.diego.id, motivo_perdida="Compró en otra"
        )

        nuevo = self._crear(telefono="1155550005")

        self.assertNotEqual(nuevo.pk, primero.pk)
        self.assertEqual(nuevo.estado, "consulta")

    # AC-T3-81
    def test_si_el_numero_es_de_un_cliente_activo_se_precarga_el_cliente(self):
        cliente = fabricas.crear_cliente(nombre="Laura", apellido="Pérez")
        fabricas.crear_contacto(cliente, numero="+5491155550006")

        interesado = self._crear(nombre="Laura", telefono="1155550006")

        interesado.refresh_from_db()
        self.assertEqual(interesado.cliente_id, cliente.pk)
        self.assertEqual(interesado.estado, "consulta")

    # AC-T3-81
    def test_si_el_cliente_esta_dado_de_baja_no_se_precarga(self):
        cliente = fabricas.crear_cliente(activo=False)
        fabricas.crear_contacto(cliente, numero="+5491155550007")

        self.assertIsNone(self._crear(telefono="1155550007").cliente_id)

    # AC-T3-81
    def test_los_datos_iniciales_se_normalizan_y_validan(self):
        interesado = self._crear(
            datos={"patente": "ab 123 cd", "dni": "30.111.222", "marca": " Toyota ", "modelo": None}
        )
        interesado.refresh_from_db()
        self.assertEqual(
            interesado.datos, {"patente": "AB123CD", "dni": "30111222", "marca": "Toyota"}
        )

        for datos in ({"patente": "xx"}, {"dni": "12"}, {"marca": ["a"]}, "texto", {"anio": 1800}):
            with self.subTest(datos=datos):
                with self.assertRaises(DatosInvalidos):
                    self._crear(datos=datos)

    # AC-T3-81
    def test_un_funcionario_inactivo_o_inexistente_no_puede_crear(self):
        inactivo = fabricas.crear_funcionario("Inactivo", activo=False)
        for funcionario_id in (inactivo.id, 0):
            with self.subTest(funcionario_id=funcionario_id):
                with self.assertRaises(PermisoDenegado):
                    interesados.crear_interesado(funcionario_id, "Marta", "web")


class MoverInteresadoTests(BaseInteresadosTests):
    # AC-T3-82
    def test_recorre_el_embudo_una_etapa_por_vez_y_deja_el_historial(self):
        interesado = self._crear(telefono="1155550010")
        antes = interesado.actualizado_en

        # Reloj controlado: dos llamadas rápidas pueden tener la misma marca
        # temporal en Windows, sin que eso implique un error de persistencia.
        with patch('negocio.interesados.timezone.now', return_value=antes+timedelta(seconds=1)):
            interesados.mover_interesado(interesado.pk, "cotizando", self.diego.id, nota="Pidió precio")
            interesados.mover_interesado(interesado.pk, "documentacion", self.graciela.id)
        # Emitir exige cliente y póliza: se prueba aparte.

        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "documentacion")
        self.assertGreater(interesado.actualizado_en, antes)
        lineas = [
            (h.estado_anterior, h.estado_nuevo, h.nota, h.funcionario_id)
            for h in interesado.historial.order_by("id")
        ]
        self.assertEqual(
            lineas,
            [
                (None, "consulta", "Alta del interesado (origen: Web).", self.diego.id),
                ("consulta", "cotizando", "Pidió precio", self.diego.id),
                ("cotizando", "documentacion", "", self.graciela.id),
            ],
        )

    # AC-T3-82
    def test_saltear_una_etapa_es_estado_invalido(self):
        interesado = self._crear()
        for destino in ("documentacion", "emitida", "consulta"):
            with self.subTest(desde="consulta", destino=destino):
                with self.assertRaises(EstadoInvalido):
                    interesados.mover_interesado(interesado.pk, destino, self.diego.id)

        self._en(interesado, "cotizando")
        for destino in ("emitida", "cotizando"):
            with self.subTest(desde="cotizando", destino=destino):
                with self.assertRaises(EstadoInvalido):
                    interesados.mover_interesado(interesado.pk, destino, self.diego.id)
        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "cotizando")

    # AC-T3-82
    def test_se_puede_volver_una_etapa_atras_pero_no_dos(self):
        interesado = self._crear()
        self._en(interesado, "cotizando", "documentacion")

        with self.assertRaises(EstadoInvalido):
            interesados.mover_interesado(interesado.pk, "consulta", self.diego.id)  # dos atrás
        interesados.mover_interesado(
            interesado.pk, "cotizando", self.diego.id, nota="Pidió otra cotización"
        )
        interesados.mover_interesado(interesado.pk, "consulta", self.diego.id)

        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "consulta")
        lineas = [(h.estado_anterior, h.estado_nuevo) for h in interesado.historial.order_by("id")]
        self.assertEqual(
            lineas[-2:], [("documentacion", "cotizando"), ("cotizando", "consulta")]
        )
        # Y se vuelve a avanzar con normalidad.
        interesados.mover_interesado(interesado.pk, "cotizando", self.diego.id)

    # AC-T3-82
    def test_volver_atras_conserva_el_cliente_ya_convertido(self):
        interesado = self._crear(telefono="1155550013")
        self._en(interesado, "cotizando", "documentacion")
        interesados.convertir_en_cliente(
            interesado.pk, self.graciela.id, "30111222", "Marta", "Gómez"
        )

        interesados.mover_interesado(interesado.pk, "cotizando", self.diego.id)

        interesado.refresh_from_db()
        self.assertIsNotNone(interesado.cliente_id)

    # AC-T3-82
    def test_una_etapa_que_no_existe_o_un_interesado_que_no_existe(self):
        interesado = self._crear()
        with self.assertRaises(DatosInvalidos):
            interesados.mover_interesado(interesado.pk, "volando", self.diego.id)
        with self.assertRaises(NoEncontrado):
            interesados.mover_interesado(0, "cotizando", self.diego.id)

    # AC-T3-82
    def test_perdida_exige_un_motivo_de_tres_o_mas_caracteres(self):
        interesado = self._crear()
        for motivo in (None, "", "  ", "ab", "  ab  "):
            with self.subTest(motivo=motivo):
                with self.assertRaises(DatosInvalidos):
                    interesados.mover_interesado(
                        interesado.pk, "perdida", self.diego.id, motivo_perdida=motivo
                    )
        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "consulta")

        interesados.mover_interesado(
            interesado.pk, "perdida", self.diego.id, motivo_perdida="  Se fue  con otra ", nota="Llamar en marzo"
        )
        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "perdida")
        self.assertEqual(interesado.motivo_perdida, "Se fue con otra")
        ultimo = interesado.historial.order_by("-id").first()
        self.assertEqual(ultimo.nota, "Motivo: Se fue con otra. Llamar en marzo")

    # AC-T3-82
    def test_se_puede_perder_desde_cualquier_etapa_abierta(self):
        for etapas in ((), ("cotizando",), ("cotizando", "documentacion")):
            with self.subTest(etapas=etapas):
                interesado = self._en(self._crear(), *etapas)
                interesados.mover_interesado(
                    interesado.pk, "perdida", self.diego.id, motivo_perdida="Muy caro"
                )
                interesado.refresh_from_db()
                self.assertEqual(interesado.estado, "perdida")

    # AC-T3-82
    def test_de_perdida_se_vuelve_a_consulta_y_se_limpia_el_motivo(self):
        interesado = self._crear()
        self._en(interesado, "cotizando")
        interesados.mover_interesado(
            interesado.pk, "perdida", self.diego.id, motivo_perdida="Muy caro"
        )
        for destino in ("cotizando", "documentacion", "emitida", "perdida"):
            with self.subTest(destino=destino):
                with self.assertRaises(EstadoInvalido):
                    interesados.mover_interesado(
                        interesado.pk, destino, self.diego.id, motivo_perdida="Otra vez"
                    )

        interesados.mover_interesado(interesado.pk, "consulta", self.diego.id)

        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "consulta")
        self.assertIsNone(interesado.motivo_perdida)

    # AC-T3-82
    def test_no_se_reabre_si_el_numero_ya_tiene_otro_interesado_abierto(self):
        viejo = self._crear(telefono="1155550011")
        interesados.mover_interesado(
            viejo.pk, "perdida", self.diego.id, motivo_perdida="No contestó"
        )
        self._crear(telefono="1155550011")  # el mismo número, de nuevo en el embudo

        with self.assertRaises(EstadoInvalido):
            interesados.mover_interesado(viejo.pk, "consulta", self.diego.id)
        viejo.refresh_from_db()
        self.assertEqual(viejo.estado, "perdida")

    # AC-T3-82
    def test_emitida_exige_cliente_y_una_poliza_creada_despues_del_interesado(self):
        interesado = self._crear(telefono="1155550012")
        self._en(interesado, "cotizando", "documentacion")

        # Sin cliente.
        with self.assertRaises(EstadoInvalido):
            interesados.mover_interesado(interesado.pk, "emitida", self.diego.id)

        # Con cliente pero sin ninguna póliza.
        cliente = fabricas.crear_cliente()
        Interesado.objects.filter(pk=interesado.pk).update(cliente=cliente)
        with self.assertRaises(EstadoInvalido):
            interesados.mover_interesado(interesado.pk, "emitida", self.diego.id)

        # Con una póliza **anterior** al interesado (ya la tenía): tampoco.
        fabricas.crear_poliza(
            cliente, creado_en=interesado.creado_en - timedelta(days=30)
        )
        with self.assertRaises(EstadoInvalido):
            interesados.mover_interesado(interesado.pk, "emitida", self.diego.id)
        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "documentacion")

        # Con una póliza nueva, sí.
        fabricas.crear_poliza(cliente)
        interesados.mover_interesado(interesado.pk, "emitida", self.diego.id)
        interesado.refresh_from_db()
        self.assertEqual(interesado.estado, "emitida")

    # AC-T3-82
    def test_emitida_es_final(self):
        interesado = self._crear()
        cliente = fabricas.crear_cliente()
        self._en(interesado, "cotizando", "documentacion")
        Interesado.objects.filter(pk=interesado.pk).update(cliente=cliente)
        fabricas.crear_poliza(cliente)
        interesados.mover_interesado(interesado.pk, "emitida", self.diego.id)

        for destino in ("consulta", "cotizando", "documentacion", "perdida", "emitida"):
            with self.subTest(destino=destino):
                with self.assertRaises(EstadoInvalido):
                    interesados.mover_interesado(
                        interesado.pk, destino, self.graciela.id, motivo_perdida="Muy caro"
                    )

    # AC-T3-82
    def test_cualquier_funcionario_activo_puede_mover_y_uno_inactivo_no(self):
        interesado = self._crear()
        interesados.mover_interesado(interesado.pk, "cotizando", self.diego.id)  # operador

        inactivo = fabricas.crear_funcionario("Baja", activo=False)
        with self.assertRaises(PermisoDenegado):
            interesados.mover_interesado(interesado.pk, "documentacion", inactivo.id)
        with self.assertRaises(PermisoDenegado):
            interesados.mover_interesado(interesado.pk, "documentacion", 0)


class ConvertirEnClienteTests(BaseInteresadosTests):
    def _en_documentacion(self, **campos):
        interesado = self._crear(**campos)
        return self._en(interesado, "cotizando", "documentacion")

    # AC-T3-83
    def test_da_de_alta_al_cliente_adoptando_el_contacto_que_ya_existe(self):
        contacto = fabricas.crear_contacto(numero="+5491155550020")
        interesado = self._en_documentacion(telefono="1155550020")
        self.assertEqual(interesado.contacto_id, contacto.pk)

        resultado = interesados.convertir_en_cliente(
            interesado.pk, self.graciela.id, "30.111.222", "Marta", "Gómez", "marta@correo.com"
        )

        resultado.refresh_from_db()
        cliente = Cliente.objects.get(dni="30111222")
        self.assertEqual((cliente.nombre, cliente.apellido, cliente.email), ("Marta", "Gómez", "marta@correo.com"))
        self.assertEqual(resultado.cliente_id, cliente.pk)
        contacto.refresh_from_db()
        self.assertEqual(contacto.cliente_id, cliente.pk)
        self.assertEqual(ContactoWhatsapp.objects.filter(numero="+5491155550020").count(), 1)
        self.assertEqual(resultado.datos["dni"], "30111222")
        # No cambia de etapa: pasar a emitida es `mover_interesado`.
        self.assertEqual(resultado.estado, "documentacion")
        self.assertIn("Convertido en cliente", interesado.historial.order_by("-id").first().nota)

    # AC-T3-83
    def test_si_ya_existe_un_cliente_con_ese_dni_lo_reutiliza(self):
        existente = fabricas.crear_cliente(dni="30111222", nombre="Marta", apellido="Gómez")
        interesado = self._en_documentacion(telefono="1155550021")

        resultado = interesados.convertir_en_cliente(
            interesado.pk, self.graciela.id, "30111222", "Otro Nombre", "Otro Apellido"
        )

        resultado.refresh_from_db()
        self.assertEqual(resultado.cliente_id, existente.pk)
        self.assertEqual(Cliente.objects.filter(dni="30111222").count(), 1)
        existente.refresh_from_db()
        self.assertEqual(existente.nombre, "Marta")  # no se pisa
        # Su WhatsApp, que estaba libre, pasa a ser del cliente: así el bot lo reconoce.
        self.assertEqual(resultado.contacto.cliente_id, existente.pk)

    # AC-T3-83
    def test_un_operador_no_puede_convertir(self):
        interesado = self._en_documentacion(telefono="1155550022")

        with self.assertRaises(PermisoDenegado):
            interesados.convertir_en_cliente(interesado.pk, self.diego.id, "30111222", "Marta", "Gómez")

        interesado.refresh_from_db()
        self.assertIsNone(interesado.cliente_id)
        self.assertFalse(Cliente.objects.filter(dni="30111222").exists())

    # AC-T3-83
    def test_solo_se_convierte_en_documentacion(self):
        for etapas in ((), ("cotizando",)):
            with self.subTest(etapas=etapas):
                interesado = self._en(self._crear(), *etapas)
                with self.assertRaises(EstadoInvalido):
                    interesados.convertir_en_cliente(
                        interesado.pk, self.graciela.id, "30111222", "Marta", "Gómez"
                    )
        with self.assertRaises(NoEncontrado):
            interesados.convertir_en_cliente(0, self.graciela.id, "30111222", "Marta", "Gómez")

    # AC-T3-83
    def test_un_dni_o_nombre_invalidos_no_dejan_nada_a_medias(self):
        interesado = self._en_documentacion(telefono="1155550023")
        for dni, nombre in (("12", "Marta"), ("30111222", ""), ("30111222", "Mar7a")):
            with self.subTest(dni=dni, nombre=nombre):
                with self.assertRaises(DatosInvalidos):
                    interesados.convertir_en_cliente(
                        interesado.pk, self.graciela.id, dni, nombre, "Gómez"
                    )
        interesado.refresh_from_db()
        self.assertIsNone(interesado.cliente_id)
        self.assertFalse(Cliente.objects.exists())

    # AC-T3-83
    def test_sin_whatsapp_hace_falta_un_telefono_para_el_alta(self):
        interesado = self._en_documentacion()  # cargado a mano, sin teléfono
        with self.assertRaises(DatosInvalidos):
            interesados.convertir_en_cliente(
                interesado.pk, self.graciela.id, "30111222", "Marta", "Gómez"
            )

        resultado = interesados.convertir_en_cliente(
            interesado.pk, self.graciela.id, "30111222", "Marta", "Gómez", telefono="1155550024"
        )
        resultado.refresh_from_db()
        self.assertEqual(resultado.contacto.numero, "+5491155550024")
        self.assertEqual(resultado.contacto.cliente_id, resultado.cliente_id)

    # AC-T3-83
    def test_el_whatsapp_de_otro_cliente_no_se_pisa(self):
        otro = fabricas.crear_cliente()
        fabricas.crear_contacto(otro, numero="+5491155550025")
        interesado = self._en_documentacion(telefono="1155550025")
        reutilizado = fabricas.crear_cliente(dni="30111222")

        with self.assertRaises(DatosInvalidos):
            interesados.convertir_en_cliente(
                interesado.pk, self.graciela.id, "30111222", "Marta", "Gómez"
            )
        with self.assertRaises(DatosInvalidos):
            interesados.convertir_en_cliente(
                interesado.pk, self.graciela.id, "30999888", "Marta", "Gómez"
            )
        interesado.refresh_from_db()
        # Sigue como estaba: venta cruzada con el cliente dueño de ese WhatsApp.
        self.assertEqual(interesado.cliente_id, otro.pk)
        self.assertEqual(interesado.contacto.cliente_id, otro.pk)
        self.assertNotEqual(interesado.contacto.cliente_id, reutilizado.pk)
        self.assertEqual(Cliente.objects.filter(dni="30999888").count(), 0)


class GestionDelInteresadoTests(BaseInteresadosTests):
    # AC-T3-84
    def test_asignar_cambia_el_responsable_y_registra_quien_y_cuando(self):
        interesado = self._crear()
        antes = interesado.actualizado_en

        with patch('negocio.interesados.timezone.now', return_value=antes+timedelta(seconds=1)):
            interesados.asignar_interesado(interesado.pk, self.graciela.id, self.diego.id)

        interesado.refresh_from_db()
        self.assertEqual(interesado.responsable_id, self.graciela.id)
        self.assertGreater(interesado.actualizado_en, antes)
        linea = interesado.historial.order_by("-id").first()
        self.assertEqual(linea.nota, "Asignado a Graciela.")
        self.assertEqual(linea.funcionario_id, self.diego.id)
        self.assertEqual((linea.estado_anterior, linea.estado_nuevo), ("consulta", "consulta"))
        self.assertIsNotNone(linea.fecha)

    # AC-T3-84
    def test_no_se_asigna_a_un_funcionario_inactivo_ni_inexistente(self):
        interesado = self._crear()
        inactivo = fabricas.crear_funcionario("Baja", activo=False)
        for responsable_id in (inactivo.id, 0):
            with self.subTest(responsable_id=responsable_id):
                with self.assertRaises(DatosInvalidos):
                    interesados.asignar_interesado(interesado.pk, responsable_id, self.diego.id)
        interesado.refresh_from_db()
        self.assertEqual(interesado.responsable_id, self.diego.id)

        with self.assertRaises(PermisoDenegado):
            interesados.asignar_interesado(interesado.pk, self.graciela.id, inactivo.id)
        with self.assertRaises(NoEncontrado):
            interesados.asignar_interesado(0, self.graciela.id, self.diego.id)

    # AC-T3-84
    def test_programar_contacto_acepta_hoy_o_futuro_y_vacio_lo_borra(self):
        interesado = self._crear()
        hoy = timezone.localdate()

        for fecha in (hoy, hoy + timedelta(days=3), (hoy + timedelta(days=9)).isoformat()):
            with self.subTest(fecha=fecha):
                interesados.programar_contacto(interesado.pk, fecha, self.diego.id)
                interesado.refresh_from_db()
                self.assertEqual(
                    interesado.proximo_contacto,
                    fecha if isinstance(fecha, date) else date.fromisoformat(fecha),
                )

        linea = interesado.historial.order_by("-id").first()
        self.assertTrue(linea.nota.startswith("Próximo contacto: "))
        self.assertEqual(linea.funcionario_id, self.diego.id)

        for vacio in (None, "", "  "):
            with self.subTest(vacio=vacio):
                interesados.programar_contacto(interesado.pk, hoy, self.diego.id)
                interesados.programar_contacto(interesado.pk, vacio, self.diego.id)
                interesado.refresh_from_db()
                self.assertIsNone(interesado.proximo_contacto)
        self.assertEqual(
            interesado.historial.order_by("-id").first().nota, "Se quitó el próximo contacto."
        )

    # AC-T3-84
    def test_programar_contacto_rechaza_el_pasado_y_lo_que_no_es_una_fecha(self):
        interesado = self._crear()
        ayer = timezone.localdate() - timedelta(days=1)
        for fecha in (ayer, ayer.isoformat(), "mañana", "31/12/2030", 5):
            with self.subTest(fecha=fecha):
                with self.assertRaises(DatosInvalidos):
                    interesados.programar_contacto(interesado.pk, fecha, self.diego.id)
        interesado.refresh_from_db()
        self.assertIsNone(interesado.proximo_contacto)

    # AC-T3-84
    def test_actualizar_datos_mezcla_con_lo_existente_y_normaliza(self):
        interesado = self._crear(datos={"marca": "Toyota", "localidad": "Rosario"})

        interesados.actualizar_datos_interesado(
            interesado.pk,
            {"patente": "ab-123-cd", "dni": "30.111.222", "localidad": "Santa Fe", "anio": "2020", "uso": "Particular"},
            self.diego.id,
        )

        interesado.refresh_from_db()
        self.assertEqual(
            interesado.datos,
            {
                "marca": "Toyota",
                "localidad": "Santa Fe",
                "patente": "AB123CD",
                "dni": "30111222",
                "anio": 2020,
                "uso": "particular",
            },
        )
        linea = interesado.historial.order_by("-id").first()
        self.assertEqual(linea.nota, "Datos actualizados: anio, dni, localidad, patente, uso.")
        self.assertEqual(linea.funcionario_id, self.diego.id)

    # AC-T3-84
    def test_un_dato_vacio_borra_la_clave_y_uno_invalido_no_cambia_nada(self):
        interesado = self._crear(datos={"marca": "Toyota", "patente": "AB123CD"})

        interesados.actualizar_datos_interesado(
            interesado.pk, {"marca": "", "modelo": "Corolla"}, self.diego.id
        )
        interesado.refresh_from_db()
        self.assertEqual(interesado.datos, {"patente": "AB123CD", "modelo": "Corolla"})

        for datos in ({"patente": "mala"}, {"dni": "1"}, {"anio": "dos mil"}, {"uso": "volador"}, {"x": {"a": 1}}, {"Mal Nombre": "x"}):
            with self.subTest(datos=datos):
                with self.assertRaises(DatosInvalidos):
                    interesados.actualizar_datos_interesado(interesado.pk, datos, self.diego.id)
        interesado.refresh_from_db()
        self.assertEqual(interesado.datos, {"patente": "AB123CD", "modelo": "Corolla"})

    # AC-T3-84
    def test_los_tres_los_puede_hacer_cualquier_funcionario_activo(self):
        interesado = self._crear()
        hoy = timezone.localdate()
        # Diego es operador.
        interesados.asignar_interesado(interesado.pk, self.diego.id, self.diego.id)
        interesados.programar_contacto(interesado.pk, hoy, self.diego.id)
        interesados.actualizar_datos_interesado(interesado.pk, {"marca": "Fiat"}, self.diego.id)

        inactivo = fabricas.crear_funcionario("Baja", activo=False)
        with self.assertRaises(PermisoDenegado):
            interesados.programar_contacto(interesado.pk, hoy, inactivo.id)
        with self.assertRaises(PermisoDenegado):
            interesados.actualizar_datos_interesado(interesado.pk, {"marca": "Fiat"}, inactivo.id)


class SeguimientoDeCotizacionesTests(BaseInteresadosTests):
    HOY = date(2026, 11, 20)

    def _cotizando(self, dias: int, *, telefono="1155550030", **campos):
        """Un interesado que entró a «cotizando» hace `dias` días (al mediodía)."""
        interesado = self._crear(telefono=telefono, **campos)
        interesados.mover_interesado(interesado.pk, "cotizando", self.diego.id)
        entrada = datetime(2026, 11, 20, 15, 0, tzinfo=tz.utc) - timedelta(days=dias)
        InteresadoHistorial.objects.filter(
            interesado=interesado, estado_nuevo="cotizando"
        ).update(fecha=entrada)
        return interesado

    # AC-T3-86
    def test_a_los_dos_dias_programa_el_primer_seguimiento_para_el_responsable(self):
        interesado = self._cotizando(2)

        avisos = interesados.seguimiento_interesados(self.HOY)

        self.assertEqual(
            avisos,
            [
                {
                    "tipo": "seguimiento_cotizacion_2d",
                    "contacto_id": interesado.contacto_id,
                    "referencia": f"interesado:{interesado.pk}:2d:2026-11-18",
                    "datos": {"interesado_id": interesado.pk},
                    "asignado_a_id": self.diego.id,
                }
            ],
        )

    # AC-T3-86
    def test_a_los_cinco_dias_el_segundo_y_antes_de_los_dos_ninguno(self):
        uno = self._cotizando(1, telefono="1155550031")
        cinco = self._cotizando(5, telefono="1155550032")

        avisos = interesados.seguimiento_interesados(self.HOY)

        self.assertEqual([(a["tipo"], a["datos"]["interesado_id"]) for a in avisos],
                         [("seguimiento_cotizacion_5d", cinco.pk)])
        self.assertEqual(avisos[0]["referencia"], f"interesado:{cinco.pk}:5d:2026-11-15")
        self.assertNotIn(uno.pk, [a["datos"]["interesado_id"] for a in avisos])

    # AC-T3-86
    def test_si_un_dia_no_corrio_el_aviso_se_genera_igual_hasta_que_caduca(self):
        for dias, tipo in ((3, "seguimiento_cotizacion_2d"), (4, "seguimiento_cotizacion_2d"),
                           (6, "seguimiento_cotizacion_5d"), (11, "seguimiento_cotizacion_5d")):
            with self.subTest(dias=dias):
                interesado = self._cotizando(dias, telefono=f"11555500{40 + dias}")
                avisos = [
                    a for a in interesados.seguimiento_interesados(self.HOY)
                    if a["datos"]["interesado_id"] == interesado.pk
                ]
                self.assertEqual([a["tipo"] for a in avisos], [tipo])
        # A los 12 días ya no sirve: el de 5 días caducó.
        viejo = self._cotizando(12, telefono="1155550060")
        self.assertNotIn(
            viejo.pk,
            [a["datos"]["interesado_id"] for a in interesados.seguimiento_interesados(self.HOY)],
        )

    # AC-T3-86
    def test_la_referencia_no_cambia_entre_corridas(self):
        self._cotizando(2)
        primera = interesados.seguimiento_interesados(self.HOY)
        segunda = interesados.seguimiento_interesados(self.HOY)
        self.assertEqual(primera, segunda)
        self.assertEqual(len(primera), 1)

    # AC-T3-86
    def test_si_el_contacto_escribio_despues_de_entrar_a_cotizando_no_se_programa_nada(self):
        escribio = self._cotizando(3, telefono="1155550033")
        conversacion = fabricas.crear_conversacion(escribio.contacto)
        fabricas.crear_mensaje(
            conversacion, fecha_hora=datetime(2026, 11, 19, 12, 0, tzinfo=tz.utc)
        )
        # Escribió **antes** de entrar a cotizando: sigue valiendo el seguimiento.
        no_escribio = self._cotizando(3, telefono="1155550034")
        otra = fabricas.crear_conversacion(no_escribio.contacto)
        fabricas.crear_mensaje(otra, fecha_hora=datetime(2026, 11, 1, 12, 0, tzinfo=tz.utc))
        # Un mensaje del bot o de un funcionario después tampoco cuenta como respuesta del cliente.
        fabricas.crear_mensaje(
            otra, direccion="saliente", emisor="bot", estado_envio="enviado",
            fecha_hora=datetime(2026, 11, 19, 12, 0, tzinfo=tz.utc),
        )

        ids = [a["datos"]["interesado_id"] for a in interesados.seguimiento_interesados(self.HOY)]

        self.assertEqual(ids, [no_escribio.pk])

    # AC-T3-86
    def test_solo_los_que_estan_en_cotizando_y_tienen_whatsapp(self):
        en_consulta = self._crear(telefono="1155550035")
        en_documentacion = self._cotizando(3, telefono="1155550036")
        interesados.mover_interesado(en_documentacion.pk, "documentacion", self.diego.id)
        perdido = self._cotizando(3, telefono="1155550037")
        interesados.mover_interesado(perdido.pk, "perdida", self.diego.id, motivo_perdida="Muy caro")
        sin_whatsapp = self._cotizando(3, telefono=None)
        con_whatsapp = self._cotizando(3, telefono="1155550038")

        ids = {a["datos"]["interesado_id"] for a in interesados.seguimiento_interesados(self.HOY)}

        self.assertEqual(ids, {con_whatsapp.pk})
        self.assertNotIn(en_consulta.pk, ids)
        self.assertNotIn(sin_whatsapp.pk, ids)

    # AC-T3-86
    def test_volver_a_cotizando_abre_un_seguimiento_nuevo(self):
        interesado = self._cotizando(8, telefono="1155550039")
        # Se perdió y se reabrió: entra de nuevo a cotizando hace 2 días.
        interesados.mover_interesado(interesado.pk, "perdida", self.diego.id, motivo_perdida="Muy caro")
        interesados.mover_interesado(interesado.pk, "consulta", self.diego.id)
        interesados.mover_interesado(interesado.pk, "cotizando", self.diego.id)
        nueva_entrada = datetime(2026, 11, 20, 15, 0, tzinfo=tz.utc) - timedelta(days=2)
        InteresadoHistorial.objects.filter(
            interesado=interesado, estado_nuevo="cotizando", estado_anterior="consulta"
        ).update(fecha=nueva_entrada)

        avisos = interesados.seguimiento_interesados(self.HOY)

        self.assertEqual([a["tipo"] for a in avisos], ["seguimiento_cotizacion_2d"])
        self.assertTrue(avisos[0]["referencia"].endswith(":2d:2026-11-18"))

    # AC-T3-86
    def test_las_gestiones_en_cotizando_no_reinician_la_cuenta(self):
        interesado = self._cotizando(2, telefono="1155550041")
        # Asignar o cargar datos deja líneas en la etapa actual (cotizando → cotizando).
        interesados.asignar_interesado(interesado.pk, self.graciela.id, self.diego.id)
        interesados.actualizar_datos_interesado(interesado.pk, {"marca": "Fiat"}, self.diego.id)

        avisos = interesados.seguimiento_interesados(self.HOY)

        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0]["referencia"], f"interesado:{interesado.pk}:2d:2026-11-18")
        self.assertEqual(avisos[0]["asignado_a_id"], self.graciela.id)

    # AC-T3-86
    def test_el_texto_del_aviso_lleva_el_nombre_de_la_base(self):
        interesado = self._cotizando(2, nombre="Marta")

        texto, verificados = interesados.texto_seguimiento_cotizacion(
            {"interesado_id": interesado.pk}
        )

        self.assertEqual(
            texto,
            "Hola Marta, ¿pudiste ver la cotización que te pasamos? "
            "Si tenés dudas o querés ajustar algo, contanos.",
        )
        self.assertEqual(verificados, frozenset())
        with self.assertRaises(NoEncontrado):
            interesados.texto_seguimiento_cotizacion({"interesado_id": 0})

    # AC-T3-86
    def test_sin_nombre_propio_no_se_saluda_por_el_numero(self):
        interesado = self._cotizando(2, nombre="+5491155550099", telefono="1155550099")

        texto, _ = interesados.texto_seguimiento_cotizacion({"interesado_id": interesado.pk})

        self.assertTrue(texto.startswith("Hola, ¿pudiste ver la cotización"))
        self.assertNotIn("+549", texto)
