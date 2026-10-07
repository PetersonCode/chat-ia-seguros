import { api } from "./api.js";

const contadores = [
    { clave: "acciones", etiqueta: "Acciones", destino: "/panel/acciones/" },
    { clave: "derivaciones", etiqueta: "Derivaciones", destino: "/panel/derivaciones/" },
    { clave: "alertas_criticas", etiqueta: "Alertas críticas", destino: "/panel/alertas/?severidad=critica" },
];

const destinos = [
    { etiqueta: "Bandeja", destino: "/panel/" },
    { etiqueta: "Clientes", destino: "/panel/clientes/" },
    { etiqueta: "Casos cerrados", destino: "/panel/cerrados/" },
];

function crearElemento(etiqueta, clase, texto) {
    const elemento = document.createElement(etiqueta);
    if (clase) {
        elemento.className = clase;
    }
    if (texto !== undefined) {
        elemento.textContent = texto;
    }
    return elemento;
}

function mostrarError(nav, mensaje) {
    let alerta = nav.querySelector("[data-nav-error]");
    if (!alerta) {
        alerta = crearElemento("div", "alert alert-danger mb-0", mensaje);
        alerta.dataset.navError = "true";
        alerta.setAttribute("role", "alert");
        nav.append(alerta);
    } else {
        alerta.textContent = mensaje;
    }
}

function limpiarError(nav) {
    nav.querySelector("[data-nav-error]")?.remove();
}

/**
 * Solicita a la barra superior que vuelva a leer los contadores pendientes.
 */
export function notificarActualizacionPendientes() {
    document.dispatchEvent(new Event("pendientes:actualizar"));
}

function crearNavegacion(nav) {
    nav.className = "navbar navbar-expand-lg bg-white border-bottom px-3";
    const contenedor = crearElemento("div", "container-fluid");
    const marca = crearElemento("a", "navbar-brand fw-semibold", "Seguros Castaño");
    marca.href = "/panel/";
    const usuario = crearElemento("span", "navbar-text ms-auto me-3");
    usuario.dataset.usuario = "true";
    const lista = crearElemento("ul", "navbar-nav flex-row flex-wrap gap-2 gap-lg-3 align-items-center");
    const enlaces = new Map();

    for (const destino of destinos) {
        const item = crearElemento("li", "nav-item");
        const enlace = crearElemento("a", "nav-link", destino.etiqueta);
        enlace.href = destino.destino;
        item.append(enlace);
        lista.append(item);
    }

    for (const contador of contadores) {
        const item = crearElemento("li", "nav-item");
        const enlace = crearElemento("a", "nav-link");
        enlace.href = contador.destino;
        enlace.append(document.createTextNode(`${contador.etiqueta} `));
        const badge = crearElemento("span", "badge text-bg-secondary", "—");
        badge.dataset.contador = contador.clave;
        enlace.append(badge);
        item.append(enlace);
        lista.append(item);
        enlaces.set(contador.clave, badge);
    }

    const salida = crearElemento("button", "btn btn-outline-secondary btn-sm", "Salir");
    salida.type = "button";
    salida.addEventListener("click", async () => {
        salida.disabled = true;
        try {
            await api.post("/api/auth/logout/");
            globalThis.location.assign("/");
        } catch (error) {
            mostrarError(nav, error.mensaje ?? "No se pudo cerrar la sesión.");
            salida.disabled = false;
        }
    });

    contenedor.append(marca, usuario, lista, salida);
    nav.replaceChildren(contenedor);
    return { usuario, enlaces };
}

function actualizarContadores(enlaces, pendientes) {
    for (const { clave } of contadores) {
        const valor = pendientes[clave];
        enlaces.get(clave).textContent = Number.isFinite(valor) ? String(valor) : "—";
    }
}

/**
 * Carga el funcionario y los contadores, y los actualiza cada 30 segundos.
 * @param {HTMLElement} nav
 */
export async function inicializarNav(nav = document.getElementById("nav")) {
    if (!nav) {
        throw new Error('No se encontró el elemento de navegación "#nav".');
    }
    const elementos = crearNavegacion(nav);

    const cargarDatos = async () => {
        try {
            const [me, pendientes] = await Promise.all([
                api.get("/api/auth/me/"),
                api.get("/api/pendientes/"),
            ]);
            elementos.usuario.textContent = me.nombre;
            actualizarContadores(elementos.enlaces, pendientes);
            limpiarError(nav);
        } catch (error) {
            mostrarError(nav, error.mensaje ?? "No se pudo cargar la información de navegación.");
        }
    };

    document.addEventListener("pendientes:actualizar", cargarDatos);
    await cargarDatos();
    globalThis.setInterval(cargarDatos, 30_000);
}
