/** Tarjeta de archivo adjunto de un mensaje del chat: se descarga, no se previsualiza. */

import { api } from "../api.js?v=20261105fechas1";

const PREFIJO_MARCADOR = "[mensaje de tipo ";

export function tamanoLegible(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) {
        return "";
    }
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    if (bytes < 1024 * 1024) {
        return `${Math.round(bytes / 1024)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** El marcador "[mensaje de tipo image no soportado]" no es texto del cliente. */
export function esMarcadorDeArchivo(mensaje) {
    return Boolean(mensaje.adjunto) && (mensaje.texto ?? "").startsWith(PREFIJO_MARCADOR);
}

function detalleDelArchivo(adjunto) {
    const tipo = adjunto.tipo === "video" ? "Video" : "Imagen";
    const tamano = tamanoLegible(adjunto.tamano);
    return tamano ? `${tipo} · ${tamano}` : tipo;
}

async function descargarAPedido(adjunto) {
    // Pasa por `api.js`: sesión vencida, sin conexión y errores, igual que el resto.
    const blob = await api.descargar(adjunto.descarga_url);
    const url = URL.createObjectURL(blob);
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = adjunto.nombre;
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return blob.size;
}

export function crearTarjetaAdjunto(adjunto) {
    const tarjeta = document.createElement("div");
    tarjeta.className = "adjunto-chat";

    const icono = document.createElement("span");
    icono.className = "adjunto-chat-icono";
    icono.setAttribute("aria-hidden", "true");
    icono.textContent = adjunto.tipo === "video" ? "VIDEO" : "IMG";

    const datos = document.createElement("div");
    datos.className = "adjunto-chat-datos";
    const nombre = document.createElement("span");
    nombre.className = "adjunto-chat-nombre";
    nombre.textContent = adjunto.nombre;
    const detalle = document.createElement("span");
    detalle.className = "adjunto-chat-detalle";
    detalle.textContent = detalleDelArchivo(adjunto);
    const aviso = document.createElement("span");
    aviso.className = "adjunto-chat-detalle text-danger";
    aviso.setAttribute("role", "alert");
    aviso.hidden = true;
    datos.append(nombre, detalle, aviso);

    const descarga = document.createElement("a");
    descarga.className = "btn btn-sm btn-outline-primary";
    descarga.href = adjunto.descarga_url;
    descarga.setAttribute("download", adjunto.nombre);
    descarga.textContent = "Descargar";
    descarga.setAttribute("aria-label", `Descargar ${adjunto.nombre}`);
    descarga.addEventListener("click", async (evento) => {
        if (adjunto.guardado) {
            return; // ya está guardado: descarga directa del navegador
        }
        // Todavía no se bajó de WhatsApp: se pide ahora y se avisa si falla.
        evento.preventDefault();
        if (descarga.getAttribute("aria-disabled") === "true") {
            return;
        }
        descarga.setAttribute("aria-disabled", "true");
        descarga.classList.add("disabled");
        descarga.textContent = "Descargando…";
        aviso.hidden = true;
        try {
            const tamano = await descargarAPedido(adjunto);
            adjunto.guardado = true;
            adjunto.tamano = tamano;
            detalle.textContent = detalleDelArchivo(adjunto);
        } catch (error) {
            aviso.textContent = error.message;
            aviso.hidden = false;
        } finally {
            descarga.removeAttribute("aria-disabled");
            descarga.classList.remove("disabled");
            descarga.textContent = "Descargar";
        }
    });

    tarjeta.append(icono, datos, descarga);
    return tarjeta;
}
