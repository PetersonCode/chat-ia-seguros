import { api } from "../api.js";
import { inicializarNav } from "../nav.js";
import { armarQuery } from "../lib/consulta.js";
import { debounce } from "../lib/debounce.js";
import { limpiarDni, prellenadoDesdeUrl, validarCliente } from "../lib/clientes.js";

const formulario = document.getElementById("formulario-busqueda-clientes");
const campoBusqueda = document.getElementById("busqueda-clientes");
const estado = document.getElementById("estado-clientes");
const total = document.getElementById("total-clientes");
const filas = document.getElementById("filas-clientes");
const paginaTexto = document.getElementById("pagina-clientes");
const botonAnterior = document.getElementById("clientes-anterior");
const botonSiguiente = document.getElementById("clientes-siguiente");

const panelAlta = document.getElementById("panel-alta-cliente");
const formularioAlta = document.getElementById("formulario-alta-cliente");
const estadoAlta = document.getElementById("estado-alta-cliente");
const botonAlta = document.getElementById("alta-guardar");

const CAMPOS_ALTA = ["dni", "nombre", "apellido", "telefono", "email"];

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

    const celdaEstado = document.createElement("td");
    const insignia = document.createElement("span");
    const dadoDeBaja = cliente.activo === false;
    insignia.className = dadoDeBaja ? "badge text-bg-secondary" : "badge text-bg-success";
    insignia.textContent = dadoDeBaja ? "Dado de baja" : "Activo";
    celdaEstado.append(insignia);
    fila.append(celdaEstado);

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
            celda.colSpan = 6;
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

// --- Alta de cliente -----------------------------------------------------

function mostrarEstadoAlta(mensaje, error = false) {
    estadoAlta.textContent = mensaje;
    estadoAlta.classList.toggle("d-none", !mensaje);
    estadoAlta.classList.toggle("alert-danger", error);
    estadoAlta.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function pintarErrores(errores) {
    for (const campo of CAMPOS_ALTA) {
        const entrada = formularioAlta.elements[campo];
        const aviso = formularioAlta.querySelector(`[data-error="${campo}"]`);
        const mensaje = errores[campo];
        entrada.classList.toggle("is-invalid", Boolean(mensaje));
        if (aviso) {
            aviso.textContent = mensaje ?? "";
        }
    }
}

function datosDelFormulario() {
    const datos = {};
    for (const campo of CAMPOS_ALTA) {
        datos[campo] = formularioAlta.elements[campo].value.trim();
    }
    return datos;
}

formularioAlta.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const datos = datosDelFormulario();
    const errores = validarCliente(datos);
    pintarErrores(errores);
    if (Object.keys(errores).length > 0) {
        mostrarEstadoAlta("Revisá los campos marcados.", true);
        return;
    }

    botonAlta.disabled = true;
    mostrarEstadoAlta("Guardando…");
    try {
        const cliente = await api.post("/api/clientes/", {
            ...datos,
            dni: limpiarDni(datos.dni),
        });
        formularioAlta.reset();
        pintarErrores({});
        mostrarEstadoAlta(`Cliente ${cliente.nombre} ${cliente.apellido} dado de alta.`);
        panelAlta.open = false;
        await cargarClientes(1);
    } catch (error) {
        // La API es la que manda: un DNI o un teléfono repetidos solo se
        // detectan contra la base, el navegador no puede saberlo.
        mostrarEstadoAlta(error.mensaje ?? error.message ?? "No se pudo dar de alta al cliente.", true);
    } finally {
        botonAlta.disabled = false;
    }
});

formularioAlta.addEventListener("reset", () => {
    pintarErrores({});
    mostrarEstadoAlta("");
});

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

/**
 * Abre el alta con lo poco que se sabe del contacto cuando se llega desde una
 * conversación desconocida. No crea nada: los datos reales los carga la persona.
 */
function aplicarPrellenado() {
    const { telefono, nombre, apellido, hayDatos } = prellenadoDesdeUrl(
        globalThis.location.search,
    );
    if (!hayDatos) {
        return;
    }
    formularioAlta.elements.telefono.value = telefono;
    formularioAlta.elements.nombre.value = nombre;
    formularioAlta.elements.apellido.value = apellido;
    panelAlta.open = true;
    mostrarEstadoAlta("Completá DNI, nombre y apellido con los datos reales.");
    formularioAlta.elements.dni.focus();
}

inicializarNav();
aplicarPrellenado();
cargarClientes();
