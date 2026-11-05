import { api } from "../api.js?v=20261105revision9";
import { inicializarNav } from "../nav.js?v=20261105revision9";

const COLORES_RAMO = {
    automotor: "bg-primary",
    accidentes: "bg-warning",
    otros: "bg-secondary",
};

const numero = new Intl.NumberFormat("es-AR");
const decimal = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 1 });

function texto(id, valor) {
    document.getElementById(id).textContent = valor;
}

function crear(etiqueta, clases, contenido) {
    const elemento = document.createElement(etiqueta);
    if (clases) elemento.className = clases;
    if (contenido !== undefined) elemento.textContent = contenido;
    return elemento;
}

function mostrarError(mensaje) {
    const aviso = document.getElementById("estado-metricas");
    aviso.textContent = mensaje ?? "";
    aviso.hidden = !mensaje;
}

function renderizarVariacion(variacion) {
    const insignia = document.getElementById("kpi-variacion");
    insignia.replaceChildren();
    if (variacion === null || variacion === undefined) {
        insignia.className = "badge bg-secondary-subtle text-secondary small";
        insignia.textContent = "Sin período anterior para comparar";
        return;
    }
    const sube = variacion >= 0;
    insignia.className = `badge small ${sube ? "bg-success-subtle text-success" : "bg-danger-subtle text-danger"}`;
    insignia.append(
        crear("i", `bi ${sube ? "bi-arrow-up-short" : "bi-arrow-down-short"}`),
        ` ${sube ? "+" : ""}${decimal.format(variacion)}% vs período anterior`,
    );
}

function renderizarRamos(ramos) {
    const contenedor = document.getElementById("lista-ramos");
    contenedor.replaceChildren();
    ramos.forEach((ramo, indice) => {
        const bloque = crear("div", indice < ramos.length - 1 ? "mb-3" : "");
        const cabecera = crear("div", "d-flex justify-content-between small mb-1");
        cabecera.append(
            crear("span", "", ramo.nombre),
            crear("span", "fw-semibold", `${decimal.format(ramo.porcentaje)}% (${numero.format(ramo.cantidad)} ${ramo.cantidad === 1 ? "consulta" : "consultas"})`),
        );
        const progreso = crear("div", "progress");
        progreso.style.height = "10px";
        const barra = crear("div", `progress-bar ${COLORES_RAMO[ramo.codigo] ?? "bg-secondary"}`);
        barra.setAttribute("role", "progressbar");
        barra.style.width = `${ramo.porcentaje}%`;
        progreso.append(barra);
        bloque.append(cabecera, progreso);
        contenedor.append(bloque);
    });
}

function renderizarMotivos(motivos) {
    const lista = document.getElementById("lista-motivos");
    lista.replaceChildren();
    if (!motivos.length) {
        lista.append(crear("li", "list-group-item px-0 py-2 border-0 small text-muted", "Sin derivaciones en el período."));
        return;
    }
    for (const m of motivos) {
        const item = crear("li", "list-group-item d-flex justify-content-between align-items-center px-0 py-2 border-0");
        const descripcion = crear("div");
        descripcion.append(
            crear("span", "d-block small fw-semibold", m.motivo),
            crear("small", "text-muted", `${numero.format(m.cantidad)} ${m.cantidad === 1 ? "caso" : "casos"}`),
        );
        item.append(descripcion, crear("span", "badge bg-light text-dark border", `${decimal.format(m.porcentaje)}%`));
        lista.append(item);
    }
}

function renderizar(datos) {
    texto("kpi-totales", numero.format(datos.consultas.total));
    renderizarVariacion(datos.consultas.variacion_pct);
    texto("kpi-efectividad", datos.efectividad_pct === null ? "—" : `${decimal.format(datos.efectividad_pct)}%`);
    texto("kpi-derivadas", numero.format(datos.derivadas));
    texto("kpi-tiempo", datos.tiempo_respuesta_min === null ? "—" : `${decimal.format(datos.tiempo_respuesta_min)} min`);
    renderizarRamos(datos.ramos);
    renderizarMotivos(datos.motivos_derivacion);
}

document.addEventListener("DOMContentLoaded", () => {
    const filtroPeriodo = document.getElementById("filtro-periodo");
    const btnExportar = document.getElementById("btn-exportar");
    let pedido = 0;

    async function cargar() {
        const numeroPedido = ++pedido;
        mostrarError("");
        try {
            const datos = await api.get(`/api/metricas/?periodo=${encodeURIComponent(filtroPeriodo.value)}`);
            if (numeroPedido === pedido) renderizar(datos);
        } catch (error) {
            if (numeroPedido === pedido) {
                mostrarError(error?.mensaje ?? "No se pudieron cargar las métricas.");
            }
        }
    }

    filtroPeriodo.addEventListener("change", cargar);
    btnExportar.addEventListener("click", () => {
        window.location.assign(
            `/api/metricas/?periodo=${encodeURIComponent(filtroPeriodo.value)}&formato=csv`,
        );
    });

    inicializarNav();
    cargar();
});