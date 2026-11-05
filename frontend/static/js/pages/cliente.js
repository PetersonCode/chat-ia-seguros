import { api } from "../api.js?v=20261104gestion2";
import { inicializarNav } from "../nav.js?v=20261104flotante1";
import { iniciarNotas } from "../lib/notas.js?v=20261104gestion2";
import { iniciarFidelizacion } from "../lib/fidelizacion.js?v=20261104gestion2";
import { formatearFecha, formatearMonto } from "../lib/formato.js?v=20261104gestion2";
import {
    etiquetaEstadoPoliza,
    mesesDeCobertura,
    ordenarPolizas,
    validarPoliza,
} from "../lib/polizas.js?v=20261104gestion2";
import { limpiarDni, validarCliente } from "../lib/clientes.js?v=20261104gestion2";
import { normalizarPatente } from "../lib/patente.js?v=20261104gestion2";
import {
    USOS,
    CLASES,
    descripcionVehiculo,
    etiquetaUso,
    validarVehiculo,
} from "../lib/vehiculos.js?v=20261104gestion2";
import { formatearPorcentaje } from "../lib/companias.js?v=20261104gestion2";

const dialogoCartera = document.getElementById("dialog-cartera");
const formularioCartera = document.getElementById("formulario-cartera");
const errorCartera = document.getElementById("cartera-error");
const guardarCartera = document.getElementById("cartera-guardar");
let polizaEnCartera = null;

async function abrirCartera(poliza) {
    errorCartera.textContent = "";
    polizaEnCartera = poliza;
    document.getElementById("cartera-titulo").textContent = `Completar ${poliza.numero_poliza}`;
    try {
        const companias = (await api.get("/api/companias/?activas=1")).resultados ?? [];
        if (poliza.compania && !companias.some(c => c.id === poliza.compania.id)) companias.push(poliza.compania);
        const vehiculos = [...vehiculosDelCliente];
        if (poliza.vehiculo && !vehiculos.some(v => v.id === poliza.vehiculo.id)) vehiculos.push(poliza.vehiculo);
        llenarSelect(formularioCartera.elements.vehiculo_id, [["", "Sin vehículo"],
            ...vehiculos.map(v => [String(v.id), descripcionVehiculo(v)])]);
        llenarSelect(formularioCartera.elements.compania_id, [["", "Sin compañía"],
            ...companias.map(c => [String(c.id), c.nombre])]);
        formularioCartera.elements.vehiculo_id.value = poliza.vehiculo?.id ?? "";
        formularioCartera.elements.compania_id.value = poliza.compania?.id ?? "";
        formularioCartera.elements.comision_pct.value = poliza.comision_pct ?? "";
        dialogoCartera.showModal();
    } catch (error) {
        mostrarEstado(error.mensaje ?? error.message ?? "No se pudo abrir la póliza.", true);
    }
}

document.getElementById("cartera-cancelar").addEventListener("click", () => dialogoCartera.close());
formularioCartera.elements.compania_id.addEventListener("change", () => {
    formularioCartera.elements.comision_pct.value = "";
});
formularioCartera.addEventListener("submit", async evento => {
    evento.preventDefault();
    if (!formularioCartera.reportValidity()) return;
    guardarCartera.disabled = true;
    errorCartera.textContent = "";
    const campos = formularioCartera.elements;
    const cuerpo = {};
    // No reenviar vínculos que siguen iguales: una compañía histórica inactiva
    // debe conservarse al completar, por ejemplo, solo el vehículo.
    if (String(campos.vehiculo_id.value) !== String(polizaEnCartera.vehiculo?.id ?? "")) {
        cuerpo.vehiculo_id = campos.vehiculo_id.value ? Number(campos.vehiculo_id.value) : null;
    }
    if (String(campos.compania_id.value) !== String(polizaEnCartera.compania?.id ?? "")) {
        cuerpo.compania_id = campos.compania_id.value ? Number(campos.compania_id.value) : null;
    }
    if (campos.comision_pct.value !== String(polizaEnCartera.comision_pct ?? "")) {
        cuerpo.comision_pct = campos.comision_pct.value || null;
    }
    try {
        await api.patch(`/api/polizas/${polizaEnCartera.id}/cartera/`, cuerpo);
        dialogoCartera.close();
        await cargarFicha();
        mostrarEstado("Datos de la póliza actualizados.");
    } catch (error) {
        errorCartera.textContent = error.mensaje ?? error.message ?? "No se pudo guardar.";
    } finally {
        guardarCartera.disabled = false;
    }
});

