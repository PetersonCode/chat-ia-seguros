import { api } from "../api.js?v=20261105revision9";
import { inicializarNav } from "../nav.js?v=20261105revision9";
import { armarQuery } from "../lib/consulta.js?v=20261105revision9";
import { debounce } from "../lib/debounce.js?v=20261105revision9";
import {
    ETAPAS,
    ORIGENES,
    estadoSeguimiento,
    etiquetaOrigen,
    nombreCompleto,
    validarInteresado,
} from "../lib/embudo.js?v=20261105revision9";

const $ = (id) => document.getElementById(id);
const tablero = $("tablero");
const mensajePagina = $("mensaje-pagina");
const formularioNuevo = $("formulario-nuevo");
const estadoNuevo = $("estado-nuevo");
const botonNuevo = $("nuevo-guardar");

const CAMPOS_NUEVO = ["nombre", "origen"];

// Una columna por etapa: lo que ya se cargó, cuántas hay en total y si hay más.
const columnas = new Map();
let solicitud = 0;

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

function filtrosActuales() {
    return {
        q: $("filtro-q").value.trim(),
        responsable: $("filtro-responsable").value,
        origen: $("filtro-origen").value,
        seguimiento_vencido: $("filtro-vencido").checked,
    };
}

/** «Toyota Corolla · AB123CD», con lo que haya. */
function resumenVehiculo(datos) {
    const marcaModelo = [datos?.marca, datos?.modelo].filter(Boolean).join(" ");
    return [marcaModelo, datos?.patente].filter(Boolean).join(" · ");
}

function crearTarjeta(interesado) {
    const tarjeta = crearElemento("article", "embudo-tarjeta position-relative");
    const enlace = crearElemento("a", "embudo-nombre stretched-link", nombreCompleto(interesado));
    enlace.href = `/panel/interesado/?id=${interesado.id}`;
    const encabezado = crearElemento("h3", "h6 mb-1");
    encabezado.append(enlace);
    tarjeta.append(encabezado);

    const linea = crearElemento("div", "d-flex flex-wrap gap-2 align-items-center mb-1");
    linea.append(crearElemento("span", "pildora", etiquetaOrigen(interesado.origen)));
    const vehiculo = resumenVehiculo(interesado.datos);
    if (vehiculo) {
        linea.append(crearElemento("span", "small text-muted", vehiculo));
    }
    tarjeta.append(linea);

    tarjeta.append(
        crearElemento(
            "p",
            "small mb-1",
            interesado.responsable ? `Responsable: ${interesado.responsable.nombre}` : "Sin responsable",
        ),
    );

    if (interesado.estado === "perdida") {
        tarjeta.append(crearElemento("p", "small text-muted mb-0", `Motivo: ${interesado.motivo_perdida ?? "—"}`));
    } else if (interesado.estado !== "emitida") {
        const seguimiento = estadoSeguimiento(interesado);
        // El texto dice el estado; el color solo lo refuerza.
        const clase = {
            vencido: "sev sev-critica",
            hoy: "sev sev-media",
            proximo: "sev sev-neutra",
            ninguno: "small text-muted",
        }[seguimiento.nivel];
        const nodo = crearElemento("span", clase, seguimiento.texto);
        if (seguimiento.nivel === "vencido") {
            nodo.dataset.vencido = "true";
        }
        tarjeta.append(nodo);
    }
    return tarjeta;
}

function crearColumna(etapa) {
    const seccion = crearElemento("section", "embudo-columna");
    seccion.dataset.etapa = etapa.clave;
    const titulo = crearElemento("h2", "h6 embudo-titulo");
    titulo.id = `columna-${etapa.clave}`;
    const nombre = crearElemento("span", "", etapa.etiqueta);
    const cuenta = crearElemento("span", "embudo-cuenta", "…");
    titulo.append(nombre, cuenta);
    seccion.setAttribute("aria-labelledby", titulo.id);

    const lista = crearElemento("div", "embudo-lista");
    const vacia = crearElemento("p", "small text-muted mb-0", "Cargando…");
    const masBoton = crearElemento("button", "btn btn-outline-secondary btn-sm w-100 mt-2", "Ver más");
    masBoton.type = "button";
    masBoton.hidden = true;
    masBoton.addEventListener("click", () => cargarMas(etapa.clave));
    seccion.append(titulo, lista, vacia, masBoton);

    const estado = { etapa, cuenta, lista, vacia, masBoton, pagina: 0, total: 0, cargadas: 0 };
    columnas.set(etapa.clave, estado);
    return seccion;
}

function pintarColumna(estado, resultados, { reemplazar }) {
    if (reemplazar) {
        estado.lista.replaceChildren();
        estado.cargadas = 0;
    }
    estado.lista.append(...resultados.map(crearTarjeta));
    estado.cargadas += resultados.length;
    estado.cuenta.textContent = String(estado.total);
    estado.cuenta.setAttribute("aria-label", `${estado.total} en ${estado.etapa.etiqueta}`);
    estado.vacia.hidden = estado.cargadas > 0;
    estado.vacia.textContent = "No hay interesados en esta etapa.";
    estado.masBoton.hidden = estado.cargadas >= estado.total;
}

async function pedirPagina(etapa, pagina) {
    const query = armarQuery({ ...filtrosActuales(), estado: etapa, pagina: pagina > 1 ? pagina : "" });
    return api.get(`/api/interesados/${query}`);
}

