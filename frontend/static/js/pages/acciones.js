import { api } from "../api.js";
import { inicializarNav, notificarActualizacionPendientes } from "../nav.js";
import { armarQuery } from "../lib/consulta.js";
import { describirAccion, faltantes } from "../lib/acciones.js";
import { formatearFechaHora } from "../lib/formato.js";

const estado = document.getElementById("estado-acciones");
const carga = document.getElementById("carga-acciones");
const total = document.getElementById("total-acciones");
const filas = document.getElementById("filas-acciones");
const paginaTexto = document.getElementById("pagina-acciones");
const botonAnterior = document.getElementById("acciones-anterior");
const botonSiguiente = document.getElementById("acciones-siguiente");
const panelDetalle = document.getElementById("detalle-accion");
const descripcionDetalle = document.getElementById("descripcion-accion");
const clienteDetalle = document.getElementById("cliente-accion");
const listaParametros = document.getElementById("parametros-accion");
const formularioParametros = document.getElementById("formulario-parametros");
const camposFaltantes = document.getElementById("campos-faltantes");
const avisoParametros = document.getElementById("aviso-parametros");
const botonesResolucion = document.getElementById("acciones-resolucion");
const dialogo = document.getElementById("dialogo-resolucion");
const tituloDialogo = document.getElementById("titulo-dialogo-resolucion");
const descripcionDialogo = document.getElementById("descripcion-dialogo-resolucion");
const labelMotivo = document.getElementById("label-motivo");
const motivoResolucion = document.getElementById("motivo-resolucion");
const errorResolucion = document.getElementById("error-resolucion");
const botonCancelar = document.getElementById("cancelar-resolucion");
const botonConfirmar = document.getElementById("confirmar-resolucion");

let funcionario = null;
let accionSeleccionada = null;
let resolucionSeleccionada = null;
let paginaSeleccionada = 1;
let paginasTotales = 1;
let solicitudActual = 0;

const etiquetasParametros = {
    nombre: "Nombre del conductor",
    dni: "DNI del conductor",
    importe: "Importe del reembolso",
    detalle: "Detalle de la modificación",
    fecha_ocurrencia: "Fecha de ocurrencia",
    descripcion: "Descripción del siniestro",
    poliza: "Número de póliza",
};

