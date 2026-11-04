import test from "node:test";
import assert from "node:assert/strict";

import { normalizarPatente, patenteValida } from "../static/js/lib/patente.js";

// AC-T1-24
test("normalizarPatente saca espacios, guiones y puntos y pasa a mayúsculas", () => {
    assert.equal(normalizarPatente("ab 123 cd"), "AB123CD");
    assert.equal(normalizarPatente("AB-123-CD"), "AB123CD");
    assert.equal(normalizarPatente(" abc.123 "), "ABC123");
    assert.equal(normalizarPatente("123 abc"), "123ABC");
    assert.equal(normalizarPatente(null), "");
    assert.equal(normalizarPatente(undefined), "");
});

// AC-T1-24
test("patenteValida acepta los 4 formatos, con o sin espacios", () => {
    for (const patente of ["ABC123", "AB123CD", "123ABC", "A123BCD", "ab 123 cd", "abc-123"]) {
        assert.equal(patenteValida(patente), true, patente);
    }
});

// AC-T1-24
test("patenteValida rechaza lo que no es una patente", () => {
    for (const patente of ["AB12", "ABCD123", "", "   ", "12345", "AB123C", "ÁB123CD", null, undefined]) {
        assert.equal(patenteValida(patente), false, String(patente));
    }
});