const idCliente = new URLSearchParams(globalThis.location.search).get("id");
const nombreCliente = document.getElementById("nombre-cliente");
const datosCliente = document.getElementById("datos-cliente");
const estado = document.getElementById("estado-ficha");
const contactos = document.getElementById("contactos-cliente");
const polizasCliente = document.getElementById("polizas-cliente");
const siniestrosCliente = document.getElementById("siniestros-cliente");

const insigniaActivo = document.getElementById("estado-activo-cliente");
const botonBaja = document.getElementById("boton-baja-cliente");
const botonEliminar = document.getElementById("boton-eliminar-cliente");
const dialogoEliminar = document.getElementById("dialog-eliminar-cliente");
const errorEliminar = document.getElementById("eliminar-cliente-error");
const botonEliminarCancelar = document.getElementById("eliminar-cliente-cancelar");
const botonEliminarConfirmar = document.getElementById("eliminar-cliente-confirmar");
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

const estadoVehiculos = document.getElementById("estado-vehiculos");
const vehiculosCliente = document.getElementById("vehiculos-cliente");
const botonNuevoVehiculo = document.getElementById("boton-nuevo-vehiculo");
const dialogoVehiculo = document.getElementById("dialog-vehiculo");
const formularioVehiculo = document.getElementById("formulario-vehiculo");
const tituloVehiculo = document.getElementById("vehiculo-titulo");
const errorVehiculo = document.getElementById("vehiculo-error");
const botonGuardarVehiculo = document.getElementById("vehiculo-guardar");
const dialogoBajaVehiculo = document.getElementById("dialog-baja-vehiculo");
const formularioBajaVehiculo = document.getElementById("formulario-baja-vehiculo");
const textoBajaVehiculo = document.getElementById("baja-vehiculo-texto");
const errorBajaVehiculo = document.getElementById("baja-vehiculo-error");
const botonConfirmarBaja = document.getElementById("baja-vehiculo-confirmar");
const campoComisionPoliza = document.getElementById("campo-comision-poliza");

const CAMPOS_VEHICULO = ["patente", "marca", "modelo", "anio", "valor_asegurado"];
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

/** Solo comodidad: la API es la que niega escribir y la que oculta la comisión (R17). */
let esAprobador = false;
let esAdministrador = false;
let vehiculosDelCliente = [];
let clienteActivo = true;
let funcionarioConsultado = false;

