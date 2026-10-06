import { api } from "../api.js";
import { inicializarNav, notificarActualizacionPendientes } from "../nav.js";
import { formatearFechaHora } from "../lib/formato.js";

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

function crearTarjeta(derivacion) {
    const columna = crearElemento("div", "col-12 col-lg-6 col-xxl-4");
    const tarjeta = crearElemento(
        "article",
        `card shadow-sm h-100 ${derivacion.prioridad === "urgente" ? "derivacion-urgente" : ""}`.trim(),
    );
    const cuerpo = crearElemento("div", "card-body");
    const encabezado = crearElemento("div", "d-flex justify-content-between align-items-start gap-2 mb-2");
    encabezado.append(crearElemento("h2", "h5 mb-0", `Caso ${derivacion.consulta_id}`));
    if (derivacion.prioridad === "urgente") {
        encabezado.append(crearElemento("span", "badge text-bg-danger", "Urgente"));
    } else {
        encabezado.append(crearElemento("span", "badge text-bg-secondary", "Normal"));
    }
    cuerpo.append(encabezado);
    cuerpo.append(crearElemento("p", "mb-2", derivacion.motivo));
    cuerpo.append(crearElemento("p", "small text-muted", `Derivada: ${formatearFechaHora(derivacion.creada_en)}`));

    const acciones = crearElemento("div", "d-flex justify-content-between align-items-center gap-2");
    const enlace = crearElemento("a", "btn btn-sm btn-outline-primary", "Abrir conversación");
    enlace.href = `/panel/conversacion/?id=${encodeURIComponent(derivacion.conversacion_id)}`;
    const boton = crearElemento("button", "btn btn-sm btn-success", "Marcar atendida");
    boton.type = "button";
    boton.addEventListener("click", () => marcarAtendida(derivacion.id, boton));
    acciones.append(enlace, boton);
    cuerpo.append(acciones);
    tarjeta.append(cuerpo);
    columna.append(tarjeta);
    return columna;
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
            lista.append(crearTarjeta(derivacion));
        }
        if (ordenadas.length === 0) {
            lista.append(crearElemento("p", "col-12 text-muted", "No hay derivaciones pendientes."));
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
