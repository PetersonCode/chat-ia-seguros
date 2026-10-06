import test from "node:test";
import assert from "node:assert/strict";

import { etiquetaEstadoPoliza, ordenarPolizas } from "../static/js/lib/polizas.js";

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
