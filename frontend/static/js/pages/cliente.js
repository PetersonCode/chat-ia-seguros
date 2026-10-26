import { api } from "../api.js?v=20261020b";
import { inicializarNav } from "../nav.js?v=20261020b";
import { formatearFecha, formatearMonto } from "../lib/formato.js?v=20261020b";
import {
    etiquetaEstadoPoliza,
    mesesDeCobertura,
    ordenarPolizas,
    validarPoliza,
} from "../lib/polizas.js?v=20261020b";
import { limpiarDni, validarCliente } from "../lib/clientes.js?v=20261020b";

const idCliente = new URLSearchParams(globalThis.location.search).get("id");
const nombreCliente = document.getElementById("nombre-cliente");
const datosCliente = document.getElementById("datos-cliente");
const estado = document.getElementById("estado-ficha");
const contactos = document.getElementById("contactos-cliente");
const polizasCliente = document.getElementById("polizas-cliente");
const siniestrosCliente = document.getElementById("siniestros-cliente");

const insigniaActivo = document.getElementById("estado-activo-cliente");
const botonBaja = document.getElementById("boton-baja-cliente");
const botonReactivar = document.getElementById("boton-reactivar-cliente");
const formularioEdicion = document.getElementById("formulario-edicion-cliente");
const estadoEdicion = document.getElementById("estado-edicion-cliente");
const botonGuardar = document.getElementById("edicion-guardar");

const columnaNuevaPoliza = document.getElementById("columna-nueva-poliza");
const panelNuevaPoliza = document.getElementById("panel-nueva-poliza");
const formularioPoliza = document.getElementById("formulario-nueva-poliza");
const estadoNuevaPoliza = document.getElementById("estado-nueva-poliza");
const previoCuotas = document.getElementById("previo-cuotas-poliza");
const botonCrearPoliza = document.getElementById("poliza-crear");

const CAMPOS_EDICION = ["dni", "nombre", "apellido", "telefono", "email"];
const CAMPOS_POLIZA = [
    "numero_poliza",
    "tipo_seguro",
    "cobertura",
    "prima_mensual",
    "fecha_inicio",
    "fecha_vencimiento",
    "bien_asegurado",
];

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

function mostrarEstado(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.classList.toggle("d-none", !mensaje);
    estado.classList.toggle("alert-danger", error);
    estado.classList.toggle("alert-info", Boolean(mensaje) && !error);
}

function agregarDato(contenedor, etiqueta, valor) {
    const fila = crearElemento("p", "mb-1");
    fila.append(crearElemento("strong", "", `${etiqueta}: `));
    fila.append(document.createTextNode(valor ?? "—"));
    contenedor.append(fila);
}

function renderizarContactos(cliente) {
    contactos.replaceChildren();
    const lista = Array.isArray(cliente.contactos) ? cliente.contactos : [];
    if (lista.length === 0) {
        contactos.append(crearElemento("p", "text-muted mb-0", "No hay contactos registrados."));
        return;
    }
    const ul = crearElemento("ul", "list-unstyled mb-0");
    for (const numero of lista) {
        ul.append(crearElemento("li", "mb-1", numero));
    }
    contactos.append(ul);
}

function renderizarCuotas(contenedor, cuotas) {
    contenedor.append(crearElemento("h4", "h6 mt-3", "Cuotas"));
    if (!Array.isArray(cuotas) || cuotas.length === 0) {
        contenedor.append(crearElemento("p", "text-muted small", "No hay cuotas registradas."));
        return;
    }
    const envoltorio = crearElemento("div", "table-responsive");
    const tabla = crearElemento("table", "table table-sm align-middle mb-0");
    const cabecera = document.createElement("thead");
    const encabezado = document.createElement("tr");
    for (const texto of ["Período", "Importe", "Vencimiento", "Estado"]) {
        encabezado.append(crearElemento("th", "", texto));
    }
    cabecera.append(encabezado);
    tabla.append(cabecera);
    const cuerpo = document.createElement("tbody");
    for (const cuota of cuotas) {
        const fila = document.createElement("tr");
        fila.append(crearElemento("td", "", formatearFecha(cuota.periodo)));
        fila.append(crearElemento("td", "", formatearMonto(cuota.importe)));
        fila.append(crearElemento("td", "", formatearFecha(cuota.vencimiento)));
        fila.append(crearElemento("td", "", cuota.estado));
        cuerpo.append(fila);
    }
    tabla.append(cuerpo);
    envoltorio.append(tabla);
    contenedor.append(envoltorio);
}

