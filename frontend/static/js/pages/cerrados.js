import { api } from "../api.js";
import { inicializarNav, notificarActualizacionPendientes } from "../nav.js";

const filas = document.getElementById("filas-casos");
const estado = document.getElementById("estado-casos");
const total = document.getElementById("total-casos");
const paginaTexto = document.getElementById("pagina-casos");
const botonAnterior = document.getElementById("casos-anterior");
const botonSiguiente = document.getElementById("casos-siguiente");

let paginaSeleccionada = 1;
let paginasTotales = 1;
let funcionario = null;
let solicitudActual = 0;

function crearCelda(texto) {
    const celda = document.createElement("td");
    celda.textContent = texto ?? "—";
    return celda;
}

function crearFila(caso) {
    const fila = document.createElement("tr");
    fila.append(crearCelda(caso.codigo_caso));
    fila.append(crearCelda(caso.cliente
        ? [caso.cliente.nombre, caso.cliente.apellido].filter(Boolean).join(" ")
        : "Contacto desconocido"));
    fila.append(crearCelda(caso.tipo_consulta));
    fila.append(crearCelda(String(caso.alertas_abiertas)));
    fila.append(crearCelda(caso.severidad_maxima));

    const enlace = document.createElement("a");
    enlace.href = `/panel/conversacion/?id=${encodeURIComponent(caso.conversacion_id)}`;
    enlace.textContent = "Abrir conversación";
    const celdaEnlace = document.createElement("td");
    celdaEnlace.append(enlace);
    fila.append(celdaEnlace);

    const celdaAccion = document.createElement("td");
    if (funcionario.puede_aprobar) {
        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "btn btn-sm btn-outline-primary";
        boton.textContent = "Reabrir";
        boton.addEventListener("click", () => reabrirCaso(caso.id, boton));
        celdaAccion.append(boton);
    } else {
        celdaAccion.textContent = "—";
    }
    fila.append(celdaAccion);
    return fila;
}

function actualizarPaginacion(datos) {
    paginaSeleccionada = datos.pagina;
    paginasTotales = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    total.textContent = `${datos.total} caso${datos.total === 1 ? "" : "s"}`;
    paginaTexto.textContent = `Página ${paginaSeleccionada} de ${paginasTotales}`;
    botonAnterior.disabled = paginaSeleccionada <= 1;
    botonSiguiente.disabled = paginaSeleccionada >= paginasTotales;
}

async function cargarCasos(pagina = paginaSeleccionada) {
    paginaSeleccionada = pagina;
    const idSolicitud = ++solicitudActual;
    estado.textContent = "Cargando casos…";
    estado.className = "px-3 pt-3 mb-0 text-muted";
    filas.replaceChildren();

    try {
        const datos = await api.get(`/api/consultas/cerradas-con-alertas/?pagina=${paginaSeleccionada}`);
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
            throw new Error("La respuesta de casos cerrados no tiene el formato esperado.");
        }

        if (datos.resultados.length === 0) {
            const filaVacia = document.createElement("tr");
            const celda = crearCelda("No hay casos cerrados con alertas abiertas.");
            celda.colSpan = 7;
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
        estado.textContent = error.mensaje ?? error.message ?? "No se pudieron cargar los casos.";
        estado.className = "px-3 pt-3 mb-0 text-danger";
        total.textContent = "";
        paginaTexto.textContent = "";
    }
}

async function reabrirCaso(id, boton) {
    boton.disabled = true;
    estado.textContent = "";
    try {
        await api.post(`/api/consultas/${id}/reabrir/`);
        notificarActualizacionPendientes();
        estado.textContent = "Caso reabierto.";
        estado.className = "px-3 pt-3 mb-0 text-success";
        await cargarCasos(paginaSeleccionada);
    } catch (error) {
        estado.textContent = error.mensaje ?? error.message ?? "No se pudo reabrir el caso.";
        estado.className = "px-3 pt-3 mb-0 text-danger";
        boton.disabled = false;
    }
}

botonAnterior.addEventListener("click", () => {
    if (paginaSeleccionada > 1) {
        cargarCasos(paginaSeleccionada - 1);
    }
});
botonSiguiente.addEventListener("click", () => {
    if (paginaSeleccionada < paginasTotales) {
        cargarCasos(paginaSeleccionada + 1);
    }
});

async function iniciar() {
    inicializarNav();
    try {
        funcionario = await api.get("/api/auth/me/");
        await cargarCasos();
    } catch (error) {
        estado.textContent = error.mensaje ?? error.message ?? "No se pudo cargar el usuario.";
        estado.className = "px-3 pt-3 mb-0 text-danger";
    }
}

iniciar();
