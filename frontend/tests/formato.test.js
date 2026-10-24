import test from "node:test";
import assert from "node:assert/strict";

import { formatearFecha, formatearFechaHora, formatearMonto } from "../static/js/lib/formato.js";

test("AC-T1-03: formatear monto con agrupación argentina y centavos", () => {
    assert.equal(formatearMonto("12500.00"), "$12.500");
    assert.equal(formatearMonto("12500.50"), "$12.500,50");
});

test("AC-T1-03: formatear fechas en español y hora de Buenos Aires", () => {
    assert.equal(formatearFecha("2024-04-15"), "15/04/2024");
    assert.equal(formatearFechaHora("2024-04-01T12:15:00Z"), "01/04/2024 09:15");
});

test("AC-T1-03: datos nulos o inválidos se representan con guion", () => {
    assert.equal(formatearMonto(null), "—");
    assert.equal(formatearMonto("no es un monto"), "—");
    assert.equal(formatearFecha(null), "—");
    assert.equal(formatearFecha("2024-02-31"), "—");
    assert.equal(formatearFechaHora("fecha inválida"), "—");
});
