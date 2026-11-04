/**
 * Patentes argentinas, del lado del navegador.
 *
 * Es una copia deliberada de `normalizar_patente` (datos/limpieza.py): sirve
 * para avisar en el formulario antes de pedirle nada al servidor, no para
 * reemplazarlo. La validación que vale es la del back (R17).
 */

// Auto viejo (ABC123), auto nuevo (AB123CD), moto vieja (123ABC), moto nueva (A123BCD).
const FORMATOS = /^(?:[A-Z]{3}[0-9]{3}|[A-Z]{2}[0-9]{3}[A-Z]{2}|[0-9]{3}[A-Z]{3}|[A-Z][0-9]{3}[A-Z]{3})$/;
const SEPARADORES = /[\s.\-]/g;

/**
 * 'ab 123 cd' o 'AB-123-CD' → 'AB123CD'. No valida: solo limpia.
 * @param {string} valor
 * @returns {string}
 */
export function normalizarPatente(valor) {
    return String(valor ?? "").replace(SEPARADORES, "").toUpperCase();
}

/**
 * ¿Tiene alguno de los 4 formatos de patente? (después de normalizar)
 * @param {string} valor
 * @returns {boolean}
 */
export function patenteValida(valor) {
    return FORMATOS.test(normalizarPatente(valor));
}
