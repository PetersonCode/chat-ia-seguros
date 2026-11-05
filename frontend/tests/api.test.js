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

test("adjuntos: upload conserva FormData y CSRF sin fijar el boundary", async () => {
    let opciones;
    configurarApi({
        fetch: async (url, datos) => { opciones = datos; return respuesta(201, { id: 2 }); },
        leerCookie: () => 'csrf-adjunto',
    });
    const formulario = new FormData();
    formulario.append('archivo', new Blob(['imagen ficticia'], { type: 'image/png' }), 'demo.png');
    assert.deepEqual(await api.upload('/api/siniestros/1/adjuntos/', formulario), { id: 2 });
    assert.equal(opciones.method, 'POST');
    assert.equal(opciones.body, formulario);
    assert.equal(opciones.headers['X-CSRFToken'], 'csrf-adjunto');
    assert.equal(opciones.headers['Content-Type'], undefined);
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

test('login incorrecto conserva el error sin recargar el formulario', async () => {
    let redirigio=false;
    configurarApi({fetch:async()=>respuesta(401,{error:{codigo:'credenciales_invalidas',mensaje:'Credenciales inválidas.'}}),
        redirigir:()=>{redirigio=true;}});
    await assert.rejects(api.post('/api/auth/login/',{}),e=>e.status===401 && e.mensaje==='Credenciales inválidas.');
    assert.equal(redirigio,false);
});

test('errores de red y páginas HTML de error dan un mensaje recuperable', async () => {
    configurarApi({fetch:async()=>{throw new TypeError('Failed to fetch');}});
    await assert.rejects(api.get('/api/clientes/'),e=>e.codigo==='sin_conexion' && e.status===0);
    configurarApi({fetch:async()=>({status:503,ok:false,json:async()=>{throw new SyntaxError('HTML');}})});
    await assert.rejects(api.get('/api/clientes/'),e=>e.codigo==='respuesta_invalida' && e.status===503);
});
