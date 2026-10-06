import { api } from "../api.js";
import { inicializarNav } from "../nav.js";
import { formatearFecha, formatearMonto } from "../lib/formato.js";
import { etiquetaEstadoPoliza, ordenarPolizas } from "../lib/polizas.js";

const idCliente = new URLSearchParams(globalThis.location.search).get("id");
const nombreCliente = document.getElementById("nombre-cliente");
const datosCliente = document.getElementById("datos-cliente");
const estado = document.getElementById("estado-ficha");
const contactos = document.getElementById("contactos-cliente");
const polizasCliente = document.getElementById("polizas-cliente");
const siniestrosCliente = document.getElementById("siniestros-cliente");

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
        renderizarContactos(cliente);
        polizasCliente.replaceChildren();
        if (polizasDetalladas.length === 0) {
            polizasCliente.append(crearElemento("p", "col-12 text-muted", "No hay pólizas registradas."));
        } else {
            polizasCliente.append(...polizasDetalladas.map(renderizarPoliza));
        }

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

cargarFicha();
