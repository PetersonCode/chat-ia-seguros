import test from "node:test";
import assert from "node:assert/strict";

import {
    claseDeColor,
    claseSeveridad,
    etiquetaSeveridad,
} from "../static/js/lib/color.js";

test("AC-T1-09: cada color de bandeja tiene su clase y lo desconocido queda en verde", () => {
    assert.equal(claseDeColor("rojo"), "fila-rojo");
    assert.equal(claseDeColor("naranja"), "fila-naranja");
    assert.equal(claseDeColor("amarillo"), "fila-amarillo");
    assert.equal(claseDeColor("verde"), "fila-verde");
    assert.equal(claseDeColor("desconocido"), "fila-verde");
});

test("una conversación sin alertas se muestra como Baja, no como un guion", () => {
    assert.equal(etiquetaSeveridad(null), "Baja");
    assert.equal(etiquetaSeveridad(undefined), "Baja");
    assert.equal(etiquetaSeveridad("baja"), "Baja");
    assert.equal(etiquetaSeveridad("media"), "Media");
    assert.equal(etiquetaSeveridad("alta"), "Alta");
    assert.equal(etiquetaSeveridad("critica"), "Crítica");
});

test("la severidad no decide el color: sin alertas la fila sigue verde", () => {
    // `color_por_severidad(null)` en el servidor da verde, y eso no cambia
    // porque la etiqueta diga Baja.
    assert.equal(claseDeColor("verde"), "fila-verde");
    assert.equal(claseDeColor(null), "fila-verde");
});

test("claseSeveridad da la etiqueta de cada nivel y cae en baja si no hay alertas", () => {
    assert.equal(claseSeveridad("critica"), "sev sev-critica");
    assert.equal(claseSeveridad("alta"), "sev sev-alta");
    assert.equal(claseSeveridad("media"), "sev sev-media");
    assert.equal(claseSeveridad("baja"), "sev sev-baja");
    assert.equal(claseSeveridad(null), "sev sev-baja");
    assert.equal(claseSeveridad(undefined), "sev sev-baja");
});
