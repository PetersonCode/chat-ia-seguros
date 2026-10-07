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

async function solicitar(metodo, url, cuerpo) {
    const csrf = configuracion.leerCookie("csrftoken");
    const encabezados = {
        Accept: "application/json",
        "Content-Type": "application/json",
    };
    if (csrf) {
        encabezados["X-CSRFToken"] = csrf;
    }

    const opciones = { method: metodo, headers: encabezados };
    if (cuerpo !== undefined) {
        opciones.body = JSON.stringify(cuerpo);
    }

    const respuesta = await configuracion.fetch(url, opciones);
    if (respuesta.status === 204) {
        return null;
    }

    const datos = await respuesta.json();
    if (!respuesta.ok) {
        const detalle = datos?.error;
        const error = new ApiError(
            respuesta.status,
            detalle?.codigo ?? "error_http",
            detalle?.mensaje ?? "La solicitud no pudo completarse.",
        );
        if (respuesta.status === 401) {
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
};
