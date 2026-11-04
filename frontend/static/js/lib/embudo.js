/**
 * Embudo de interesados: etapas, textos y validación previa a la API (P5).
 *
 * Las reglas de negocio (qué transición es válida, quién puede convertir) las
 * decide el servidor (R17): acá solo se ordena, se rotula y se avisa antes de
 * pedirle nada.
 */

import { formatearFecha } from "./formato.js?v=20261104bot2";
import { etiquetaUso } from "./vehiculos.js?v=20261104bot2";

/** Las etapas, en el orden del embudo. `perdida` es la salida y va al final. */
export const ETAPAS = [
    { clave: "consulta", etiqueta: "Consulta" },
    { clave: "cotizando", etiqueta: "Cotizando" },
    { clave: "documentacion", etiqueta: "Documentación" },
    { clave: "emitida", etiqueta: "Emitida" },
    { clave: "perdida", etiqueta: "Perdida" },
];

export const ORIGENES = [
    ["whatsapp", "WhatsApp"],
    ["instagram", "Instagram"],
    ["facebook", "Facebook"],
    ["web", "Web"],
    ["recomendacion", "Recomendación"],
    ["llamado", "Llamado"],
    ["otro", "Otro"],
];

export const COBERTURAS = [
    ["basica", "Básica"],
    ["intermedia", "Intermedia"],
    ["total", "Total"],
];

const GUION = "—";

/**
 * Reparte los interesados en las cinco columnas del tablero.
 * Las cinco salen siempre, aunque estén vacías, y la lista original no se toca.
 * @param {Array<{estado: string}>} interesados
 * @returns {Array<{clave: string, etiqueta: string, interesados: object[]}>}
 */
export function agruparPorEstado(interesados) {
    const columnas = ETAPAS.map((etapa) => ({ ...etapa, interesados: [] }));
    for (const interesado of interesados ?? []) {
        columnas.find((columna) => columna.clave === interesado?.estado)?.interesados.push(interesado);
    }
    return columnas;
}

/**
 * La etapa que sigue, o `null` si ya no hay: `emitida` es el final y `perdida`
 * no avanza, se reabre.
 * @param {string} estado
 * @returns {string|null}
 */
export function siguienteEtapa(estado) {
    const posicion = ETAPAS.findIndex((etapa) => etapa.clave === estado);
    if (posicion === -1 || estado === "emitida" || estado === "perdida") {
        return null;
    }
    return ETAPAS[posicion + 1].clave;
}

/**
 * La etapa anterior (se puede volver una), o `null` en la primera, en `emitida`
 * —la póliza ya existe— y en `perdida`, que se reabre.
 * @param {string} estado
 * @returns {string|null}
 */
export function etapaAnterior(estado) {
    const posicion = ETAPAS.findIndex((etapa) => etapa.clave === estado);
    if (posicion <= 0 || estado === "emitida" || estado === "perdida") {
        return null;
    }
    return ETAPAS[posicion - 1].clave;
}

/** @param {string} estado @returns {string} */
export function etiquetaEtapa(estado) {
    return ETAPAS.find((etapa) => etapa.clave === estado)?.etiqueta ?? GUION;
}

/** @param {string} origen @returns {string} */
export function etiquetaOrigen(origen) {
    return ORIGENES.find(([clave]) => clave === origen)?.[1] ?? GUION;
}

/** @param {string} cobertura @returns {string} */
export function etiquetaCobertura(cobertura) {
    return COBERTURAS.find(([clave]) => clave === cobertura)?.[1] ?? GUION;
}

/**
 * «Marta Gómez»; sin apellido, solo el nombre.
 * @param {{nombre?: string, apellido?: string|null}} interesado
 * @returns {string}
 */
export function nombreCompleto(interesado) {
    return [interesado?.nombre, interesado?.apellido].filter(Boolean).join(" ") || GUION;
}

/**
 * La fecha de hoy como `aaaa-mm-dd`, en la zona del navegador.
 * @param {Date} [ahora]
 * @returns {string}
 */
export function hoyIso(ahora = new Date()) {
    const mes = String(ahora.getMonth() + 1).padStart(2, "0");
    const dia = String(ahora.getDate()).padStart(2, "0");
    return `${ahora.getFullYear()}-${mes}-${dia}`;
}

