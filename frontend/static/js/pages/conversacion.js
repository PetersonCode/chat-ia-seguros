import { api } from "../api.js";
import { inicializarNav } from "../nav.js";
import { formatearFecha, formatearFechaHora, formatearMonto } from "../lib/formato.js";
import { accionesPermitidas, fusionarMensajes } from "../lib/mensajes.js";

const idConversacion = new URLSearchParams(globalThis.location.search).get("id");
const tituloChat = document.getElementById("titulo-chat");
const estadoChat = document.getElementById("estado-chat");
const contactoChat = document.getElementById("contacto-chat");
const mensajePagina = document.getElementById("mensaje-pagina");
const panelCliente = document.getElementById("panel-cliente");
const panelAlertas = document.getElementById("panel-alertas");
const mensajesChat = document.getElementById("mensajes-chat");
const botonModo = document.getElementById("boton-modo");
const formularioRespuesta = document.getElementById("formulario-respuesta");
const textoRespuesta = document.getElementById("texto-respuesta");
const botonResponder = document.getElementById("boton-responder");
const avisoVentana = document.getElementById("aviso-ventana");
const dialogo = document.getElementById("dialog-accion");
const dialogoTitulo = document.getElementById("dialog-titulo");
const dialogoDescripcion = document.getElementById("dialog-descripcion");
const dialogoLabel = document.getElementById("dialog-label");
const dialogoTexto = document.getElementById("dialog-texto");
const dialogoError = document.getElementById("dialog-error");
const dialogoCancelar = document.getElementById("dialog-cancelar");
const dialogoConfirmar = document.getElementById("dialog-confirmar");

let conversacion = null;
let funcionario = null;
let mensajes = [];
let accionSeleccionada = null;
let sondeoEnCurso = false;
const nodosPorId = new Map();
const mensajesPorId = new Map();

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

function mostrarMensajePagina(mensaje, error = false) {
    mensajePagina.textContent = mensaje;
    mensajePagina.classList.toggle("d-none", !mensaje);
    mensajePagina.classList.toggle("alert-danger", error);
    mensajePagina.classList.toggle("alert-info", Boolean(mensaje) && !error);
}

function nombreRemitente(mensaje) {
    if (mensaje.direccion === "entrante" || mensaje.emisor === "cliente") {
        return "Cliente";
    }
    if (mensaje.emisor === "funcionario") {
        return mensaje.funcionario?.nombre ?? "Funcionario";
    }
    return "Bot automático";
}

function crearBotonAccion(mensaje, accion) {
    const etiquetas = {
        liberar: "Liberar",
        corregir: "Corregir",
        descartar: "Descartar",
    };
    const boton = crearElemento("button", "btn btn-sm btn-danger ms-2", etiquetas[accion]);
    boton.type = "button";
    boton.addEventListener("click", () => abrirDialogo(mensaje, accion));
    return boton;
}

function actualizarNodoMensaje(nodo, mensaje) {
    nodo.className = "mensaje-chat";
    nodo.classList.add(mensaje.direccion === "entrante" ? "msg-cliente" : "msg-saliente");
    if (mensaje.estado_envio === "retenido") {
        nodo.classList.add("msg-retenido");
    }
    if (mensaje.estado_envio === "descartado") {
        nodo.classList.add("msg-descartado");
    }

    const encabezado = crearElemento(
        "p",
        "small text-muted mb-2",
        `${nombreRemitente(mensaje)} · ${formatearFechaHora(mensaje.fecha_hora)} · ${mensaje.estado_envio}`,
    );
    const texto = crearElemento("p", "mb-2", mensaje.texto ?? "");
    const contenido = [encabezado, texto];

    const acciones = accionesPermitidas(mensaje, funcionario);
    if (acciones.length > 0) {
        const grupo = crearElemento("div", "d-flex justify-content-end flex-wrap");
        for (const accion of acciones) {
            grupo.append(crearBotonAccion(mensaje, accion));
        }
        contenido.push(grupo);
    }
    nodo.replaceChildren(...contenido);
}

function renderizarMensajes() {
    for (let indice = 0; indice < mensajes.length; indice += 1) {
        const mensaje = mensajes[indice];
        let nodo = nodosPorId.get(mensaje.id);
        if (!nodo) {
            nodo = document.createElement("article");
            nodosPorId.set(mensaje.id, nodo);
            actualizarNodoMensaje(nodo, mensaje);
        } else if (JSON.stringify(mensajesPorId.get(mensaje.id)) !== JSON.stringify(mensaje)) {
            actualizarNodoMensaje(nodo, mensaje);
        }
        mensajesPorId.set(mensaje.id, mensaje);

        if (!nodo.isConnected) {
            const siguiente = mensajes[indice + 1];
            const nodoSiguiente = siguiente ? nodosPorId.get(siguiente.id) : null;
            mensajesChat.insertBefore(nodo, nodoSiguiente?.parentNode === mensajesChat ? nodoSiguiente : null);
        }
    }
}

