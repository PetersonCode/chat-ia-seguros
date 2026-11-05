/**
 * Error devuelto por la API del dashboard.
 */
export class ApiError extends Error {
    constructor(status, codigo, mensaje) {
        super(mensaje);
        this.name = "ApiError";
        this.status = status;
        this.codigo = codigo;
        this.mensaje = mensaje;
    }
}

function leerCookieDelNavegador(nombre) {
    if (typeof document === "undefined") {
        return null;
    }
    const prefijo = `${nombre}=`;
    const cookie = document.cookie
        .split(";")
        .map((parte) => parte.trim())
        .find((parte) => parte.startsWith(prefijo));
    return cookie ? decodeURIComponent(cookie.slice(prefijo.length)) : null;
}

let configuracion = {
    fetch: (...argumentos) => globalThis.fetch(...argumentos),
    leerCookie: leerCookieDelNavegador,
    redirigir: (ruta) => globalThis.location.assign(ruta),
};

/**
 * Inyecta dependencias para probar las solicitudes sin navegador ni red.
 * @param {{fetch?: typeof fetch, leerCookie?: (nombre: string) => string | null, redirigir?: (ruta: string) => void}} opciones
 */
export function configurarApi(opciones = {}) {
    configuracion = { ...configuracion, ...opciones };
}

async function solicitar(metodo, url, cuerpo, multipart = false) {
    const csrf = configuracion.leerCookie("csrftoken");
    const encabezados = {
        Accept: "application/json",
    };
    if (!multipart) encabezados["Content-Type"] = "application/json";
    if (csrf) {
        encabezados["X-CSRFToken"] = csrf;
    }

    const opciones = { method: metodo, headers: encabezados };
    if (cuerpo !== undefined) {
        opciones.body = multipart ? cuerpo : JSON.stringify(cuerpo);
    }

    let respuesta;
    try {
        respuesta = await configuracion.fetch(url, opciones);
    } catch {
        throw new ApiError(0, 'sin_conexion', 'No se pudo conectar con el servidor. Revisá la conexión e intentá nuevamente.');
    }
    if (respuesta.status === 204) {
        return null;
    }

    let datos;
    try { datos = await respuesta.json(); }
    catch {
        throw new ApiError(respuesta.status, 'respuesta_invalida', 'El servidor no pudo completar la solicitud. Intentá nuevamente.');
    }
    if (!respuesta.ok) {
        const detalle = datos?.error;
        const error = new ApiError(
            respuesta.status,
            detalle?.codigo ?? "error_http",
            detalle?.mensaje ?? "La solicitud no pudo completarse.",
        );
        if (respuesta.status === 401 && url.split('?')[0] !== '/api/auth/login/') {
            configuracion.redirigir("/");
        }
        throw error;
    }
    return datos;
}

export const api = {
    get(url) {
        return solicitar("GET", url);
    },
    post(url, cuerpo) {
        return solicitar("POST", url, cuerpo);
    },
    patch(url, cuerpo) {
        return solicitar("PATCH", url, cuerpo);
    },
    upload(url, formulario) {
        // El navegador agrega el boundary; se conserva el mismo control CSRF.
        return solicitar("POST", url, formulario, true);
    },
    /**
     * Baja un archivo y lo devuelve como `Blob`. Mismo manejo que el resto:
     * sin conexión, sesión vencida (vuelve al login) y error de la API.
     */
    async descargar(url) {
        let respuesta;
        try {
            // Acepta cualquier tipo: la respuesta buena es el archivo, no JSON.
            respuesta = await configuracion.fetch(url, { method: "GET", headers: { Accept: "*/*" } });
        } catch {
            throw new ApiError(0, 'sin_conexion', 'No se pudo conectar con el servidor. Revisá la conexión e intentá nuevamente.');
        }
        if (!respuesta.ok) {
            let detalle = null;
            try { detalle = (await respuesta.json())?.error ?? null; }
            catch { /* el error no vino en JSON: queda el mensaje genérico */ }
            if (respuesta.status === 401) {
                configuracion.redirigir("/");
            }
            throw new ApiError(
                respuesta.status,
                detalle?.codigo ?? "error_http",
                detalle?.mensaje ?? "No se pudo descargar el archivo.",
            );
        }
        return respuesta.blob();
    },
};
