import { api } from "../api.js?v=20261105burbujas1";
import { inicializarNav } from "../nav.js?v=20261105burbujas1";
import { formatearPorcentaje, validarCompania } from "../lib/companias.js?v=20261105burbujas1";
import { inicializarPlanes } from "../lib/planes.js?v=20261105burbujas1";
import { confirmarEliminacion, inicializarEliminacion } from "../lib/eliminar-total.js?v=20261105burbujas1";

const mensajePagina = document.getElementById("mensaje-pagina");
const contenido = document.getElementById("contenido-companias");
const panelAlta = document.getElementById("panel-alta-compania");
const formularioAlta = document.getElementById("formulario-alta-compania");
const estadoAlta = document.getElementById("estado-alta-compania");
const botonGuardar = document.getElementById("alta-guardar");
const tabla = document.getElementById("tabla-companias");
const columnaAcciones = document.getElementById("columna-acciones");
const avisoComision = document.getElementById("aviso-comision");
const dialogo = document.getElementById("dialog-compania");
const formularioDialogo = document.getElementById("formulario-dialogo");
const dialogoTitulo = document.getElementById("dialog-titulo");
const dialogoCampos = document.getElementById("dialog-campos");
const dialogoError = document.getElementById("dialog-error");
const dialogoCancelar = document.getElementById("dialog-cancelar");
const dialogoConfirmar = document.getElementById("dialog-confirmar");

const CAMPOS_ALTA = ["nombre", "comision_pct"];

let esAprobador = false;
let esAdministrador = false;
let alConfirmar = null;

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

