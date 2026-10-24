/**
 * Devuelve una función que se ejecuta una vez transcurrido el intervalo desde la última llamada.
 * @param {(...argumentos: any[]) => void} fn
 * @param {number} ms
 * @returns {(...argumentos: any[]) => void}
 */
export function debounce(fn, ms) {
    let temporizador;
    return (...argumentos) => {
        clearTimeout(temporizador);
        temporizador = setTimeout(() => fn(...argumentos), ms);
    };
}
