import test from "node:test";
import assert from "node:assert/strict";

import {
    etiquetaEstadoPoliza,
    mesesDeCobertura,
    ordenarPolizas,
    validarPoliza,
} from "../static/js/lib/polizas.js";

test("AC-T1-20: ordenarPolizas pone vigentes primero por vencimiento sin mutar la lista", () => {
    const polizas = [
        { id: 1, estado: "vencida", fecha_vencimiento: "2024-01-01" },
        { id: 2, estado: "vigente", fecha_vencimiento: "2024-05-01" },
        { id: 3, estado: "vigente", fecha_vencimiento: "2024-03-01" },
        { id: 4, estado: "dada_de_baja", fecha_vencimiento: "2024-02-01" },
    ];
    const originales = structuredClone(polizas);

    assert.deepEqual(ordenarPolizas(polizas).map(({ id }) => id), [3, 2, 1, 4]);
    assert.deepEqual(polizas, originales);
});

test("AC-T1-20: etiquetaEstadoPoliza traduce estados conocidos y marca desconocidos", () => {
    assert.equal(etiquetaEstadoPoliza("vigente"), "Vigente");
    assert.equal(etiquetaEstadoPoliza("vencida"), "Vencida");
    assert.equal(etiquetaEstadoPoliza("dada_de_baja"), "Dada de baja");
    assert.equal(etiquetaEstadoPoliza("otro"), "—");
});

test("validarPoliza acepta un alta completa y el número vacío (lo pone el servidor)", () => {
    const alta = {
        numero_poliza: "",
        tipo_seguro: "automotor",
        cobertura: "intermedia",
        fecha_inicio: "2026-01-10",
        fecha_vencimiento: "2027-01-10",
        prima_mensual: "18000",
    };

    assert.deepEqual(validarPoliza(alta), {});
    assert.deepEqual(validarPoliza({ ...alta, numero_poliza: "POL-00109" }), {});
});

test("validarPoliza marca los campos que faltan o están mal", () => {
    const errores = validarPoliza({});

    assert.deepEqual(Object.keys(errores).sort(), [
        "cobertura",
        "fecha_inicio",
        "fecha_vencimiento",
        "prima_mensual",
        "tipo_seguro",
    ]);
    assert.ok(validarPoliza({ numero_poliza: "12345" }).numero_poliza);
    assert.ok(validarPoliza({ prima_mensual: "-5" }).prima_mensual);
    assert.ok(validarPoliza({ prima_mensual: "dos pesos" }).prima_mensual);
});

test("validarPoliza exige que el vencimiento sea posterior al inicio", () => {
    const base = {
        tipo_seguro: "automotor",
        cobertura: "basica",
        prima_mensual: "1000",
        fecha_inicio: "2026-05-01",
    };

    assert.ok(validarPoliza({ ...base, fecha_vencimiento: "2026-05-01" }).fecha_vencimiento);
    assert.ok(validarPoliza({ ...base, fecha_vencimiento: "2026-04-01" }).fecha_vencimiento);
    assert.equal(validarPoliza({ ...base, fecha_vencimiento: "2026-05-02" }).fecha_vencimiento, undefined);
});

test("mesesDeCobertura espeja la regla del servidor: un año son 12 cuotas, no 13", () => {
    assert.equal(mesesDeCobertura("2026-01-10", "2027-01-10"), 12);
    assert.equal(mesesDeCobertura("2026-01-10", "2026-07-10"), 6);
    assert.equal(mesesDeCobertura("2026-01-20", "2026-03-10"), 1);
    assert.equal(mesesDeCobertura("2026-01-10", "2026-01-25"), 1);
    assert.equal(mesesDeCobertura("", "2026-01-25"), 0);
});
