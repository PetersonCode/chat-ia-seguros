/**
 * Construye la query de la bandeja, omitiendo filtros vacíos o desactivados.
 * @param {Record<string, string | number | boolean | null | undefined>} filtros
 * @returns {string}
 */
export function armarQuery(filtros) {
    const parametros = new URLSearchParams();
    for (const [clave, valor] of Object.entries(filtros)) {
        if (valor === null || valor === undefined || valor === false || valor === "") {
            continue;
        }
        parametros.set(clave, valor === true ? "1" : String(valor));
    }
    const query = parametros.toString();
    return query ? `?${query}` : "";
}
