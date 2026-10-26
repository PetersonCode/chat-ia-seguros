import { api } from "../api.js?v=20261026fix2";
import { inicializarNav } from "../nav.js?v=20261026fix2";
import { formatearFecha, formatearFechaHora, formatearMonto } from "../lib/formato.js?v=20261026fix2";
import { accionesPermitidas, fusionarMensajes } from "../lib/mensajes.js?v=20261026fix2";
import { claseSeveridad, etiquetaSeveridad } from "../lib/color.js?v=20261026fix2";
import { claseTarjetaSeveridad, crearInsignia, crearTarjeta } from "../lib/tarjetas.js?v=20261026fix2";

const idConversacion = new URLSearchParams(globalThis.location.search).get("id");
const tituloChat = document.getElementById("titulo-chat");
const estadoChat = document.getElementById("estado-chat");
const contactoChat = document.getElementById("contacto-chat");
const mensajePagina = document.getElementById("mensaje-pagina");
const panelCasos = document.getElementById("panel-casos");
const panelCliente = document.getElementById("panel-cliente");
const panelAlertas = document.getElementById("panel-alertas");
const mensajesChat = document.getElementById("mensajes-chat");
const botonModo = document.getElementById("boton-modo");
const botonCerrarCasos = document.getElementById("boton-cerrar-casos");
const botonVaciar = document.getElementById("boton-vaciar");
const formularioRespuesta = document.getElementById("formulario-respuesta");
const textoRespuesta = document.getElementById("texto-respuesta");
const botonResponder = document.getElementById("boton-responder");
const avisoVentana = document.getElementById("aviso-ventana");
const dialogo = document.getElementById("dialog-accion");
const dialogoTitulo = document.getElementById("dialog-titulo");
const dialogoDescripcion = document.getElementById("dialog-descripcion");
const dialogoLabel = document.getElementById("dialog-label");
const dialogoTexto = document.getElementById("dialog-texto");
const camposPago = document.getElementById("campos-pago");
const referenciaPago = document.getElementById("referencia-pago");
const importePago = document.getElementById("importe-pago");
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
        panelCliente.append(crearElemento("p", "text-muted small mb-3", detalle.whatsapp));

        // Abre el alta con el teléfono y el nombre de perfil ya cargados. No se
        // crea ningún cliente acá: los datos reales los completa la persona.
        const parametros = new URLSearchParams({ telefono: detalle.whatsapp ?? "" });
        if (detalle.nombre_perfil) {
            parametros.set("perfil", detalle.nombre_perfil);
        }
        const alta = crearElemento("a", "btn btn-sm btn-outline-primary", "Dar de alta como cliente");
        alta.href = `/panel/clientes/?${parametros.toString()}`;
        panelCliente.append(alta);
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

    const grilla = crearElemento("div", "grilla-tarjetas grilla-angosta");
    for (const poliza of polizas) {
        // `saldo_pendiente` sale de `v_polizas_resumen`: si es cero no hay
        // ninguna cuota que cobrar y el botón no tendría qué hacer.
        const debe = Number(poliza.saldo_pendiente ?? 0) > 0;
        let pagar = null;
        if (debe) {
            pagar = crearElemento("button", "btn btn-sm btn-outline-success", "Póliza pagada");
            pagar.type = "button";
            pagar.addEventListener("click", () => confirmarPago(poliza));
        }
        grilla.append(crearTarjeta({
            titulo: poliza.numero_poliza,
            subtitulo: poliza.tipo_seguro,
            clase: debe ? "tarjeta-amarillo" : "tarjeta-verde",
            insignias: [crearInsignia(poliza.estado)],
            datos: [
                ["Saldo", debe ? formatearMonto(poliza.saldo_pendiente) : "Sin cuotas pendientes"],
                ["Vence pago", formatearFecha(poliza.proximo_vencimiento_pago)],
            ],
            acciones: [pagar],
        }));
    }
    panelCliente.append(grilla);
}

function renderizarAlertas(alertas) {
    panelAlertas.replaceChildren();
    if (!Array.isArray(alertas) || alertas.length === 0) {
        panelAlertas.append(crearElemento("p", "text-muted mb-0", "No hay alertas."));
        return;
    }

    const grilla = crearElemento("div", "grilla-tarjetas grilla-angosta");
    for (const alerta of alertas) {
        grilla.append(crearTarjeta({
            titulo: alerta.tipo,
            clase: claseTarjetaSeveridad(alerta.severidad),
            insignias: [crearInsignia(etiquetaSeveridad(alerta.severidad), claseSeveridad(alerta.severidad))],
            texto: alerta.descripcion,
        }));
    }
    panelAlertas.append(grilla);
}