async function saberSiAprueba() {
    if (funcionarioConsultado) {
        return;
    }
    try {
        const me = await api.get("/api/auth/me/");
        esAprobador = Boolean(me?.puede_aprobar);
        esAdministrador = me?.rol === "administrador";
    } catch {
        esAprobador = false;
        esAdministrador = false;
    }
    funcionarioConsultado = true;
}

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
    agregarDato(cuerpo, "Vehículo", poliza.vehiculo ? descripcionVehiculo(poliza.vehiculo) : poliza.bien_asegurado);
    agregarDato(cuerpo, "Compañía", poliza.compania?.nombre);
    if (poliza.comision_pct !== null && poliza.comision_pct !== undefined) {
        // La API manda null a quien no puede verla: acá simplemente no hay fila.
        agregarDato(cuerpo, "Comisión", formatearPorcentaje(poliza.comision_pct));
        agregarDato(cuerpo, "Comisión mensual estimada", formatearMonto(poliza.comision_mensual_estimada));
    }
    agregarDato(cuerpo, "Saldo pendiente", formatearMonto(poliza.saldo_pendiente));
    agregarDato(cuerpo, "Próximo vencimiento de pago", formatearFecha(poliza.proximo_vencimiento_pago));
    renderizarCuotas(cuerpo, poliza.cuotas);
    const diagnostico = crearElemento('details', 'mt-3');
    const tituloBot = crearElemento('summary', 'small', 'Condiciones que puede leer el bot');
    const estadoBot = crearElemento('p', 'small text-muted mt-2', 'Abrí para comprobar vigencia y documentos vinculados.');
    const contenidoBot = crearElemento('div', 'mt-2');
    diagnostico.append(tituloBot, estadoBot, contenidoBot);
    diagnostico.addEventListener('toggle', async () => {
        if (!diagnostico.open) return;
        estadoBot.textContent = 'Comprobando…';
        try {
            const d = await api.get(`/api/polizas/${poliza.id}/diagnostico-bot/`);
            estadoBot.textContent = d.listo ? 'Lista para consultas desde el número de WhatsApp del cliente.' : d.problemas.join(' ');
            contenidoBot.replaceChildren();
            for (const doc of d.documentos) contenidoBot.append(crearElemento('p', 'small mb-1', `${doc.titulo}: ${doc.estado}`));
            if (esAprobador) {
                const opciones = document.createElement('select');
                opciones.className = 'form-select form-select-sm mb-2';
                opciones.setAttribute('aria-label', `Condiciones para ${poliza.numero_poliza}`);
                opciones.add(new Option('Elegí un documento aprobado', ''));
                for (const doc of d.disponibles) opciones.add(new Option(`${doc.titulo} · ${doc.version}`, String(doc.id)));
                const vincular = botonDeVehiculo('Vincular condiciones a esta póliza', 'btn-outline-primary', async () => {
                    if (!opciones.value) { estadoBot.textContent = 'Seleccioná las condiciones correspondientes a este contrato.'; return; }
                    vincular.disabled = true;
                    try {
                        await api.post(`/api/polizas/${poliza.id}/documentos/`, {documento_id:Number(opciones.value)});
                        estadoBot.textContent = 'Condiciones vinculadas. Si el chat está en modo humano, devolvelo al bot desde la conversación para volver a probar.';
                    } catch (e) { estadoBot.textContent = e.mensaje ?? e.message; }
                    finally { vincular.disabled = false; }
                });
                contenidoBot.append(opciones, vincular);
            }
        } catch (e) { estadoBot.textContent = e.mensaje ?? e.message; }
    });
    cuerpo.append(diagnostico);
    const credencial=crearElemento('a','btn btn-outline-secondary mt-3 me-2','Credencial para celular · PNG');
    credencial.href=`/api/gestion/polizas/${poliza.id}/credencial/?formato=png`;cuerpo.append(credencial);
    const versionWeb=crearElemento('a','btn btn-outline-secondary mt-3 me-2','Versión web de la credencial');
    versionWeb.href=`/api/gestion/polizas/${poliza.id}/credencial/`;cuerpo.append(versionWeb);
    if (esAprobador) {
        cuerpo.append(botonDeVehiculo("Completar vehículo y compañía", "btn-outline-primary mt-3",
            () => abrirCartera(poliza)));
    }
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

// --- Vehículos ------------------------------------------------------------

