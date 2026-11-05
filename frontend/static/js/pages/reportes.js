<<<<<<< HEAD
import { formatearMonto } from "../lib/formato.js?v=20261105revision10";
import { api } from "../api.js?v=20261105revision10";
import { inicializarNav } from "../nav.js?v=20261105revision10";
=======
import { formatearMonto } from "../lib/formato.js?v=20261105burbujas1";
import { api } from "../api.js?v=20261105burbujas1";
import { inicializarNav } from "../nav.js?v=20261105burbujas1";
>>>>>>> origin/main

const formulario = document.getElementById("filtros-reportes");
const campoDesde = document.getElementById("reporte-desde");
const campoHasta = document.getElementById("reporte-hasta");
const botonGenerar = document.getElementById("generar-reporte");
const exportar = document.getElementById("exportar-reporte");
const estado = document.getElementById("estado-reportes");
const periodo = document.getElementById("periodo-reportado");
const resumen = document.getElementById("resumen-reportes");
const filasMotivos = document.getElementById("filas-motivos");
const motivosVacios = document.getElementById("motivos-vacios");
const listaDefiniciones = document.getElementById("definiciones-reportes");

function renderizarComisiones(reporte) {
    const seccion = document.getElementById("seccion-comisiones");
    document.getElementById("totales-comisiones").replaceChildren(
        crearIndicador("Comisión estimada", formatearMonto(reporte.totales.estimada), "Sobre cuotas del período."),
        crearIndicador("Sobre cobros", formatearMonto(reporte.totales.sobre_cobros), "Sobre pagos registrados en el período."),
    );
    document.getElementById("aviso-comisiones").textContent = reporte.sin_porcentaje
        ? `${reporte.sin_porcentaje} póliza(s) del período sin porcentaje: sus comisiones no se incluyen. Completalas desde la ficha del cliente.` : "";
    for (const [destino, filas] of [["comisiones-companias", reporte.por_compania], ["comisiones-clientes", reporte.por_cliente]]) {
        const cuerpo = document.getElementById(destino);
        cuerpo.replaceChildren();
        for (const datos of filas) {
            const fila = document.createElement("tr");
            const nombre = crearCelda("th", datos.nombre, "fw-normal");
            nombre.scope = "row";
            if (destino === "comisiones-clientes") {
                const enlace = document.createElement("a");
                enlace.href = `/panel/cliente/?id=${encodeURIComponent(datos.id)}`;
                enlace.textContent = datos.nombre;
                nombre.replaceChildren(enlace);
            }
            if (datos.sin_porcentaje) nombre.append(crearCelda("div",
                `${datos.sin_porcentaje} póliza(s) sin porcentaje`, "small text-warning"));
            fila.append(nombre, crearCelda("td", formatearMonto(datos.estimada), "text-end"),
                crearCelda("td", formatearMonto(datos.sobre_cobros), "text-end"));
            cuerpo.append(fila);
        }
        if (!filas.length) {
            const fila = document.createElement("tr");
            const celda = crearCelda("td", "No hay movimientos en el período.", "text-muted");
            celda.colSpan = 3;
            fila.append(celda);
            cuerpo.append(fila);
        }
    }
    seccion.hidden = false;
    document.getElementById("exportar-comisiones").href = `/api/reportes/comisiones/?` +
        new URLSearchParams({...reporte.periodo, formato: "csv"});
}

function fechaLocal(fecha) {
    const anio = fecha.getFullYear();
    const mes = String(fecha.getMonth() + 1).padStart(2, "0");
    const dia = String(fecha.getDate()).padStart(2, "0");
    return `${anio}-${mes}-${dia}`;
}