function renderizarPoliza(poliza) {
    const columna = crearElemento("div", "col-12 col-xl-6");
    const tarjeta = crearElemento("article", "card shadow-sm border-0 h-100");
    const encabezado = crearElemento("div", "card-header bg-white d-flex justify-content-between align-items-center");
    encabezado.append(crearElemento("h3", "h5 mb-0", poliza.numero_poliza));
    encabezado.append(crearElemento(
        "span",
        poliza.estado === "vigente" ? "badge text-bg-success" : "badge text-bg-secondary",
        etiquetaEstadoPoliza(poliza.estado),
    ));
    const cuerpo = crearElemento("div", "card-body");
    agregarDato(cuerpo, "Tipo", poliza.tipo_seguro);
    agregarDato(cuerpo, "Cobertura", poliza.cobertura);
    agregarDato(cuerpo, "Vencimiento de póliza", formatearFecha(poliza.fecha_vencimiento));
    agregarDato(cuerpo, "Saldo pendiente", formatearMonto(poliza.saldo_pendiente));
    agregarDato(cuerpo, "Próximo vencimiento de pago", formatearFecha(poliza.proximo_vencimiento_pago));
    renderizarCuotas(cuerpo, poliza.cuotas);
    tarjeta.append(encabezado, cuerpo);
    columna.append(tarjeta);
    return columna;
}

function renderizarSiniestros(siniestros) {
    siniestrosCliente.replaceChildren();
    if (!Array.isArray(siniestros) || siniestros.length === 0) {
        siniestrosCliente.append(crearElemento("p", "text-muted mb-0", "No hay siniestros registrados."));
        return;
    }
    const lista = crearElemento("div", "list-group list-group-flush");
    for (const siniestro of siniestros) {
        const item = crearElemento("article", "list-group-item px-0");
        item.append(crearElemento("h3", "h6", siniestro.numero_siniestro));
        item.append(crearElemento(
            "p",
            "small mb-1",
            `${formatearFecha(siniestro.fecha_ocurrencia)} · ${siniestro.estado}`,
        ));
        item.append(crearElemento("p", "mb-0", siniestro.descripcion));
        lista.append(item);
    }
    siniestrosCliente.append(lista);
}

// --- ABM ------------------------------------------------------------------

function mostrarEstadoEdicion(mensaje, error = false) {
    estadoEdicion.textContent = mensaje;
    estadoEdicion.classList.toggle("d-none", !mensaje);
    estadoEdicion.classList.toggle("alert-danger", error);
    estadoEdicion.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function pintarErroresEdicion(errores) {
    for (const campo of CAMPOS_EDICION) {
        const entrada = formularioEdicion.elements[campo];
        const aviso = formularioEdicion.querySelector(`[data-error="${campo}"]`);
        const mensaje = errores[campo];
        entrada.classList.toggle("is-invalid", Boolean(mensaje));
        if (aviso) {
            aviso.textContent = mensaje ?? "";
        }
    }
}

function prepararAbm(cliente) {
    const dadoDeBaja = cliente.activo === false;
    insigniaActivo.textContent = dadoDeBaja ? "Dado de baja" : "Activo";
    insigniaActivo.className = dadoDeBaja
        ? "badge text-bg-secondary mt-2"
        : "badge text-bg-success mt-2";
    botonBaja.classList.toggle("d-none", dadoDeBaja);
    botonReactivar.classList.toggle("d-none", !dadoDeBaja);

    formularioEdicion.elements.dni.value = cliente.dni ?? "";
    formularioEdicion.elements.nombre.value = cliente.nombre ?? "";
    formularioEdicion.elements.apellido.value = cliente.apellido ?? "";
    formularioEdicion.elements.email.value = cliente.email ?? "";
    formularioEdicion.elements.telefono.value = (cliente.contactos ?? [])[0] ?? "";
    pintarErroresEdicion({});
}

/** Solo viaja lo que tiene valor; el email viaja siempre, porque vaciarlo lo borra. */
function cambiosDelFormulario() {
    const cuerpo = {};
    for (const campo of ["dni", "nombre", "apellido", "telefono"]) {
        const valor = formularioEdicion.elements[campo].value.trim();
        if (valor) {
            cuerpo[campo] = campo === "dni" ? limpiarDni(valor) : valor;
        }
    }
    cuerpo.email = formularioEdicion.elements.email.value.trim();
    return cuerpo;
}

formularioEdicion.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const cuerpo = cambiosDelFormulario();
    const errores = validarCliente(cuerpo, { parcial: true });
    pintarErroresEdicion(errores);
    if (Object.keys(errores).length > 0) {
        mostrarEstadoEdicion("Revisá los campos marcados.", true);
        return;
    }

    botonGuardar.disabled = true;
    mostrarEstadoEdicion("Guardando…");
    try {
        await api.patch(`/api/clientes/${idCliente}/`, cuerpo);
        mostrarEstadoEdicion("Cambios guardados.");
        await cargarFicha();
    } catch (error) {
        mostrarEstadoEdicion(error.mensaje ?? error.message ?? "No se pudieron guardar los cambios.", true);
    } finally {
        botonGuardar.disabled = false;
    }
});

