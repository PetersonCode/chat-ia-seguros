const guion = "—";

/**
 * Formatea un monto decimal como moneda argentina sin decimales innecesarios.
 * @param {string | number | null | undefined} monto
 * @returns {string}
 */
export function formatearMonto(monto) {
    if (monto === null || monto === undefined || String(monto).trim() === "") {
        return guion;
    }
    const numero = Number(monto);
    if (!Number.isFinite(numero)) {
        return guion;
    }

    const formato = new Intl.NumberFormat("es-AR", {
        minimumFractionDigits: Number.isInteger(numero) ? 0 : 2,
        maximumFractionDigits: 2,
    }).format(numero);
    return `$${formato}`;
}

/**
 * Formatea una fecha ISO sin hora como DD/MM/AAAA.
 * @param {string | null | undefined} fecha
 * @returns {string}
 */
export function formatearFecha(fecha) {
    if (typeof fecha !== "string") {
        return guion;
    }
    const coincidencia = /^(\d{4})-(\d{2})-(\d{2})$/.exec(fecha);
    if (!coincidencia) {
        return guion;
    }
    const [, anio, mes, dia] = coincidencia;
    const fechaValidada = new Date(Date.UTC(Number(anio), Number(mes) - 1, Number(dia)));
    if (
        fechaValidada.getUTCFullYear() !== Number(anio)
        || fechaValidada.getUTCMonth() !== Number(mes) - 1
        || fechaValidada.getUTCDate() !== Number(dia)
    ) {
        return guion;
    }
    return `${dia}/${mes}/${anio}`;
}

/**
 * Formatea una fecha/hora ISO en la zona horaria de Buenos Aires.
 * @param {string | null | undefined} fechaHora
 * @returns {string}
 */
export function formatearFechaHora(fechaHora) {
    if (typeof fechaHora !== "string") {
        return guion;
    }
    const fecha = new Date(fechaHora);
    if (!Number.isFinite(fecha.getTime())) {
        return guion;
    }

    const partes = new Intl.DateTimeFormat("es-AR", {
        timeZone: "America/Argentina/Buenos_Aires",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
    }).formatToParts(fecha);
    const valores = Object.fromEntries(partes.map(({ type, value }) => [type, value]));
    return `${valores.day}/${valores.month}/${valores.year} ${valores.hour}:${valores.minute}`;
}
