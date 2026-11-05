/** Tarjeta de archivo adjunto de un mensaje del chat: se descarga, no se previsualiza. */

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
    detalle.textContent = `${adjunto.tipo === "video" ? "Video" : "Imagen"} \u00b7 ${tamanoLegible(adjunto.tamano)}`;
    datos.append(nombre, detalle);

    const descarga = document.createElement("a");
    descarga.className = "btn btn-sm btn-outline-primary";
    descarga.href = adjunto.descarga_url;
    descarga.setAttribute("download", adjunto.nombre);
    descarga.textContent = "Descargar";
    descarga.setAttribute("aria-label", `Descargar ${adjunto.nombre}`);

    tarjeta.append(icono, datos, descarga);
    return tarjeta;
}