function mostrarEstado(mensaje, error = false) {
    estado.textContent = mensaje;
    estado.classList.toggle("d-none", !mensaje);
    estado.classList.toggle("alert-danger", error);
    estado.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function crearCelda(tag, texto, clase = "") {
    const elemento = document.createElement(tag);
    elemento.textContent = texto;
    elemento.className = clase;
    return elemento;
}

function crearIndicador(etiqueta, valor, descripcion) {
    const columna = document.createElement("div");
    columna.className = "col-sm-6 col-xl-3";
    const tarjeta = document.createElement("article");
    tarjeta.className = "card border-0 shadow-sm h-100";
    const cuerpo = document.createElement("div");
    cuerpo.className = "card-body";
    const titulo = crearCelda("h3", etiqueta, "h6 text-muted");
    const numero = crearCelda("p", valor, "display-6 fw-semibold mb-2");
    const ayuda = crearCelda("p", descripcion, "small text-muted mb-0");
    cuerpo.append(titulo, numero, ayuda);
    tarjeta.append(cuerpo);
    columna.append(tarjeta);
    return columna;
}

function renderizarReporte(reporte) {
    periodo.textContent = `Período: ${reporte.periodo.desde} a ${reporte.periodo.hasta}`;
    resumen.replaceChildren(
        crearIndicador("Consultas", String(reporte.consultas.total), reporte.definiciones.consultas),
        crearIndicador("Cerradas", String(reporte.consultas.cerradas), reporte.definiciones.cerradas),
        crearIndicador("Pendientes", String(reporte.consultas.pendientes), reporte.definiciones.pendientes),
        crearIndicador(
            "Derivaciones urgentes",
            String(reporte.derivaciones_urgentes),
            reporte.definiciones.derivaciones_urgentes,
        ),
        crearIndicador(
            "Cobros registrados",
            String(reporte.cobros.cantidad),
            reporte.definiciones.cobros,
        ),
        crearIndicador(
            "Importe de cobros",
            formatearMonto(reporte.cobros.importe_total),
            "Suma de movimientos Pago en moneda registrada; no se infiere de cuotas impagas.",
        ),
    );

    filasMotivos.replaceChildren();
    for (const motivo of reporte.motivos) {
        const fila = document.createElement("tr");
        fila.append(
            crearCelda("th", motivo.nombre, "fw-normal"),
            crearCelda("td", String(motivo.cantidad), "text-end"),
        );
        filasMotivos.append(fila);
    }
    motivosVacios.hidden = reporte.motivos.length > 0;

    listaDefiniciones.replaceChildren();
    for (const definicion of Object.values(reporte.definiciones)) {
        listaDefiniciones.append(crearCelda("li", definicion));
    }
    exportar.href = `/api/reportes/gestion/?desde=${encodeURIComponent(reporte.periodo.desde)}` +
        `&hasta=${encodeURIComponent(reporte.periodo.hasta)}&formato=csv`;
    exportar.hidden = false;
}

async function cargarReporte(evento) {
    evento.preventDefault();
    if (!formulario.reportValidity()) {
        return;
    }
    if (campoHasta.value < campoDesde.value) {
        mostrarEstado("La fecha final debe ser igual o posterior a la inicial.", true);
        exportar.hidden = true;
        return;
    }
    botonGenerar.disabled = true;
    exportar.hidden = true;
    mostrarEstado("Calculando reporte…");
    try {
        const filtros = new URLSearchParams({
            desde: campoDesde.value,
            hasta: campoHasta.value,
        });
        document.getElementById("seccion-comisiones").hidden = true;
        const usuario = await api.get("/api/auth/me/");
        const [reporte, comisiones] = await Promise.all([
            api.get(`/api/reportes/gestion/?${filtros}`),
            usuario.puede_aprobar ? api.get(`/api/reportes/comisiones/?${filtros}`) : null,
        ]);
        if (comisiones) renderizarComisiones(comisiones);
        renderizarReporte(reporte);
        mostrarEstado("");
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo generar el reporte.", true);
    } finally {
        botonGenerar.disabled = false;
    }
}

const hoy = new Date();
campoHasta.value = fechaLocal(hoy);
campoDesde.value = fechaLocal(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
formulario.addEventListener("submit", cargarReporte);

inicializarNav();
