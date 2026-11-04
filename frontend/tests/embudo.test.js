import test from "node:test";
import assert from "node:assert/strict";

import {
    ETAPAS,
    agruparPorEstado,
    datosDelInteresado,
    estadoSeguimiento,
    etapaAnterior,
    etiquetaCobertura,
    etiquetaEtapa,
    etiquetaOrigen,
    hoyIso,
    idMasBarata,
    nombreCompleto,
    siguienteEtapa,
    validarCotizacion,
    validarInteresado,
    validarMotivoPerdida,
} from "../static/js/lib/embudo.js";

test("AC-T1-35: ETAPAS es la lista ordenada del embudo con su etiqueta", () => {
    assert.deepEqual(ETAPAS, [
        { clave: "consulta", etiqueta: "Consulta" },
        { clave: "cotizando", etiqueta: "Cotizando" },
        { clave: "documentacion", etiqueta: "Documentación" },
        { clave: "emitida", etiqueta: "Emitida" },
        { clave: "perdida", etiqueta: "Perdida" },
    ]);
});

test("AC-T1-35: agruparPorEstado devuelve las cinco columnas aunque estén vacías", () => {
    const columnas = agruparPorEstado([]);

    assert.deepEqual(columnas.map((columna) => columna.clave), ETAPAS.map((etapa) => etapa.clave));
    assert.deepEqual(columnas.map((columna) => columna.etiqueta), ETAPAS.map((etapa) => etapa.etiqueta));
    assert.ok(columnas.every((columna) => columna.interesados.length === 0));
    assert.equal(agruparPorEstado(undefined).length, 5);
    assert.equal(agruparPorEstado(null).length, 5);
});

test("AC-T1-35: agruparPorEstado reparte por estado, conserva el orden y no modifica la lista original", () => {
    const original = [
        { id: 1, estado: "cotizando" },
        { id: 2, estado: "consulta" },
        { id: 3, estado: "cotizando" },
        { id: 4, estado: "perdida" },
    ];
    const copia = structuredClone(original);

    const columnas = agruparPorEstado(original);

    assert.deepEqual(original, copia);
    const ids = Object.fromEntries(columnas.map((columna) => [columna.clave, columna.interesados.map((i) => i.id)]));
    assert.deepEqual(ids, { consulta: [2], cotizando: [1, 3], documentacion: [], emitida: [], perdida: [4] });
    // Los objetos son los mismos, no copias.
    assert.equal(columnas[1].interesados[0], original[0]);
});

test("AC-T1-35: agruparPorEstado ignora lo que no tiene una etapa conocida", () => {
    const columnas = agruparPorEstado([{ id: 1, estado: "volando" }, { id: 2 }, null]);
    assert.equal(columnas.reduce((suma, columna) => suma + columna.interesados.length, 0), 0);
});

test("AC-T1-35: siguienteEtapa da la próxima o null en emitida y perdida", () => {
    assert.equal(siguienteEtapa("consulta"), "cotizando");
    assert.equal(siguienteEtapa("cotizando"), "documentacion");
    assert.equal(siguienteEtapa("documentacion"), "emitida");
    assert.equal(siguienteEtapa("emitida"), null);
    assert.equal(siguienteEtapa("perdida"), null);
    assert.equal(siguienteEtapa("volando"), null);
    assert.equal(siguienteEtapa(undefined), null);
});

test("AC-T1-35: etapaAnterior permite volver una etapa, salvo desde la primera, emitida y perdida", () => {
    assert.equal(etapaAnterior("cotizando"), "consulta");
    assert.equal(etapaAnterior("documentacion"), "cotizando");
    assert.equal(etapaAnterior("consulta"), null);
    assert.equal(etapaAnterior("emitida"), null);
    assert.equal(etapaAnterior("perdida"), null);
    assert.equal(etapaAnterior("volando"), null);
});

test("embudo: etiquetas, con un guion para lo desconocido", () => {
    assert.equal(etiquetaEtapa("documentacion"), "Documentación");
    assert.equal(etiquetaEtapa("x"), "—");
    assert.equal(etiquetaOrigen("recomendacion"), "Recomendación");
    assert.equal(etiquetaOrigen("whatsapp"), "WhatsApp");
    assert.equal(etiquetaOrigen(null), "—");
    assert.equal(etiquetaCobertura("intermedia"), "Intermedia");
    assert.equal(etiquetaCobertura("premium"), "—");
});

