import { api } from "../api.js?v=20261026fix2";
import { inicializarNav, notificarActualizacionPendientes } from "../nav.js?v=20261026fix2";
import { armarQuery } from "../lib/consulta.js?v=20261026fix2";
import { describirAccion, faltantes } from "../lib/acciones.js?v=20261026fix2";
import { formatearFechaHora } from "../lib/formato.js?v=20261026fix2";
import { crearTarjeta, crearTarjetaVacia } from "../lib/tarjetas.js?v=20261026fix2";

const estado = document.getElementById("estado-acciones");
const filtroEstado = document.getElementById("filtro-estado-acciones");
const estadoInicial = new URLSearchParams(globalThis.location.search).get("estado");
if (["pendiente", "aprobada", "ejecutada", "rechazada"].includes(estadoInicial)) {
    filtroEstado.value = estadoInicial;
}
const carga = document.getElementById("carga-acciones");
const total = document.getElementById("total-acciones");
const filas = document.getElementById("filas-acciones");
const paginaTexto = document.getElementById("pagina-acciones");
const botonAnterior = document.getElementById("acciones-anterior");
const botonSiguiente = document.getElementById("acciones-siguiente");
const panelDetalle = document.getElementById("detalle-accion");
const descripcionDetalle = document.getElementById("descripcion-accion");
const estadoDetalle = document.getElementById("estado-detalle-accion");
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
const botonAprobar = document.getElementById("aprobar-accion");
const botonFinalizar = document.getElementById("finalizar-accion");
const finalizacionDetalle = document.getElementById("finalizacion-accion");
const campoReferencia = document.getElementById("campo-referencia-finalizacion");
const referenciaFinalizacion = document.getElementById("referencia-finalizacion");

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
    poliza: "Póliza",
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

/** Marca la tarjeta cuyo detalle se está viendo al lado. */
function marcarSeleccionada(id) {
    for (const tarjeta of filas.querySelectorAll(".tarjeta")) {
        tarjeta.classList.toggle("seleccionada", tarjeta.dataset.id === String(id));
    }
}

function crearTarjetaAccion(accion) {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "btn btn-sm btn-outline-primary";
    boton.textContent = "Ver detalle";
    boton.addEventListener("click", () => {
        marcarSeleccionada(accion.id);
        cargarDetalle(accion.id);
    });

    const tarjeta = crearTarjeta({
        titulo: describirAccion(accion),
        subtitulo: accion.cliente
            ? [accion.cliente.nombre, accion.cliente.apellido].filter(Boolean).join(" ")
            : "Contacto desconocido",
        clase: "tarjeta-azul",
        datos: [
            [
                "Estado",
                accion.estado === "aprobada"
                    ? "Aprobada · gestión externa pendiente"
                    : ({ pendiente: "Pendiente de aprobación", ejecutada: "Completada", rechazada: "Rechazada" }[accion.estado] ?? accion.estado),
            ],
            ["Solicitada", antiguedad(accion.solicitada_en)],
        ],
        acciones: [boton],
    });
    tarjeta.dataset.id = String(accion.id);
    return tarjeta;
}

