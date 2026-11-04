export function plazoVencimiento(dias) {
    if (dias < 0) return `Venció hace ${Math.abs(dias)} día${dias === -1 ? "" : "s"}`;
    if (dias === 0) return "Vence hoy";
    if (dias === 1) return "Vence mañana";
    return `Vence en ${dias} días`;
}

export function enlaceRecordatorio(numero, texto) {
    if (!/^\+[1-9]\d{7,14}$/.test(numero ?? "")) return null;
    return `https://wa.me/${numero.slice(1)}?text=${encodeURIComponent(texto)}`;
}