async function cargarMas(etapa) {
    const estado = columnas.get(etapa);
    estado.masBoton.disabled = true;
    try {
        const respuesta = await pedirPagina(etapa, estado.pagina + 1);
        estado.pagina = respuesta.pagina;
        estado.total = respuesta.total;
        pintarColumna(estado, respuesta.resultados, { reemplazar: false });
    } catch (error) {
        mostrarAviso(mensajePagina, textoError(error, "No se pudieron cargar más interesados."), true);
    } finally {
        estado.masBoton.disabled = false;
    }
}

/** Vuelve a pedir las cinco columnas con los filtros de ahora. */
async function recargar() {
    const turno = ++solicitud;
    mostrarAviso(mensajePagina, "");
    try {
        const [respuestas, embudo] = await Promise.all([
            Promise.all(ETAPAS.map((etapa) => pedirPagina(etapa.clave, 1))),
            api.get(`/api/interesados/embudo/${armarQuery({ responsable: $("filtro-responsable").value })}`),
        ]);
        if (turno !== solicitud) {
            return; // una búsqueda más nueva ya está en camino
        }
        ETAPAS.forEach((etapa, indice) => {
            const estado = columnas.get(etapa.clave);
            estado.pagina = respuestas[indice].pagina;
            estado.total = respuestas[indice].total;
            pintarColumna(estado, respuestas[indice].resultados, { reemplazar: true });
        });
        $("resumen-mes").textContent =
            `Este mes: ${embudo.convertidos_mes} emitida${embudo.convertidos_mes === 1 ? "" : "s"} · ` +
            `${embudo.perdidos_mes} perdida${embudo.perdidos_mes === 1 ? "" : "s"}.`;
    } catch (error) {
        if (turno === solicitud) {
            mostrarAviso(mensajePagina, textoError(error, "No se pudo cargar el tablero."), true);
        }
    }
}

function pintarErroresNuevo(errores) {
    for (const nombre of CAMPOS_NUEVO) {
        const entrada = formularioNuevo.elements[nombre];
        const aviso = formularioNuevo.querySelector(`[data-error="${nombre}"]`);
        entrada.classList.toggle("is-invalid", Boolean(errores[nombre]));
        if (aviso) {
            aviso.textContent = errores[nombre] ?? "";
        }
    }
}

async function crearInteresado(evento) {
    evento.preventDefault();
    const cuerpo = {
        nombre: formularioNuevo.elements.nombre.value.trim(),
        apellido: formularioNuevo.elements.apellido.value.trim(),
        telefono: formularioNuevo.elements.telefono.value.trim(),
        origen: formularioNuevo.elements.origen.value,
    };
    const errores = validarInteresado(cuerpo);
    pintarErroresNuevo(errores);
    if (Object.keys(errores).length > 0) {
        mostrarAviso(estadoNuevo, "Revisá los campos marcados.", true);
        return;
    }
    botonNuevo.disabled = true;
    mostrarAviso(estadoNuevo, "");
    try {
        const interesado = await api.post("/api/interesados/", cuerpo);
        formularioNuevo.reset();
        pintarErroresNuevo({});
        const nombre = nombreCompleto(interesado);
        mostrarAviso(
            estadoNuevo,
            interesado.ya_existia
                ? `Ese número ya tenía un interesado abierto: ${nombre}. Lo encontrás en «${ETAPAS.find((e) => e.clave === interesado.estado)?.etiqueta ?? "—"}».`
                : `Se creó el interesado ${nombre}.`,
        );
        await recargar();
    } catch (error) {
        mostrarAviso(estadoNuevo, textoError(error, "No se pudo crear el interesado."), true);
    } finally {
        botonNuevo.disabled = false;
    }
}

async function cargarFuncionarios() {
    const respuesta = await api.get("/api/funcionarios/");
    const selector = $("filtro-responsable");
    for (const funcionario of respuesta.resultados ?? []) {
        const opcion = crearElemento("option", "", funcionario.nombre);
        opcion.value = String(funcionario.id);
        selector.append(opcion);
    }
}

async function iniciar() {
    inicializarNav();
    for (const [clave, etiqueta] of ORIGENES) {
        for (const selector of [$("filtro-origen"), $("nuevo-origen")]) {
            const opcion = crearElemento("option", "", etiqueta);
            opcion.value = clave;
            selector.append(opcion);
        }
    }
    // En el alta no hay un «todos»: hay que elegir de dónde llegó.
    const placeholder = crearElemento("option", "", "Elegí…");
    placeholder.value = "";
    $("nuevo-origen").prepend(placeholder);
    $("nuevo-origen").value = "";

    tablero.replaceChildren(...ETAPAS.map(crearColumna));
    try {
        await cargarFuncionarios();
    } catch (error) {
        mostrarAviso(mensajePagina, textoError(error, "No se pudo cargar la lista de responsables."), true);
    }
    await recargar();
}

const recargarTrasEscribir = debounce(recargar, 300);
$("filtro-q").addEventListener("input", recargarTrasEscribir);
for (const id of ["filtro-responsable", "filtro-origen", "filtro-vencido"]) {
    $(id).addEventListener("change", recargar);
}
$("filtros").addEventListener("submit", (evento) => {
    evento.preventDefault();
    recargar();
});
formularioNuevo.addEventListener("submit", crearInteresado);

iniciar();
