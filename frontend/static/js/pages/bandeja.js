import { api } from "../api.js";
import { inicializarNav } from "../nav.js";
import { claseDeColor } from "../lib/color.js";
import { armarQuery } from "../lib/consulta.js";
import { debounce } from "../lib/debounce.js";

const formulario = document.getElementById("formulario-filtros");
const campoEstado = document.getElementById("filtro-estado");
const campoBusqueda = document.getElementById("filtro-busqueda");
const campoAlertas = document.getElementById("filtro-alertas");
const campoHumano = document.getElementById("filtro-humano");
const filas = document.getElementById("filas-conversaciones");
const estadoCarga = document.getElementById("estado-carga");
const totalResultados = document.getElementById("total-resultados");
const paginaActual = document.getElementById("pagina-actual");
const botonAnterior = document.getElementById("pagina-anterior");
const botonSiguiente = document.getElementById("pagina-siguiente");

const etiquetasSeveridad = {
    baja: "Baja",
    media: "Media",
    alta: "Alta",
    critica: "Crítica",
};

let paginaSeleccionada = 1;
let paginasTotales = 1;
let solicitudActual = 0;

function crearCelda(texto) {
    const celda = document.createElement("td");
    celda.textContent = texto;
    return celda;
}

function nombreCliente(cliente) {
    if (!cliente) {
        return "Contacto desconocido";
    }
    return [cliente.nombre, cliente.apellido].filter(Boolean).join(" ") || "Contacto desconocido";
}

function enlaceConversacion(conversacion, texto, clase = "") {
    const enlace = document.createElement("a");
    enlace.href = `/panel/conversacion/?id=${encodeURIComponent(conversacion.id)}`;
    enlace.className = clase;
    enlace.textContent = texto;
    enlace.setAttribute("aria-label", `Abrir conversación ${conversacion.whatsapp}`);
    return enlace;
}

function crearFila(conversacion) {
    const fila = document.createElement("tr");
    fila.className = claseDeColor(conversacion.color);
    const numero = document.createElement("td");
    numero.append(enlaceConversacion(conversacion, conversacion.whatsapp));
    fila.append(numero);
    fila.append(crearCelda(nombreCliente(conversacion.cliente)));
    fila.append(crearCelda(conversacion.ultimo_mensaje?.texto ?? "—"));
    fila.append(crearCelda(conversacion.estado));
    fila.append(crearCelda(conversacion.modo));
    fila.append(crearCelda(conversacion.atendida_por?.nombre ?? "—"));

    const severidad = etiquetasSeveridad[conversacion.severidad_maxima] ?? "—";
    const celdaSeveridad = document.createElement("td");
    celdaSeveridad.textContent = severidad;
    if (Number.isInteger(conversacion.alertas_abiertas) && conversacion.alertas_abiertas > 0) {
        const cantidad = document.createElement("span");
        cantidad.className = "ms-1 small";
        cantidad.textContent = `(${conversacion.alertas_abiertas})`;
        celdaSeveridad.append(cantidad);
    }
    fila.append(celdaSeveridad);
    fila.append(crearCelda(conversacion.sin_respuesta ? "Sin respuesta" : "—"));

    const accion = document.createElement("td");
    accion.append(enlaceConversacion(conversacion, "Ver", "btn btn-sm btn-outline-primary"));
    fila.append(accion);
    return fila;
}

function mostrarConversaciones(resultados) {
    filas.replaceChildren();
    if (resultados.length === 0) {
        const filaVacia = document.createElement("tr");
        const celda = document.createElement("td");
        celda.colSpan = 9;
        celda.className = "text-center text-muted py-4";
        celda.textContent = "No se encontraron conversaciones.";
        filaVacia.append(celda);
        filas.append(filaVacia);
        return;
    }
    filas.append(...resultados.map(crearFila));
}

function filtrosActuales() {
    return {
        estado: campoEstado.value,
        con_alertas: campoAlertas.checked,
        esperando_humano: campoHumano.checked,
        q: campoBusqueda.value.trim(),
        pagina: paginaSeleccionada,
    };
}

function actualizarPaginacion(datos) {
    paginaSeleccionada = datos.pagina;
    paginasTotales = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    totalResultados.textContent = `${datos.total} conversación${datos.total === 1 ? "" : "es"}`;
    paginaActual.textContent = `Página ${paginaSeleccionada} de ${paginasTotales}`;
    botonAnterior.disabled = paginaSeleccionada <= 1;
    botonSiguiente.disabled = paginaSeleccionada >= paginasTotales;
}

async function cargarConversaciones(pagina = paginaSeleccionada) {
    paginaSeleccionada = pagina;
    const idSolicitud = ++solicitudActual;
    estadoCarga.textContent = "Cargando conversaciones…";
    estadoCarga.className = "px-3 pt-3 mb-0 text-muted";
    filas.replaceChildren();

    try {
        const datos = await api.get(`/api/conversaciones/${armarQuery(filtrosActuales())}`);
        if (idSolicitud !== solicitudActual) {
            return;
        }
        if (
            !Array.isArray(datos.resultados)
            || !Number.isInteger(datos.total)
            || !Number.isInteger(datos.pagina)
            || !Number.isInteger(datos.por_pagina)
            || datos.por_pagina <= 0
        ) {
            throw new Error("La respuesta de conversaciones no tiene el formato esperado.");
        }
        mostrarConversaciones(datos.resultados);
        actualizarPaginacion(datos);
        estadoCarga.textContent = "";
        estadoCarga.className = "px-3 pt-3 mb-0";
    } catch (error) {
        if (idSolicitud !== solicitudActual) {
            return;
        }
        estadoCarga.textContent = error.mensaje ?? error.message ?? "No se pudieron cargar las conversaciones.";
        estadoCarga.className = "px-3 pt-3 mb-0 text-danger";
        totalResultados.textContent = "";
        paginaActual.textContent = "";
    }
}

const buscarConDemora = debounce(() => cargarConversaciones(1), 300);

formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    cargarConversaciones(1);
});
campoBusqueda.addEventListener("input", buscarConDemora);
for (const filtro of [campoEstado, campoAlertas, campoHumano]) {
    filtro.addEventListener("change", () => cargarConversaciones(1));
}
botonAnterior.addEventListener("click", () => {
    if (paginaSeleccionada > 1) {
        cargarConversaciones(paginaSeleccionada - 1);
    }
});
botonSiguiente.addEventListener("click", () => {
    if (paginaSeleccionada < paginasTotales) {
        cargarConversaciones(paginaSeleccionada + 1);
    }
});

inicializarNav();
cargarConversaciones();
