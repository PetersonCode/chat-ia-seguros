import { api } from "../api.js?v=20261104integrado1";
import { inicializarNav } from "../nav.js?v=20261104integrado1";
import { claseSeveridad, etiquetaSeveridad } from "../lib/color.js?v=20261104integrado1";
import { claseTarjeta, crearInsignia, crearTarjeta, crearTarjetaVacia } from "../lib/tarjetas.js?v=20261104integrado1";
import { armarQuery } from "../lib/consulta.js?v=20261104integrado1";
import { debounce } from "../lib/debounce.js?v=20261104integrado1";

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

const dialogoBorrar = document.getElementById("dialog-borrar");
const dialogoBorrarDescripcion = document.getElementById("dialog-borrar-descripcion");
const dialogoBorrarError = document.getElementById("dialog-borrar-error");
const dialogoBorrarCancelar = document.getElementById("dialog-borrar-cancelar");
const dialogoBorrarConfirmar = document.getElementById("dialog-borrar-confirmar");

let esAprobador = false;
let conversacionABorrar = null;
let paginaSeleccionada = 1;
let paginasTotales = 1;
let solicitudActual = 0;

function nombreCliente(cliente) {
    if (!cliente) {
        return "Contacto desconocido";
    }
    return [cliente.nombre, cliente.apellido].filter(Boolean).join(" ") || "Contacto desconocido";
}

/** La etiqueta de severidad, con la cantidad de alertas abiertas si hay. */
function insigniaSeveridad(conversacion) {
    if (conversacion.derivacion_urgente) {
        return crearInsignia("Derivación urgente", claseSeveridad("critica"));
    }
    const etiqueta = crearInsignia(
        etiquetaSeveridad(conversacion.severidad_maxima),
        claseSeveridad(conversacion.severidad_maxima),
    );
    if (Number.isInteger(conversacion.alertas_abiertas) && conversacion.alertas_abiertas > 0) {
        etiqueta.append(` · ${conversacion.alertas_abiertas}`);
    }
    return etiqueta;
}

function pedirBorrado(conversacion) {
    conversacionABorrar = conversacion;
    dialogoBorrarError.textContent = "";
    dialogoBorrarDescripcion.textContent =
        `Se borran para siempre la conversación con ${conversacion.whatsapp}, sus mensajes,`
        + " sus casos y sus alertas. No se puede deshacer. Si tiene acciones administrativas"
        + " o siniestros asociados, no se borra.";
    dialogoBorrar.showModal();
}

async function confirmarBorrado() {
    if (!conversacionABorrar) {
        return;
    }
    dialogoBorrarConfirmar.disabled = true;
    dialogoBorrarError.textContent = "";
    try {
        await api.post(`/api/conversaciones/${conversacionABorrar.id}/borrar/`);
        dialogoBorrar.close();
        conversacionABorrar = null;
        // Si se borró la última de la página, se vuelve a la anterior.
        await cargarConversaciones(
            filas.children.length <= 1 && paginaSeleccionada > 1
                ? paginaSeleccionada - 1
                : paginaSeleccionada,
        );
    } catch (error) {
        dialogoBorrarError.textContent = error.mensaje ?? error.message ?? "No se pudo borrar la conversación.";
    } finally {
        dialogoBorrarConfirmar.disabled = false;
    }
}

/** La tarjeta toma el color de la urgencia que calcula el servidor. */
function crearTarjetaConversacion(conversacion) {
    const enlace = `/panel/conversacion/?id=${encodeURIComponent(conversacion.id)}`;
    const ver = document.createElement("a");
    ver.href = enlace;
    ver.className = "btn btn-sm btn-outline-primary";
    ver.textContent = "Ver";
    ver.setAttribute("aria-label", `Abrir conversación ${conversacion.whatsapp}`);

    // Borrar es de aprobadores; la API lo exige igual, esto evita ofrecer un
    // botón que va a contestar 403.
    let borrar = null;
    if (esAprobador) {
        borrar = document.createElement("button");
        borrar.type = "button";
        borrar.className = "btn btn-sm btn-outline-danger";
        borrar.textContent = "Borrar";
        borrar.setAttribute("aria-label", `Borrar conversación ${conversacion.whatsapp}`);
        borrar.addEventListener("click", () => pedirBorrado(conversacion));
    }

    return crearTarjeta({
        titulo: nombreCliente(conversacion.cliente),
        enlace,
        subtitulo: conversacion.whatsapp,
        clase: claseTarjeta(conversacion.color),
        insignias: [
            insigniaSeveridad(conversacion),
            conversacion.sin_respuesta
                ? crearInsignia("Sin respuesta", "pildora pildora-aviso")
                : null,
        ],
        texto: conversacion.ultimo_mensaje?.texto ?? "Sin mensajes.",
        datos: [
            ["Estado", crearInsignia(conversacion.estado)],
            ["Modo", crearInsignia(
                conversacion.modo,
                conversacion.modo === "humano" ? "pildora pildora-activa" : "pildora",
            )],
            ["Atiende", conversacion.atendida_por?.nombre ?? "—"],
        ],
        acciones: [ver, borrar],
    });
}

function mostrarConversaciones(resultados) {
    filas.replaceChildren();
    if (resultados.length === 0) {
        filas.append(crearTarjetaVacia("No se encontraron conversaciones."));
        return;
    }
    filas.append(...resultados.map(crearTarjetaConversacion));
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

dialogoBorrarCancelar.addEventListener("click", () => dialogoBorrar.close());
dialogoBorrarConfirmar.addEventListener("click", confirmarBorrado);

inicializarNav();
// El botón de borrar depende del rol: se sabe antes de pintar las tarjetas. Si
// no se puede saber, la bandeja se muestra igual, sin el botón.
api.get("/api/auth/me/")
    .then((me) => {
        esAprobador = Boolean(me?.puede_aprobar);
    })
    .catch(() => {})
    .finally(() => cargarConversaciones());
