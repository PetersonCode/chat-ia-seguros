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
 * Ciclos mensuales, incluido el último parcial, para anticipar las cuotas.
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
    const ultimoDia = new Date(Date.UTC(hasta.anio, hasta.mes, 0)).getUTCDate();
    const aniversario = Math.min(desde.dia, ultimoDia);
    if (aniversario < hasta.dia) {
        meses += 1;
    }
    return Math.max(1, meses);
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

/**
 * La fecha escrita con palabras: «5 de noviembre de 2026».
 *
 * El campo `type="date"` lo dibuja el navegador con el formato de su idioma:
 * en inglés espera mes/día, y «05/11/2026» queda guardado como 11 de mayo.
 * Escrita así no hay forma de confundirla.
 * @param {string} iso Fecha ISO `aaaa-mm-dd`.
 * @returns {string} Vacío si la fecha no es válida.
 */
export function fechaEnPalabras(iso) {
    const fecha = partesDeFecha(iso);
    if (!fecha || fecha.mes < 1 || fecha.mes > 12) {
        return "";
    }
    return `${fecha.dia} de ${MESES[fecha.mes - 1]} de ${fecha.anio}`;
}

/** Días entre dos fechas ISO (positivo si `iso` es posterior a `hoy`). */
function diasEntre(hoy, iso) {
    const a = partesDeFecha(hoy);
    const b = partesDeFecha(iso);
    if (!a || !b) {
        return null;
    }
    const ms = Date.UTC(b.anio, b.mes - 1, b.dia) - Date.UTC(a.anio, a.mes - 1, a.dia);
    return Math.round(ms / 86_400_000);
}

/** Hoy en la zona del navegador, como `aaaa-mm-dd`. */
export function hoyIso(ahora = new Date()) {
    const dos = (n) => String(n).padStart(2, "0");
    return `${ahora.getFullYear()}-${dos(ahora.getMonth() + 1)}-${dos(ahora.getDate())}`;
}

/** Más allá de esto, un inicio se confirma antes de guardar. */
export const DIAS_INICIO_SIN_AVISO = 30;

/**
 * Aviso si el inicio queda lejos de hoy: suele ser día y mes invertidos.
 * @param {string} inicio Fecha ISO de inicio.
 * @param {string} hoy Fecha ISO de hoy.
 * @returns {string | null} El texto del aviso, o `null` si no hace falta.
 */
export function avisoInicioLejano(inicio, hoy) {
    const dias = diasEntre(hoy, inicio);
    if (dias === null || Math.abs(dias) <= DIAS_INICIO_SIN_AVISO) {
        return null;
    }
    const cuando = dias < 0 ? `${-dias} días antes de hoy` : `${dias} días después de hoy`;
    return `El inicio quedó el ${fechaEnPalabras(inicio)}, ${cuando}. `
        + "Si escribiste día/mes, revisalo: el campo puede estar esperando mes/día. "
        + "Si la fecha es correcta, tocá «Crear igual».";
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
