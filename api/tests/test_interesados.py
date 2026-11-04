"""P5 · Embudo de interesados y cotizaciones por la API (AC-T2-36 y AC-T2-37).

Cualquier funcionario trabaja el embudo; solo un aprobador convierte un interesado
en cliente. La comisión de la compañía es del dueño: a un operador le llega en `null`.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from api import paginas
from api.tests.base import ApiTestCase
from datos import fabricas
from datos.models import Cliente, Cotizacion, Interesado
from negocio import interesados

CLAVES_ITEM = {
    "id", "nombre", "apellido", "origen", "estado", "responsable", "proximo_contacto",
    "seguimiento_vencido", "motivo_perdida", "datos", "cliente_id", "contacto",
    "creado_en", "actualizado_en",
}
CLAVES_DETALLE = CLAVES_ITEM | {"cliente", "historial", "cotizaciones"}
CLAVES_COTIZACION = {
    "id", "interesado", "poliza", "compania", "cobertura", "prima_mensual",
    "vigencia_hasta", "elegida", "notas", "creada_por", "creada_en",
}


class BaseInteresadosApi(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()

    def crear(self, **campos):
        """Un interesado de la aprobadora, listo para usar."""
        argumentos = {"nombre": "Marta", "origen": "web"}
        argumentos.update(campos)
        return interesados.crear_interesado(self.aprobadora.id, **argumentos)

    def en_documentacion(self, **campos):
        interesado = self.crear(**campos)
        for etapa in ("cotizando", "documentacion"):
            interesados.mover_interesado(interesado.pk, etapa, self.aprobadora.id)
        return interesado


class ListarInteresadosApiTests(BaseInteresadosApi):
    # AC-T2-36
    def test_exige_sesion(self):
        for ruta in ("/api/interesados/", "/api/interesados/1/", "/api/interesados/embudo/"):
            with self.subTest(ruta=ruta):
                self.assertError(self.cliente_api.get(ruta), 401, "no_autenticado")
        self.assertError(
            self.cliente_api.post("/api/interesados/", {"nombre": "A", "origen": "web"}, format="json"),
            401, "no_autenticado",
        )

    # AC-T2-36
    def test_lista_paginada_con_la_forma_del_contrato(self):
        responsable = self.operador
        a = self.crear(nombre="Ana", telefono="1155550101", datos={"patente": "AB123CD"})
        interesados.asignar_interesado(a.pk, responsable.id, self.aprobadora.id)
        self.entrar(self.operador)

        respuesta = self.cliente_api.get("/api/interesados/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(set(cuerpo), {"total", "pagina", "por_pagina", "resultados"})
        self.assertEqual(cuerpo["total"], 1)
        item = cuerpo["resultados"][0]
        self.assertEqual(set(item), CLAVES_ITEM)
        self.assertEqual(item["nombre"], "Ana")
        self.assertEqual(item["estado"], "consulta")
        self.assertEqual(item["responsable"], {"id": responsable.id, "nombre": "Diego"})
        self.assertEqual(item["datos"], {"patente": "AB123CD"})
        self.assertEqual(item["contacto"]["whatsapp"], "+5491155550101")
        self.assertIs(item["seguimiento_vencido"], False)
        self.assertTrue(item["creado_en"].endswith("Z"))

    # AC-T2-36
    def test_pagina_de_a_25(self):
        for numero in range(27):
            fabricas.crear_interesado(nombre=f"Persona {numero}")
        self.entrar()

        primera = self.cliente_api.get("/api/interesados/").json()
        segunda = self.cliente_api.get("/api/interesados/?pagina=2").json()

        self.assertEqual((primera["total"], len(primera["resultados"]), primera["por_pagina"]), (27, 25, 25))
        self.assertEqual((segunda["pagina"], len(segunda["resultados"])), (2, 2))

    # AC-T2-36
    def test_filtra_por_estado_responsable_origen_y_busqueda(self):
        ana = fabricas.crear_funcionario("Ana")
        a = fabricas.crear_interesado(nombre="Laura", responsable=ana, origen="web", datos={"patente": "AB123CD"})
        b = fabricas.crear_interesado(nombre="Pedro", origen="llamado", estado="cotizando")
        self.entrar(ana)

        def ids(consulta):
            respuesta = self.cliente_api.get(f"/api/interesados/?{consulta}")
            self.assertEqual(respuesta.status_code, 200, respuesta.content)
            return {i["id"] for i in respuesta.json()["resultados"]}

        self.assertEqual(ids("estado=cotizando"), {b.pk})
        self.assertEqual(ids(f"responsable={ana.id}"), {a.pk})
        self.assertEqual(ids("responsable=me"), {a.pk})
        self.assertEqual(ids("origen=llamado"), {b.pk})
        self.assertEqual(ids("q=laura"), {a.pk})
        self.assertEqual(ids("q=ab123cd"), {a.pk})
        self.assertEqual(ids("q=ab 123 cd"), {a.pk})
        self.assertEqual(ids("estado=&responsable=&origen=&q="), {a.pk, b.pk})

    # AC-T2-36
    def test_seguimiento_vencido_filtra_y_ordena_primero(self):
        hoy = timezone.localdate()
        al_dia = fabricas.crear_interesado(proximo_contacto=hoy + timedelta(days=2))
        vencido = fabricas.crear_interesado(proximo_contacto=hoy - timedelta(days=2))
        para_hoy = fabricas.crear_interesado(proximo_contacto=hoy)
        self.entrar()

        todos = self.cliente_api.get("/api/interesados/").json()["resultados"]
        solo = self.cliente_api.get("/api/interesados/?seguimiento_vencido=1").json()["resultados"]

        self.assertEqual(todos[0]["id"], vencido.pk)
        self.assertIs(todos[0]["seguimiento_vencido"], True)
        self.assertEqual([i["id"] for i in solo], [vencido.pk])
        por_id = {i["id"]: i for i in todos}
        self.assertIs(por_id[para_hoy.pk]["seguimiento_vencido"], False)
        self.assertIs(por_id[al_dia.pk]["seguimiento_vencido"], False)

    # AC-T2-36
    def test_un_filtro_invalido_es_400(self):
        self.entrar()
        for consulta in ("estado=volando", "origen=paloma", "responsable=abc", "responsable=0"):
            with self.subTest(consulta=consulta):
                self.assertError(
                    self.cliente_api.get(f"/api/interesados/?{consulta}"), 400, "datos_invalidos"
                )


class CrearInteresadoApiTests(BaseInteresadosApi):
    # AC-T2-36
    def test_cualquier_funcionario_crea_un_interesado(self):
        self.entrar(self.operador)

        respuesta = self.cliente_api.post(
            "/api/interesados/",
            {"nombre": "Marta", "apellido": "Gómez", "origen": "instagram", "telefono": "11 5555-0102",
             "datos": {"patente": "ab 123 cd", "marca": "Toyota"}},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(set(cuerpo), CLAVES_DETALLE | {"ya_existia"})
        self.assertIs(cuerpo["ya_existia"], False)
        self.assertEqual(cuerpo["estado"], "consulta")
        self.assertEqual(cuerpo["responsable"]["id"], self.operador.id)
        self.assertEqual(cuerpo["contacto"]["whatsapp"], "+5491155550102")
        self.assertEqual(cuerpo["datos"], {"patente": "AB123CD", "marca": "Toyota"})
        self.assertEqual(len(cuerpo["historial"]), 1)
        self.assertIsNone(cuerpo["historial"][0]["estado_anterior"])

    # AC-T2-36
    def test_si_el_numero_ya_tiene_un_interesado_abierto_devuelve_ese_con_200(self):
        existente = self.crear(telefono="1155550103")
        self.entrar()

        respuesta = self.cliente_api.post(
            "/api/interesados/", {"nombre": "Otro", "origen": "web", "telefono": "1155550103"}, format="json"
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertEqual(respuesta.json()["id"], existente.pk)
        self.assertIs(respuesta.json()["ya_existia"], True)
        self.assertEqual(Interesado.objects.count(), 1)

    # AC-T2-36
    def test_los_errores_siguen_el_formato_comun(self):
        self.entrar()
        casos = (
            {"nombre": "", "origen": "web"},
            {"nombre": "Marta", "origen": "paloma"},
            {"nombre": "Marta", "origen": "web", "telefono": "123"},
            {"nombre": "Marta", "origen": "web", "datos": {"patente": "mala"}},
        )
        for cuerpo in casos:
            with self.subTest(cuerpo=cuerpo):
                self.assertError(
                    self.cliente_api.post("/api/interesados/", cuerpo, format="json"), 400, "datos_invalidos"
                )
        # Faltan campos obligatorios.
        self.assertError(self.cliente_api.post("/api/interesados/", {}, format="json"), 400, "datos_invalidos")
        self.assertFalse(Interesado.objects.exists())


class DetalleDelInteresadoApiTests(BaseInteresadosApi):
    # AC-T2-36
    def test_detalle_con_historial_cotizaciones_y_contacto(self):
        interesado = self.crear(telefono="1155550104")
        interesados.mover_interesado(interesado.pk, "cotizando", self.aprobadora.id, nota="Pidió precio")
        cara = fabricas.crear_cotizacion(interesado, prima_mensual="30000.00", compania=fabricas.crear_compania(nombre="Cara"))
        barata = fabricas.crear_cotizacion(interesado, prima_mensual="12500.50", compania=fabricas.crear_compania(nombre="Barata"))
        self.entrar()

        respuesta = self.cliente_api.get(f"/api/interesados/{interesado.pk}/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(set(cuerpo), CLAVES_DETALLE)
        self.assertEqual(cuerpo["contacto"]["whatsapp"], "+5491155550104")
        self.assertEqual(
            [(h["estado_anterior"], h["estado_nuevo"], h["nota"]) for h in cuerpo["historial"]],
            [(None, "consulta", "Alta del interesado (origen: Web)."), ("consulta", "cotizando", "Pidió precio")],
        )
        self.assertEqual(cuerpo["historial"][1]["funcionario"], {"id": self.aprobadora.id, "nombre": "Graciela"})
        # Las cotizaciones, de la más barata a la más cara.
        self.assertEqual([c["id"] for c in cuerpo["cotizaciones"]], [barata.pk, cara.pk])
        self.assertEqual(set(cuerpo["cotizaciones"][0]), CLAVES_COTIZACION)
        self.assertEqual(cuerpo["cotizaciones"][0]["prima_mensual"], "12500.50")
        self.assertEqual(cuerpo["cotizaciones"][0]["compania"]["nombre"], "Barata")

    # AC-T2-36
    def test_el_detalle_inexistente_es_404(self):
        self.entrar()
        self.assertError(self.cliente_api.get("/api/interesados/0/"), 404, "no_encontrado")

    # AC-T2-36
    def test_el_cliente_aparece_cuando_hay(self):
        interesado = self.crear(telefono="1155550105")
        Interesado.objects.filter(pk=interesado.pk).update(cliente=self.cliente)
        self.entrar()

        cuerpo = self.cliente_api.get(f"/api/interesados/{interesado.pk}/").json()

        self.assertEqual(cuerpo["cliente_id"], self.cliente.id)
        self.assertEqual(cuerpo["cliente"], {"id": self.cliente.id, "nombre": "Laura", "apellido": "Fernández"})


class ModificarInteresadoApiTests(BaseInteresadosApi):
    # AC-T2-36
    def test_patch_cambia_responsable_proximo_contacto_y_datos(self):
        interesado = self.crear(datos={"marca": "Toyota"})
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.entrar(self.operador)  # cualquier funcionario

        respuesta = self.cliente_api.patch(
            f"/api/interesados/{interesado.pk}/",
            {"responsable_id": self.operador.id, "proximo_contacto": manana,
             "datos": {"patente": "ab123cd", "localidad": "Rosario"}},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["responsable"]["id"], self.operador.id)
        self.assertEqual(cuerpo["proximo_contacto"], manana)
        self.assertEqual(cuerpo["datos"], {"marca": "Toyota", "patente": "AB123CD", "localidad": "Rosario"})
        # Cada gestión deja su línea de historial.
        self.assertEqual(len(cuerpo["historial"]), 4)

    # AC-T2-36
    def test_proximo_contacto_vacio_o_null_lo_borra(self):
        interesado = self.crear()
        interesados.programar_contacto(interesado.pk, timezone.localdate(), self.aprobadora.id)
        self.entrar()
        for vacio in ("", None):
            with self.subTest(vacio=vacio):
                interesados.programar_contacto(interesado.pk, timezone.localdate(), self.aprobadora.id)
                respuesta = self.cliente_api.patch(
                    f"/api/interesados/{interesado.pk}/", {"proximo_contacto": vacio}, format="json"
                )
                self.assertEqual(respuesta.status_code, 200, respuesta.content)
                self.assertIsNone(respuesta.json()["proximo_contacto"])

    # AC-T2-36
    def test_si_un_cambio_falla_no_queda_ninguno(self):
        interesado = self.crear()
        self.entrar()

        respuesta = self.cliente_api.patch(
            f"/api/interesados/{interesado.pk}/",
            {"responsable_id": self.operador.id, "datos": {"patente": "mala"}},
            format="json",
        )

        self.assertError(respuesta, 400, "datos_invalidos")
        interesado.refresh_from_db()
        self.assertEqual(interesado.responsable_id, self.aprobadora.id)  # la asignación se deshizo
        self.assertEqual(interesado.historial.count(), 1)

    # AC-T2-36
    def test_errores_de_patch(self):
        interesado = self.crear()
        inactivo = fabricas.crear_funcionario("Baja", activo=False)
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.entrar()
        casos = (
            ({"responsable_id": inactivo.id}, 400),
            ({"responsable_id": 0}, 400),
            ({"proximo_contacto": ayer}, 400),
            ({"proximo_contacto": "mañana"}, 400),
            ({"datos": "texto"}, 400),
        )
        for cuerpo, http in casos:
            with self.subTest(cuerpo=cuerpo):
                self.assertError(
                    self.cliente_api.patch(f"/api/interesados/{interesado.pk}/", cuerpo, format="json"),
                    http, "datos_invalidos",
                )
        self.assertError(
            self.cliente_api.patch("/api/interesados/0/", {"datos": {"marca": "x"}}, format="json"),
            404, "no_encontrado",
        )


class MoverInteresadoApiTests(BaseInteresadosApi):
    # AC-T2-36
    def test_mover_avanza_una_etapa_y_devuelve_la_ficha(self):
        interesado = self.crear()
        self.entrar(self.operador)

        respuesta = self.cliente_api.post(
            f"/api/interesados/{interesado.pk}/mover/",
            {"estado": "cotizando", "nota": "Ya pidió precio"},
            format="json",
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["estado"], "cotizando")
        self.assertEqual(cuerpo["historial"][-1]["nota"], "Ya pidió precio")
        self.assertEqual(cuerpo["historial"][-1]["funcionario"]["id"], self.operador.id)

    # AC-T2-36
    def test_perder_exige_motivo_y_se_puede_reabrir(self):
        interesado = self.crear()
        self.entrar()
        ruta = f"/api/interesados/{interesado.pk}/mover/"

        sin_motivo = self.cliente_api.post(ruta, {"estado": "perdida"}, format="json")
        self.assertError(sin_motivo, 400, "datos_invalidos")

        perdido = self.cliente_api.post(
            ruta, {"estado": "perdida", "motivo_perdida": "Muy caro"}, format="json"
        )
        self.assertEqual(perdido.status_code, 200, perdido.content)
        self.assertEqual(perdido.json()["motivo_perdida"], "Muy caro")

        reabierto = self.cliente_api.post(ruta, {"estado": "consulta"}, format="json")
        self.assertEqual(reabierto.json()["estado"], "consulta")
        self.assertIsNone(reabierto.json()["motivo_perdida"])

    # AC-T2-36
    def test_una_transicion_invalida_es_409_y_una_etapa_inexistente_400(self):
        interesado = self.crear()
        self.entrar()
        ruta = f"/api/interesados/{interesado.pk}/mover/"
        self.assertError(self.cliente_api.post(ruta, {"estado": "emitida"}, format="json"), 409, "estado_invalido")
        self.assertError(self.cliente_api.post(ruta, {"estado": "volando"}, format="json"), 400, "datos_invalidos")
        self.assertError(self.cliente_api.post(ruta, {}, format="json"), 400, "datos_invalidos")
        self.assertError(
            self.cliente_api.post("/api/interesados/0/mover/", {"estado": "cotizando"}, format="json"),
            404, "no_encontrado",
        )


class ConvertirInteresadoApiTests(BaseInteresadosApi):
    CUERPO = {"dni": "30.111.222", "nombre": "Marta", "apellido": "Gómez", "email": "marta@correo.com"}

    # AC-T2-36
    def test_un_aprobador_convierte_al_interesado_en_cliente(self):
        interesado = self.en_documentacion(telefono="1155550106")
        self.entrar()

        respuesta = self.cliente_api.post(
            f"/api/interesados/{interesado.pk}/convertir/", self.CUERPO, format="json"
        )

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        cliente = Cliente.objects.get(dni="30111222")
        self.assertEqual(cuerpo["cliente_id"], cliente.id)
        self.assertEqual(cuerpo["cliente"]["apellido"], "Gómez")
        self.assertEqual(cuerpo["estado"], "documentacion")  # no cambia la etapa
        self.assertEqual(cuerpo["datos"]["dni"], "30111222")

    # AC-T2-36
    def test_un_operador_recibe_403(self):
        interesado = self.en_documentacion(telefono="1155550107")
        self.entrar(self.operador)

        respuesta = self.cliente_api.post(
            f"/api/interesados/{interesado.pk}/convertir/", self.CUERPO, format="json"
        )

        self.assertError(respuesta, 403, "permiso_denegado")
        self.assertFalse(Cliente.objects.filter(dni="30111222").exists())

    # AC-T2-36
    def test_errores_de_negocio(self):
        en_consulta = self.crear(telefono="1155550108")
        en_doc = self.en_documentacion(telefono="1155550109")
        self.entrar()
        self.assertError(
            self.cliente_api.post(f"/api/interesados/{en_consulta.pk}/convertir/", self.CUERPO, format="json"),
            409, "estado_invalido",
        )
        self.assertError(
            self.cliente_api.post(f"/api/interesados/{en_doc.pk}/convertir/", {**self.CUERPO, "dni": "12"}, format="json"),
            400, "datos_invalidos",
        )
        self.assertError(
            self.cliente_api.post("/api/interesados/0/convertir/", self.CUERPO, format="json"),
            404, "no_encontrado",
        )


class EmbudoApiTests(BaseInteresadosApi):
    # AC-T2-37
    def test_embudo_devuelve_conteos_y_cierres_del_mes(self):
        ana = fabricas.crear_funcionario("Ana")
        mias = self.crear(nombre="Mía")
        interesados.asignar_interesado(mias.pk, ana.id, self.aprobadora.id)
        for etapa in ("cotizando",):
            interesados.mover_interesado(mias.pk, etapa, ana.id)
        perdida = self.crear(nombre="Perdida")
        interesados.mover_interesado(perdida.pk, "perdida", self.aprobadora.id, motivo_perdida="Muy caro")
        self.crear(nombre="Otra", telefono="1155550110")
        self.entrar()

        todos = self.cliente_api.get("/api/interesados/embudo/")
        de_ana = self.cliente_api.get(f"/api/interesados/embudo/?responsable={ana.id}")

        self.assertEqual(todos.status_code, 200, todos.content)
        self.assertEqual(set(todos.json()), {"conteos", "convertidos_mes", "perdidos_mes"})
        self.assertEqual(
            todos.json()["conteos"],
            {"consulta": 1, "cotizando": 1, "documentacion": 0, "emitida": 0, "perdida": 1},
        )
        self.assertEqual((todos.json()["convertidos_mes"], todos.json()["perdidos_mes"]), (0, 1))
        self.assertEqual(
            de_ana.json()["conteos"],
            {"consulta": 0, "cotizando": 1, "documentacion": 0, "emitida": 0, "perdida": 0},
        )
        self.assertEqual(de_ana.json()["perdidos_mes"], 0)
        self.assertEqual(self.cliente_api.get("/api/interesados/embudo/?responsable=me").json()["conteos"]["cotizando"], 0)
        self.assertError(self.cliente_api.get("/api/interesados/embudo/?responsable=x"), 400, "datos_invalidos")


class CotizacionesApiTests(BaseInteresadosApi):
    def setUp(self):
        super().setUp()
        self.compania = fabricas.crear_compania(nombre="La Caja", comision_pct="12.50")
        self.otra = fabricas.crear_compania(nombre="Sancor", comision_pct="9.00")
        self.interesado = self.crear()
        self.poliza = fabricas.crear_poliza(self.cliente)

    def cuerpo(self, **campos):
        base = {
            "interesado_id": self.interesado.pk,
            "compania_id": self.compania.id,
            "cobertura": "intermedia",
            "prima_mensual": "15000.50",
        }
        base.update(campos)
        return base

    # AC-T2-37
    def test_exige_sesion(self):
        self.assertError(self.cliente_api.get("/api/cotizaciones/?interesado=1"), 401, "no_autenticado")
        self.assertError(self.cliente_api.post("/api/cotizaciones/", self.cuerpo(), format="json"), 401, "no_autenticado")
        self.assertError(self.cliente_api.post("/api/cotizaciones/1/elegir/"), 401, "no_autenticado")
        self.assertError(self.cliente_api.post("/api/cotizaciones/1/quitar/"), 401, "no_autenticado")

    # AC-T2-37
    def test_cargar_una_cotizacion_de_interesado_y_de_poliza(self):
        self.entrar(self.operador)  # cualquier funcionario

        de_interesado = self.cliente_api.post("/api/cotizaciones/", self.cuerpo(notas="Con granizo"), format="json")
        de_poliza = self.cliente_api.post(
            "/api/cotizaciones/",
            self.cuerpo(interesado_id=None, poliza_id=self.poliza.pk, prima_mensual=9000, vigencia_hasta="2027-01-31"),
            format="json",
        )

        self.assertEqual(de_interesado.status_code, 201, de_interesado.content)
        cuerpo = de_interesado.json()
        self.assertEqual(set(cuerpo), CLAVES_COTIZACION)
        self.assertEqual(cuerpo["prima_mensual"], "15000.50")
        self.assertEqual(cuerpo["interesado"], self.interesado.pk)
        self.assertIsNone(cuerpo["poliza"])
        self.assertFalse(cuerpo["elegida"])
        self.assertEqual(cuerpo["notas"], "Con granizo")
        self.assertEqual(cuerpo["creada_por"], {"id": self.operador.id, "nombre": "Diego"})
        self.assertEqual(de_poliza.status_code, 201, de_poliza.content)
        self.assertEqual(de_poliza.json()["poliza"], self.poliza.pk)
        self.assertEqual(de_poliza.json()["vigencia_hasta"], "2027-01-31")
        self.assertEqual(de_poliza.json()["prima_mensual"], "9000.00")

    # AC-T2-37
    def test_errores_al_cargar(self):
        inactiva = fabricas.crear_compania(activa=False)
        self.entrar()
        casos = (
            (self.cuerpo(interesado_id=None), 400),                          # ni interesado ni póliza
            (self.cuerpo(poliza_id=self.poliza.pk), 400),                    # las dos
            (self.cuerpo(prima_mensual="0"), 400),
            (self.cuerpo(prima_mensual="abc"), 400),
            (self.cuerpo(cobertura="premium"), 400),
            (self.cuerpo(compania_id=inactiva.id), 400),
            (self.cuerpo(interesado_id=0 + 99999), 404),
            (self.cuerpo(compania_id=99999), 404),
        )
        for cuerpo, http in casos:
            with self.subTest(cuerpo=cuerpo):
                respuesta = self.cliente_api.post("/api/cotizaciones/", cuerpo, format="json")
                self.assertEqual(respuesta.status_code, http, respuesta.content)
                self.assertIn("error", respuesta.json())
        self.assertFalse(Cotizacion.objects.exists())

    # AC-T2-37
    def test_listar_por_interesado_o_por_poliza_de_la_mas_barata_a_la_mas_cara(self):
        cara = fabricas.crear_cotizacion(self.interesado, prima_mensual="30000", compania=self.compania)
        barata = fabricas.crear_cotizacion(self.interesado, prima_mensual="12000", compania=self.otra)
        de_poliza = fabricas.crear_cotizacion(poliza=self.poliza, prima_mensual="8000", compania=self.otra)
        fabricas.crear_cotizacion()  # de otro interesado
        self.entrar()

        por_interesado = self.cliente_api.get(f"/api/cotizaciones/?interesado={self.interesado.pk}")
        por_poliza = self.cliente_api.get(f"/api/cotizaciones/?poliza={self.poliza.pk}")

        self.assertEqual(por_interesado.status_code, 200, por_interesado.content)
        self.assertEqual([c["id"] for c in por_interesado.json()["resultados"]], [barata.pk, cara.pk])
        self.assertEqual([c["id"] for c in por_poliza.json()["resultados"]], [de_poliza.pk])
        self.assertEqual(set(por_interesado.json()["resultados"][0]), CLAVES_COTIZACION)

    # AC-T2-37
    def test_listar_exige_exactamente_un_destino(self):
        self.entrar()
        for ruta in (
            "/api/cotizaciones/",
            f"/api/cotizaciones/?interesado={self.interesado.pk}&poliza={self.poliza.pk}",
            "/api/cotizaciones/?interesado=abc",
            "/api/cotizaciones/?interesado=0",
        ):
            with self.subTest(ruta=ruta):
                self.assertError(self.cliente_api.get(ruta), 400, "datos_invalidos")

    # AC-T2-37
    def test_elegir_marca_una_sola_y_quitar_borra_las_otras(self):
        primera = fabricas.crear_cotizacion(self.interesado, prima_mensual="10000", compania=self.compania)
        segunda = fabricas.crear_cotizacion(self.interesado, prima_mensual="12000", compania=self.otra)
        self.entrar()

        elegida = self.cliente_api.post(f"/api/cotizaciones/{primera.pk}/elegir/")
        self.assertEqual(elegida.status_code, 200, elegida.content)
        self.assertIs(elegida.json()["elegida"], True)

        cambia = self.cliente_api.post(f"/api/cotizaciones/{segunda.pk}/elegir/")
        self.assertIs(cambia.json()["elegida"], True)
        primera.refresh_from_db()
        self.assertFalse(primera.elegida)

        # La elegida no se quita; la otra, sí.
        self.assertError(self.cliente_api.post(f"/api/cotizaciones/{segunda.pk}/quitar/"), 409, "estado_invalido")
        quitada = self.cliente_api.post(f"/api/cotizaciones/{primera.pk}/quitar/")
        self.assertEqual(quitada.status_code, 204)
        self.assertFalse(Cotizacion.objects.filter(pk=primera.pk).exists())
        self.assertError(self.cliente_api.post("/api/cotizaciones/0/elegir/"), 404, "no_encontrado")
        self.assertError(self.cliente_api.post("/api/cotizaciones/0/quitar/"), 404, "no_encontrado")

    # AC-T2-37
    def test_la_comision_de_la_compania_es_solo_para_aprobadores(self):
        fabricas.crear_cotizacion(self.interesado, compania=self.compania)

        self.entrar()
        aprobador = self.cliente_api.get(f"/api/cotizaciones/?interesado={self.interesado.pk}").json()
        self.assertEqual(aprobador["resultados"][0]["compania"]["comision_pct"], "12.50")
        detalle = self.cliente_api.get(f"/api/interesados/{self.interesado.pk}/").json()
        self.assertEqual(detalle["cotizaciones"][0]["compania"]["comision_pct"], "12.50")

        self.cliente_api.logout()
        self.entrar(self.operador)
        operador = self.cliente_api.get(f"/api/cotizaciones/?interesado={self.interesado.pk}").json()
        self.assertIsNone(operador["resultados"][0]["compania"]["comision_pct"])
        self.assertEqual(operador["resultados"][0]["compania"]["nombre"], "La Caja")
        detalle = self.cliente_api.get(f"/api/interesados/{self.interesado.pk}/").json()
        self.assertIsNone(detalle["cotizaciones"][0]["compania"]["comision_pct"])


class PaginasYFuncionariosApiTests(BaseInteresadosApi):
    # AC-T2-36
    def test_las_rutas_de_las_paginas_estan_en_la_lista_blanca(self):
        for ruta, archivo in (
            ("/panel/interesados/", "interesados.html"),
            ("/panel/interesado/", "interesado.html"),
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(paginas._PAGINAS[ruta], archivo)
                esperado = settings.BASE_DIR / "frontend" / "pages" / archivo
                self.assertTrue(esperado.exists(), f"falta {archivo}")
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(b"".join(respuesta.streaming_content), esperado.read_bytes())

    # AC-T2-36
    def test_los_funcionarios_activos_los_puede_leer_cualquiera_para_elegir_responsable(self):
        fabricas.crear_funcionario("Zoe", puede_aprobar=False, activo=False)
        self.assertError(self.cliente_api.get("/api/funcionarios/"), 401, "no_autenticado")
        self.entrar(self.operador)

        respuesta = self.cliente_api.get("/api/funcionarios/")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        resultados = respuesta.json()["resultados"]
        self.assertEqual([f["nombre"] for f in resultados], ["Diego", "Graciela"])
        # Ni el correo ni los permisos: eso es del propietario.
        self.assertEqual(set(resultados[0]), {"id", "nombre", "rol"})

    # AC-T2-36
    def test_cada_pedido_pagina_con_su_propio_paginador(self):
        """El tablero pide las cinco columnas en paralelo. Con un paginador compartido
        entre hilos, el total de una columna aparecía en otra (visto en el navegador)."""
        from api import views

        self.assertFalse(hasattr(views, "PAGINADOR"))
        for _ in range(3):
            fabricas.crear_interesado()
        fabricas.crear_interesado(estado="cotizando")
        self.entrar()
        totales = [
            self.cliente_api.get(f"/api/interesados/?estado={estado}").json()["total"]
            for estado in ("consulta", "cotizando", "consulta", "documentacion")
        ]
        self.assertEqual(totales, [3, 1, 3, 0])
