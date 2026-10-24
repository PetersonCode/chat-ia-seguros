import test from "node:test";
import assert from "node:assert/strict";

import { api, ApiError, configurarApi } from "../static/js/api.js";

function respuesta(status, cuerpo = null) {
    return {
        ok: status >= 200 && status < 300,
        status,
        async json() {
            return cuerpo;
        },
    };
}

test("AC-T1-02: get envía encabezados JSON y devuelve el cuerpo", async () => {
    let llamada;
    let cookieLeida;
    configurarApi({
        fetch: async (...argumentos) => {
            llamada = argumentos;
            return respuesta(200, { id: 1 });
        },
        leerCookie: (nombre) => {
            cookieLeida = nombre;
            return "token-csrf";
        },
    });

    assert.deepEqual(await api.get("/api/auth/me/"), { id: 1 });
    assert.equal(llamada[0], "/api/auth/me/");
    assert.equal(llamada[1].headers.Accept, "application/json");
    assert.equal(llamada[1].headers["Content-Type"], "application/json");
    assert.equal(llamada[1].headers["X-CSRFToken"], "token-csrf");
    assert.equal(cookieLeida, "csrftoken");
});

test("AC-T1-02: post y patch serializan sus cuerpos", async () => {
    const llamadas = [];
    configurarApi({
        fetch: async (...argumentos) => {
            llamadas.push(argumentos);
            return respuesta(200, { ok: true });
        },
        leerCookie: () => "csrf",
    });

    await api.post("/api/auth/login/", { email: "a@b.test", password: "clave" });
    await api.patch("/api/acciones/1/parametros/", { parametros: { detalle: "Dato" } });

    assert.equal(llamadas[0][1].method, "POST");
    assert.equal(llamadas[0][1].body, JSON.stringify({ email: "a@b.test", password: "clave" }));
    assert.equal(llamadas[0][1].headers["X-CSRFToken"], "csrf");
    assert.equal(llamadas[1][1].method, "PATCH");
    assert.equal(llamadas[1][1].body, JSON.stringify({ parametros: { detalle: "Dato" } }));
});

test("AC-T1-02: errores de API conservan status, codigo y mensaje", async () => {
    configurarApi({
        fetch: async () => respuesta(409, {
            error: { codigo: "estado_invalido", mensaje: "La acción ya fue resuelta." },
        }),
    });

    await assert.rejects(
        api.post("/api/acciones/1/aprobar/", {}),
        (error) => error instanceof ApiError
            && error.status === 409
            && error.codigo === "estado_invalido"
            && error.mensaje === "La acción ya fue resuelta.",
    );
});

test("AC-T1-02: una respuesta 401 redirige al login y lanza ApiError", async () => {
    let destino;
    configurarApi({
        fetch: async () => respuesta(401, {
            error: { codigo: "no_autenticado", mensaje: "Iniciá sesión." },
        }),
        redirigir: (ruta) => {
            destino = ruta;
        },
    });

    await assert.rejects(api.get("/api/auth/me/"), ApiError);
    assert.equal(destino, "/");
});