function renderizarCasosAbiertos(casos) {
    panelCasos.replaceChildren();
    panelCasos.hidden = casos.length === 0;
    if (casos.length === 0) {
        return;
    }

    const titulo = crearElemento("h2", "h6 fw-bold", "Trabajo pendiente de esta conversación");
    const lista = crearElemento("ul", "mb-0");
    let accionesPendientes = 0;
    for (const caso of casos) {
        const item = crearElemento("li", "mb-2");
        item.append(crearElemento("strong", "", `${caso.codigo_caso}: `));
        item.append(document.createTextNode(`Caso ${caso.estado}.`));
        const acciones = Array.isArray(caso.acciones_pendientes)
            ? caso.acciones_pendientes
            : [];
        accionesPendientes += acciones.length;
        for (const accion of acciones) {
            const descripcion = crearElemento(
                "p",
                "mb-0 ms-3",
                `Acción ${accion.id} · ${accion.tipo_accion} · ${
                    accion.estado === "aprobada"
                        ? "Aprobada; pendiente de gestión externa"
                        : "Pendiente de aprobación"
                }.`,
            );
            const enlace = crearElemento(
                "a",
                "ms-3",
                "Ver acciones pendientes",
            );
            enlace.href = `/panel/acciones/?estado=${encodeURIComponent(accion.estado)}`;
            descripcion.append(enlace);
            item.append(descripcion);
        }
        lista.append(item);
    }
    panelCasos.append(titulo, lista);
    if (accionesPendientes > 0) {
        panelCasos.append(crearElemento(
            "p",
            "small fw-semibold mt-2 mb-0",
            "No se puede cerrar el caso mientras estas acciones sigan pendientes.",
        ));
    }
}

function renderizarConversacion(detalle) {
    conversacion = detalle;
    tituloChat.textContent = `Conversación ${detalle.id}`;
    contactoChat.textContent = `Chat con: ${detalle.whatsapp}`;
    const responsable = detalle.atendida_por?.nombre;
    estadoChat.textContent = [
        `Estado: ${detalle.estado}`,
        `Modo: ${detalle.modo}`,
        responsable ? `Responsable: ${responsable}` : null,
    ].filter(Boolean).join(" · ");

    // Una conversación vaciada ya no recibe mensajes: el cliente sigue en una
    // nueva. Queda solo para consulta.
    const cerrada = detalle.estado === "cerrada";
    botonModo.hidden = cerrada;
    const esResponsable = detalle.atendida_por?.id === funcionario?.id;
    botonModo.textContent = detalle.modo !== "humano"
        ? "Tomar conversación"
        : esResponsable
            ? "Devolver al bot"
            : "Reasignar conversación";
    botonVaciar.hidden = cerrada;

    const casosAbiertos = Array.isArray(detalle.casos_abiertos) ? detalle.casos_abiertos : [];
    botonCerrarCasos.hidden = casosAbiertos.length === 0;
    botonCerrarCasos.textContent = casosAbiertos.length > 1
        ? `Cerrar ${casosAbiertos.length} casos`
        : "Cerrar caso";
    const accionesPendientes = casosAbiertos.some(
        (caso) => Array.isArray(caso.acciones_pendientes) && caso.acciones_pendientes.length > 0,
    );
    botonCerrarCasos.disabled = accionesPendientes;
    botonCerrarCasos.title = accionesPendientes
        ? "Resolvé las acciones administrativas pendientes antes de cerrar."
        : "";
    renderizarCasosAbiertos(casosAbiertos);

    const modoHumano = detalle.modo === "humano";
    formularioRespuesta.hidden = !modoHumano || !esResponsable || cerrada;
    textoRespuesta.disabled = !detalle.ventana_24h_abierta;
    botonResponder.disabled = !detalle.ventana_24h_abierta;
    avisoVentana.hidden = detalle.ventana_24h_abierta;
    avisoVentana.textContent = detalle.ventana_24h_abierta
        ? ""
        : "La ventana de atención de 24 horas está cerrada; no se puede responder por WhatsApp.";

    renderizarCliente(detalle);
    renderizarAlertas(detalle.alertas);
}

/**
 * Abre el mismo diálogo que los mensajes retenidos, para una confirmación
 * simple sin campos de edición.
 */
function abrirConfirmacion(titulo, descripcion, alConfirmar) {
    accionSeleccionada = { alConfirmar };
    dialogoError.textContent = "";
    dialogoTexto.value = "";
    camposPago.hidden = true;
    referenciaPago.value = "";
    importePago.value = "";
    dialogoLabel.hidden = true;
    dialogoTexto.hidden = true;
    dialogoTexto.required = false;
    dialogoTitulo.textContent = titulo;
    dialogoDescripcion.textContent = descripcion;
    dialogo.showModal();
}