function mostrarAviso(nodo, mensaje, error = false) {
    nodo.textContent = mensaje;
    nodo.classList.toggle("d-none", !mensaje);
    nodo.classList.toggle("alert-danger", error);
    nodo.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function textoError(error, porDefecto) {
    return error.mensaje ?? error.message ?? porDefecto;
}

function campo(etiqueta, control) {
    const grupo = crearElemento("div", "mb-3");
    const label = crearElemento("label", "form-label", etiqueta);
    label.htmlFor = control.id;
    grupo.append(label, control);
    return grupo;
}

function abrirDialogo(titulo, campos, accion) {
    dialogoTitulo.textContent = titulo;
    dialogoCampos.replaceChildren(...campos);
    dialogoError.textContent = "";
    alConfirmar = accion;
    dialogo.showModal();
}

function boton(texto, clase, alHacerClic) {
    const elemento = crearElemento("button", `btn btn-sm ${clase}`, texto);
    elemento.type = "button";
    elemento.addEventListener("click", alHacerClic);
    return elemento;
}

function editarCompania(compania) {
    const nombre = crearElemento("input", "form-control");
    nombre.id = "dialog-nombre";
    nombre.value = compania.nombre;
    const comision = crearElemento("input", "form-control");
    comision.id = "dialog-comision";
    comision.inputMode = "decimal";
    comision.value = compania.comision_pct ?? "";

    abrirDialogo(`Editar ${compania.nombre}`, [campo("Nombre", nombre), campo("Comisión (%)", comision)], async () => {
        const cuerpo = { nombre: nombre.value.trim(), comision_pct: comision.value.trim() };
        const errores = validarCompania(cuerpo);
        if (Object.keys(errores).length > 0) {
            throw new Error(Object.values(errores)[0]);
        }
        await api.patch(`/api/companias/${compania.id}/`, cuerpo);
        return `Se actualizó ${cuerpo.nombre}.`;
    });
}

function cambiarEstado(compania) {
    const activar = !compania.activa;
    const aviso = crearElemento(
        "p",
        "",
        activar
            ? `${compania.nombre} vuelve a ofrecerse para pólizas nuevas.`
            : `${compania.nombre} deja de ofrecerse para pólizas nuevas. Las pólizas que ya la usan no cambian.`,
    );
    abrirDialogo(activar ? "Activar compañía" : "Desactivar compañía", [aviso], async () => {
        await api.patch(`/api/companias/${compania.id}/`, { activa: activar });
        return activar ? `${compania.nombre} está activa.` : `${compania.nombre} quedó desactivada.`;
    });
}

function crearFila(compania) {
    const fila = document.createElement("tr");
    if (!compania.activa) {
        fila.classList.add("tarjeta-apagada");
    }
    fila.append(crearElemento("th", "fw-semibold", compania.nombre));
    fila.lastChild.scope = "row";
    fila.append(crearElemento("td", "", formatearPorcentaje(compania.comision_pct)));
    const estado = crearElemento("td");
    estado.append(crearElemento(
        "span",
        compania.activa ? "badge text-bg-success" : "badge text-bg-secondary",
        compania.activa ? "Activa" : "Desactivada",
    ));
    fila.append(estado);
    if (esAprobador) {
        const acciones = crearElemento("td", "text-end text-nowrap");
        acciones.append(
            boton("Editar", "btn-outline-primary me-2", () => editarCompania(compania)),
            boton(
                compania.activa ? "Desactivar" : "Activar",
                compania.activa ? "btn-outline-danger" : "btn-outline-success",
                () => cambiarEstado(compania),
            ),
        );
        if (esAdministrador) {
            acciones.append(boton("Eliminar (total)", "btn-danger fw-bold ms-2", () => confirmarEliminacion(
                `Eliminar ${compania.nombre}`,
                "Se borran de la base la compañía, todas sus pólizas (con cuotas, pagos y condiciones), "
                + "sus planes y sus cotizaciones. Los clientes quedan, sin esas pólizas. "
                + "No se puede deshacer. Si hay siniestros o acciones finalizadas, no se borra nada.",
                async () => {
                    const r = await api.post(`/api/companias/${compania.id}/eliminar-definitivo/`, {});
                    mostrarAviso(mensajePagina, `${compania.nombre} eliminada: ${r.borrados.polizas} póliza(s) y ${r.borrados.planes} plan(es).`);
                    await cargarCompanias();
                },
            )));
        }
        fila.append(acciones);
    }
    return fila;
}

function renderizar(companias) {
    tabla.replaceChildren();
    if (companias.length === 0) {
        const fila = document.createElement("tr");
        const celda = crearElemento("td", "text-muted", "Todavía no hay compañías cargadas.");
        celda.colSpan = esAprobador ? 4 : 3;
        fila.append(celda);
        tabla.append(fila);
        return;
    }
    tabla.append(...companias.map(crearFila));
}

async function cargarCompanias() {
    const respuesta = await api.get("/api/companias/");
    renderizar(respuesta.resultados ?? []);
    await inicializarPlanes(esAprobador,respuesta.resultados??[],{esAdministrador,confirmarEliminacion,alEliminar:async(nombre)=>{mostrarAviso(mensajePagina,`Plan ${nombre} eliminado.`);await cargarCompanias();}});
}

function pintarErroresAlta(errores) {
    for (const nombre of CAMPOS_ALTA) {
        const entrada = formularioAlta.elements[nombre];
        const aviso = formularioAlta.querySelector(`[data-error="${nombre}"]`);
        entrada.classList.toggle("is-invalid", Boolean(errores[nombre]));
        if (aviso) {
            aviso.textContent = errores[nombre] ?? "";
        }
    }
}

async function crearCompania(evento) {
    evento.preventDefault();
    const cuerpo = {
        nombre: formularioAlta.elements.nombre.value.trim(),
        comision_pct: formularioAlta.elements.comision_pct.value.trim(),
    };
    const errores = validarCompania(cuerpo);
    pintarErroresAlta(errores);
    if (Object.keys(errores).length > 0) {
        mostrarAviso(estadoAlta, "Revisá los campos marcados.", true);
        return;
    }
    botonGuardar.disabled = true;
    mostrarAviso(estadoAlta, "");
    try {
        const compania = await api.post("/api/companias/", cuerpo);
        formularioAlta.reset();
        pintarErroresAlta({});
        mostrarAviso(estadoAlta, `Se creó la compañía ${compania.nombre}.`);
        await cargarCompanias();
    } catch (error) {
        mostrarAviso(estadoAlta, textoError(error, "No se pudo crear la compañía."), true);
    } finally {
        botonGuardar.disabled = false;
    }
}

async function confirmarDialogo(evento) {
    evento.preventDefault();
    if (!alConfirmar) {
        return;
    }
    dialogoConfirmar.disabled = true;
    dialogoError.textContent = "";
    try {
        const mensaje = await alConfirmar();
        dialogo.close();
        mostrarAviso(mensajePagina, mensaje);
        await cargarCompanias();
    } catch (error) {
        dialogoError.textContent = textoError(error, "No se pudo completar la acción.");
    } finally {
        dialogoConfirmar.disabled = false;
    }
}

async function iniciar() {
    inicializarNav();
    try {
        const me = await api.get("/api/auth/me/");
        esAprobador = Boolean(me?.puede_aprobar);
        esAdministrador = me?.rol === "administrador";
        // Solo comodidad: la API es la que niega escribir y la que oculta la comisión.
        panelAlta.hidden = !esAprobador;
        columnaAcciones.hidden = !esAprobador;
        avisoComision.hidden = esAprobador;
        await cargarCompanias();
        contenido.hidden = false;
    } catch (error) {
        mostrarAviso(mensajePagina, textoError(error, "No se pudieron cargar las compañías."), true);
    }
}

formularioAlta.addEventListener("submit", crearCompania);
formularioDialogo.addEventListener("submit", confirmarDialogo);
dialogoCancelar.addEventListener("click", () => dialogo.close());

inicializarEliminacion();
iniciar();
