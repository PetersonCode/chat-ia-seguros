from datetime import date, datetime, timedelta, timezone as tz
from pathlib import Path

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import DO_NOTHING
from django.test import SimpleTestCase, TestCase

from datos import fabricas, models, selectors

SQL_17 = Path(settings.BASE_DIR) / "SDD" / "sql" / "17_interesados.sql"
HOY = date(2026, 11, 4)


def _sin_transaccion(sql: str) -> str:
    """El SQL sin su BEGIN/COMMIT, para correrlo dentro de la transacción del test."""
    return "\n".join(
        linea for linea in sql.splitlines() if linea.strip() not in ("BEGIN;", "COMMIT;")
    )


class ModeloInteresadosTests(SimpleTestCase):
    # AC-T4-38
    def test_modelos_no_administrados_y_relaciones(self):
        for modelo, tabla in (
            (models.Interesado, "interesados"),
            (models.InteresadoHistorial, "interesado_historial"),
            (models.Cotizacion, "cotizaciones"),
        ):
            with self.subTest(modelo=modelo.__name__):
                self.assertFalse(modelo._meta.managed)
                self.assertEqual(modelo._meta.db_table, tabla)

        relaciones = (
            (models.Interesado, "contacto", models.ContactoWhatsapp, "interesados", True),
            (models.Interesado, "cliente", models.Cliente, "interesados", True),
            (models.Interesado, "responsable", models.Funcionario, "interesados", True),
            (models.InteresadoHistorial, "interesado", models.Interesado, "historial", False),
            (models.InteresadoHistorial, "funcionario", models.Funcionario, "+", True),
            (models.Cotizacion, "interesado", models.Interesado, "cotizaciones", True),
            (models.Cotizacion, "poliza", models.Poliza, "cotizaciones", True),
            (models.Cotizacion, "compania", models.Compania, "cotizaciones", False),
            (models.Cotizacion, "creada_por", models.Funcionario, "+", False),
        )
        for modelo, campo, destino, related_name, nulo in relaciones:
            with self.subTest(modelo=modelo.__name__, campo=campo):
                fk = modelo._meta.get_field(campo)
                self.assertIs(fk.remote_field.model, destino)
                self.assertEqual(fk.remote_field.related_name, related_name)
                self.assertIs(fk.remote_field.on_delete, DO_NOTHING)
                self.assertEqual(fk.null, nulo)

    # AC-T4-38
    def test_los_textchoices_tienen_los_valores_del_esquema(self):
        self.assertEqual(
            models.EstadoInteresado.values,
            ["consulta", "cotizando", "documentacion", "emitida", "perdida"],
        )
        self.assertEqual(
            models.OrigenInteresado.values,
            ["whatsapp", "instagram", "facebook", "web", "recomendacion", "llamado", "otro"],
        )
        self.assertEqual(models.Cobertura.values, ["basica", "intermedia", "total"])


