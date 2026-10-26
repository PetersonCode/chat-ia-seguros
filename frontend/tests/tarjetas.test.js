import test from "node:test";
import assert from "node:assert/strict";

import { claseTarjeta, claseTarjetaSeveridad } from "../static/js/lib/tarjetas.js";

test("la tarjeta toma el color de la urgencia y lo desconocido queda en verde", () => {
    assert.equal(claseTarjeta("rojo"), "tarjeta-rojo");
    assert.equal(claseTarjeta("naranja"), "tarjeta-naranja");
    assert.equal(claseTarjeta("amarillo"), "tarjeta-amarillo");
    assert.equal(claseTarjeta("verde"), "tarjeta-verde");
    assert.equal(claseTarjeta("desconocido"), "tarjeta-verde");
    assert.equal(claseTarjeta(null), "tarjeta-verde");
});

test("la severidad se pinta con la misma escala que el servidor", () => {
    assert.equal(claseTarjetaSeveridad("critica"), "tarjeta-rojo");
    assert.equal(claseTarjetaSeveridad("alta"), "tarjeta-naranja");
    assert.equal(claseTarjetaSeveridad("media"), "tarjeta-amarillo");
    assert.equal(claseTarjetaSeveridad("baja"), "tarjeta-amarillo");
    assert.equal(claseTarjetaSeveridad(null), "tarjeta-verde");
});