function confirmarPago(poliza) {
    accionSeleccionada = { tipo: "pago", poliza };
    dialogoError.textContent = "";
    dialogoTexto.value = "";
    dialogoLabel.hidden = true;
    dialogoTexto.hidden = true;
    dialogoTexto.required = false;
    dialogoTitulo.textContent = "Registrar pago";
    dialogoDescripcion.textContent = [
        `Cuota de ${poliza.numero_poliza} con vencimiento ${formatearFecha(poliza.proximo_vencimiento_pago)}.`,
        "Solo se admiten pagos completos: el importe debe coincidir exactamente con el de una cuota.",
        "La referencia identifica el comprobante y no puede reutilizarse para otro cobro.",
    ].join(" ");
    camposPago.hidden = false;
    referenciaPago.value = "";
    importePago.value = "";
    dialogo.showModal();
}

function cerrarCasos() {
    const casos = conversacion?.casos_abiertos ?? [];
    if (casos.length === 0) {
        return;
    }
    const codigos = casos.map((caso) => caso.codigo_caso).join(", ");
    abrirConfirmacion(
        casos.length > 1 ? "Cerrar los casos" : "Cerrar el caso",
        `Se dan por terminados: ${codigos}. El chat queda abierto, así que el cliente`
        + " puede volver a escribir y el bot va a seguir atendiéndolo.",
        async () => {
            conversacion = await api.post(`/api/conversaciones/${idConversacion}/cerrar-casos/`);
            renderizarConversacion(conversacion);
            mostrarMensajePagina(casos.length > 1 ? "Casos cerrados." : "Caso cerrado.");
        },
    );
}

function vaciarChat() {
    abrirConfirmacion(
        "Vaciar chat",
        "El bot se olvida de todo lo hablado: el próximo mensaje del cliente abre una"
        + " conversación nueva, sin historial. Los mensajes, casos y alertas de esta"
        + " quedan guardados para consulta.",
        async () => {
            conversacion = await api.post(`/api/conversaciones/${idConversacion}/vaciar/`);
            renderizarConversacion(conversacion);
            mensajes = [];
            mensajesPorId.clear();
            nodosPorId.clear();
            mensajesChat.replaceChildren();
            mostrarMensajePagina("Chat vaciado. El próximo mensaje del cliente empieza una conversación nueva.");
        },
    );
}

function abrirDialogo(mensaje, accion) {
    accionSeleccionada = { mensaje, accion };
    dialogoError.textContent = "";
    dialogoTexto.value = "";
    camposPago.hidden = true;
    referenciaPago.value = "";
    importePago.value = "";
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
    if (accionSeleccionada.tipo === "pago") {
        const referencia = referenciaPago.value.trim();
        const importe = importePago.value.trim();
        if (!referencia || !importe) {
            dialogoError.textContent = "Ingresá la referencia del comprobante y el importe completo de la cuota.";
            return;
        }
        dialogoConfirmar.disabled = true;
        dialogoError.textContent = "";
        try {
            const pago = await api.post(
                `/api/polizas/${accionSeleccionada.poliza.id}/pagos/`,
                { referencia, importe },
            );
            conversacion = await api.get(`/api/conversaciones/${idConversacion}/`);
            renderizarConversacion(conversacion);
            mostrarMensajePagina(
                `Pago ${pago.pago.referencia} registrado para ${accionSeleccionada.poliza.numero_poliza}.`,
            );
            dialogo.close();
        } catch (error) {
            dialogoError.textContent = error.mensaje ?? error.message ?? "No se pudo registrar el pago.";
        } finally {
            dialogoConfirmar.disabled = false;
        }
        return;
    }
    // Confirmación simple (por ejemplo, cerrar un caso): no hay texto que validar.
    if (accionSeleccionada.alConfirmar) {
        dialogoConfirmar.disabled = true;
        dialogoError.textContent = "";
        try {
            await accionSeleccionada.alConfirmar();
            dialogo.close();
        } catch (error) {
            dialogoError.textContent = error.mensaje ?? error.message ?? "No se pudo completar la acción.";
        } finally {
            dialogoConfirmar.disabled = false;
        }
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
        const esResponsable = conversacion.atendida_por?.id === funcionario?.id;
        const accion = conversacion.modo === "humano" && esResponsable
            ? "devolver"
            : "tomar";
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
        const [respuesta, detalle] = await Promise.all([
            api.get(
                `/api/conversaciones/${idConversacion}/mensajes/?despues_de=${encodeURIComponent(ultimoId)}`,
            ),
            api.get(`/api/conversaciones/${idConversacion}/`),
        ]);
        if (!Array.isArray(respuesta.mensajes)) {
            throw new Error("La respuesta de mensajes no tiene el formato esperado.");
        }
        mensajes = fusionarMensajes(mensajes, respuesta.mensajes);
        renderizarConversacion(detalle);
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
botonCerrarCasos.addEventListener("click", cerrarCasos);
botonVaciar.addEventListener("click", vaciarChat);
formularioRespuesta.addEventListener("submit", responder);
dialogoCancelar.addEventListener("click", () => dialogo.close());
dialogoConfirmar.addEventListener("click", confirmarAccion);

iniciar();