function mostrarEstadoVehiculos(mensaje, error = false) {
    estadoVehiculos.textContent = mensaje;
    estadoVehiculos.classList.toggle("d-none", !mensaje);
    estadoVehiculos.classList.toggle("alert-danger", error);
    estadoVehiculos.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function botonDeVehiculo(texto, clase, alHacerClic) {
    const elemento = crearElemento("button", `btn btn-sm ${clase}`, texto);
    elemento.type = "button";
    elemento.addEventListener("click", alHacerClic);
    return elemento;
}

function filaDeVehiculo(vehiculo) {
    const fila = document.createElement("tr");
    const patente = crearElemento("th", "fw-semibold", vehiculo.patente);
    patente.scope = "row";
    fila.append(
        patente,
        crearElemento("td", "", vehiculo.marca),
        crearElemento("td", "", vehiculo.modelo),
        crearElemento("td", "", String(vehiculo.anio)),
        crearElemento("td", "", CLASES.find(([c]) => c === vehiculo.clase)?.[1] ?? "Sin especificar"),
        crearElemento("td", "", etiquetaUso(vehiculo.uso)),
        crearElemento("td", "", vehiculo.chasis ?? "—"),
        crearElemento("td", "text-end", formatearMonto(vehiculo.valor_asegurado)),
    );
    if (esAprobador) {
        const acciones = crearElemento("td", "text-end text-nowrap");
        acciones.append(
            botonDeVehiculo("Editar", "btn-outline-primary me-2", () => abrirFormularioVehiculo(vehiculo)),
            botonDeVehiculo("Dar de baja", "btn-outline-danger", () => abrirBajaVehiculo(vehiculo)),
        );
        fila.append(acciones);
    }
    return fila;
}

function renderizarVehiculos(vehiculos) {
    vehiculosCliente.replaceChildren();
    botonNuevoVehiculo.classList.toggle("d-none", !esAprobador || !clienteActivo);
    if (vehiculos.length === 0) {
        vehiculosCliente.append(crearElemento("p", "text-muted mb-0", "No hay vehículos registrados."));
        return;
    }
    const envoltorio = crearElemento("div", "table-responsive");
    const tabla = crearElemento("table", "table table-sm align-middle mb-0");
    const cabecera = document.createElement("thead");
    const encabezado = document.createElement("tr");
    const titulos = ["Patente", "Marca", "Modelo", "Año", "Clase", "Uso", "Chasis", "Valor asegurado"];
    for (const texto of titulos) {
        const th = crearElemento("th", "", texto);
        th.scope = "col";
        encabezado.append(th);
    }
    if (esAprobador) {
        const th = document.createElement("th");
        th.scope = "col";
        th.append(crearElemento("span", "visually-hidden", "Acciones"));
        encabezado.append(th);
    }
    cabecera.append(encabezado);
    const cuerpo = document.createElement("tbody");
    cuerpo.append(...vehiculos.map(filaDeVehiculo));
    tabla.append(cabecera, cuerpo);
    envoltorio.append(tabla);
    vehiculosCliente.append(envoltorio);
}

function pintarErroresVehiculo(errores) {
    for (const campo of CAMPOS_VEHICULO) {
        const entrada = formularioVehiculo.elements[campo];
        const aviso = formularioVehiculo.querySelector(`[data-error="${campo}"]`);
        entrada.classList.toggle("is-invalid", Boolean(errores[campo]));
        if (aviso) {
            aviso.textContent = errores[campo] ?? "";
        }
    }
}

let vehiculoEnEdicion = null;

function abrirFormularioVehiculo(vehiculo = null) {
    vehiculoEnEdicion = vehiculo;
    tituloVehiculo.textContent = vehiculo ? `Editar ${vehiculo.patente}` : "Agregar vehículo";
    const elementos = formularioVehiculo.elements;
    elementos.patente.value = vehiculo?.patente ?? "";
    elementos.marca.value = vehiculo?.marca ?? "";
    elementos.modelo.value = vehiculo?.modelo ?? "";
    elementos.anio.value = vehiculo ? String(vehiculo.anio) : "";
    elementos.uso.value = vehiculo?.uso ?? "particular";
    elementos.clase.value = vehiculo?.clase ?? "sin_especificar";
    elementos.chasis.value = vehiculo?.chasis ?? "";
    elementos.valor_asegurado.value = vehiculo?.valor_asegurado ?? "";
    pintarErroresVehiculo({});
    errorVehiculo.textContent = "";
    dialogoVehiculo.showModal();
}

function abrirBajaVehiculo(vehiculo) {
    vehiculoEnEdicion = vehiculo;
    textoBajaVehiculo.textContent = `${descripcionVehiculo(vehiculo)} deja de figurar entre los vehículos del cliente. `
        + "Su historial se conserva. Si todavía tiene una póliza vigente, la baja se rechaza.";
    errorBajaVehiculo.textContent = "";
    dialogoBajaVehiculo.showModal();
}

/** Lo que viaja: en la edición, solo lo que tiene valor (chasis y valor vacíos lo borran). */
function cuerpoDeVehiculo() {
    const elementos = formularioVehiculo.elements;
    const cuerpo = {
        patente: normalizarPatente(elementos.patente.value),
        marca: elementos.marca.value.trim(),
        modelo: elementos.modelo.value.trim(),
        anio: elementos.anio.value.trim(),
        uso: elementos.uso.value,
        clase: elementos.clase.value,
        chasis: elementos.chasis.value.trim(),
        valor_asegurado: elementos.valor_asegurado.value.trim(),
    };
    if (!vehiculoEnEdicion) {
        // En el alta, vacío es «sin dato»: no se manda.
        for (const clave of ["chasis", "valor_asegurado"]) {
            if (!cuerpo[clave]) {
                delete cuerpo[clave];
            }
        }
    }
    return cuerpo;
}

formularioVehiculo.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const cuerpo = cuerpoDeVehiculo();
    const errores = validarVehiculo(cuerpo);
    pintarErroresVehiculo(errores);
    if (Object.keys(errores).length > 0) {
        errorVehiculo.textContent = "Revisá los campos marcados.";
        return;
    }
    botonGuardarVehiculo.disabled = true;
    errorVehiculo.textContent = "";
    try {
        if (vehiculoEnEdicion) {
            const guardado = await api.patch(`/api/vehiculos/${vehiculoEnEdicion.id}/`, {
                ...cuerpo,
                anio: Number(cuerpo.anio),
            });
            mostrarEstadoVehiculos(`Se actualizó ${guardado.patente}.`);
        } else {
            const guardado = await api.post("/api/vehiculos/", {
                ...cuerpo,
                anio: Number(cuerpo.anio),
                cliente: Number(idCliente),
            });
            mostrarEstadoVehiculos(`Se agregó ${guardado.patente}.`);
        }
        dialogoVehiculo.close();
        await cargarFicha();
    } catch (error) {
        errorVehiculo.textContent = error.mensaje ?? error.message ?? "No se pudo guardar el vehículo.";
    } finally {
        botonGuardarVehiculo.disabled = false;
    }
});

