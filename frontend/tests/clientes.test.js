import test from "node:test";
import assert from "node:assert/strict";

import {
    digitosNacionales,
    limpiarDni,
    prellenadoDesdeUrl,
    separarNombrePerfil,
    validarCliente,
} from "../static/js/lib/clientes.js";

const COMPLETO = {
    dni: "28.111.222",
    nombre: "Juan",
    apellido: "García",
    telefono: "11 2691-4442",
    email: "juan@tests.local",
};

test("AC-T1-22: limpiarDni deja solo los dígitos", () => {
    assert.equal(limpiarDni("28.111.222"), "28111222");
    assert.equal(limpiarDni(" 28-111-222 "), "28111222");
    assert.equal(limpiarDni(undefined), "");
});

test("AC-T1-22: digitosNacionales descarta +54, el 9 y el 0 inicial", () => {
    for (const entrada of [
        "+54 9 11 2691-4442",
        "5491126914442",
        "011 2691 4442",
        "11 2691-4442",
    ]) {
        assert.equal(digitosNacionales(entrada), "1126914442", entrada);
    }
});

test("AC-T1-22: un cliente completo y correcto no tiene errores", () => {
    assert.deepEqual(validarCliente(COMPLETO), {});
});

test("AC-T1-22: el email es opcional pero si viene se valida", () => {
    assert.deepEqual(validarCliente({ ...COMPLETO, email: "" }), {});
    assert.deepEqual(validarCliente({ ...COMPLETO, email: undefined }), {});
    assert.equal(
        validarCliente({ ...COMPLETO, email: "arroba-no" }).email,
        "El email no tiene un formato válido.",
    );
});

test("AC-T1-22: se rechazan DNI, teléfono y nombres sucios", () => {
    assert.ok(validarCliente({ ...COMPLETO, dni: "123" }).dni);
    assert.ok(validarCliente({ ...COMPLETO, telefono: "123" }).telefono);
    assert.ok(validarCliente({ ...COMPLETO, nombre: "   " }).nombre);
    assert.ok(validarCliente({ ...COMPLETO, nombre: "Juan 2" }).nombre);
    assert.ok(validarCliente({ ...COMPLETO, apellido: "28111222" }).apellido);
});

test("AC-T1-22: el alta exige todos los campos obligatorios", () => {
    const errores = validarCliente({});
    assert.deepEqual(
        Object.keys(errores).sort(),
        ["apellido", "dni", "nombre", "telefono"],
    );
});

test("AC-T1-22: separarNombrePerfil parte en nombre y apellido sin inventar", () => {
    assert.deepEqual(separarNombrePerfil("Daniel Peterson"), {
        nombre: "Daniel",
        apellido: "Peterson",
    });
    assert.deepEqual(separarNombrePerfil("  Ana   María  Lopez "), {
        nombre: "Ana",
        apellido: "María Lopez",
    });
    assert.deepEqual(separarNombrePerfil("Daniel"), { nombre: "Daniel", apellido: "" });
    assert.deepEqual(separarNombrePerfil(""), { nombre: "", apellido: "" });
    assert.deepEqual(separarNombrePerfil(null), { nombre: "", apellido: "" });
});

test("AC-T1-22: prellenadoDesdeUrl arma el alta a partir de la conversación", () => {
    assert.deepEqual(
        prellenadoDesdeUrl("?telefono=%2B5491132032060&perfil=Daniel%20Peterson"),
        {
            telefono: "+5491132032060",
            nombre: "Daniel",
            apellido: "Peterson",
            hayDatos: true,
        },
    );
    assert.equal(prellenadoDesdeUrl("").hayDatos, false);
    assert.equal(prellenadoDesdeUrl("?pagina=2").hayDatos, false);
});

test("AC-T1-23: en modo parcial solo se valida lo que viene cargado", () => {
    assert.deepEqual(validarCliente({}, { parcial: true }), {});
    assert.deepEqual(validarCliente({ nombre: "Juan" }, { parcial: true }), {});
    assert.ok(validarCliente({ dni: "123" }, { parcial: true }).dni);
    assert.ok(validarCliente({ nombre: "Juan 2" }, { parcial: true }).nombre);
});
