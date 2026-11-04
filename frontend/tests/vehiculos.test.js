import test from "node:test";
import assert from "node:assert/strict";

import { descripcionVehiculo, etiquetaUso, validarVehiculo } from "../static/js/lib/vehiculos.js";
import { formatearPorcentaje, validarCompania } from "../static/js/lib/companias.js";

const valido = { patente: "ab 123 cd", marca: "Toyota", modelo: "Corolla", anio: "2020" };

test("vehículos: un vehículo completo es válido", () => {
    assert.deepEqual(validarVehiculo(valido, { anioMaximo: 2027 }), {});
});

test("vehículos: marca el campo que está mal", () => {
    const errores = validarVehiculo(
        { patente: "AB12", marca: " ", modelo: "", anio: "1949", valor_asegurado: "0" },
        { anioMaximo: 2027 },
    );
    assert.deepEqual(Object.keys(errores).sort(), ["anio", "marca", "modelo", "patente", "valor_asegurado"]);
    assert.match(validarVehiculo({ ...valido, anio: "2028" }, { anioMaximo: 2027 }).anio, /entre 1950 y 2027/);
});

test("vehículos: en modo parcial solo se validan los campos presentes", () => {
    assert.deepEqual(validarVehiculo({ modelo: "Etios" }, { parcial: true }), {});
    assert.deepEqual(Object.keys(validarVehiculo({ patente: "xx" }, { parcial: true })), ["patente"]);
});

test("vehículos: textos para mostrar", () => {
    assert.equal(etiquetaUso("remis_taxi"), "Remis o taxi");
    assert.equal(etiquetaUso("otro"), "—");
    assert.equal(
        descripcionVehiculo({ marca: "Toyota", modelo: "Corolla", anio: 2020, patente: "AB123CD" }),
        "Toyota Corolla 2020 (AB123CD)",
    );
    assert.equal(descripcionVehiculo(null), "—");
});

test("compañías: la comisión se muestra con coma y se oculta si es null", () => {
    assert.equal(formatearPorcentaje("12.50"), "12,50 %");
    assert.equal(formatearPorcentaje(0), "0,00 %");
    assert.equal(formatearPorcentaje(null), "—");
    assert.equal(formatearPorcentaje(undefined), "—");
});

test("compañías: valida nombre y comisión de 0 a 100", () => {
    assert.deepEqual(validarCompania({ nombre: "La Caja", comision_pct: "12,5" }), {});
    assert.deepEqual(validarCompania({ nombre: "La Caja", comision_pct: "0" }), {});
    assert.deepEqual(validarCompania({ nombre: "La Caja", comision_pct: "100" }), {});
    for (const comision of ["-1", "100.5", "abc", "", "1.234"]) {
        assert.ok(validarCompania({ nombre: "X", comision_pct: comision }).comision_pct, comision);
    }
    assert.ok(validarCompania({ nombre: "  ", comision_pct: "5" }).nombre);
    assert.deepEqual(validarCompania({ comision_pct: "7" }, { parcial: true }), {});
});