async function cambiarEstado(ruta, boton) {
    boton.disabled = true;
    mostrarEstado("Actualizando…");
    try {
        await api.post(`/api/clientes/${idCliente}/${ruta}/`, {});
        await cargarFicha();
    } catch (error) {
        // El 409 de "tiene pólizas vigentes" llega acá con su mensaje.
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo cambiar el estado.", true);
    } finally {
        boton.disabled = false;
    }
}

botonBaja.addEventListener("click", () => cambiarEstado("baja", botonBaja));
botonReactivar.addEventListener("click", () => cambiarEstado("reactivar", botonReactivar));

async function cargarFicha() {
    inicializarNav();
    if (!/^[1-9]\d*$/.test(idCliente ?? "")) {
        mostrarEstado("El identificador de cliente no es válido.", true);
        return;
    }

    mostrarEstado("Cargando ficha…");
    try {
        const cliente = await api.get(`/api/clientes/${idCliente}/`);
        const polizasOrdenadas = ordenarPolizas(cliente.polizas ?? []);
        const polizasDetalladas = await Promise.all(polizasOrdenadas.map(
            (poliza) => api.get(`/api/polizas/${poliza.id}/`),
        ));

        nombreCliente.textContent = `${cliente.nombre} ${cliente.apellido}`;
        datosCliente.textContent = `DNI: ${cliente.dni} · Correo: ${cliente.email ?? "—"}`;
        prepararAbm(cliente);
        renderizarContactos(cliente);
        polizasCliente.replaceChildren();
        if (polizasDetalladas.length === 0) {
            polizasCliente.append(crearElemento("p", "col-12 text-muted", "No hay pólizas registradas."));
        } else {
            polizasCliente.append(...polizasDetalladas.map(renderizarPoliza));
        }
        // La tarjeta de alta es una más de la grilla: se mueve acá en cada
        // render, porque el `replaceChildren` de arriba vacía el contenedor.
        // A un cliente dado de baja no se le agregan pólizas (el alta lo
        // rechaza con un 409), así que ahí ni se ofrece.
        polizasCliente.append(columnaNuevaPoliza);
        columnaNuevaPoliza.classList.toggle("d-none", cliente.activo === false);

        const siniestros = Array.isArray(cliente.siniestros) && cliente.siniestros.length > 0
            ? cliente.siniestros
            : polizasDetalladas.flatMap((poliza) => poliza.siniestros ?? []);
        const siniestrosUnicos = [...new Map(
            siniestros.map((siniestro) => [siniestro.numero_siniestro, siniestro]),
        ).values()];
        renderizarSiniestros(siniestrosUnicos);
        mostrarEstado("");
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo cargar la ficha del cliente.", true);
    }
}

// --- Alta de póliza -------------------------------------------------------

let opcionesPoliza = null;