/**
 * Cómo está el próximo contacto: el texto siempre dice el estado, porque el
 * color solo no alcanza para quien no lo distingue.
 * @param {{proximo_contacto?: string|null, seguimiento_vencido?: boolean}} interesado
 * @param {string} [hoy] `aaaa-mm-dd`; por defecto, el de hoy
 * @returns {{nivel: "vencido"|"hoy"|"proximo"|"ninguno", texto: string}}
 */
export function estadoSeguimiento(interesado, hoy = hoyIso()) {
    const fecha = interesado?.proximo_contacto;
    if (!fecha) {
        return { nivel: "ninguno", texto: "Sin próximo contacto" };
    }
    // El servidor decide qué está vencido; el navegador solo distingue «hoy».
    if (interesado.seguimiento_vencido) {
        return { nivel: "vencido", texto: `Vencido: ${formatearFecha(fecha)}` };
    }
    if (fecha === hoy) {
        return { nivel: "hoy", texto: "Contactar hoy" };
    }
    return { nivel: "proximo", texto: `Próximo contacto: ${formatearFecha(fecha)}` };
}

const ROTULOS_DATOS = [
    ["dni", "DNI"],
    ["patente", "Patente"],
    ["marca", "Marca"],
    ["modelo", "Modelo"],
    ["anio", "Año"],
    ["uso", "Uso"],
    ["localidad", "Localidad"],
    ["tipo_seguro", "Tipo de seguro"],
];

/**
 * Los datos juntados para cotizar, rotulados y en el orden de la ficha. Lo que
 * no está en la lista conocida se ignora: no se muestra nada que no se entienda.
 * @param {Record<string, unknown>|null|undefined} datos
 * @returns {Array<[string, string]>}
 */
export function datosDelInteresado(datos) {
    const filas = [];
    for (const [clave, rotulo] of ROTULOS_DATOS) {
        const valor = datos?.[clave];
        if (valor === undefined || valor === null || valor === "") {
            continue;
        }
        filas.push([rotulo, clave === "uso" ? etiquetaUso(String(valor)) : String(valor)]);
    }
    return filas;
}

/**
 * El id de la cotización más barata, para marcarla en la tabla comparativa.
 * @param {Array<{id: number, prima_mensual: string}>} cotizaciones
 * @returns {number|null}
 */
export function idMasBarata(cotizaciones) {
    let mejor = null;
    for (const cotizacion of cotizaciones ?? []) {
        const prima = Number(cotizacion.prima_mensual);
        if (Number.isFinite(prima) && (mejor === null || prima < mejor.prima)) {
            mejor = { id: cotizacion.id, prima };
        }
    }
    return mejor?.id ?? null;
}

/**
 * Valida el alta de un interesado. Objeto vacío = válido.
 * @param {{nombre?: string, origen?: string}} datos
 * @returns {Record<string, string>}
 */
export function validarInteresado(datos = {}) {
    const errores = {};
    if (!String(datos.nombre ?? "").trim()) {
        errores.nombre = "El nombre es obligatorio.";
    }
    if (!ORIGENES.some(([clave]) => clave === datos.origen)) {
        errores.origen = "Elegí de dónde llegó.";
    }
    return errores;
}

/**
 * Valida la carga de una cotización. Objeto vacío = válido.
 * @param {{compania_id?: string|number, cobertura?: string, prima_mensual?: string|number}} datos
 * @returns {Record<string, string>}
 */
export function validarCotizacion(datos = {}) {
    const errores = {};
    if (!datos.compania_id) {
        errores.compania_id = "Elegí la compañía.";
    }
    if (!COBERTURAS.some(([clave]) => clave === datos.cobertura)) {
        errores.cobertura = "Elegí la cobertura.";
    }
    const texto = String(datos.prima_mensual ?? "").trim().replace(",", ".");
    const prima = Number(texto);
    if (!texto || Number.isNaN(prima)) {
        errores.prima_mensual = "La prima tiene que ser un número.";
    } else if (prima <= 0) {
        errores.prima_mensual = "La prima tiene que ser mayor que cero.";
    } else if (!/^\d+(\.\d{1,2})?$/.test(texto)) {
        errores.prima_mensual = "La prima admite como máximo dos decimales.";
    }
    return errores;
}

/**
 * Valida el motivo de pérdida (3 o más caracteres, como el servidor).
 * @param {string} motivo
 * @returns {string} Mensaje de error, o cadena vacía si es válido.
 */
export function validarMotivoPerdida(motivo) {
    return String(motivo ?? "").trim().length >= 3
        ? ""
        : "Contá por qué se perdió (3 caracteres como mínimo).";
}
