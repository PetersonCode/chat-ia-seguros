const etiquetas = new Map([
    ["vigente", "Vigente"],
    ["vencida", "Vencida"],
    ["dada_de_baja", "Dada de baja"],
]);

/**
 * Ordena pólizas vigentes primero y luego por vencimiento, sin mutar la lista original.
 * @param {Array<{estado: string, fecha_vencimiento: string}>} polizas
 * @returns {Array<{estado: string, fecha_vencimiento: string}>}
 */
export function ordenarPolizas(polizas) {
    return [...polizas].sort((a, b) => {
        const aVigente = a.estado === "vigente" ? 0 : 1;
        const bVigente = b.estado === "vigente" ? 0 : 1;
        return aVigente - bVigente
            || a.fecha_vencimiento.localeCompare(b.fecha_vencimiento);
    });
}

/**
 * Convierte el estado de una póliza a una etiqueta visible.
 * @param {string} estado
 * @returns {string}
 */
export function etiquetaEstadoPoliza(estado) {
    return etiquetas.get(estado) ?? "—";
}
