import { api } from "../api.js?v=20261026fix2";
import { inicializarNav } from "../nav.js?v=20261026fix2";

const formulario = document.getElementById("buscar-documentos");
const campoConsulta = document.getElementById("consulta-documental");
const botonBuscar = document.getElementById("buscar-documental");
const estado = document.getElementById("estado-documentos");
const resultados = document.getElementById("resultados-documentales");

function mostrarEstado(mensaje, clase = "alert-info") {
    estado.textContent = mensaje;
    estado.classList.toggle("d-none", !mensaje);
    for (const nombre of ["alert-danger", "alert-info", "alert-success", "alert-warning"]) {
        estado.classList.toggle(nombre, nombre === clase && Boolean(mensaje));
    }
}

function crearTexto(etiqueta, texto, clase = "") {
    const elemento = document.createElement(etiqueta);
    elemento.textContent = texto;
    elemento.className = clase;
    return elemento;
}

function renderizarResultados(respuesta) {
    resultados.replaceChildren();
    if (!respuesta.respaldo_suficiente) {
        mostrarEstado(respuesta.mensaje, "alert-warning");
        return;
    }

    for (const fuente of respuesta.resultados) {
        const tarjeta = document.createElement("article");
        tarjeta.className = "card border-0 shadow-sm";
        const cuerpo = document.createElement("div");
        cuerpo.className = "card-body";
        cuerpo.append(
            crearTexto("h3", `${fuente.titulo} · versión ${fuente.version}`, "h6 fw-semibold"),
            crearTexto("p", `Fuente: ${fuente.referencia}`, "small text-muted"),
            crearTexto("blockquote", fuente.pasaje, "mb-0"),
        );
        tarjeta.append(cuerpo);
        resultados.append(tarjeta);
    }
    mostrarEstado(respuesta.mensaje, "alert-success");
}

async function buscar(evento) {
    evento.preventDefault();
    if (!formulario.reportValidity()) {
        return;
    }
    botonBuscar.disabled = true;
    resultados.replaceChildren();
    mostrarEstado("Buscando en documentos aprobados…");
    try {
        const consulta = new URLSearchParams({ q: campoConsulta.value });
        renderizarResultados(await api.get(`/api/documentos/buscar/?${consulta}`));
    } catch (error) {
        mostrarEstado(
            error.mensaje ?? error.message ?? "No se pudo consultar la biblioteca.",
            "alert-danger",
        );
    } finally {
        botonBuscar.disabled = false;
    }
}

formulario.addEventListener("submit", buscar);
inicializarNav();

const formularioAlta = document.getElementById("crear-documento");
const biblioteca = document.getElementById("lista-biblioteca");
const estadoBiblioteca = document.getElementById("estado-biblioteca");
const filtroBiblioteca = document.getElementById("filtro-biblioteca");
const anterior = document.getElementById("biblioteca-anterior");
const siguiente = document.getElementById("biblioteca-siguiente");
let aprobador = false;
let pagina = 1;
let paginas = 1;
let solicitudBiblioteca = 0;

async function verDocumento(documento) {
    try {
        const detalle = await api.get(`/api/documentos/${documento.id}/`);
        document.getElementById("vista-documento-titulo").textContent = `${detalle.titulo} · versión ${detalle.version} · ${detalle.estado}`;
        document.getElementById("vista-documento-texto").textContent = detalle.contenido;
        document.getElementById("vista-documento").hidden = false;
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message, "alert-danger");
    }
}

async function decidirDocumento(documento, operacion, boton) {
    boton.disabled = true;
    try {
        await api.post(`/api/documentos/${documento.id}/${operacion}/`);
        mostrarEstado(operacion === "aprobar" ? "Documento aprobado y disponible para consultas." : "Documento retirado de las consultas.", "alert-success");
        resultados.replaceChildren();
        document.getElementById("vista-documento").hidden = true;
        await cargarBiblioteca(pagina);
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message, "alert-danger");
    } finally {
        boton.disabled = false;
    }
}

function tarjetaDocumento(documento) {
    const tarjeta = crearTexto("article", "", "border rounded p-3");
    tarjeta.append(
        crearTexto("h3", `${documento.titulo} · versión ${documento.version}`, "h6"),
        crearTexto("p", `${documento.estado} · Fuente: ${documento.referencia}`, "small text-muted"),
    );
    const acciones = crearTexto("div", "", "d-flex flex-wrap gap-2");
    const ver = crearTexto("button", "Ver contenido", "btn btn-outline-primary btn-sm");
    ver.type = "button";
    ver.addEventListener("click", () => verDocumento(documento));
    acciones.append(ver);
    if (aprobador && documento.estado !== "retirado") {
        const operacion = documento.estado === "borrador" ? "aprobar" : "retirar";
        const decidir = crearTexto("button", operacion === "aprobar" ? "Aprobar fuente" : "Retirar fuente", "btn btn-outline-secondary btn-sm");
        decidir.type = "button";
        decidir.addEventListener("click", () => decidirDocumento(documento, operacion, decidir));
        acciones.append(decidir);
    }
    tarjeta.append(acciones);
    return tarjeta;
}

async function cargarBiblioteca(numero = 1) {
    const solicitud = ++solicitudBiblioteca;
    estadoBiblioteca.textContent = "Cargando biblioteca…";
    try {
        const filtros = new URLSearchParams({ pagina: String(numero) });
        if (filtroBiblioteca.value) filtros.set("estado", filtroBiblioteca.value);
        const respuesta = await api.get(`/api/documentos/?${filtros}`);
        if (solicitud !== solicitudBiblioteca) return;
        pagina = respuesta.pagina;
        paginas = Math.max(1, Math.ceil(respuesta.total / respuesta.por_pagina));
        biblioteca.replaceChildren(...respuesta.resultados.map(tarjetaDocumento));
        estadoBiblioteca.textContent = respuesta.total ? `${respuesta.total} documento(s).` : "Todavía no hay documentos disponibles.";
        document.getElementById("biblioteca-pagina").textContent = `Página ${pagina} de ${paginas}`;
        anterior.disabled = pagina <= 1;
        siguiente.disabled = pagina >= paginas;
    } catch (error) {
        if (solicitud === solicitudBiblioteca) estadoBiblioteca.textContent = error.mensaje ?? error.message ?? "No se pudo cargar la biblioteca.";
    }
}

formularioAlta.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!formularioAlta.reportValidity()) return;
    const boton = document.getElementById("guardar-documento");
    boton.disabled = true;
    try {
        const datos = Object.fromEntries(new FormData(formularioAlta));
        await api.post("/api/documentos/", datos);
        formularioAlta.reset();
        filtroBiblioteca.value = "borrador";
        mostrarEstado("Borrador guardado. Revisá su contenido y aprobalo para habilitar la consulta.", "alert-success");
        await cargarBiblioteca(1);
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message, "alert-danger");
    } finally {
        boton.disabled = false;
    }
});
filtroBiblioteca.addEventListener("change", () => cargarBiblioteca(1));
anterior.addEventListener("click", () => cargarBiblioteca(pagina - 1));
siguiente.addEventListener("click", () => cargarBiblioteca(pagina + 1));

async function iniciarBiblioteca() {
    try {
        const usuario = await api.get("/api/auth/me/");
        aprobador = usuario.puede_aprobar;
        document.getElementById("gestion-documentos").hidden = !aprobador;
        document.getElementById("filtro-biblioteca-contenedor").hidden = !aprobador;
        await cargarBiblioteca();
    } catch (error) {
        estadoBiblioteca.textContent = error.mensaje ?? error.message;
    }
}
iniciarBiblioteca();
