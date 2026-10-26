import { api } from "../api.js?v=20261026fix2";
import { inicializarNav } from "../nav.js?v=20261026fix2";
import { crearTarjeta, crearTarjetaVacia } from "../lib/tarjetas.js?v=20261026fix2";

const formularioDenuncia = document.getElementById("formulario-denuncia");
const buscarCliente = document.getElementById("buscar-cliente-siniestro");
const botonBuscarCliente = document.getElementById("buscar-cliente-siniestro-boton");
const selectCliente = document.getElementById("cliente-siniestro");
const selectPoliza = document.getElementById("poliza-siniestro");
const fechaOcurrencia = document.getElementById("fecha-siniestro");
const descripcion = document.getElementById("descripcion-siniestro");
const vigencia = document.getElementById("vigencia-siniestro");
const estado = document.getElementById("estado-siniestros");
const carga = document.getElementById("carga-siniestros");
const filas = document.getElementById("filas-siniestros");
const filtroEstado = document.getElementById("filtro-siniestros");
const total = document.getElementById("total-siniestros");
const paginaTexto = document.getElementById("pagina-siniestros");
const anterior = document.getElementById("siniestros-anterior");
const siguiente = document.getElementById("siniestros-siguiente");
const panelDetalle = document.getElementById("detalle-siniestro");
const datosDetalle = document.getElementById("datos-detalle-siniestro");
const formularioAdjunto = document.getElementById("formulario-adjunto-siniestro");
const archivoAdjunto = document.getElementById("archivo-adjunto-siniestro");
const listaAdjuntos = document.getElementById("adjuntos-siniestro");
const adjuntosVacio = document.getElementById("adjuntos-siniestro-vacio");
const historial = document.getElementById("historial-siniestro");
const formularioTransicion = document.getElementById("formulario-transicion");
const estadoSiguiente = document.getElementById("estado-siguiente-siniestro");
const motivoDecision = document.getElementById("motivo-siniestro");
const mensajeSinTransicion = document.getElementById("sin-transiciones-siniestro");

const ETIQUETAS_ESTADO = {
    denunciado: "Denunciado",
    en_evaluacion: "En evaluación",
    aprobado: "Aprobado internamente",
    rechazado: "Rechazado",
    cerrado: "Cerrado",
};
const SIGUIENTES_ESTADOS = {
    denunciado: ["en_evaluacion"],
    en_evaluacion: ["aprobado", "rechazado"],
    aprobado: ["cerrado"],
    rechazado: ["cerrado"],
    cerrado: [],
};

let funcionario = null;
let paginaActual = 1;
let paginasTotales = 1;
let solicitudActual = 0;
let polizaSeleccionada = null;

