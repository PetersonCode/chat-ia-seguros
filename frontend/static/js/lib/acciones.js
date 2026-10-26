import { formatearMonto } from "./formato.js?v=20261026fix2";

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
    return accion.poliza?.numero_poliza ?? "—";
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
    ) {
        const nombres = { baja_poliza: "Baja de póliza", agregar_conductor: "Agregar conductor", modificar_poliza: "Modificar póliza", apertura_siniestro: "Apertura de siniestro" };
        return `${nombres[accion.tipo_accion]} · sin póliza asociada`;
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
        case "alta_cliente": {
            // El bot ya juntó nombre y DNI; se muestran para que quien aprueba
            // vea qué va a crear sin tener que abrir la conversación.
            const nombre = [parametros.nombre, parametros.apellido]
                .filter((parte) => !parametroFaltante(parte))
                .join(" ");
            const dni = parametroFaltante(parametros.dni) ? "" : ` (DNI ${parametros.dni})`;
            return nombre ? `Alta de ${nombre}${dni}` : "Alta de cliente (datos incompletos)";
        }
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
        alta_cliente: ["nombre", "apellido", "dni", "telefono"],
        baja_poliza: [],
    };
    const requeridos = requeridosPorTipo[accion.tipo_accion] ?? [];
    const faltantesParametros = requeridos.filter((clave) => parametroFaltante(parametros[clave]));
    if (
        accion.tipo_accion === "baja_poliza"
        && !accion.poliza
    ) {
        faltantesParametros.push("poliza");
    }
    return faltantesParametros;
}