function actualizarPaginacion(datos) {
    paginaSeleccionada = datos.pagina;
    paginasTotales = Math.max(1, Math.ceil(datos.total / datos.por_pagina));
    total.textContent = `${datos.total} ${datos.total === 1 ? "acción" : "acciones"}`;
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
            estado: filtroEstado.value,
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
            filas.append(crearTarjetaVacia(
                {
                    aprobada: "No hay acciones aprobadas pendientes de gestión externa.",
                    pendiente: "No hay acciones pendientes de aprobación.",
                    ejecutada: "No hay gestiones completadas.",
                    rechazada: "No hay acciones rechazadas.",
                }[filtroEstado.value] ?? "No hay acciones para este filtro.",
            ));
        } else {
            filas.append(...datos.resultados.map(crearTarjetaAccion));
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

function crearCampoParametro(clave, accion) {
    const contenedor = document.createElement("div");
    contenedor.className = "mb-3";
    const label = document.createElement("label");
    label.className = "form-label";
    label.htmlFor = `parametro-${clave}`;
    label.textContent = etiquetasParametros[clave] ?? clave;

    const input = clave === "poliza"
        ? document.createElement("select")
        : document.createElement(clave === "descripcion" ? "textarea" : "input");
    input.id = `parametro-${clave}`;
    input.name = clave;
    input.className = clave === "poliza" ? "form-select" : "form-control";
    input.required = true;
    if (clave === "poliza") {
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Seleccioná una póliza";
        input.append(placeholder);
        for (const poliza of accion.polizas_disponibles ?? []) {
            const opcion = document.createElement("option");
            opcion.value = String(poliza.id);
            opcion.textContent = poliza.bien_asegurado
                ? `${poliza.numero_poliza} · ${poliza.bien_asegurado}`
                : poliza.numero_poliza;
            input.append(opcion);
        }
    } else if (clave === "importe") {
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
    estadoDetalle.hidden = accion.estado !== "aprobada";
    if (accion.estado === "aprobada") {
        estadoDetalle.textContent = accion.tipo_accion === "reembolso"
            ? "Aprobada; el reembolso todavía no se realizó y queda pendiente de gestión externa."
            : accion.tipo_accion === "modificar_poliza"
                ? "Aprobada; el cambio todavía no se aplicó y queda pendiente de gestión externa."
                : "Aprobada; pendiente de gestión externa.";
    }
    clienteDetalle.textContent = accion.cliente
        ? `Cliente: ${[accion.cliente.nombre, accion.cliente.apellido].filter(Boolean).join(" ")}`
        : "Cliente: Contacto desconocido";
    botonFinalizar.hidden = !funcionario.puede_aprobar || accion.estado !== "aprobada"
        || !["reembolso", "modificar_poliza"].includes(accion.tipo_accion);
    finalizacionDetalle.hidden = !accion.finalizacion;
    finalizacionDetalle.textContent = accion.finalizacion
        ? `Gestión completada por ${accion.finalizacion.funcionario.nombre} el ${formatearFechaHora(accion.finalizacion.fecha)}. Referencia: ${accion.finalizacion.referencia}. ${accion.finalizacion.motivo}`
        : "";

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
    const polizaNoDisponible = campos.includes("poliza")
        && Boolean(accion.poliza_no_disponible || !accion.polizas_disponibles?.length);
    camposFaltantes.replaceChildren(...campos.map((clave) => crearCampoParametro(clave, accion)));
    const pendiente = accion.estado === "pendiente";
    formularioParametros.hidden = campos.length === 0
        || !funcionario.puede_aprobar
        || !pendiente
        || polizaNoDisponible;
    avisoParametros.hidden = !pendiente
        || (campos.length === 0 && !accion.poliza_no_disponible)
        || (funcionario.puede_aprobar && !polizaNoDisponible);
    avisoParametros.textContent = polizaNoDisponible
        ? accion.poliza_no_disponible || "No hay pólizas disponibles para seleccionar."
        : campos.length > 0 && !funcionario.puede_aprobar
            ? "Faltan datos requeridos. Solo un aprobador puede completarlos."
            : "";
    botonesResolucion.hidden = !funcionario.puede_aprobar || !pendiente;
    botonAprobar.hidden = polizaNoDisponible;
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
    const campos = [...camposFaltantes.querySelectorAll("input, textarea, select")];
    const parametros = {};
    for (const campo of campos) {
        const valor = campo.value.trim();
        if (!valor) {
            throw new Error(`${etiquetasParametros[campo.name] ?? campo.name} es obligatorio.`);
        }
        if (campo.name === "poliza") {
            const id = Number(valor);
            if (!Number.isSafeInteger(id) || id <= 0) {
                throw new Error("Seleccioná una póliza válida.");
            }
            parametros[campo.name] = id;
        } else if (campo.name === "importe") {
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
    referenciaFinalizacion.value = "";
    campoReferencia.hidden = resolucion !== "finalizar";
    motivoResolucion.required = resolucion !== "aprobar";
    if (resolucion === "aprobar") {
        tituloDialogo.textContent = "Aprobar acción";
        descripcionDialogo.textContent = "¿Confirmás la aprobación de esta acción?";
        labelMotivo.textContent = "Motivo (opcional)";
    } else if (resolucion === "finalizar") {
        tituloDialogo.textContent = "Registrar gestión completada";
        descripcionDialogo.textContent = "Confirmá que la gestión ya se completó fuera del sistema e indicá la evidencia. Este registro no mueve dinero ni modifica contratos externos.";
        labelMotivo.textContent = "Detalle de lo realizado";
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
    if (resolucionSeleccionada !== "aprobar" && motivo.length < 3) {
        errorResolucion.textContent = "Indicá un motivo de al menos 3 caracteres.";
        return;
    }
    if (resolucionSeleccionada === "finalizar" && referenciaFinalizacion.value.trim().length < 3) {
        errorResolucion.textContent = "La referencia del trámite es obligatoria (mínimo 3 caracteres).";
        return;
    }

    botonConfirmar.disabled = true;
    errorResolucion.textContent = "";
    const id = accionSeleccionada.id;
    try {
        const ruta = `/api/acciones/${id}/${resolucionSeleccionada}/`;
        let resultado;
        if (resolucionSeleccionada === "aprobar" && !motivo) {
            resultado = await api.post(ruta);
        } else {
            resultado = await api.post(ruta, {
                motivo,
                ...(resolucionSeleccionada === "finalizar" ? { referencia: referenciaFinalizacion.value.trim() } : {}),
            });
        }
        dialogo.close();
        panelDetalle.hidden = true;
        accionSeleccionada = null;
        mostrarEstado(
            resolucionSeleccionada === "rechazar"
                ? "Acción rechazada."
                : resolucionSeleccionada === "finalizar"
                    ? "Gestión completada y registrada con su referencia."
                : resultado.estado === "aprobada"
                    ? "Acción aprobada; pendiente de gestión externa."
                    : "Acción aprobada y ejecutada.",
        );
        notificarActualizacionPendientes();
        await cargarAcciones(paginaSeleccionada);
    } catch (error) {
        errorResolucion.textContent = error.mensaje ?? error.message ?? "No se pudo resolver la acción.";
    } finally {
        botonConfirmar.disabled = false;
    }
}

formularioParametros.addEventListener("submit", guardarParametros);
filtroEstado.addEventListener("change", () => {
    panelDetalle.hidden = true;
    accionSeleccionada = null;
    cargarAcciones(1);
});
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
botonFinalizar.addEventListener("click", () => abrirDialogoResolucion("finalizar"));
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