formularioBajaVehiculo.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    botonConfirmarBaja.disabled = true;
    errorBajaVehiculo.textContent = "";
    try {
        await api.post(`/api/vehiculos/${vehiculoEnEdicion.id}/baja/`, {});
        dialogoBajaVehiculo.close();
        mostrarEstadoVehiculos(`${vehiculoEnEdicion.patente} quedó dado de baja.`);
        await cargarFicha();
    } catch (error) {
        // El 409 de «tiene una póliza vigente» llega acá con el mensaje de la API.
        errorBajaVehiculo.textContent = error.mensaje ?? error.message ?? "No se pudo dar de baja.";
    } finally {
        botonConfirmarBaja.disabled = false;
    }
});

botonNuevoVehiculo.addEventListener("click", () => abrirFormularioVehiculo(null));
document.getElementById("vehiculo-cancelar").addEventListener("click", () => dialogoVehiculo.close());
document.getElementById("baja-vehiculo-cancelar").addEventListener("click", () => dialogoBajaVehiculo.close());
for (const [codigo, texto] of CLASES) {
    formularioVehiculo.elements.clase.add(new Option(texto, codigo));
}
for (const [codigo, texto] of USOS) {
    const opcion = document.createElement("option");
    opcion.value = codigo;
    opcion.textContent = texto;
    formularioVehiculo.elements.uso.append(opcion);
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
    // Solo el rol administrador; la API lo exige igual.
    botonEliminar.classList.toggle("d-none", !esAdministrador);
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

botonEliminar.addEventListener("click", () => {
    errorEliminar.textContent = "";
    dialogoEliminar.showModal();
});
botonEliminarCancelar.addEventListener("click", () => dialogoEliminar.close());
botonEliminarConfirmar.addEventListener("click", async () => {
    botonEliminarConfirmar.disabled = true;
    errorEliminar.textContent = "";
    try {
        await api.post(`/api/clientes/${idCliente}/eliminar-definitivo/`, {});
        globalThis.location.assign("/panel/clientes/");
    } catch (error) {
        errorEliminar.textContent = error.mensaje ?? error.message ?? "No se pudo eliminar el cliente.";
    } finally {
        botonEliminarConfirmar.disabled = false;
    }
});

async function cargarFicha() {
    inicializarNav();
    if (!/^[1-9]\d*$/.test(idCliente ?? "")) {
        mostrarEstado("El identificador de cliente no es válido.", true);
        return;
    }

    mostrarEstado("Cargando ficha…");
    try {
        await saberSiAprueba();
        const cliente = await api.get(`/api/clientes/${idCliente}/`);
        const polizasOrdenadas = ordenarPolizas(cliente.polizas ?? []);
        const polizasDetalladas = await Promise.all(polizasOrdenadas.map(
            (poliza) => api.get(`/api/polizas/${poliza.id}/`),
        ));

        nombreCliente.textContent = `${cliente.nombre} ${cliente.apellido}`;
        datosCliente.textContent = `DNI: ${cliente.dni} · Correo: ${cliente.email ?? "—"}`;
        prepararAbm(cliente);
        renderizarContactos(cliente);
        clienteActivo = cliente.activo !== false;
        vehiculosDelCliente = cliente.vehiculos ?? [];
        renderizarVehiculos(vehiculosDelCliente);
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

/** Compañías activas y vehículos del cliente para los dos selects opcionales. */
async function cargarCompaniasDePoliza() {
    campoComisionPoliza.classList.toggle("d-none", !esAprobador);
    let companias = [];
    try {
        companias = (await api.get("/api/companias/?activas=1")).resultados ?? [];
    } catch (error) {
        mostrarEstadoNuevaPoliza(
            error.mensaje ?? error.message ?? "No se pudieron cargar las compañías.",
            true,
        );
    }
    llenarSelect(
        formularioPoliza.elements.compania_id,
        [["", "Sin compañía"], ...companias.map((compania) => [String(compania.id), compania.nombre])],
    );
    llenarSelect(
        formularioPoliza.elements.vehiculo_id,
        [["", "Sin vehículo"], ...vehiculosDelCliente.map((vehiculo) => [
            String(vehiculo.id),
            descripcionVehiculo(vehiculo),
        ])],
    );
}

panelNuevaPoliza.addEventListener("toggle", async () => {
    if (panelNuevaPoliza.open) {
        await cargarOpcionesPoliza();
        // Cada vez que se abre: los vehículos pudieron cambiar desde la última vez.
        await cargarCompaniasDePoliza();
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
        + "con vencimiento al inicio de cada ciclo mensual desde la fecha de inicio.";
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
    // Opcionales: lo vacío no viaja (la API entiende su ausencia como «ninguno»).
    for (const campo of ["vehiculo_id", "compania_id"]) {
        const valor = formularioPoliza.elements[campo].value;
        if (valor) {
            cuerpo[campo] = Number(valor);
        }
    }
    const comision = formularioPoliza.elements.comision_pct.value.trim();
    if (comision) {
        cuerpo.comision_pct = comision;
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
if(idCliente)iniciarNotas(idCliente);
if(idCliente)iniciarFidelizacion(idCliente).catch(e=>mostrarEstado(e.mensaje??e.message));
