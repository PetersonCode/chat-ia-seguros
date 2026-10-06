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
