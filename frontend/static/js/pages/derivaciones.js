import { api } from "../api.js?v=20261026fix2";
import { inicializarNav, notificarActualizacionPendientes } from "../nav.js?v=20261026fix2";
import { formatearFechaHora } from "../lib/formato.js?v=20261026fix2";
import { crearInsignia, crearTarjeta, crearTarjetaVacia } from "../lib/tarjetas.js?v=20261026fix2";

const lista = document.getElementById("lista-derivaciones");
const estado = document.getElementById("estado-derivaciones");
const total = document.getElementById("total-derivaciones");
const paginaTexto = document.getElementById("pagina-derivaciones");
const botonAnterior = document.getElementById("derivaciones-anterior");
const botonSiguiente = document.getElementById("derivaciones-siguiente");
let paginaSeleccionada = 1;
let paginasTotales = 1;
let solicitudActual = 0;

function mostrarEstado(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.classList.toggle("d-none", !mensaje);
    estado.classList.toggle("alert-danger", error);
    estado.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

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

function crearTarjetaDerivacion(derivacion) {
    const urgente = derivacion.prioridad === "urgente";
    const enlace = `/panel/conversacion/?id=${encodeURIComponent(derivacion.conversacion_id)}`;
    const abrir = crearElemento("a", "btn btn-sm btn-outline-primary", "Abrir conversación");
    abrir.href = enlace;
    const boton = crearElemento("button", "btn btn-sm btn-success", "Marcar atendida");
    boton.type = "button";
    boton.addEventListener("click", () => marcarAtendida(derivacion.id, boton));

    return crearTarjeta({
        titulo: `Caso ${derivacion.consulta_id}`,
        enlace,
        subtitulo: `Derivada ${formatearFechaHora(derivacion.creada_en)}`,
        clase: urgente ? "tarjeta-rojo" : "tarjeta-azul",
        insignias: [crearInsignia(
            urgente ? "Urgente" : "Normal",
            urgente ? "sev sev-critica" : "pildora",
        )],
        texto: derivacion.motivo,
        acciones: [abrir, boton],
    });
}

async function marcarAtendida(id, boton) {
    boton.disabled = true;
    mostrarEstado("");
    try {
        await api.post(`/api/derivaciones/${id}/atender/`);
        notificarActualizacionPendientes();
        const cargaCorrecta = await cargarDerivaciones(paginaSeleccionada);
        if (cargaCorrecta) {
            mostrarEstado("Derivación marcada como atendida.");
        }
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo marcar la derivación como atendida.", true);
        boton.disabled = false;
    }
}

async function cargarDerivaciones(pagina = paginaSeleccionada) {
    paginaSeleccionada = pagina;
    const idSolicitud = ++solicitudActual;
    lista.replaceChildren();
    mostrarEstado("Cargando derivaciones…");
    try {
        const datos = await api.get(`/api/derivaciones/?pagina=${paginaSeleccionada}`);
        if (idSolicitud !== solicitudActual) {
            return false;
        }
        if (
            !Array.isArray(datos.resultados)
            || !Number.isInteger(datos.total)
            || !Number.isInteger(datos.pagina)
            || !Number.isInteger(datos.por_pagina)
            || datos.por_pagina <= 0
        ) {
            throw new Error("La respuesta de derivaciones no tiene el formato esperado.");
        }
        const paginasRespuesta = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
        if (datos.pagina > paginasRespuesta) {
            return cargarDerivaciones(paginasRespuesta);
        }
        paginaSeleccionada = datos.pagina;
        paginasTotales = paginasRespuesta;
        total.textContent = `${datos.total} derivación${datos.total === 1 ? "" : "es"}`;
        paginaTexto.textContent = `Página ${paginaSeleccionada} de ${paginasTotales}`;
        botonAnterior.disabled = paginaSeleccionada <= 1;
        botonSiguiente.disabled = paginaSeleccionada >= paginasTotales;
        const ordenadas = datos.resultados
            .map((derivacion, indice) => ({ derivacion, indice }))
            .sort((a, b) => {
                const aUrgente = a.derivacion.prioridad === "urgente" ? 1 : 0;
                const bUrgente = b.derivacion.prioridad === "urgente" ? 1 : 0;
                return bUrgente - aUrgente || a.indice - b.indice;
            });
        for (const { derivacion } of ordenadas) {
            lista.append(crearTarjetaDerivacion(derivacion));
        }
        if (ordenadas.length === 0) {
            lista.append(crearTarjetaVacia("No hay derivaciones pendientes."));
        }
        mostrarEstado("");
        return true;
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudieron cargar las derivaciones.", true);
        total.textContent = "";
        paginaTexto.textContent = "";
        return false;
    }
}

botonAnterior.addEventListener("click", () => {
    if (paginaSeleccionada > 1) {
        cargarDerivaciones(paginaSeleccionada - 1);
    }
});
botonSiguiente.addEventListener("click", () => {
    if (paginaSeleccionada < paginasTotales) {
        cargarDerivaciones(paginaSeleccionada + 1);
    }
});

inicializarNav();
cargarDerivaciones();
