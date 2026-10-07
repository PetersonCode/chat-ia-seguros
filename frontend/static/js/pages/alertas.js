import { api } from "../api.js";
import { inicializarNav } from "../nav.js";
import { armarQuery } from "../lib/consulta.js";
import { formatearFechaHora } from "../lib/formato.js";

const formulario = document.getElementById("filtros-alertas");
const campoTipo = document.getElementById("filtro-tipo");
const campoSeveridad = document.getElementById("filtro-severidad");
const filas = document.getElementById("filas-alertas");
const estado = document.getElementById("estado-alertas");
const total = document.getElementById("total-alertas");
const paginaTexto = document.getElementById("pagina-alertas");
const botonAnterior = document.getElementById("alertas-anterior");
const botonSiguiente = document.getElementById("alertas-siguiente");

const filtrosIniciales = new URLSearchParams(globalThis.location.search);
if ([...campoTipo.options].some((opcion) => opcion.value === filtrosIniciales.get("tipo"))) {
    campoTipo.value = filtrosIniciales.get("tipo");
}
if ([...campoSeveridad.options].some((opcion) => opcion.value === filtrosIniciales.get("severidad"))) {
    campoSeveridad.value = filtrosIniciales.get("severidad");
}

let paginaSeleccionada = 1;
let paginasTotales = 1;
let solicitudActual = 0;

function crearCelda(texto) {
    const celda = document.createElement("td");
    celda.textContent = texto ?? "—";
    return celda;
}

function crearFila(alerta) {
    const fila = document.createElement("tr");
    fila.append(crearCelda(formatearFechaHora(alerta.creada_en)));
    fila.append(crearCelda(alerta.tipo));
    fila.append(crearCelda(alerta.severidad));
    fila.append(crearCelda(alerta.descripcion));

    const enlace = document.createElement("a");
    enlace.href = `/panel/conversacion/?id=${encodeURIComponent(alerta.conversacion_id)}`;
    enlace.textContent = `Abrir conversación ${alerta.conversacion_id}`;
    const celdaEnlace = document.createElement("td");
    celdaEnlace.append(enlace);
    fila.append(celdaEnlace);
    return fila;
}

function actualizarPaginacion(datos) {
    paginaSeleccionada = datos.pagina;
    paginasTotales = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    total.textContent = `${datos.total} alerta${datos.total === 1 ? "" : "s"}`;
    paginaTexto.textContent = `Página ${paginaSeleccionada} de ${paginasTotales}`;
    botonAnterior.disabled = paginaSeleccionada <= 1;
    botonSiguiente.disabled = paginaSeleccionada >= paginasTotales;
}

async function cargarAlertas(pagina = paginaSeleccionada) {
    paginaSeleccionada = pagina;
    const idSolicitud = ++solicitudActual;
    const query = armarQuery({
        tipo: campoTipo.value,
        severidad: campoSeveridad.value,
        pagina: paginaSeleccionada,
    });
    estado.textContent = "Cargando alertas…";
    estado.className = "px-3 pt-3 mb-0 text-muted";
    filas.replaceChildren();

    try {
        const datos = await api.get(`/api/alertas/${query}`);
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
            throw new Error("La respuesta de alertas no tiene el formato esperado.");
        }

        if (datos.resultados.length === 0) {
            const filaVacia = document.createElement("tr");
            const celda = crearCelda("No se encontraron alertas abiertas.");
            celda.colSpan = 5;
            celda.className = "text-center text-muted py-4";
            filaVacia.append(celda);
            filas.append(filaVacia);
        } else {
            filas.append(...datos.resultados.map(crearFila));
        }
        actualizarPaginacion(datos);
        estado.textContent = "";
        estado.className = "px-3 pt-3 mb-0";
    } catch (error) {
        if (idSolicitud !== solicitudActual) {
            return;
        }
        estado.textContent = error.mensaje ?? error.message ?? "No se pudieron cargar las alertas.";
        estado.className = "px-3 pt-3 mb-0 text-danger";
        total.textContent = "";
        paginaTexto.textContent = "";
    }
}

formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    cargarAlertas(1);
});
botonAnterior.addEventListener("click", () => {
    if (paginaSeleccionada > 1) {
        cargarAlertas(paginaSeleccionada - 1);
    }
});
botonSiguiente.addEventListener("click", () => {
    if (paginaSeleccionada < paginasTotales) {
        cargarAlertas(paginaSeleccionada + 1);
    }
});

inicializarNav();
cargarAlertas();
