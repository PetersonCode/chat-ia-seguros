import { api } from "../api.js?v=20261105burbujas1";
import { inicializarNav } from "../nav.js?v=20261105burbujas1";
import { formatearMonto, formatearFecha, formatearFechaHora } from "../lib/formato.js?v=20261105burbujas1";
import { plazoVencimiento, enlaceRecordatorio } from "../lib/vencimientos.js?v=20261105burbujas1";

const $ = (id) => document.getElementById(id);
const dialogo = $("recordatorio");
let pagina = 1;
let seleccion = null;
let vista = null;
let solicitud = 0;
let solicitudVista = 0;
let enviando = false;
const estados = {enviado:"Enviado",pendiente_envio:"En cola",fallido:"Falló el envío",enviado_manual:"Envío manual registrado",descartado:"Descartado",sin_mensaje:"Registro conservado"};
const etiquetaEstado = (estado) => estados[estado] ?? estado;

function nodo(tag, texto, clase) {
    const n = document.createElement(tag);
    if (texto !== undefined) n.textContent = texto;
    if (clase) n.className = clase;
    return n;
}

async function cargar() {
    const turno = ++solicitud;
    $("estado").textContent = "Cargando vencimientos…";
    $("anterior").disabled = true;
    $("siguiente").disabled = true;
    const params = new URLSearchParams({pagina, incluir_vencidas: $("vencidas").checked});
    if ($("dias").value) params.set("dias", $("dias").value);
    if ($("buscar").value.trim()) params.set("q", $("buscar").value.trim());
    try {
        const datos = await api.get(`/api/vencimientos/?${params}`);
        if (turno !== solicitud) return;
        $("filas").replaceChildren();
        for (const p of datos.resultados) {
            const fila = nodo("tr");
            const cliente = nodo("td");
            cliente.append(nodo("div", `${p.cliente.nombre} ${p.cliente.apellido}`, "fw-semibold"), nodo("div", p.vehiculo || "Vehículo sin descripción", "small text-muted"));
            if (p.compania) cliente.append(nodo("div", p.compania, "small text-muted"));
            const plazo = nodo("td");
            plazo.append(nodo("span", plazoVencimiento(p.dias_restantes), `sev ${p.dias_restantes <= 7 ? "sev-critica" : p.dias_restantes <= 30 ? "sev-media" : "sev-baja"}`));
            const accion = nodo("td");
            const saldo = nodo("td", formatearMonto(p.saldo_pendiente));
            if (Number(p.saldo_vencido) > 0) {
                saldo.append(nodo("div", `Pago atrasado: ${formatearMonto(p.saldo_vencido)}`, "small text-danger fw-semibold"),
                    nodo("div", `Desde ${formatearFecha(p.primera_cuota_vencida)}`, "small text-muted"));
            }
            const boton = nodo("button", "Enviar recordatorio", "btn btn-sm btn-outline-primary");
            boton.type = "button";
            boton.addEventListener("click", () => abrir(p));
            accion.append(boton);
            fila.append(cliente, nodo("td", p.numero_poliza), nodo("td", formatearFecha(p.fecha_vencimiento)), plazo,
                saldo, nodo("td", p.ultimo_recordatorio ? formatearFechaHora(p.ultimo_recordatorio) : "Sin avisos"), accion);
            $("filas").append(fila);
        }
        $("total").textContent = `${datos.total} póliza${datos.total === 1 ? "" : "s"}`;
        $("pagina").textContent = `Página ${datos.pagina} de ${Math.max(1, Math.ceil(datos.total / datos.por_pagina))}`;
        $("anterior").disabled = datos.pagina <= 1;
        $("siguiente").disabled = datos.pagina * datos.por_pagina >= datos.total;
        $("estado").textContent = datos.total ? "" : "No hay pólizas con estos filtros.";
    } catch (e) {
        if (turno === solicitud) $("estado").textContent = e.mensaje || e.message;
    }
}

async function abrir(poliza) {
    seleccion = poliza;
    vista = null;
    $("contacto").replaceChildren();
    $("texto").value = "";
    $("historial").replaceChildren();
    $("dialog-titulo").textContent = `Recordatorio · ${poliza.numero_poliza}`;
    dialogo.showModal();
    await cargarVista();
}

