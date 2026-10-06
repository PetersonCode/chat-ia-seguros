import test from "node:test";
import assert from "node:assert/strict";

import { claseDeColor } from "../static/js/lib/color.js";

test("AC-T1-09: cada color de bandeja tiene su clase y lo desconocido queda en verde", () => {
    assert.equal(claseDeColor("rojo"), "fila-rojo");
    assert.equal(claseDeColor("naranja"), "fila-naranja");
    assert.equal(claseDeColor("amarillo"), "fila-amarillo");
    assert.equal(claseDeColor("verde"), "fila-verde");
    assert.equal(claseDeColor("desconocido"), "fila-verde");
});