function mostrarEstado(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.classList.toggle("d-none", !mensaje);
    estado.classList.toggle("alert-danger", error);
    estado.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function antiguedad(fecha) {
    const instante = Date.parse(fecha);
    if (!Number.isFinite(instante)) {
        return "—";
    }
    const minutos = Math.round((instante - Date.now()) / 60_000);
    const formato = new Intl.RelativeTimeFormat("es", { numeric: "auto" });
    if (Math.abs(minutos) < 60) {
        return formato.format(minutos, "minute");
    }
    const horas = Math.round(minutos / 60);
    if (Math.abs(horas) < 24) {
        return formato.format(horas, "hour");
    }
    return formato.format(Math.round(horas / 24), "day");
}

function crearCelda(texto) {
    const celda = document.createElement("td");
    celda.textContent = texto ?? "—";
    return celda;
}

function crearFila(accion) {
    const fila = document.createElement("tr");
    fila.append(crearCelda(describirAccion(accion)));
    fila.append(crearCelda(accion.cliente
        ? [accion.cliente.nombre, accion.cliente.apellido].filter(Boolean).join(" ")
        : "Contacto desconocido"));
    fila.append(crearCelda(antiguedad(accion.solicitada_en)));

    const celdaAccion = document.createElement("td");
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "btn btn-sm btn-outline-primary";
    boton.textContent = "Ver detalle";
    boton.addEventListener("click", () => cargarDetalle(accion.id));
    celdaAccion.append(boton);
    fila.append(celdaAccion);
    return fila;
}

function actualizarPaginacion(datos) {
    paginaSeleccionada = datos.pagina;
    paginasTotales = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    total.textContent = `${datos.total} acción${datos.total === 1 ? "" : "es"}`;
    paginaTexto.textContent = `Página ${paginaSeleccionada} de ${paginasTotales}`;
    botonAnterior.disabled = paginaSeleccionada <= 1;
    botonSiguiente.disabled = paginaSeleccionada >= paginasTotales;
}

async function cargarAcciones(pagina = paginaSeleccionada) {
    paginaSeleccionada = pagina;
    const idSolicitud = ++solicitudActual;
    carga.textContent = "Cargando acciones…";
    carga.className = "px-3 pt-3 mb-0 text-muted";
    filas.replaceChildren();

    try {
        const datos = await api.get(`/api/acciones/${armarQuery({
            estado: "pendiente",
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
            throw new Error("La respuesta de acciones no tiene el formato esperado.");
        }
        if (datos.resultados.length === 0) {
            const filaVacia = document.createElement("tr");
            const celda = crearCelda("No hay acciones pendientes.");
            celda.colSpan = 4;
            celda.className = "text-center text-muted py-4";
            filaVacia.append(celda);
            filas.append(filaVacia);
        } else {
            filas.append(...datos.resultados.map(crearFila));
        }
        actualizarPaginacion(datos);
        carga.textContent = "";
        carga.className = "px-3 pt-3 mb-0";
    } catch (error) {
        if (idSolicitud !== solicitudActual) {
            return;
        }
        carga.textContent = error.mensaje ?? error.message ?? "No se pudieron cargar las acciones.";
        carga.className = "px-3 pt-3 mb-0 text-danger";
        total.textContent = "";
        paginaTexto.textContent = "";
    }
}

function valorLegible(valor) {
    if (valor === null || valor === undefined || valor === "") {
        return "—";
    }
    return typeof valor === "object" ? JSON.stringify(valor) : String(valor);
}

function crearCampoParametro(clave) {
    const contenedor = document.createElement("div");
    contenedor.className = "mb-3";
    const label = document.createElement("label");
    label.className = "form-label";
    label.htmlFor = `parametro-${clave}`;
    label.textContent = etiquetasParametros[clave] ?? clave;

    const input = document.createElement(clave === "descripcion" ? "textarea" : "input");
    input.id = `parametro-${clave}`;
    input.name = clave;
    input.className = "form-control";
    input.required = true;
    if (clave === "importe") {
        input.type = "number";
        input.step = "0.01";
    } else if (clave === "fecha_ocurrencia") {
        input.type = "date";
    } else if (input instanceof HTMLTextAreaElement) {
        input.rows = 3;
    } else {
        input.type = "text";
    }
    contenedor.append(label, input);
    return contenedor;
}

function renderizarDetalle(accion) {
    accionSeleccionada = accion;
    panelDetalle.hidden = false;
    descripcionDetalle.textContent = describirAccion(accion);
    clienteDetalle.textContent = accion.cliente
        ? `Cliente: ${[accion.cliente.nombre, accion.cliente.apellido].filter(Boolean).join(" ")}`
        : "Cliente: Contacto desconocido";

    listaParametros.replaceChildren();
    for (const [clave, valor] of Object.entries(accion.parametros ?? {})) {
        const termino = document.createElement("dt");
        termino.className = "col-sm-5";
        termino.textContent = etiquetasParametros[clave] ?? clave;
        const definicion = document.createElement("dd");
        definicion.className = "col-sm-7";
        definicion.textContent = valorLegible(valor);
        listaParametros.append(termino, definicion);
    }
    if (accion.poliza) {
        const termino = document.createElement("dt");
        termino.className = "col-sm-5";
        termino.textContent = "Póliza";
        const definicion = document.createElement("dd");
        definicion.className = "col-sm-7";
        definicion.textContent = accion.poliza.numero_poliza;
        listaParametros.append(termino, definicion);
    }

    const campos = faltantes(accion);
    camposFaltantes.replaceChildren(...campos.map(crearCampoParametro));
    formularioParametros.hidden = campos.length === 0 || !funcionario.puede_aprobar;
    avisoParametros.hidden = campos.length === 0 || funcionario.puede_aprobar;
    avisoParametros.textContent = campos.length > 0 && !funcionario.puede_aprobar
        ? "Faltan datos requeridos. Solo un aprobador puede completarlos."
        : "";
    botonesResolucion.hidden = !funcionario.puede_aprobar;
}

async function cargarDetalle(id) {
    mostrarEstado("");
    try {
        const detalle = await api.get(`/api/acciones/${id}/`);
        renderizarDetalle(detalle);
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo cargar el detalle de la acción.", true);
    }
}

function parametrosCompletados() {
    const campos = [...camposFaltantes.querySelectorAll("input, textarea")];
    const parametros = {};
    for (const campo of campos) {
        const valor = campo.value.trim();
        if (!valor) {
            throw new Error(`${etiquetasParametros[campo.name] ?? campo.name} es obligatorio.`);
        }
        if (campo.name === "importe") {
            const importe = Number(valor);
            if (!Number.isFinite(importe)) {
                throw new Error("El importe debe ser un número válido.");
            }
            parametros[campo.name] = importe.toFixed(2);
        } else {
            parametros[campo.name] = valor;
        }
    }
    return parametros;
}

async function guardarParametros(evento) {
    evento.preventDefault();
    if (!accionSeleccionada || !funcionario.puede_aprobar) {
        return;
    }
    const boton = document.getElementById("guardar-parametros");
    boton.disabled = true;
    mostrarEstado("");
    try {
        const parametros = parametrosCompletados();
        const actualizada = await api.patch(
            `/api/acciones/${accionSeleccionada.id}/parametros/`,
            { parametros },
        );
        renderizarDetalle(actualizada);
        mostrarEstado("Parámetros guardados.");
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudieron guardar los parámetros.", true);
    } finally {
        boton.disabled = false;
    }
}

function abrirDialogoResolucion(resolucion) {
    resolucionSeleccionada = resolucion;
    errorResolucion.textContent = "";
    motivoResolucion.value = "";
    motivoResolucion.required = resolucion === "rechazar";
    if (resolucion === "aprobar") {
        tituloDialogo.textContent = "Aprobar acción";
        descripcionDialogo.textContent = "¿Confirmás la aprobación de esta acción?";
        labelMotivo.textContent = "Motivo (opcional)";
    } else {
        tituloDialogo.textContent = "Rechazar acción";
        descripcionDialogo.textContent = "Indicá el motivo del rechazo.";
        labelMotivo.textContent = "Motivo";
    }
    dialogo.showModal();
}

async function confirmarResolucion() {
    if (!accionSeleccionada || !resolucionSeleccionada) {
        return;
    }
    const motivo = motivoResolucion.value.trim();
    if (resolucionSeleccionada === "rechazar" && !motivo) {
        errorResolucion.textContent = "El motivo del rechazo es obligatorio.";
        return;
    }

    botonConfirmar.disabled = true;
    errorResolucion.textContent = "";
    const id = accionSeleccionada.id;
    try {
        const ruta = `/api/acciones/${id}/${resolucionSeleccionada}/`;
        if (resolucionSeleccionada === "aprobar" && !motivo) {
            await api.post(ruta);
        } else {
            await api.post(ruta, { motivo });
        }
        dialogo.close();
        panelDetalle.hidden = true;
        accionSeleccionada = null;
        mostrarEstado(resolucionSeleccionada === "aprobar" ? "Acción aprobada." : "Acción rechazada.");
        notificarActualizacionPendientes();
        await cargarAcciones(paginaSeleccionada);
    } catch (error) {
        errorResolucion.textContent = error.mensaje ?? error.message ?? "No se pudo resolver la acción.";
    } finally {
        botonConfirmar.disabled = false;
    }
}

formularioParametros.addEventListener("submit", guardarParametros);
botonAnterior.addEventListener("click", () => {
    if (paginaSeleccionada > 1) {
        cargarAcciones(paginaSeleccionada - 1);
    }
});
botonSiguiente.addEventListener("click", () => {
    if (paginaSeleccionada < paginasTotales) {
        cargarAcciones(paginaSeleccionada + 1);
    }
});
document.getElementById("aprobar-accion").addEventListener("click", () => abrirDialogoResolucion("aprobar"));
document.getElementById("rechazar-accion").addEventListener("click", () => abrirDialogoResolucion("rechazar"));
botonCancelar.addEventListener("click", () => dialogo.close());
botonConfirmar.addEventListener("click", confirmarResolucion);

async function iniciar() {
    inicializarNav();
    try {
        funcionario = await api.get("/api/auth/me/");
        await cargarAcciones();
    } catch (error) {
        carga.textContent = error.mensaje ?? error.message ?? "No se pudo cargar el usuario.";
        carga.className = "px-3 pt-3 mb-0 text-danger";
    }
}

iniciar();