async function cargarVista(contactoId) {
    const turno = ++solicitudVista;
    $("enviar").disabled = true;
    $("manual").hidden = true;
    $("abrir-whatsapp").hidden = true;
    $("copiar").disabled = true;
    $("error-dialogo").textContent = "";
    $("disponibilidad").textContent = "Preparando mensaje…";
    try {
        const datos = await api.get(`/api/polizas/${seleccion.id}/recordatorio/${contactoId ? `?contacto_id=${contactoId}` : ""}`);
        if (turno !== solicitudVista || !dialogo.open) return;
        vista = datos;
        $("contacto").replaceChildren();
        if (!datos.contacto_id) {
            const opcion = nodo("option", datos.contactos.length ? "Elegí un número" : "Sin número vinculado");
            opcion.value = "";
            $("contacto").append(opcion);
        }
        for (const c of datos.contactos) {
            const opcion = nodo("option", c.numero);
            opcion.value = c.id;
            $("contacto").append(opcion);
        }
        $("contacto").value = datos.contacto_id ?? "";
        $("texto").value = datos.texto;
        $("copiar").disabled = !datos.contacto_id;
        const previo = datos.ya_enviado_hoy;
        $("enviar").disabled = !datos.puede_enviar || Boolean(previo) || enviando;
        $("disponibilidad").textContent = previo
            ? `Ya hay un aviso de hoy: ${etiquetaEstado(previo.estado)}. No se enviará otro al mismo número.`
            : !datos.contacto_id ? "Seleccioná un número registrado del cliente."
            : datos.puede_enviar ? "Se enviará desde la línea de la agencia y quedará registrado en la conversación."
            : "No hay una conversación con ventana de envío abierta. Podés abrir WhatsApp o copiar el texto para contactar manualmente. Abrir WhatsApp no significa que se haya enviado.";
        const contacto = datos.contactos.find((c) => c.id === datos.contacto_id);
        const enlace = enlaceRecordatorio(contacto?.numero, datos.texto);
        if (!previo && !datos.puede_enviar && enlace) {
            $("abrir-whatsapp").href = enlace;
            $("abrir-whatsapp").hidden = false;
            $("manual").hidden = false;
        }
        $("historial").replaceChildren(...datos.historial.map((a) => nodo("p", `${formatearFechaHora(a.creado_en)} · ${a.funcionario} · ${etiquetaEstado(a.estado)}`, "mb-1")));
    } catch (e) {
        if (turno === solicitudVista) $("error-dialogo").textContent = e.mensaje || e.message;
    }
}

async function enviar(canal) {
    if (enviando || !vista?.contacto_id || vista.ya_enviado_hoy) return;
    // La confirmación externa se registra solo por declaración explícita del asesor.
    let fallo = "";
    enviando = true;
    $("contacto").disabled = true;
    $("cerrar").disabled = true;
    $("enviar").disabled = true;
    $("manual").disabled = true;
    try {
        const datos = await api.post(`/api/polizas/${seleccion.id}/recordatorio/`, {contacto_id: vista.contacto_id, canal});
        const aviso = datos.recordatorio;
        $("estado").textContent = canal === "manual" ? "Envío manual registrado."
            : aviso.estado === "enviado" ? "Recordatorio enviado."
            : aviso.estado === "fallido" ? "El envío falló. El historial conserva el intento y el sistema gestiona los reintentos permitidos."
            : "Recordatorio en cola de envío. Podés revisar su estado en el historial.";
        dialogo.close();
        await cargar();
        $("estado").textContent = canal === "manual" ? "Envío manual registrado." : `Recordatorio: ${etiquetaEstado(aviso.estado)}.`;
    } catch (e) {
        fallo = e.mensaje || e.message;
    } finally {
        enviando = false;
        $("contacto").disabled = false;
        $("cerrar").disabled = false;
        $("manual").disabled = false;
        if (dialogo.open) {
            await cargarVista(vista.contacto_id);
            if (fallo) $("error-dialogo").textContent = fallo;
        }
    }
}

$("filtros").addEventListener("submit", (e) => {e.preventDefault(); pagina = 1; cargar();});
$("anterior").addEventListener("click", () => {pagina -= 1; cargar();});
$("siguiente").addEventListener("click", () => {pagina += 1; cargar();});
$("contacto").addEventListener("change", () => cargarVista($("contacto").value));
$("cerrar").addEventListener("click", () => {solicitudVista += 1; dialogo.close();});
dialogo.addEventListener("cancel", (e) => {if (enviando) e.preventDefault(); else solicitudVista += 1;});
$("enviar").addEventListener("click", () => enviar("api"));
$("manual").addEventListener("click", () => enviar("manual"));
$("copiar").addEventListener("click", async () => {
    try {await navigator.clipboard.writeText($("texto").value); $("error-dialogo").textContent = "";}
    catch {$("error-dialogo").textContent = "Seleccioná y copiá el texto del mensaje.";}
});
inicializarNav();
cargar();
