const clasesPorColor = new Map([
    ["rojo", "fila-rojo"],
    ["naranja", "fila-naranja"],
    ["amarillo", "fila-amarillo"],
    ["verde", "fila-verde"],
]);

/**
 * Traduce el color de supervisión a la clase visual de la fila.
 * @param {string} color
 * @returns {string}
 */
export function claseDeColor(color) {
    return clasesPorColor.get(color) ?? "fila-verde";
}

const etiquetasPorSeveridad = new Map([
    ["baja", "Baja"],
    ["media", "Media"],
    ["alta", "Alta"],
    ["critica", "Crítica"],
]);

/**
 * Etiqueta visible de la severidad de una conversación.
 *
 * Sin alertas abiertas la API devuelve `null`. Eso no es un dato que falta sino
 * "no hay nada marcado", y un guion se leía como un error de carga: se muestra
 * Baja. El color de la fila no cambia —lo decide `color_por_severidad`, que sin
 * alertas da verde—, así que una bandeja tranquila se sigue viendo tranquila.
 * @param {string|null|undefined} severidad
 * @returns {string}
 */
export function etiquetaSeveridad(severidad) {
    return etiquetasPorSeveridad.get(severidad) ?? "Baja";
}

const clasesPorSeveridad = new Map([
    ["critica", "sev sev-critica"],
    ["alta", "sev sev-alta"],
    ["media", "sev sev-media"],
    ["baja", "sev sev-baja"],
]);

/**
 * Clases de la etiqueta de severidad.
 *
 * La severidad dejó de pintar la fila entera y pasó a ser una etiqueta en su
 * columna: el color acompaña al dato en vez de taparlo. Sin alertas abiertas
 * la API manda `null`, que se muestra como Baja (ver `etiquetaSeveridad`).
 * @param {string|null|undefined} severidad
 * @returns {string}
 */
export function claseSeveridad(severidad) {
    return clasesPorSeveridad.get(severidad) ?? "sev sev-baja";
}