function mostrarEstadoNuevaPoliza(mensaje, error = false) {
    estadoNuevaPoliza.textContent = mensaje;
    estadoNuevaPoliza.classList.toggle("d-none", !mensaje);
    estadoNuevaPoliza.classList.toggle("alert-danger", error);
    estadoNuevaPoliza.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function llenarSelect(select, opciones) {
    select.replaceChildren();
    for (const [valor, texto] of opciones) {
        const opcion = document.createElement("option");
        opcion.value = valor;
        opcion.textContent = texto;
        select.append(opcion);
    }
}

function conMayuscula(texto) {
    return texto.charAt(0).toUpperCase() + texto.slice(1);
}

/** Tipos, coberturas y número sugerido. Se pide al abrir, no al cargar la ficha. */
async function cargarOpcionesPoliza() {
    if (opcionesPoliza) {
        return;
    }
    try {
        opcionesPoliza = await api.get("/api/polizas/opciones/");
    } catch (error) {
        mostrarEstadoNuevaPoliza(
            error.mensaje ?? error.message ?? "No se pudieron cargar los tipos de seguro.",
            true,
        );
        return;
    }
    llenarSelect(
        formularioPoliza.elements.tipo_seguro,
        (opcionesPoliza.tipos_seguro ?? []).map((tipo) => [tipo.codigo, tipo.nombre]),
    );
    llenarSelect(
        formularioPoliza.elements.cobertura,
        (opcionesPoliza.coberturas ?? []).map((cobertura) => [cobertura, conMayuscula(cobertura)]),
    );
    if (!formularioPoliza.elements.numero_poliza.value) {
        formularioPoliza.elements.numero_poliza.value = opcionesPoliza.numero_sugerido ?? "";
    }
}

panelNuevaPoliza.addEventListener("toggle", () => {
    if (panelNuevaPoliza.open) {
        cargarOpcionesPoliza();
    }
});

/** Cuántas cuotas va a generar el alta, para que no sea una sorpresa. */
function actualizarPrevioCuotas() {
    const inicio = formularioPoliza.elements.fecha_inicio.value;
    const vencimiento = formularioPoliza.elements.fecha_vencimiento.value;
    const prima = formularioPoliza.elements.prima_mensual.value;
    if (!inicio || !vencimiento || vencimiento <= inicio || !prima.trim()) {
        previoCuotas.textContent = "";
        return;
    }
    const meses = mesesDeCobertura(inicio, vencimiento);
    const plural = meses === 1 ? "cuota" : "cuotas";
    previoCuotas.textContent = `Se van a generar ${meses} ${plural} de ${formatearMonto(prima)}, `
        + "con vencimiento el 15 de cada mes.";
}

formularioPoliza.addEventListener("input", actualizarPrevioCuotas);

function pintarErroresPoliza(errores) {
    for (const campo of CAMPOS_POLIZA) {
        const entrada = formularioPoliza.elements[campo];
        const aviso = formularioPoliza.querySelector(`[data-error="${campo}"]`);
        const mensaje = errores[campo];
        entrada.classList.toggle("is-invalid", Boolean(mensaje));
        if (aviso) {
            aviso.textContent = mensaje ?? "";
        }
    }
}

function datosDelFormularioPoliza() {
    const cuerpo = {};
    for (const campo of CAMPOS_POLIZA) {
        cuerpo[campo] = formularioPoliza.elements[campo].value.trim();
    }
    return cuerpo;
}

formularioPoliza.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const cuerpo = datosDelFormularioPoliza();
    const errores = validarPoliza(cuerpo);
    pintarErroresPoliza(errores);
    if (Object.keys(errores).length > 0) {
        mostrarEstadoNuevaPoliza("Revisá los campos marcados.", true);
        return;
    }

    botonCrearPoliza.disabled = true;
    mostrarEstadoNuevaPoliza("Creando la póliza…");
    try {
        const poliza = await api.post(`/api/clientes/${idCliente}/polizas/`, cuerpo);
        formularioPoliza.reset();
        pintarErroresPoliza({});
        previoCuotas.textContent = "";
        // El próximo número libre ya cambió: que se vuelva a pedir al abrir.
        opcionesPoliza = null;
        panelNuevaPoliza.open = false;
        mostrarEstadoNuevaPoliza(`Póliza ${poliza.numero_poliza} creada.`);
        await cargarFicha();
    } catch (error) {
        mostrarEstadoNuevaPoliza(
            error.mensaje ?? error.message ?? "No se pudo crear la póliza.",
            true,
        );
    } finally {
        botonCrearPoliza.disabled = false;
    }
});

cargarFicha();
