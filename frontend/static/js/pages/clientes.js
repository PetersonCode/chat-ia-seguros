import { api } from "../api.js";
import { inicializarNav } from "../nav.js";
import { armarQuery } from "../lib/consulta.js";
import { debounce } from "../lib/debounce.js";

const formulario = document.getElementById("formulario-busqueda-clientes");
const campoBusqueda = document.getElementById("busqueda-clientes");
const estado = document.getElementById("estado-clientes");
const total = document.getElementById("total-clientes");
const filas = document.getElementById("filas-clientes");
const paginaTexto = document.getElementById("pagina-clientes");
const botonAnterior = document.getElementById("clientes-anterior");
const botonSiguiente = document.getElementById("clientes-siguiente");

let paginaSeleccionada = 1;
let paginasTotales = 1;
let solicitudActual = 0;

function dniLegible(dni) {
    return String(dni).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

function textoBusqueda() {
    const texto = campoBusqueda.value.trim();
    return /^\d[\d.]*$/.test(texto) ? texto.replaceAll(".", "") : texto;
}

function crearFila(cliente) {
    const fila = document.createElement("tr");
    const nombre = [cliente.nombre, cliente.apellido].filter(Boolean).join(" ");
    const celdaNombre = document.createElement("td");
    celdaNombre.textContent = nombre;
    fila.append(celdaNombre);

    const celdaDni = document.createElement("td");
    celdaDni.textContent = dniLegible(cliente.dni);
    fila.append(celdaDni);

    const celdaCorreo = document.createElement("td");
    celdaCorreo.textContent = cliente.email ?? "—";
    fila.append(celdaCorreo);

    const celdaPolizas = document.createElement("td");
    celdaPolizas.textContent = String(cliente.polizas_vigentes);
    fila.append(celdaPolizas);

    const celdaFicha = document.createElement("td");
    const enlace = document.createElement("a");
    enlace.href = `/panel/cliente/?id=${encodeURIComponent(cliente.id)}`;
    enlace.className = "btn btn-sm btn-outline-primary";
    enlace.textContent = "Ver ficha";
    celdaFicha.append(enlace);
    fila.append(celdaFicha);
    return fila;
}

function actualizarPaginacion(datos) {
    paginaSeleccionada = datos.pagina;
    paginasTotales = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    total.textContent = `${datos.total} cliente${datos.total === 1 ? "" : "s"}`;
    paginaTexto.textContent = `Página ${paginaSeleccionada} de ${paginasTotales}`;
    botonAnterior.disabled = paginaSeleccionada <= 1;
    botonSiguiente.disabled = paginaSeleccionada >= paginasTotales;
}

async function cargarClientes(pagina = paginaSeleccionada) {
    paginaSeleccionada = pagina;
    const idSolicitud = ++solicitudActual;
    estado.textContent = "Cargando clientes…";
    estado.className = "px-3 pt-3 mb-0 text-muted";
    filas.replaceChildren();
    try {
        const datos = await api.get(`/api/clientes/${armarQuery({
            q: textoBusqueda(),
            pagina: paginaSeleccionada,
        })}`);
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
            throw new Error("La respuesta de clientes no tiene el formato esperado.");
        }
        if (datos.resultados.length === 0) {
            const filaVacia = document.createElement("tr");
            const celda = document.createElement("td");
            celda.colSpan = 5;
            celda.className = "text-center text-muted py-4";
            celda.textContent = "No se encontraron clientes.";
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
        estado.textContent = error.mensaje ?? error.message ?? "No se pudieron cargar los clientes.";
        estado.className = "px-3 pt-3 mb-0 text-danger";
        total.textContent = "";
        paginaTexto.textContent = "";
    }
}

const buscarConDemora = debounce(() => cargarClientes(1), 300);

formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    cargarClientes(1);
});
campoBusqueda.addEventListener("input", buscarConDemora);
botonAnterior.addEventListener("click", () => {
    if (paginaSeleccionada > 1) {
        cargarClientes(paginaSeleccionada - 1);
    }
});
botonSiguiente.addEventListener("click", () => {
    if (paginaSeleccionada < paginasTotales) {
        cargarClientes(paginaSeleccionada + 1);
    }
});

inicializarNav();
cargarClientes();