function renderizarCliente(detalle) {
    panelCliente.replaceChildren();
    const cliente = detalle.cliente_info;
    if (!cliente) {
        panelCliente.append(crearElemento("p", "mb-1", "Contacto desconocido"));
        panelCliente.append(crearElemento("p", "text-muted small mb-0", detalle.whatsapp));
        return;
    }

    const nombre = [cliente.nombre, cliente.apellido].filter(Boolean).join(" ");
    panelCliente.append(crearElemento("h3", "h6", nombre || "Cliente"));
    panelCliente.append(crearElemento("p", "small text-muted mb-3", `DNI: ${cliente.dni}`));

    const polizas = Array.isArray(cliente.polizas) ? cliente.polizas : [];
    if (polizas.length === 0) {
        panelCliente.append(crearElemento("p", "text-muted mb-0", "Sin pólizas registradas."));
        return;
    }

    const lista = crearElemento("ul", "list-group list-group-flush");
    for (const poliza of polizas) {
        const item = crearElemento("li", "list-group-item px-0");
        item.append(crearElemento("strong", "", poliza.numero_poliza));
        item.append(crearElemento("div", "small", `${poliza.tipo_seguro} · ${poliza.estado}`));
        item.append(crearElemento("div", "small", `Saldo pendiente: ${formatearMonto(poliza.saldo_pendiente)}`));
        item.append(crearElemento("div", "small", `Próximo vencimiento: ${formatearFecha(poliza.proximo_vencimiento_pago)}`));
        lista.append(item);
    }
    panelCliente.append(lista);
}

function renderizarAlertas(alertas) {
    panelAlertas.replaceChildren();
    if (!Array.isArray(alertas) || alertas.length === 0) {
        panelAlertas.append(crearElemento("p", "text-muted mb-0", "No hay alertas."));
        return;
    }

    const lista = crearElemento("ul", "list-group list-group-flush");
    for (const alerta of alertas) {
        const item = crearElemento("li", "list-group-item px-0");
        item.append(crearElemento("strong", "d-block", `${alerta.severidad}: ${alerta.tipo}`));
        item.append(crearElemento("span", "small", alerta.descripcion));
        lista.append(item);
    }
    panelAlertas.append(lista);
}

function renderizarConversacion(detalle) {
    conversacion = detalle;
    tituloChat.textContent = `Conversación ${detalle.id}`;
    contactoChat.textContent = `Chat con: ${detalle.whatsapp}`;
    estadoChat.textContent = `Estado: ${detalle.estado} · Modo: ${detalle.modo}`;

    botonModo.hidden = false;
    botonModo.textContent = detalle.modo === "humano" ? "Devolver al bot" : "Tomar conversación";

    const modoHumano = detalle.modo === "humano";
    formularioRespuesta.hidden = !modoHumano;
    textoRespuesta.disabled = !detalle.ventana_24h_abierta;
    botonResponder.disabled = !detalle.ventana_24h_abierta;
    avisoVentana.hidden = detalle.ventana_24h_abierta;
    avisoVentana.textContent = detalle.ventana_24h_abierta
        ? ""
        : "La ventana de atención de 24 horas está cerrada; no se puede responder por WhatsApp.";

    renderizarCliente(detalle);
    renderizarAlertas(detalle.alertas);
}

function abrirDialogo(mensaje, accion) {
    accionSeleccionada = { mensaje, accion };
    dialogoError.textContent = "";
    dialogoTexto.value = "";
    dialogoLabel.hidden = accion === "liberar";
    dialogoTexto.hidden = accion === "liberar";
    dialogoTexto.required = accion !== "liberar";

    if (accion === "liberar") {
        dialogoTitulo.textContent = "Liberar respuesta";
        dialogoDescripcion.textContent = "La respuesta retenida se enviará al cliente. ¿Querés continuar?";
    } else if (accion === "corregir") {
        dialogoTitulo.textContent = "Corregir respuesta";
        dialogoDescripcion.textContent = "Revisá el texto antes de enviarlo al cliente.";
        dialogoLabel.textContent = "Texto corregido";
        dialogoTexto.value = mensaje.texto;
    } else {
        dialogoTitulo.textContent = "Descartar respuesta";
        dialogoDescripcion.textContent = "Indicá el motivo para dejar registro de la decisión.";
        dialogoLabel.textContent = "Motivo";
    }
    dialogo.showModal();
}

