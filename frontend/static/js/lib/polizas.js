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

const RE_NUMERO_POLIZA = /^POL-\d{5}$/;

function partesDeFecha(iso) {
    const partes = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso ?? "");
    if (!partes) {
        return null;
    }
    return { anio: Number(partes[1]), mes: Number(partes[2]), dia: Number(partes[3]) };
}

/**
 * Meses enteros que cubre una póliza, para anticipar cuántas cuotas se generan.
 *
 * Espeja a propósito `negocio.polizas.meses_de_cobertura`: acá es solo el aviso
 * que ve el funcionario antes de guardar, y el que manda es el del servidor.
 * Del 10/01 al 10/01 del año siguiente son 12 cuotas, no 13.
 * @param {string} inicio Fecha ISO `aaaa-mm-dd`.
 * @param {string} vencimiento Fecha ISO `aaaa-mm-dd`.
 * @returns {number} Cantidad de cuotas, o 0 si alguna fecha no es válida.
 */
export function mesesDeCobertura(inicio, vencimiento) {
    const desde = partesDeFecha(inicio);
    const hasta = partesDeFecha(vencimiento);
    if (!desde || !hasta) {
        return 0;
    }
    let meses = (hasta.anio - desde.anio) * 12 + (hasta.mes - desde.mes);
    if (hasta.dia < desde.dia) {
        meses -= 1;
    }
    return Math.max(1, meses);
}

/**
 * Valida el alta de una póliza antes de mandarla.
 *
 * Adelanta los mismos rechazos que `negocio.polizas` para no gastar un viaje;
 * la validación que vale es la del servidor, que además mira duplicados.
 * @param {{numero_poliza?: string, tipo_seguro?: string, cobertura?: string, fecha_inicio?: string, fecha_vencimiento?: string, prima_mensual?: string}} datos
 * @returns {Record<string, string>} Errores por campo; vacío si está todo bien.
 */
export function validarPoliza(datos = {}) {
    const errores = {};
    // Vacío es válido: significa "usá el próximo número libre".
    if (datos.numero_poliza && !RE_NUMERO_POLIZA.test(datos.numero_poliza)) {
        errores.numero_poliza = "El formato es POL- y 5 dígitos, por ejemplo POL-00109.";
    }
    if (!datos.tipo_seguro) {
        errores.tipo_seguro = "Elegí un tipo de seguro.";
    }
    if (!datos.cobertura) {
        errores.cobertura = "Elegí una cobertura.";
    }
    if (!partesDeFecha(datos.fecha_inicio)) {
        errores.fecha_inicio = "La fecha de inicio es obligatoria.";
    }
    if (!partesDeFecha(datos.fecha_vencimiento)) {
        errores.fecha_vencimiento = "La fecha de vencimiento es obligatoria.";
    } else if (datos.fecha_vencimiento <= datos.fecha_inicio) {
        // Las fechas ISO se comparan bien como texto.
        errores.fecha_vencimiento = "El vencimiento tiene que ser posterior al inicio.";
    }
    const prima = Number(String(datos.prima_mensual ?? "").replace(",", "."));
    if (!String(datos.prima_mensual ?? "").trim() || Number.isNaN(prima)) {
        errores.prima_mensual = "La prima mensual tiene que ser un número.";
    } else if (prima < 0) {
        errores.prima_mensual = "La prima mensual no puede ser negativa.";
    }
    return errores;
}
