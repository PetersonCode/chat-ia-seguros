import { api } from "../api.js?v=20261029a";
import { claseSeveridad, etiquetaSeveridad } from "../lib/color.js?v=20261029a";
import { inicializarNav } from "../nav.js?v=20261029a";
import { claseTarjetaSeveridad, crearInsignia, crearTarjeta, crearTarjetaVacia } from "../lib/tarjetas.js?v=20261029a";
import { armarQuery } from "../lib/consulta.js?v=20261029a";
import { formatearFechaHora } from "../lib/formato.js?v=20261029a";

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

function crearTarjetaAlerta(alerta) {
    const enlace = `/panel/conversacion/?id=${encodeURIComponent(alerta.conversacion_id)}`;
    const abrir = document.createElement("a");
    abrir.href = enlace;
    abrir.className = "btn btn-sm btn-outline-primary";
    abrir.textContent = "Abrir conversación";
    return crearTarjeta({
        titulo: alerta.tipo,
        enlace,
        subtitulo: `${formatearFechaHora(alerta.creada_en)} · Conversación ${alerta.conversacion_id}`,
        clase: claseTarjetaSeveridad(alerta.severidad),
        insignias: [crearInsignia(etiquetaSeveridad(alerta.severidad), claseSeveridad(alerta.severidad))],
        texto: alerta.descripcion,
        acciones: [abrir],
    });
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
            filas.append(crearTarjetaVacia("No se encontraron alertas abiertas."));
        } else {
            filas.append(...datos.resultados.map(crearTarjetaAlerta));
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