async function confirmarAccion() {
    if (!accionSeleccionada) {
        return;
    }
    const { mensaje, accion } = accionSeleccionada;
    const valorTexto = dialogoTexto.value.trim();
    if (accion !== "liberar" && !valorTexto) {
        dialogoError.textContent = accion === "descartar"
            ? "El motivo es obligatorio."
            : "La corrección no puede quedar vacía.";
        return;
    }

    dialogoConfirmar.disabled = true;
    dialogoError.textContent = "";
    try {
        let actualizado;
        if (accion === "descartar") {
            actualizado = await api.post(`/api/mensajes/${mensaje.id}/descartar/`, { motivo: valorTexto });
        } else if (accion === "corregir") {
            actualizado = await api.post(`/api/mensajes/${mensaje.id}/liberar/`, { texto_corregido: valorTexto });
        } else {
            actualizado = await api.post(`/api/mensajes/${mensaje.id}/liberar/`);
        }
        mensajes = fusionarMensajes(mensajes, [actualizado]);
        renderizarMensajes();
        dialogo.close();
        mostrarMensajePagina(accion === "descartar" ? "Respuesta descartada." : "Respuesta enviada.");
    } catch (error) {
        dialogoError.textContent = error.mensaje ?? error.message ?? "No se pudo completar la acción.";
    } finally {
        dialogoConfirmar.disabled = false;
    }
}

async function cambiarModo() {
    if (!conversacion) {
        return;
    }
    botonModo.disabled = true;
    mostrarMensajePagina("");
    try {
        const accion = conversacion.modo === "humano" ? "devolver" : "tomar";
        conversacion = await api.post(`/api/conversaciones/${idConversacion}/${accion}/`);
        renderizarConversacion(conversacion);
    } catch (error) {
        mostrarMensajePagina(error.mensaje ?? error.message ?? "No se pudo cambiar el modo de atención.", true);
    } finally {
        botonModo.disabled = false;
    }
}

async function responder(evento) {
    evento.preventDefault();
    const texto = textoRespuesta.value.trim();
    if (!texto || !conversacion?.ventana_24h_abierta) {
        return;
    }
    botonResponder.disabled = true;
    try {
        const mensaje = await api.post(`/api/conversaciones/${idConversacion}/responder/`, { texto });
        mensajes = fusionarMensajes(mensajes, [mensaje]);
        renderizarMensajes();
        textoRespuesta.value = "";
        mensajesChat.scrollTop = mensajesChat.scrollHeight;
    } catch (error) {
        mostrarMensajePagina(error.mensaje ?? error.message ?? "No se pudo enviar la respuesta.", true);
    } finally {
        botonResponder.disabled = !conversacion.ventana_24h_abierta;
    }
}

async function cargarNuevosMensajes() {
    if (sondeoEnCurso || document.hidden || !conversacion) {
        return;
    }
    sondeoEnCurso = true;
    try {
        const ultimoId = mensajes.length > 0 ? mensajes[mensajes.length - 1].id : 0;
        const respuesta = await api.get(
            `/api/conversaciones/${idConversacion}/mensajes/?despues_de=${encodeURIComponent(ultimoId)}`,
        );
        if (!Array.isArray(respuesta.mensajes)) {
            throw new Error("La respuesta de mensajes no tiene el formato esperado.");
        }
        mensajes = fusionarMensajes(mensajes, respuesta.mensajes);
        renderizarMensajes();
    } catch (error) {
        mostrarMensajePagina(error.mensaje ?? error.message ?? "No se pudieron actualizar los mensajes.", true);
    } finally {
        sondeoEnCurso = false;
    }
}

async function iniciar() {
    inicializarNav();
    if (!/^[1-9]\d*$/.test(idConversacion ?? "")) {
        mostrarMensajePagina("El identificador de conversación no es válido.", true);
        return;
    }

    mostrarMensajePagina("Cargando conversación…");
    try {
        const [detalle, respuestaMensajes, me] = await Promise.all([
            api.get(`/api/conversaciones/${idConversacion}/`),
            api.get(`/api/conversaciones/${idConversacion}/mensajes/`),
            api.get("/api/auth/me/"),
        ]);
        if (!Array.isArray(respuestaMensajes.mensajes)) {
            throw new Error("La respuesta de mensajes no tiene el formato esperado.");
        }
        funcionario = me;
        conversacion = detalle;
        mensajes = fusionarMensajes([], respuestaMensajes.mensajes);
        renderizarConversacion(detalle);
        renderizarMensajes();
        mostrarMensajePagina("");
        mensajesChat.scrollTop = mensajesChat.scrollHeight;
        globalThis.setInterval(cargarNuevosMensajes, 5_000);
    } catch (error) {
        mostrarMensajePagina(error.mensaje ?? error.message ?? "No se pudo cargar la conversación.", true);
    }
}

botonModo.addEventListener("click", cambiarModo);
formularioRespuesta.addEventListener("submit", responder);
dialogoCancelar.addEventListener("click", () => dialogo.close());
dialogoConfirmar.addEventListener("click", confirmarAccion);

iniciar();