test("embudo: nombre completo con o sin apellido", () => {
    assert.equal(nombreCompleto({ nombre: "Marta", apellido: "Gómez" }), "Marta Gómez");
    assert.equal(nombreCompleto({ nombre: "Marta", apellido: null }), "Marta");
    assert.equal(nombreCompleto({}), "—");
});

test("embudo: hoyIso arma la fecha local con ceros", () => {
    assert.equal(hoyIso(new Date(2026, 0, 5, 23, 59)), "2026-01-05");
    assert.equal(hoyIso(new Date(2026, 10, 24, 0, 1)), "2026-11-24");
});

test("embudo: el próximo contacto dice con texto si está vencido, es hoy o falta", () => {
    const hoy = "2026-11-10";
    assert.deepEqual(estadoSeguimiento({ proximo_contacto: null }, hoy), {
        nivel: "ninguno",
        texto: "Sin próximo contacto",
    });
    assert.deepEqual(estadoSeguimiento({ proximo_contacto: "2026-11-08", seguimiento_vencido: true }, hoy), {
        nivel: "vencido",
        texto: "Vencido: 08/11/2026",
    });
    assert.deepEqual(estadoSeguimiento({ proximo_contacto: "2026-11-10", seguimiento_vencido: false }, hoy), {
        nivel: "hoy",
        texto: "Contactar hoy",
    });
    assert.deepEqual(estadoSeguimiento({ proximo_contacto: "2026-11-12", seguimiento_vencido: false }, hoy), {
        nivel: "proximo",
        texto: "Próximo contacto: 12/11/2026",
    });
});

test("embudo: los datos juntados salen rotulados y en orden, sin lo que no se conoce", () => {
    const filas = datosDelInteresado({
        localidad: "Rosario",
        patente: "AB123CD",
        uso: "remis_taxi",
        anio: 2020,
        marca: "Toyota",
        modelo: "",
        desconocido: "no se muestra",
        dni: null,
    });
    assert.deepEqual(filas, [
        ["Patente", "AB123CD"],
        ["Marca", "Toyota"],
        ["Año", "2020"],
        ["Uso", "Remis o taxi"],
        ["Localidad", "Rosario"],
    ]);
    assert.deepEqual(datosDelInteresado(null), []);
    assert.deepEqual(datosDelInteresado({}), []);
});

test("embudo: idMasBarata compara números, no textos", () => {
    assert.equal(
        idMasBarata([
            { id: 1, prima_mensual: "9000.00" },
            { id: 2, prima_mensual: "12500.50" },
            { id: 3, prima_mensual: "10000.00" },
        ]),
        1,
    );
    assert.equal(idMasBarata([]), null);
    assert.equal(idMasBarata(undefined), null);
});

test("embudo: validar el alta de un interesado", () => {
    assert.deepEqual(validarInteresado({ nombre: "Marta", origen: "web" }), {});
    assert.deepEqual(Object.keys(validarInteresado({ nombre: "  ", origen: "paloma" })).sort(), ["nombre", "origen"]);
    assert.deepEqual(Object.keys(validarInteresado()).sort(), ["nombre", "origen"]);
});

test("embudo: validar la carga de una cotización", () => {
    assert.deepEqual(validarCotizacion({ compania_id: "3", cobertura: "total", prima_mensual: "12500,50" }), {});
    assert.deepEqual(validarCotizacion({ compania_id: 1, cobertura: "basica", prima_mensual: "15000,5" }), {});
    assert.deepEqual(
        Object.keys(validarCotizacion({ compania_id: "", cobertura: "premium", prima_mensual: "" })).sort(),
        ["cobertura", "compania_id", "prima_mensual"],
    );
    for (const prima of ["0", "-3", "abc", "1.234"]) {
        assert.ok(validarCotizacion({ compania_id: 1, cobertura: "total", prima_mensual: prima }).prima_mensual, prima);
    }
});

test("embudo: el motivo de pérdida pide tres caracteres", () => {
    assert.equal(validarMotivoPerdida("Muy caro"), "");
    assert.equal(validarMotivoPerdida("  ab "), "Contá por qué se perdió (3 caracteres como mínimo).");
    assert.notEqual(validarMotivoPerdida(""), "");
    assert.notEqual(validarMotivoPerdida(undefined), "");
});
