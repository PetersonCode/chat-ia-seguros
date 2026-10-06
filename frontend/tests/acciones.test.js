import test from "node:test";
import assert from "node:assert/strict";

import { describirAccion, faltantes } from "../static/js/lib/acciones.js";

test("AC-T1-17: describirAccion presenta acciones y pólizas en texto legible", () => {
    assert.equal(
        describirAccion({
            tipo_accion: "baja_poliza",
            poliza: { numero_poliza: "POL-00107" },
        }),
        "Baja de la póliza POL-00107",
    );
    assert.equal(
        describirAccion({
            tipo_accion: "agregar_conductor",
            poliza: { numero_poliza: "POL-00123" },
        }),
        "Agregar conductor a la póliza POL-00123",
    );
    assert.equal(
        describirAccion({
            tipo_accion: "reembolso",
            poliza: { numero_poliza: "POL-00108" },
            parametros: { importe: 3200, moneda: "ARS" },
        }),
        "Reembolso de $3.200",
    );
    assert.equal(describirAccion({ tipo_accion: "baja_poliza", poliza: null }), "Sin póliza asociada");
});

test("AC-T1-17: faltantes informa los parámetros necesarios para cada acción", () => {
    assert.deepEqual(
        faltantes({
            tipo_accion: "agregar_conductor",
            parametros: { relacion: "hijo", nombre: "(a completar: falta nombre)" },
        }),
        ["nombre", "dni"],
    );
    assert.deepEqual(
        faltantes({ tipo_accion: "reembolso", parametros: {} }),
        ["importe"],
    );
    assert.deepEqual(
        faltantes({ tipo_accion: "modificar_poliza", parametros: { detalle: "" } }),
        ["detalle"],
    );
    assert.deepEqual(
        faltantes({ tipo_accion: "apertura_siniestro", parametros: { fecha_ocurrencia: "2024-04-02" } }),
        ["descripcion"],
    );
    assert.deepEqual(faltantes({ tipo_accion: "baja_poliza", poliza: null, parametros: {} }), ["poliza"]);
    assert.deepEqual(
        faltantes({ tipo_accion: "baja_poliza", poliza: null, parametros: { poliza: "POL-00107" } }),
        [],
    );
});