function mostrarEstado(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.classList.toggle("d-none", !mensaje);
    estado.classList.toggle("alert-danger", error);
    estado.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function opcion(texto, valor = "") {
    const elemento = document.createElement("option");
    elemento.value = valor;
    elemento.textContent = texto;
    return elemento;
}

function nombreCliente(cliente) {
    return [cliente.nombre, cliente.apellido].filter(Boolean).join(" ");
}

async function cargarClientes() {
    const q = buscarCliente.value.trim();
    if (!q) {
        buscarCliente.focus();
        return;
    }
    botonBuscarCliente.disabled = true;
    selectCliente.disabled = true;
    selectCliente.replaceChildren(opcion("Buscando clientes…"));
    try {
        const respuesta = await api.get(`/api/clientes/?q=${encodeURIComponent(q)}`);
        selectCliente.replaceChildren(opcion("Seleccioná un cliente"));
        for (const cliente of respuesta.resultados) {
            const elemento = opcion(
                `${nombreCliente(cliente)} · DNI ${cliente.dni}`,
                String(cliente.id),
            );
            selectCliente.append(elemento);
        }
        selectCliente.disabled = respuesta.resultados.length === 0;
        if (!respuesta.resultados.length) {
            selectCliente.replaceChildren(opcion("No se encontraron clientes"));
            mostrarEstado("No se encontraron clientes con esos datos.", true);
        } else {
            mostrarEstado(
                respuesta.total > respuesta.resultados.length
                    ? `Se muestran ${respuesta.resultados.length} resultados; afiná la búsqueda para encontrar otro cliente.`
                    : "",
            );
        }
    } catch (error) {
        selectCliente.replaceChildren(opcion("No se pudieron cargar los clientes"));
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudieron buscar clientes.", true);
    } finally {
        botonBuscarCliente.disabled = false;
    }
}

async function cargarPolizasCliente() {
    selectPoliza.disabled = true;
    selectPoliza.replaceChildren(opcion("Cargando pólizas…"));
    fechaOcurrencia.disabled = true;
    fechaOcurrencia.value = "";
    polizaSeleccionada = null;
    vigencia.textContent = "";
    if (!selectCliente.value) {
        selectPoliza.replaceChildren(opcion("Primero seleccioná el cliente"));
        return;
    }
    try {
        const cliente = await api.get(`/api/clientes/${selectCliente.value}/`);
        selectPoliza.replaceChildren(opcion("Seleccioná una póliza"));
        for (const poliza of cliente.polizas) {
            const etiqueta = poliza.bien_asegurado
                ? `${poliza.numero_poliza} · ${poliza.bien_asegurado}`
                : poliza.numero_poliza;
            selectPoliza.append(opcion(etiqueta, String(poliza.id)));
        }
        if (!cliente.polizas.length) {
            selectPoliza.replaceChildren(opcion("Este cliente no tiene pólizas"));
        } else {
            selectPoliza.disabled = false;
        }
    } catch (error) {
        selectPoliza.replaceChildren(opcion("No se pudieron cargar las pólizas"));
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudieron cargar las pólizas.", true);
    }
}

async function cargarPolizaSeleccionada() {
    polizaSeleccionada = null;
    fechaOcurrencia.disabled = true;
    fechaOcurrencia.value = "";
    if (!selectPoliza.value) {
        return;
    }
    try {
        const poliza = await api.get(`/api/polizas/${selectPoliza.value}/`);
        polizaSeleccionada = poliza;
        fechaOcurrencia.min = poliza.fecha_inicio;
        fechaOcurrencia.max = poliza.fecha_vencimiento;
        fechaOcurrencia.disabled = false;
        vigencia.textContent =
            `La ocurrencia debe quedar dentro de la cobertura: ${poliza.fecha_inicio} a ${poliza.fecha_vencimiento}.`;
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo cargar la póliza.", true);
    }
}

function agregarDato(lista, titulo, valor) {
    const termino = document.createElement("dt");
    termino.className = "col-sm-5";
    termino.textContent = titulo;
    const detalle = document.createElement("dd");
    detalle.className = "col-sm-7";
    detalle.textContent = valor || "—";
    lista.append(termino, detalle);
}

function formatearFechaHora(valor) {
    const fecha = new Date(valor);
    if (!Number.isFinite(fecha.getTime())) {
        return "Fecha desconocida";
    }
    return new Intl.DateTimeFormat("es-AR", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(fecha);
}

function crearTarjetaSiniestro(siniestro) {
    const abrir = document.createElement("button");
    abrir.type = "button";
    abrir.className = "btn btn-sm btn-outline-primary";
    abrir.textContent = "Abrir expediente";
    abrir.addEventListener("click", () => cargarDetalle(siniestro.id));
    const tarjeta = crearTarjeta({
        titulo: `${siniestro.numero_siniestro} · ${ETIQUETAS_ESTADO[siniestro.estado]}`,
        subtitulo: `${nombreCliente(siniestro.cliente)} · ${siniestro.poliza.numero_poliza}`,
        clase: siniestro.estado === "cerrado" ? "tarjeta-apagada" : "tarjeta-azul",
        datos: [
            ["Ocurrencia", siniestro.fecha_ocurrencia],
            ["Denuncia", formatearFechaHora(siniestro.creado_en)],
        ],
        acciones: [abrir],
    });
    tarjeta.dataset.id = String(siniestro.id);
    return tarjeta;
}

function actualizarPaginacion(respuesta) {
    paginaActual = respuesta.pagina;
    paginasTotales = Math.max(1, Math.ceil(respuesta.total / respuesta.por_pagina));
    total.textContent = `${respuesta.total} expediente${respuesta.total === 1 ? "" : "s"}`;
    paginaTexto.textContent = `Página ${paginaActual} de ${paginasTotales}`;
    anterior.disabled = paginaActual <= 1;
    siguiente.disabled = paginaActual >= paginasTotales;
}

async function cargarSiniestros(pagina = paginaActual) {
    paginaActual = pagina;
    const solicitud = ++solicitudActual;
    carga.textContent = "Cargando expedientes…";
    carga.className = "px-3 pt-3 mb-0 text-muted";
    filas.replaceChildren();
    const params = new URLSearchParams({ pagina: String(paginaActual) });
    if (filtroEstado.value) {
        params.set("estado", filtroEstado.value);
    }
    try {
        const respuesta = await api.get(`/api/siniestros/?${params}`);
        if (solicitud !== solicitudActual) {
            return;
        }
        if (!Array.isArray(respuesta.resultados)) {
            throw new Error("La respuesta de expedientes no tiene el formato esperado.");
        }
        if (respuesta.resultados.length) {
            filas.append(...respuesta.resultados.map(crearTarjetaSiniestro));
        } else {
            filas.append(crearTarjetaVacia("No hay expedientes para mostrar."));
        }
        actualizarPaginacion(respuesta);
        carga.textContent = "";
        carga.className = "px-3 pt-3 mb-0";
    } catch (error) {
        if (solicitud !== solicitudActual) {
            return;
        }
        carga.textContent = error.mensaje ?? error.message ?? "No se pudieron cargar los expedientes.";
        carga.className = "px-3 pt-3 mb-0 text-danger";
        total.textContent = "";
        paginaTexto.textContent = "";
    }
}

function renderizarDetalle(siniestro) {
    panelDetalle.hidden = false;
    formularioAdjunto.reset();
    datosDetalle.dataset.id = String(siniestro.id);
    document.getElementById("titulo-detalle-siniestro").textContent =
        `Expediente ${siniestro.numero_siniestro}`;
    datosDetalle.replaceChildren();
    agregarDato(datosDetalle, "Estado", ETIQUETAS_ESTADO[siniestro.estado]);
    agregarDato(datosDetalle, "Cliente", nombreCliente(siniestro.cliente));
    agregarDato(datosDetalle, "Póliza", siniestro.poliza.numero_poliza);
    agregarDato(datosDetalle, "Ocurrencia", siniestro.fecha_ocurrencia);
    agregarDato(datosDetalle, "Denuncia registrada", formatearFechaHora(siniestro.creado_en));
    agregarDato(datosDetalle, "Descripción", siniestro.descripcion);

    listaAdjuntos.replaceChildren();
    const adjuntos = Array.isArray(siniestro.adjuntos) ? siniestro.adjuntos : [];
    if (adjuntos.length) {
        for (const adjunto of adjuntos) {
            const item = document.createElement("li");
            item.className = "list-group-item d-flex justify-content-between align-items-center gap-2";
            const detalle = document.createElement("span");
            detalle.className = "small";
            detalle.textContent =
                `${adjunto.content_type} · ${Math.ceil(adjunto.tamano / 1024)} KB · ` +
                `${formatearFechaHora(adjunto.creado_en)}`;
            const descarga = document.createElement("a");
            descarga.className = "btn btn-sm btn-outline-secondary flex-shrink-0";
            descarga.href = adjunto.descarga_url;
            descarga.textContent = "Descargar";
            item.append(detalle, descarga);
            listaAdjuntos.append(item);
        }
        adjuntosVacio.textContent = "";
    } else {
        adjuntosVacio.textContent = "Todavía no hay archivos adjuntos.";
    }

    historial.replaceChildren();
    if (!siniestro.historial.length) {
        const sinHistorial = document.createElement("li");
        sinHistorial.className = "list-group-item text-muted";
        sinHistorial.textContent = "Este expediente no tiene decisiones registradas.";
        historial.append(sinHistorial);
    }
    for (const entrada of siniestro.historial) {
        const elemento = document.createElement("li");
        elemento.className = "list-group-item";
        const transicion = entrada.estado_anterior
            ? `${ETIQUETAS_ESTADO[entrada.estado_anterior]} → ${ETIQUETAS_ESTADO[entrada.estado_nuevo]}`
            : ETIQUETAS_ESTADO[entrada.estado_nuevo];
        const encabezado = document.createElement("strong");
        encabezado.textContent = transicion;
        const detalle = document.createElement("p");
        detalle.className = "mb-1";
        detalle.textContent = entrada.motivo;
        const responsable = document.createElement("small");
        responsable.className = "text-muted";
        responsable.textContent =
            `${entrada.responsable.nombre} · ${formatearFechaHora(entrada.fecha)}`;
        elemento.append(encabezado, detalle, responsable);
        historial.append(elemento);
    }

    const siguientes = SIGUIENTES_ESTADOS[siniestro.estado] ?? [];
    formularioTransicion.hidden = !funcionario.puede_aprobar || siguientes.length === 0;
    mensajeSinTransicion.hidden = funcionario.puede_aprobar && siguientes.length !== 0;
    mensajeSinTransicion.textContent = funcionario.puede_aprobar
        ? "El expediente está cerrado; no admite más cambios."
        : "Tu usuario puede consultar el expediente, pero no registrar decisiones.";
    estadoSiguiente.replaceChildren(opcion("Seleccioná el estado siguiente"));
    for (const proximo of siguientes) {
        estadoSiguiente.append(opcion(ETIQUETAS_ESTADO[proximo], proximo));
    }
}

async function cargarDetalle(id) {
    mostrarEstado("");
    try {
        const detalle = await api.get(`/api/siniestros/${id}/`);
        renderizarDetalle(detalle);
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo cargar el expediente.", true);
    }
}

async function registrarDenuncia(evento) {
    evento.preventDefault();
    if (!formularioDenuncia.reportValidity()) {
        return;
    }
    if (!polizaSeleccionada || !selectCliente.value || !selectPoliza.value) {
        mostrarEstado("Seleccioná un cliente y una póliza antes de registrar.", true);
        return;
    }
    const boton = document.getElementById("guardar-denuncia");
    boton.disabled = true;
    mostrarEstado("");
    try {
        const creada = await api.post("/api/siniestros/", {
            cliente_id: Number(selectCliente.value),
            poliza_id: Number(selectPoliza.value),
            fecha_ocurrencia: fechaOcurrencia.value,
            descripcion: descripcion.value.trim(),
        });
        formularioDenuncia.reset();
        selectCliente.replaceChildren(opcion("Buscá y seleccioná un cliente"));
        selectCliente.disabled = true;
        selectPoliza.replaceChildren(opcion("Primero seleccioná el cliente"));
        selectPoliza.disabled = true;
        fechaOcurrencia.disabled = true;
        vigencia.textContent = "";
        polizaSeleccionada = null;
        await cargarSiniestros(1);
        renderizarDetalle(creada);
        mostrarEstado(`Denuncia ${creada.numero_siniestro} registrada.`);
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo registrar la denuncia.", true);
    } finally {
        boton.disabled = false;
    }
}

async function guardarTransicion(evento) {
    evento.preventDefault();
    if (!formularioTransicion.reportValidity()) {
        return;
    }
    const boton = document.getElementById("guardar-transicion-siniestro");
    boton.disabled = true;
    mostrarEstado("");
    try {
        const detalle = await api.post(
            `/api/siniestros/${datosDetalle.dataset.id}/transiciones/`,
            {
                estado: estadoSiguiente.value,
                motivo: motivoDecision.value.trim(),
            },
        );
        motivoDecision.value = "";
        renderizarDetalle(detalle);
        await cargarSiniestros(paginaActual);
        mostrarEstado("Decisión interna registrada; no implica una indemnización.");
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo registrar la decisión.", true);
    } finally {
        boton.disabled = false;
    }
}

async function subirAdjunto(evento) {
    evento.preventDefault();
    if (!formularioAdjunto.reportValidity()) {
        return;
    }
    const boton = document.getElementById("subir-adjunto-siniestro");
    const formulario = new FormData();
    formulario.append("archivo", archivoAdjunto.files[0]);
    boton.disabled = true;
    mostrarEstado("");
    try {
        const detalle = await api.upload(
            `/api/siniestros/${datosDetalle.dataset.id}/adjuntos/`,
            formulario,
        );
        formularioAdjunto.reset();
        renderizarDetalle(detalle);
        mostrarEstado("Imagen incorporada al expediente privado.");
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo adjuntar la imagen.", true);
    } finally {
        boton.disabled = false;
    }
}

async function iniciar() {
    inicializarNav();
    funcionario = await api.get("/api/auth/me/");
    await cargarSiniestros();
}

botonBuscarCliente.addEventListener("click", cargarClientes);
buscarCliente.addEventListener("keydown", (evento) => {
    if (evento.key === "Enter") {
        evento.preventDefault();
        cargarClientes();
    }
});
selectCliente.addEventListener("change", cargarPolizasCliente);
selectPoliza.addEventListener("change", cargarPolizaSeleccionada);
formularioDenuncia.addEventListener("submit", registrarDenuncia);
formularioAdjunto.addEventListener("submit", subirAdjunto);
formularioTransicion.addEventListener("submit", guardarTransicion);
filtroEstado.addEventListener("change", () => cargarSiniestros(1));
anterior.addEventListener("click", () => cargarSiniestros(paginaActual - 1));
siguiente.addEventListener("click", () => cargarSiniestros(paginaActual + 1));

iniciar().catch((error) => {
    mostrarEstado(error.mensaje ?? error.message ?? "No se pudo iniciar el panel de siniestros.", true);
});