class SqlInteresadosTests(TestCase):
    # AC-T4-38
    def test_el_sql_17_puede_aplicarse_dos_veces_seguidas(self):
        cuerpo = _sin_transaccion(SQL_17.read_text(encoding="utf-8"))
        with connection.cursor() as cursor:
            cursor.execute(cuerpo)
            cursor.execute(cuerpo)

    # AC-T4-38
    def test_el_sql_17_esta_en_la_lista_del_test_runner(self):
        fuente = (Path(settings.BASE_DIR) / "config" / "test_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"17_interesados.sql"', fuente)

    # AC-T4-38
    def test_el_sql_17_suma_los_tipos_de_aviso_solo_si_existe_el_catalogo(self):
        cuerpo = _sin_transaccion(SQL_17.read_text(encoding="utf-8"))
        with connection.cursor() as cursor:
            # Sin el motor de avisos (P2) aplicado no hay nada que insertar, y no falla.
            cursor.execute("SELECT to_regclass('tipos_aviso')")
            self.assertIsNone(cursor.fetchone()[0])

            cursor.execute(
                "CREATE TABLE tipos_aviso (codigo text PRIMARY KEY, nombre text NOT NULL, "
                "prioridad smallint NOT NULL, activo boolean NOT NULL DEFAULT true)"
            )
            cursor.execute(cuerpo)
            cursor.execute(cuerpo)
            cursor.execute("SELECT codigo, activo FROM tipos_aviso ORDER BY codigo")
            self.assertEqual(
                cursor.fetchall(),
                [("seguimiento_cotizacion_2d", True), ("seguimiento_cotizacion_5d", True)],
            )

    # AC-T4-38
    def test_una_cotizacion_sin_interesado_ni_poliza_o_con_las_dos_la_rechaza_la_base(self):
        compania = fabricas.crear_compania()
        funcionario = fabricas.crear_funcionario("Cotizador")
        interesado = fabricas.crear_interesado()
        poliza = fabricas.crear_poliza()

        sql = (
            "INSERT INTO cotizaciones (interesado_id, poliza_id, compania_id, cobertura, "
            "prima_mensual, creada_por_id) VALUES (%s, %s, %s, 'total', 100, %s)"
        )
        for interesado_id, poliza_id in ((None, None), (interesado.pk, poliza.pk)):
            with self.subTest(interesado=interesado_id, poliza=poliza_id):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            sql, [interesado_id, poliza_id, compania.pk, funcionario.pk]
                        )

        # Una o la otra, sí.
        with connection.cursor() as cursor:
            cursor.execute(sql, [interesado.pk, None, compania.pk, funcionario.pk])
            cursor.execute(sql, [None, poliza.pk, compania.pk, funcionario.pk])

    # AC-T4-38
    def test_la_base_hace_cumplir_las_reglas_del_interesado(self):
        cliente = fabricas.crear_cliente()
        invalidos = (
            {"nombre": "   "},
            {"origen": "paloma_mensajera"},
            {"estado": "dormido"},
            {"estado": "perdida"},  # sin motivo
            {"estado": "perdida", "motivo_perdida": "  a "},  # menos de 3 caracteres
            {"estado": "emitida"},  # sin cliente
            {"datos": []},  # tiene que ser un objeto
        )
        for campos in invalidos:
            with self.subTest(campos=campos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    fabricas.crear_interesado(**campos)

        perdido = fabricas.crear_interesado(estado="perdida", motivo_perdida="Se fue con otra")
        emitido = fabricas.crear_interesado(estado="emitida", cliente=cliente)
        for interesado in (perdido, emitido):
            interesado.refresh_from_db()
            self.assertEqual(interesado.datos, {})

    # AC-T4-38
    def test_un_contacto_tiene_a_lo_sumo_un_interesado_abierto(self):
        contacto = fabricas.crear_contacto()
        fabricas.crear_interesado(contacto=contacto)
        with self.assertRaises(IntegrityError), transaction.atomic():
            fabricas.crear_interesado(contacto=contacto, estado="cotizando")

        # Los cerrados no cuentan: se puede tener un historial de intentos.
        fabricas.crear_interesado(contacto=contacto, estado="perdida", motivo_perdida="No contestó")
        fabricas.crear_interesado(
            contacto=contacto, estado="emitida", cliente=fabricas.crear_cliente()
        )
        # Y sin contacto no hay límite.
        fabricas.crear_interesado()
        fabricas.crear_interesado()

    # AC-T4-38
    def test_una_sola_cotizacion_elegida_por_interesado_y_por_poliza(self):
        interesado = fabricas.crear_interesado()
        poliza = fabricas.crear_poliza()
        for destino in ({"interesado": interesado}, {"poliza": poliza}):
            with self.subTest(destino=list(destino)):
                fabricas.crear_cotizacion(**destino, elegida=True)
                fabricas.crear_cotizacion(**destino)  # no elegida: puede haber las que sean
                with self.assertRaises(IntegrityError), transaction.atomic():
                    fabricas.crear_cotizacion(**destino, elegida=True)

        # Otra póliza o interesado tiene su propia elegida.
        fabricas.crear_cotizacion(interesado=fabricas.crear_interesado(), elegida=True)

    # AC-T4-38
    def test_la_base_hace_cumplir_prima_y_cobertura(self):
        interesado = fabricas.crear_interesado()
        for campos in (
            {"prima_mensual": 0},
            {"prima_mensual": -5},
            {"cobertura": "premium"},
        ):
            with self.subTest(campos=campos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    fabricas.crear_cotizacion(interesado, **campos)

    # AC-T4-38
    def test_las_fabricas_crean_objetos_validos_y_distintos(self):
        interesados = [fabricas.crear_interesado() for _ in range(3)]
        self.assertEqual(len({i.apellido for i in interesados}), 3)
        for interesado in interesados:
            interesado.refresh_from_db()
            self.assertEqual(interesado.estado, "consulta")
            self.assertEqual(interesado.origen, "whatsapp")
            self.assertIsNotNone(interesado.creado_en)
            self.assertIsNotNone(interesado.actualizado_en)

        # Sin destino, la fábrica crea un interesado; con póliza, no.
        sin_destino = fabricas.crear_cotizacion()
        self.assertIsNotNone(sin_destino.interesado_id)
        self.assertIsNone(sin_destino.poliza_id)
        poliza = fabricas.crear_poliza()
        de_poliza = fabricas.crear_cotizacion(poliza=poliza)
        self.assertEqual(de_poliza.poliza_id, poliza.pk)
        self.assertIsNone(de_poliza.interesado_id)
        de_poliza.refresh_from_db()
        self.assertFalse(de_poliza.elegida)
        self.assertEqual(str(de_poliza.prima_mensual), "15000.00")

        historial = models.InteresadoHistorial.objects.create(
            interesado=interesados[0], estado_nuevo="consulta"
        )
        historial.refresh_from_db()
        self.assertIsNone(historial.estado_anterior)
        self.assertIsNotNone(historial.fecha)
        self.assertEqual(list(interesados[0].historial.all()), [historial])


class ConsultasInteresadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fabricas.crear_catalogos()

    def _en(self, interesado, dias_atras: int):
        """Fija `actualizado_en` hace `dias_atras` días (el default es el momento de crearlo)."""
        momento = datetime(2026, 11, 4, 12, 0, tzinfo=tz.utc) - timedelta(days=dias_atras)
        models.Interesado.objects.filter(pk=interesado.pk).update(actualizado_en=momento)
        return interesado

    # AC-T4-39
    def test_listar_interesados_pone_primero_los_de_seguimiento_vencido(self):
        viejo = self._en(fabricas.crear_interesado(), 5)
        nuevo = self._en(fabricas.crear_interesado(), 1)
        vencido_viejo = self._en(
            fabricas.crear_interesado(proximo_contacto=HOY - timedelta(days=3)), 9
        )
        vencido_nuevo = self._en(
            fabricas.crear_interesado(proximo_contacto=HOY - timedelta(days=1)), 2
        )
        para_hoy = self._en(fabricas.crear_interesado(proximo_contacto=HOY), 0)
        futuro = self._en(
            fabricas.crear_interesado(proximo_contacto=HOY + timedelta(days=2)), 7
        )

        orden = list(selectors.listar_interesados(hoy=HOY))

        # Primero los vencidos (el tocado más recientemente antes), después el resto
        # por `actualizado_en` descendente. Uno para hoy todavía no está vencido.
        self.assertEqual(
            orden, [vencido_nuevo, vencido_viejo, para_hoy, nuevo, viejo, futuro]
        )

    # AC-T4-39
    def test_un_interesado_cerrado_no_cuenta_como_vencido(self):
        cliente = fabricas.crear_cliente()
        abierto = fabricas.crear_interesado(proximo_contacto=HOY - timedelta(days=2))
        fabricas.crear_interesado(
            estado="perdida",
            motivo_perdida="Muy caro",
            proximo_contacto=HOY - timedelta(days=2),
        )
        fabricas.crear_interesado(
            estado="emitida", cliente=cliente, proximo_contacto=HOY - timedelta(days=2)
        )

        self.assertEqual(
            list(selectors.listar_interesados(seguimiento_vencido=True, hoy=HOY)), [abierto]
        )

    # AC-T4-39
    def test_listar_interesados_filtra_por_estado_responsable_y_origen(self):
        ana = fabricas.crear_funcionario("Ana")
        beto = fabricas.crear_funcionario("Beto", puede_aprobar=False)
        a = fabricas.crear_interesado(responsable=ana, origen="web")
        b = fabricas.crear_interesado(responsable=beto, origen="web", estado="cotizando")
        c = fabricas.crear_interesado(responsable=ana, origen="llamado", estado="cotizando")
        sin_dueno = fabricas.crear_interesado(origen="instagram")

        def ids(**filtros):
            return {i.pk for i in selectors.listar_interesados(hoy=HOY, **filtros)}

        self.assertEqual(ids(), {a.pk, b.pk, c.pk, sin_dueno.pk})
        self.assertEqual(ids(estado="cotizando"), {b.pk, c.pk})
        self.assertEqual(ids(responsable_id=ana.pk), {a.pk, c.pk})
        self.assertEqual(ids(origen="web"), {a.pk, b.pk})
        self.assertEqual(
            ids(estado="cotizando", responsable_id=ana.pk, origen="llamado"), {c.pk}
        )
        self.assertEqual(ids(estado="emitida"), set())

    # AC-T4-39
    def test_la_busqueda_encuentra_por_nombre_apellido_telefono_y_patente(self):
        contacto = fabricas.crear_contacto(numero="+5491126914442")
        laura = fabricas.crear_interesado(
            nombre="Laura", apellido="Pérez", contacto=contacto,
            datos={"patente": "AB123CD", "marca": "Toyota"},
        )
        otro = fabricas.crear_interesado(
            nombre="Marcos", apellido="Gómez", datos={"patente": "XYZ987"}
        )
        sin_datos = fabricas.crear_interesado(nombre="Pablo", apellido="Ruiz")

        def buscar(q):
            return {i.pk for i in selectors.listar_interesados(q=q, hoy=HOY)}

        self.assertEqual(buscar("laura"), {laura.pk})
        self.assertEqual(buscar("PÉREZ"), {laura.pk})
        self.assertEqual(buscar("laura pérez"), {laura.pk})  # nombre y apellido juntos
        self.assertEqual(buscar("2691"), {laura.pk})  # parte del teléfono
        self.assertEqual(buscar("11 2691 4442"), {laura.pk})
        self.assertEqual(buscar("ab123cd"), {laura.pk})  # patente exacta
        self.assertEqual(buscar("ab 123 cd"), {laura.pk})  # con espacios
        self.assertEqual(buscar("xyz"), {otro.pk})  # parte de la patente
        self.assertEqual(buscar("pablo"), {sin_datos.pk})
        self.assertEqual(buscar("nadie"), set())
        self.assertEqual(buscar("   "), {laura.pk, otro.pk, sin_datos.pk})

    # AC-T4-39
    def test_listar_interesados_hace_una_consulta_y_trae_lo_que_muestra_el_tablero(self):
        responsable = fabricas.crear_funcionario("Ana")
        contacto = fabricas.crear_contacto()
        cliente = fabricas.crear_cliente()
        for _ in range(3):
            fabricas.crear_interesado(responsable=responsable)
        fabricas.crear_interesado(contacto=contacto, cliente=cliente)

        with self.assertNumQueries(1):
            interesados = list(selectors.listar_interesados(hoy=HOY))
            nombres = [
                (i.responsable.nombre if i.responsable else None,
                 i.contacto.numero if i.contacto else None,
                 i.cliente.dni if i.cliente else None)
                for i in interesados
            ]
        self.assertEqual(len(nombres), 4)

    # AC-T4-39
    def test_contar_por_estado_trae_los_cinco_estados(self):
        ana = fabricas.crear_funcionario("Ana")
        cliente = fabricas.crear_cliente()
        self.assertEqual(
            selectors.contar_por_estado(),
            {"consulta": 0, "cotizando": 0, "documentacion": 0, "emitida": 0, "perdida": 0},
        )

        fabricas.crear_interesado(responsable=ana)
        fabricas.crear_interesado()
        fabricas.crear_interesado(responsable=ana, estado="cotizando")
        fabricas.crear_interesado(estado="emitida", cliente=cliente)
        fabricas.crear_interesado(estado="perdida", motivo_perdida="Muy caro")

        self.assertEqual(
            selectors.contar_por_estado(),
            {"consulta": 2, "cotizando": 1, "documentacion": 0, "emitida": 1, "perdida": 1},
        )
        self.assertEqual(
            selectors.contar_por_estado(responsable_id=ana.pk),
            {"consulta": 1, "cotizando": 1, "documentacion": 0, "emitida": 0, "perdida": 0},
        )
        # Los claves salen en el orden del embudo.
        self.assertEqual(list(selectors.contar_por_estado()), models.EstadoInteresado.values)
        with self.assertNumQueries(1):
            selectors.contar_por_estado(responsable_id=ana.pk)

    # AC-T4-39
    def test_cotizaciones_de_ordena_por_prima_con_la_compania_incluida(self):
        interesado = fabricas.crear_interesado()
        poliza = fabricas.crear_poliza()
        cara = fabricas.crear_cotizacion(interesado, prima_mensual="30000.00")
        barata = fabricas.crear_cotizacion(interesado, prima_mensual="12500.50")
        media = fabricas.crear_cotizacion(interesado, prima_mensual="20000.00")
        de_poliza = fabricas.crear_cotizacion(poliza=poliza, prima_mensual="9000.00")
        fabricas.crear_cotizacion()  # de otro interesado

        self.assertEqual(
            list(selectors.cotizaciones_de(interesado_id=interesado.pk)),
            [barata, media, cara],
        )
        self.assertEqual(
            list(selectors.cotizaciones_de(poliza_id=poliza.pk)), [de_poliza]
        )
        self.assertEqual(list(selectors.cotizaciones_de()), [])

        with self.assertNumQueries(1):
            cotizaciones = list(selectors.cotizaciones_de(interesado_id=interesado.pk))
            for cotizacion in cotizaciones:
                self.assertTrue(cotizacion.compania.nombre)
                self.assertTrue(cotizacion.creada_por.nombre)

    # AC-T4-39
    def test_interesado_abierto_de_ignora_los_cerrados(self):
        contacto = fabricas.crear_contacto()
        self.assertIsNone(selectors.interesado_abierto_de(contacto.pk))

        fabricas.crear_interesado(
            contacto=contacto, estado="perdida", motivo_perdida="No contestó"
        )
        fabricas.crear_interesado(
            contacto=contacto, estado="emitida", cliente=fabricas.crear_cliente()
        )
        self.assertIsNone(selectors.interesado_abierto_de(contacto.pk))

        abierto = fabricas.crear_interesado(contacto=contacto, estado="documentacion")
        self.assertEqual(selectors.interesado_abierto_de(contacto.pk), abierto)
        # Otro número no se mezcla.
        self.assertIsNone(selectors.interesado_abierto_de(fabricas.crear_contacto().pk))

    # AC-T4-39
    def test_detalle_interesado_trae_historial_cotizaciones_y_contacto_en_pocas_consultas(self):
        contacto = fabricas.crear_contacto()
        interesado = fabricas.crear_interesado(
            contacto=contacto, responsable=fabricas.crear_funcionario("Ana")
        )
        funcionario = fabricas.crear_funcionario("Beto")
        models.InteresadoHistorial.objects.create(
            interesado=interesado, estado_nuevo="consulta", funcionario=funcionario
        )
        models.InteresadoHistorial.objects.create(
            interesado=interesado, estado_anterior="consulta", estado_nuevo="cotizando",
            funcionario=funcionario,
        )
        fabricas.crear_cotizacion(interesado, prima_mensual="2000.00")
        fabricas.crear_cotizacion(interesado, prima_mensual="1000.00")

        with self.assertNumQueries(3):
            detalle = selectors.detalle_interesado(interesado.pk)
            historial = list(detalle.historial.all())
            cotizaciones = list(detalle.cotizaciones.all())
            self.assertEqual(detalle.contacto.numero, contacto.numero)
            self.assertEqual(detalle.responsable.nombre, "Ana")
            self.assertEqual([h.estado_nuevo for h in historial], ["consulta", "cotizando"])
            self.assertEqual(historial[0].funcionario.nombre, "Beto")
            self.assertEqual(
                [str(c.prima_mensual) for c in cotizaciones], ["1000.00", "2000.00"]
            )
            self.assertTrue(all(c.compania.nombre for c in cotizaciones))

        with self.assertRaises(models.Interesado.DoesNotExist):
            selectors.detalle_interesado(0)

    # AC-T4-39
    def test_cierres_del_mes_cuenta_emitidos_y_perdidos_distintos_del_mes(self):
        ana = fabricas.crear_funcionario("Ana")
        cliente = fabricas.crear_cliente()
        emitido = fabricas.crear_interesado(estado="emitida", cliente=cliente, responsable=ana)
        perdido = fabricas.crear_interesado(
            estado="perdida", motivo_perdida="Muy caro", responsable=ana
        )
        ajeno = fabricas.crear_interesado(estado="perdida", motivo_perdida="Muy caro")
        de_octubre = fabricas.crear_interesado(
            estado="perdida", motivo_perdida="Muy caro", responsable=ana
        )

        def linea(interesado, anterior, nuevo, fecha):
            models.InteresadoHistorial.objects.create(
                interesado=interesado, estado_anterior=anterior, estado_nuevo=nuevo,
                fecha=fecha,
            )

        noviembre = datetime(2026, 11, 10, 15, 0, tzinfo=tz.utc)
        linea(emitido, "documentacion", "emitida", noviembre)
        linea(emitido, "emitida", "emitida", noviembre)  # una gestión no es un cierre
        linea(perdido, "consulta", "perdida", noviembre)
        linea(perdido, "perdida", "consulta", noviembre + timedelta(days=1))
        linea(perdido, "consulta", "perdida", noviembre + timedelta(days=2))  # cuenta una vez
        linea(ajeno, "cotizando", "perdida", noviembre)
        linea(de_octubre, "consulta", "perdida", datetime(2026, 10, 31, 20, 0, tzinfo=tz.utc))
        linea(de_octubre, "perdida", "perdida", noviembre)  # gestión sobre una perdida vieja

        self.assertEqual(
            selectors.cierres_del_mes(hoy=HOY), {"convertidos_mes": 1, "perdidos_mes": 2}
        )
        self.assertEqual(
            selectors.cierres_del_mes(ana.pk, hoy=HOY),
            {"convertidos_mes": 1, "perdidos_mes": 1},
        )
        # El mes anterior, aparte.
        self.assertEqual(
            selectors.cierres_del_mes(hoy=date(2026, 10, 15)),
            {"convertidos_mes": 0, "perdidos_mes": 1},
        )
        self.assertEqual(
            selectors.cierres_del_mes(hoy=date(2026, 12, 15)),
            {"convertidos_mes": 0, "perdidos_mes": 0},
        )
        with self.assertNumQueries(1):
            selectors.cierres_del_mes(ana.pk, hoy=HOY)
