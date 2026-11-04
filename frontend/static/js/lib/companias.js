/**
 * Compañías aseguradoras: textos y validación previa a la API.
 *
 * La comisión es información del dueño: a un operador la API la manda en
 * `null` y acá se muestra como «—». Que el front la oculte es solo comodidad;
 * quien la protege es el back (R17).
 */

/**
 * `"12.50"` → `"12,50 %"`; `null` → `"—"`.
 * @param {string|number|null|undefined} valor
 * @returns {string}
 */
export function formatearPorcentaje(valor) {
    if (valor === null || valor === undefined || valor === "") {
        return "—";
    }
    const numero = Number(valor);
    if (Number.isNaN(numero)) {
        return "—";
    }
    return `${numero.toFixed(2).replace(".", ",")} %`;
}

/**
 * Valida el alta o la edición de una compañía. Objeto vacío = válido.
 * @param {{nombre?: string, comision_pct?: string|number}} datos
 * @param {{parcial?: boolean}} opciones
 * @returns {Record<string, string>}
 */
export function validarCompania(datos = {}, { parcial = false } = {}) {
    const errores = {};
    const presente = (clave) => datos[clave] !== undefined && String(datos[clave]).trim() !== "";

    if (!parcial || presente("nombre")) {
        if (!String(datos.nombre ?? "").trim()) {
            errores.nombre = "El nombre es obligatorio.";
        }
    }
    if (!parcial || presente("comision_pct")) {
        const texto = String(datos.comision_pct ?? "").trim().replace(",", ".");
        const numero = Number(texto);
        if (!texto || Number.isNaN(numero)) {
            errores.comision_pct = "La comisión tiene que ser un número.";
        } else if (numero < 0 || numero > 100) {
            errores.comision_pct = "La comisión tiene que estar entre 0 y 100.";
        } else if (!/^\d+(\.\d{1,2})?$/.test(texto)) {
            errores.comision_pct = "La comisión admite como máximo dos decimales.";
        }
    }
    return errores;
}
