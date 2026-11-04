"""P1 · Vehículos y compañías por la API (AC-T2-26 a AC-T2-28).

Leer lo puede hacer cualquier funcionario; escribir, solo un aprobador. La
comisión es información del dueño: a un operador le llega siempre en `null`.
"""

from __future__ import annotations

from django.conf import settings

from api import paginas
from api.tests.base import ApiTestCase
from datos import fabricas

CLAVES_VEHICULO = {
    "id", "cliente", "patente", "marca", "modelo", "anio",
    "uso", "chasis", "valor_asegurado", "activo",
}
CLAVES_COMPANIA = {"id", "nombre", "comision_pct", "activa"}

ALTA_VEHICULO = {
    "patente": "ab 123 cd",
    "marca": "Toyota",
    "modelo": "Corolla",
    "anio": 2020,
}


class VehiculosApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()

    def alta(self, **campos):
        cuerpo = {"cliente": self.cliente.id, **ALTA_VEHICULO, **campos}
        return self.cliente_api.post("/api/vehiculos/", cuerpo, format="json")

    # AC-T2-26
    def test_cualquier_funcionario_lista_los_vehiculos_de_un_cliente(self):
        fabricas.crear_vehiculo(self.cliente, patente="BBB222")
        fabricas.crear_vehiculo(self.cliente, patente="AAA111")
        fabricas.crear_vehiculo(self.cliente, patente="CCC333", activo=False)
        fabricas.crear_vehiculo()  # de otro cliente
        self.entrar(self.operador)

        respuesta = self.cliente_api.get(f"/api/vehiculos/?cliente={self.cliente.id}")

        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        resultados = respuesta.json()["resultados"]
        self.assertEqual([v["patente"] for v in resultados], ["AAA111", "BBB222"])
        self.assertEqual(set(resultados[0]), CLAVES_VEHICULO)
        self.assertEqual(resultados[0]["cliente"], self.cliente.id)

    # AC-T2-26
    def test_el_listado_exige_sesion_y_un_cliente_valido(self):
        self.assertError(self.cliente_api.get("/api/vehiculos/?cliente=1"), 401, "no_autenticado")
        self.entrar()
        for ruta in ("/api/vehiculos/", "/api/vehiculos/?cliente=", "/api/vehiculos/?cliente=abc",
                     "/api/vehiculos/?cliente=0"):
            with self.subTest(ruta=ruta):
                self.assertError(self.cliente_api.get(ruta), 400, "datos_invalidos")

    # AC-T2-26
    def test_un_aprobador_da_de_alta_y_la_respuesta_es_el_objeto_vehiculo(self):
        self.entrar()

        respuesta = self.alta(chasis="8AB123", valor_asegurado="15000000", uso="comercial")

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual(set(cuerpo), CLAVES_VEHICULO)
        self.assertEqual(cuerpo["patente"], "AB123CD")
        self.assertEqual(cuerpo["cliente"], self.cliente.id)
        self.assertEqual(cuerpo["uso"], "comercial")
        self.assertEqual(cuerpo["valor_asegurado"], "15000000.00")
        self.assertEqual(cuerpo["chasis"], "8AB123")
        self.assertTrue(cuerpo["activo"])

    # AC-T2-26
    def test_los_errores_siguen_el_formato_del_contrato(self):
        self.entrar()
        self.assertEqual(self.alta().status_code, 201)

        self.assertError(self.alta(patente="AB-123-CD"), 400, "datos_invalidos")  # repetida
        self.assertError(self.alta(patente="AB12"), 400, "datos_invalidos")
        self.assertError(self.alta(patente="ZZ111ZZ", anio=1900), 400, "datos_invalidos")
        self.assertError(self.alta(patente="ZZ111ZZ", marca=""), 400, "datos_invalidos")
        self.assertError(self.alta(patente="ZZ111ZZ", valor_asegurado="0"), 400, "datos_invalidos")
        self.assertError(self.alta(patente="ZZ111ZZ", anio="dos mil"), 400, "datos_invalidos")
        self.assertError(self.alta(cliente=999_999, patente="ZZ111ZZ"), 404, "no_encontrado")
        # Falta un campo obligatorio.
        sin_modelo = {k: v for k, v in ALTA_VEHICULO.items() if k != "modelo"}
        self.assertError(
            self.cliente_api.post(
                "/api/vehiculos/", {"cliente": self.cliente.id, **sin_modelo}, format="json"
            ),
            400, "datos_invalidos",
        )

    # AC-T2-26
    def test_un_operador_no_escribe(self):
        vehiculo = fabricas.crear_vehiculo(self.cliente)
        self.entrar(self.operador)

        self.assertError(self.alta(), 403, "permiso_denegado")
        self.assertError(
            self.cliente_api.patch(f"/api/vehiculos/{vehiculo.id}/", {"marca": "X"}, format="json"),
            403, "permiso_denegado",
        )
        self.assertError(
            self.cliente_api.post(f"/api/vehiculos/{vehiculo.id}/baja/"), 403, "permiso_denegado"
        )
        vehiculo.refresh_from_db()
        self.assertNotEqual(vehiculo.marca, "X")
        self.assertTrue(vehiculo.activo)

    # AC-T2-26
    def test_patch_actualiza_solo_lo_recibido_y_puede_borrar_chasis_y_valor(self):
        vehiculo = fabricas.crear_vehiculo(
            self.cliente, patente="AB123CD", chasis="X1", valor_asegurado="100.00"
        )
        self.entrar()
        ruta = f"/api/vehiculos/{vehiculo.id}/"

        respuesta = self.cliente_api.patch(ruta, {"modelo": "Etios"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        cuerpo = respuesta.json()
        self.assertEqual((cuerpo["modelo"], cuerpo["patente"], cuerpo["chasis"]), ("Etios", "AB123CD", "X1"))
        self.assertEqual(cuerpo["valor_asegurado"], "100.00")

        # La patente propia no es repetida; la ajena sí.
        self.assertEqual(
            self.cliente_api.patch(ruta, {"patente": "ab 123 cd"}, format="json").status_code, 200
        )
        fabricas.crear_vehiculo(patente="XY987ZW")
        self.assertError(
            self.cliente_api.patch(ruta, {"patente": "XY987ZW"}, format="json"),
            400, "datos_invalidos",
        )

        borrado = self.cliente_api.patch(ruta, {"chasis": "", "valor_asegurado": None}, format="json")
        self.assertEqual(borrado.status_code, 200, borrado.content)
        self.assertIsNone(borrado.json()["chasis"])
        self.assertIsNone(borrado.json()["valor_asegurado"])
        self.assertError(
            self.cliente_api.patch("/api/vehiculos/999999/", {"marca": "X"}, format="json"),
            404, "no_encontrado",
        )

    # AC-T2-26
    def test_la_baja_es_logica_y_con_poliza_vigente_es_409(self):
        libre = fabricas.crear_vehiculo(self.cliente)
        asegurado = fabricas.crear_vehiculo(self.cliente)
        fabricas.crear_poliza(self.cliente, vehiculo=asegurado)
        self.entrar()

        respuesta = self.cliente_api.post(f"/api/vehiculos/{libre.id}/baja/")
        self.assertEqual(respuesta.status_code, 200, respuesta.content)
        self.assertFalse(respuesta.json()["activo"])

        self.assertError(
            self.cliente_api.post(f"/api/vehiculos/{asegurado.id}/baja/"), 409, "estado_invalido"
        )
        self.assertError(
            self.cliente_api.post(f"/api/vehiculos/{libre.id}/baja/"), 409, "estado_invalido"
        )
        self.assertError(self.cliente_api.post("/api/vehiculos/999999/baja/"), 404, "no_encontrado")

    # AC-T2-26
    def test_put_y_delete_son_405(self):
        vehiculo = fabricas.crear_vehiculo(self.cliente)
        self.entrar()
        for ruta in ("/api/vehiculos/", f"/api/vehiculos/{vehiculo.id}/"):
            for metodo in ("put", "delete"):
                with self.subTest(ruta=ruta, metodo=metodo):
                    respuesta = getattr(self.cliente_api, metodo)(ruta)
                    self.assertError(respuesta, 405, "metodo_no_permitido")
        self.assertError(
            self.cliente_api.get(f"/api/vehiculos/{vehiculo.id}/baja/"), 405, "metodo_no_permitido"
        )


class CompaniasApiTests(ApiTestCase):
    # AC-T2-27
    def test_cualquier_funcionario_lista_y_activas_filtra(self):
        fabricas.crear_compania(nombre="Zurich")
        fabricas.crear_compania(nombre="Allianz")
        fabricas.crear_compania(nombre="Mapfre", activa=False)
        self.entrar(self.operador)

        todas = self.cliente_api.get("/api/companias/")
        activas = self.cliente_api.get("/api/companias/?activas=1")

        self.assertEqual(todas.status_code, 200, todas.content)
        self.assertEqual([c["nombre"] for c in todas.json()["resultados"]],
                         ["Allianz", "Mapfre", "Zurich"])
        self.assertEqual([c["nombre"] for c in activas.json()["resultados"]],
                         ["Allianz", "Zurich"])
        self.assertEqual(set(activas.json()["resultados"][0]), CLAVES_COMPANIA)

    # AC-T2-27
    def test_la_comision_de_una_compania_es_null_para_un_operador(self):
        fabricas.crear_compania(nombre="Zurich", comision_pct="12.50")
        self.entrar()
        self.assertEqual(
            self.cliente_api.get("/api/companias/").json()["resultados"][0]["comision_pct"], "12.50"
        )
        self.cliente_api.logout()
        self.entrar(self.operador)
        self.assertIsNone(
            self.cliente_api.get("/api/companias/").json()["resultados"][0]["comision_pct"]
        )

    # AC-T2-27
    def test_un_aprobador_crea_y_modifica(self):
        self.entrar()

        creada = self.cliente_api.post(
            "/api/companias/", {"nombre": "La Caja", "comision_pct": "12.5"}, format="json"
        )
        self.assertEqual(creada.status_code, 201, creada.content)
        cuerpo = creada.json()
        self.assertEqual(set(cuerpo), CLAVES_COMPANIA)
        self.assertEqual(
            (cuerpo["nombre"], cuerpo["comision_pct"], cuerpo["activa"]), ("La Caja", "12.50", True)
        )

        ruta = f"/api/companias/{cuerpo['id']}/"
        cambiada = self.cliente_api.patch(ruta, {"comision_pct": 15}, format="json")
        self.assertEqual(cambiada.status_code, 200, cambiada.content)
        self.assertEqual(cambiada.json()["comision_pct"], "15.00")
        self.assertEqual(cambiada.json()["nombre"], "La Caja")

        apagada = self.cliente_api.patch(ruta, {"activa": False}, format="json")
        self.assertFalse(apagada.json()["activa"])
        prendida = self.cliente_api.patch(ruta, {"activa": True}, format="json")
        self.assertTrue(prendida.json()["activa"])

    # AC-T2-27
    def test_errores_y_permisos_de_companias(self):
        existente = fabricas.crear_compania(nombre="La Caja")
        self.entrar(self.operador)
        self.assertError(
            self.cliente_api.post("/api/companias/", {"nombre": "X", "comision_pct": 1}, format="json"),
            403, "permiso_denegado",
        )
        self.assertError(
            self.cliente_api.patch(f"/api/companias/{existente.id}/", {"activa": False}, format="json"),
            403, "permiso_denegado",
        )

        self.cliente_api.logout()
        self.entrar()
        for cuerpo in (
            {"nombre": "la  caja", "comision_pct": 5},   # repetida sin distinguir mayúsculas ni espacios
            {"nombre": "Nueva", "comision_pct": 101},
            {"nombre": "Nueva", "comision_pct": "abc"},
            {"nombre": "  ", "comision_pct": 5},
            {"nombre": "Nueva"},                         # falta la comisión
        ):
            with self.subTest(cuerpo=cuerpo):
                self.assertError(
                    self.cliente_api.post("/api/companias/", cuerpo, format="json"),
                    400, "datos_invalidos",
                )
        self.assertError(
            self.cliente_api.patch("/api/companias/999999/", {"activa": False}, format="json"),
            404, "no_encontrado",
        )
        self.assertError(
            self.cliente_api.delete(f"/api/companias/{existente.id}/"), 405, "metodo_no_permitido"
        )


class DetallesConVehiculoYCompaniaTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        fabricas.crear_catalogos()
        self.vehiculo = fabricas.crear_vehiculo(
            self.cliente, patente="AB123CD", marca="Toyota", modelo="Corolla", anio=2020
        )
        self.baja = fabricas.crear_vehiculo(self.cliente, patente="ZZ999ZZ", activo=False)
        self.compania = fabricas.crear_compania(nombre="La Caja", comision_pct="12.50")
        self.poliza = fabricas.crear_poliza(
            self.cliente,
            vehiculo=self.vehiculo,
            compania=self.compania,
            comision_pct="12.50",
        )
        self.sin_bien = fabricas.crear_poliza(self.cliente)

    # AC-T2-28
    def test_cliente_detalle_incluye_vehiculos_activos_y_vehiculo_compania_y_comision(self):
        self.entrar()

        cuerpo = self.cliente_api.get(f"/api/clientes/{self.cliente.id}/").json()

        self.assertEqual([v["patente"] for v in cuerpo["vehiculos"]], ["AB123CD"])
        self.assertEqual(set(cuerpo["vehiculos"][0]), CLAVES_VEHICULO)
        polizas = {p["id"]: p for p in cuerpo["polizas"]}
        con = polizas[self.poliza.id]
        self.assertEqual(con["vehiculo"]["patente"], "AB123CD")
        self.assertEqual(con["compania"]["nombre"], "La Caja")
        self.assertEqual(con["compania"]["comision_pct"], "12.50")
        self.assertEqual(con["comision_pct"], "12.50")
        sin = polizas[self.sin_bien.id]
        self.assertEqual((sin["vehiculo"], sin["compania"], sin["comision_pct"]), (None, None, None))

    # AC-T2-28
    def test_poliza_detalle_incluye_vehiculo_compania_y_comision(self):
        self.entrar()

        cuerpo = self.cliente_api.get(f"/api/polizas/{self.poliza.id}/").json()

        self.assertEqual(cuerpo["vehiculo"]["marca"], "Toyota")
        self.assertEqual(cuerpo["compania"]["id"], self.compania.id)
        self.assertEqual(cuerpo["comision_pct"], "12.50")

    # AC-T2-28
    def test_la_comision_es_null_para_un_operador_en_todas_partes(self):
        self.entrar(self.operador)

        ficha = self.cliente_api.get(f"/api/clientes/{self.cliente.id}/").json()
        poliza = self.cliente_api.get(f"/api/polizas/{self.poliza.id}/").json()

        con = next(p for p in ficha["polizas"] if p["id"] == self.poliza.id)
        self.assertIsNone(con["comision_pct"])
        self.assertIsNone(con["compania"]["comision_pct"])
        self.assertEqual(con["compania"]["nombre"], "La Caja")  # la compañía sí se ve
        self.assertIsNone(poliza["comision_pct"])
        self.assertIsNone(poliza["compania"]["comision_pct"])
        self.assertNotIn("12.5", self.cliente_api.get(f"/api/polizas/{self.poliza.id}/").content.decode())

    # AC-T2-28
    def test_buscar_clientes_por_patente_encuentra_al_dueno(self):
        self.entrar(self.operador)
        otro = fabricas.crear_cliente(nombre="Otro", apellido="Cliente")

        for q in ("ab123cd", "AB 123 CD", "ab-123-cd"):
            with self.subTest(q=q):
                respuesta = self.cliente_api.get("/api/clientes/", {"q": q})
                self.assertEqual(respuesta.status_code, 200, respuesta.content)
                self.assertEqual([c["id"] for c in respuesta.json()["resultados"]], [self.cliente.id])
        self.assertNotIn(otro.id, [c["id"] for c in self.cliente_api.get("/api/clientes/", {"q": "ab123cd"}).json()["resultados"]])

    # AC-T2-28
    def test_el_alta_de_poliza_acepta_vehiculo_y_compania(self):
        self.entrar()
        nuevo = fabricas.crear_vehiculo(self.cliente, patente="XY987ZW", marca="Ford", modelo="Ka", anio=2019)
        cuerpo = {
            "tipo_seguro": "automotor", "cobertura": "total",
            "fecha_inicio": "2026-01-10", "fecha_vencimiento": "2027-01-10",
            "prima_mensual": "18000",
            "vehiculo_id": nuevo.id, "compania_id": self.compania.id, "comision_pct": "",
        }

        respuesta = self.cliente_api.post(
            f"/api/clientes/{self.cliente.id}/polizas/", cuerpo, format="json"
        )

        self.assertEqual(respuesta.status_code, 201, respuesta.content)
        creada = respuesta.json()
        self.assertEqual(creada["vehiculo"]["id"], nuevo.id)
        self.assertEqual(creada["compania"]["id"], self.compania.id)
        self.assertEqual(creada["comision_pct"], "12.50")
        self.assertEqual(creada["bien_asegurado"], "Ford Ka 2019 (XY987ZW)")

        ajeno = fabricas.crear_vehiculo()
        self.assertError(
            self.cliente_api.post(
                f"/api/clientes/{self.cliente.id}/polizas/",
                {**cuerpo, "vehiculo_id": ajeno.id}, format="json",
            ),
            400, "datos_invalidos",
        )

    # AC-T2-28
    def test_la_ruta_de_companias_esta_en_la_lista_blanca_de_paginas(self):
        self.assertEqual(paginas._PAGINAS["/panel/companias/"], "companias.html")
        esperado = settings.BASE_DIR / "frontend" / "pages" / "companias.html"
        self.assertTrue(esperado.exists(), "falta companias.html")
        respuesta = self.client.get("/panel/companias/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(b"".join(respuesta.streaming_content), esperado.read_bytes())
