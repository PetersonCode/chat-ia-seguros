import { api } from "./api.js?v=20261029a";

const contadores = [
    { clave: "acciones", etiqueta: "Acciones", destino: "/panel/acciones/" },
    { clave: "derivaciones", etiqueta: "Derivaciones", destino: "/panel/derivaciones/" },
    { clave: "alertas_criticas", etiqueta: "Alertas críticas", destino: "/panel/alertas/?severidad=critica" },
];

const destinos = [
    { etiqueta: "Bandeja", destino: "/panel/" },
    { etiqueta: "Clientes", destino: "/panel/clientes/" },
    { etiqueta: "Casos cerrados", destino: "/panel/cerrados/" },
    { etiqueta: "Métricas", destino: "/panel/metricas/" },
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

/** Marca el enlace de la sección donde está parado el funcionario.
 *
 * Compara solo la ruta: "Alertas críticas" apunta a `/panel/alertas/?severidad=…`
 * y tiene que marcarse igual cuando se está en esa página. Es solo estilo: el
 * enlace sigue llevando exactamente al mismo lado.
 */
function marcarSiEsLaActual(enlace, destino) {
    const ruta = destino.split("?")[0];
    if (globalThis.location?.pathname === ruta) {
        enlace.classList.add("activo");
        enlace.setAttribute("aria-current", "page");
    }
}

/** Las iniciales del funcionario, para el círculo de identidad. */
function iniciales(nombre) {
    return (nombre || "")
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((palabra) => palabra[0].toUpperCase())
        .join("");
}

/**
 * Arma la barra en tres grupos, de izquierda a derecha: a dónde ir, qué hay
 * pendiente, y quién soy.
 *
 * Antes iban todos mezclados en una sola fila —y el nombre del funcionario
 * quedaba en el medio, entre la marca y los enlaces—, así que no se distinguía
 * la navegación de los contadores ni el dato de los controles.
 */
function crearNavegacion(nav) {
    nav.className = "navbar bg-white border-bottom";
    const contenedor = crearElemento("div", "container-fluid barra");

    const marca = crearElemento("a", "navbar-brand", "Seguros Castaño");
    marca.href = "/panel/";

    // Grupo 1: navegación.
    const principal = crearElemento("ul", "navbar-nav nav-principal flex-row");
    for (const destino of destinos) {
        const item = crearElemento("li", "nav-item");
        const enlace = crearElemento("a", "nav-link", destino.etiqueta);
        enlace.href = destino.destino;
        marcarSiEsLaActual(enlace, destino.destino);
        item.append(enlace);
        principal.append(item);
    }

    // Grupo 2: pendientes. Son atajos con un número, no secciones: van juntos
    // y con otra forma para que no se confundan con la navegación.
    const enlaces = new Map();
    const pendientes = crearElemento("ul", "navbar-nav nav-pendientes flex-row");
    pendientes.setAttribute("aria-label", "Pendientes");
    for (const contador of contadores) {
        const item = crearElemento("li", "nav-item");
        const enlace = crearElemento("a", "nav-link nav-chip");
        enlace.href = contador.destino;
        marcarSiEsLaActual(enlace, contador.destino);
        enlace.append(crearElemento("span", "nav-chip-texto", contador.etiqueta));
        const numero = crearElemento("span", "nav-contador", "—");
        numero.dataset.contador = contador.clave;
        enlace.append(numero);
        item.append(enlace);
        pendientes.append(item);
        enlaces.set(contador.clave, numero);
    }

    // Grupo 3: identidad. El nombre es un dato, no un control: va sin borde ni
    // fondo, al lado de sus iniciales.
    const identidad = crearElemento("div", "nav-usuario");
    const avatar = crearElemento("span", "nav-avatar", "—");
    avatar.setAttribute("aria-hidden", "true");
    const usuario = crearElemento("span", "nav-usuario-nombre");
    usuario.dataset.usuario = "true";
    identidad.append(avatar, usuario);

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

    const derecha = crearElemento("div", "barra-derecha");
    derecha.append(
        pendientes,
        crearElemento("span", "nav-separador"),
        identidad,
        salida,
    );

    contenedor.append(marca, principal, derecha);
    nav.replaceChildren(contenedor);
    return { usuario, avatar, enlaces, principal };
}

function actualizarContadores(enlaces, pendientes) {
    for (const { clave, etiqueta } of contadores) {
        const valor = pendientes[clave];
        const hay = Number.isFinite(valor) && valor > 0;
        const numero = enlaces.get(clave);
        numero.textContent = Number.isFinite(valor) ? String(valor) : "—";
        // Un cero no es lo mismo que tres cosas sin atender: el color lo dice
        // sin que haya que leer el número.
        numero.className = "nav-contador";
        if (hay) {
            numero.classList.add(clave === "alertas_criticas" ? "urgente" : "hay");
        }
        numero.closest(".nav-chip")?.setAttribute(
            "aria-label",
            Number.isFinite(valor) ? `${etiqueta}: ${valor}` : etiqueta,
        );
    }
}

/**
 * Suma "Usuarios" a la navegación, una sola vez, si quien entró es el
 * propietario. Es solo para no mostrarle un enlace inútil al resto: quien
 * decide el acceso es la API, que a cualquier otro le contesta 403.
 */
function agregarSeccionPropietario(principal, me) {
    if (me?.rol !== "propietario" || principal.querySelector("[data-usuarios]")) {
        return;
    }
    const item = crearElemento("li", "nav-item");
    const enlace = crearElemento("a", "nav-link", "Usuarios");
    enlace.href = "/panel/usuarios/";
    enlace.dataset.usuarios = "true";
    marcarSiEsLaActual(enlace, "/panel/usuarios/");
    item.append(enlace);
    principal.append(item);
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
            elementos.avatar.textContent = iniciales(me.nombre) || "—";
            agregarSeccionPropietario(elementos.principal, me);
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
