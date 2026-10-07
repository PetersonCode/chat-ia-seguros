/**
 * Combina mensajes por id y devuelve una copia ordenada cronológicamente.
 * Los mensajes recibidos más recientemente reemplazan una versión previa con el mismo id.
 * @param {Array<{id: number, fecha_hora: string}>} actuales
 * @param {Array<{id: number, fecha_hora: string}>} nuevos
 * @returns {Array<{id: number, fecha_hora: string}>}
 */
export function fusionarMensajes(actuales, nuevos) {
    const porId = new Map(actuales.map((mensaje) => [mensaje.id, mensaje]));
    for (const mensaje of nuevos) {
        porId.set(mensaje.id, mensaje);
    }
    return [...porId.values()].sort((a, b) => {
        const diferenciaTemporal = Date.parse(a.fecha_hora) - Date.parse(b.fecha_hora);
        return diferenciaTemporal || a.id - b.id;
    });
}

/**
 * Devuelve las acciones de supervisión disponibles para el funcionario.
 * @param {{estado_envio: string}} mensaje
 * @param {{puede_aprobar: boolean} | null | undefined} me
 * @returns {Array<"liberar" | "corregir" | "descartar">}
 */
export function accionesPermitidas(mensaje, me) {
    if (me?.puede_aprobar && mensaje.estado_envio === "retenido") {
        return ["liberar", "corregir", "descartar"];
    }
    return [];
}
