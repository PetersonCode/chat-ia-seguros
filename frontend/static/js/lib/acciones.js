import { formatearMonto } from "./formato.js";

const tiposQueRequierenPoliza = new Set([
    "baja_poliza",
    "agregar_conductor",
    "modificar_poliza",
    "apertura_siniestro",
]);

function parametroFaltante(valor) {
    return valor === null
        || valor === undefined
        || (typeof valor === "string" && (
            valor.trim() === ""
            || /^\(a completar\b/i.test(valor.trim())
        ));
}

function numeroPoliza(accion) {
    return accion.poliza?.numero_poliza ?? accion.parametros?.poliza ?? "—";
}

/**
 * Describe una acción pendiente con los datos de póliza y parámetros disponibles.
 * @param {{tipo_accion: string, poliza?: {numero_poliza: string} | null, parametros?: Record<string, unknown>}} accion
 * @returns {string}
 */
export function describirAccion(accion) {
    const parametros = accion.parametros ?? {};
    if (
        !accion.poliza
        && tiposQueRequierenPoliza.has(accion.tipo_accion)
        && parametroFaltante(parametros.poliza)
    ) {
        return "Sin póliza asociada";
    }

    switch (accion.tipo_accion) {
        case "baja_poliza":
            return `Baja de la póliza ${numeroPoliza(accion)}`;
        case "agregar_conductor":
            return `Agregar conductor a la póliza ${numeroPoliza(accion)}`;
        case "modificar_poliza":
            return `Modificar la póliza ${numeroPoliza(accion)}`;
        case "reembolso": {
            const importe = formatearMonto(parametros.importe);
            return importe === "—" ? "Reembolso (importe pendiente)" : `Reembolso de ${importe}`;
        }
        case "apertura_siniestro":
            return `Apertura de siniestro para la póliza ${numeroPoliza(accion)}`;
        default:
            return "Acción pendiente";
    }
}

/**
 * Devuelve los campos requeridos que todavía no están completos.
 * @param {{tipo_accion: string, poliza?: {numero_poliza: string} | null, parametros?: Record<string, unknown>}} accion
 * @returns {string[]}
 */
export function faltantes(accion) {
    const parametros = accion.parametros ?? {};
    const requeridosPorTipo = {
        agregar_conductor: ["nombre", "dni"],
        reembolso: ["importe"],
        modificar_poliza: ["detalle"],
        apertura_siniestro: ["fecha_ocurrencia", "descripcion"],
        baja_poliza: [],
    };
    const requeridos = requeridosPorTipo[accion.tipo_accion] ?? [];
    const faltantesParametros = requeridos.filter((clave) => parametroFaltante(parametros[clave]));
    if (
        accion.tipo_accion === "baja_poliza"
        && !accion.poliza
        && parametroFaltante(parametros.poliza)
    ) {
        faltantesParametros.push("poliza");
    }
    return faltantesParametros;
}
