import test from "node:test";
import assert from "node:assert/strict";

import { accionesPermitidas, fusionarMensajes } from "../static/js/lib/mensajes.js";

test("AC-T1-11: fusionarMensajes ordena por fecha e id, quita duplicados y no muta las entradas", () => {
    const actuales = [
        { id: 3, fecha_hora: "2024-04-01T12:00:01Z", texto: "tres" },
        { id: 1, fecha_hora: "2024-04-01T12:00:00Z", texto: "uno" },
    ];
    const nuevos = [
        { id: 2, fecha_hora: "2024-04-01T12:00:00Z", texto: "dos" },
        { id: 3, fecha_hora: "2024-04-01T12:00:01Z", texto: "tres repetido" },
    ];
    const actualesOriginales = structuredClone(actuales);
    const nuevosOriginales = structuredClone(nuevos);

    const resultado = fusionarMensajes(actuales, nuevos);

    assert.deepEqual(resultado.map(({ id }) => id), [1, 2, 3]);
    assert.deepEqual(actuales, actualesOriginales);
    assert.deepEqual(nuevos, nuevosOriginales);
});

test("AC-T1-11: accionesPermitidas exige aprobador y mensaje retenido", () => {
    const aprobador = { puede_aprobar: true };
    const operador = { puede_aprobar: false };
    const retenido = { estado_envio: "retenido" };
    const enviado = { estado_envio: "enviado" };

    assert.deepEqual(accionesPermitidas(retenido, aprobador), ["liberar", "corregir", "descartar"]);
    assert.deepEqual(accionesPermitidas(retenido, operador), []);
    assert.deepEqual(accionesPermitidas(enviado, aprobador), []);
    assert.deepEqual(accionesPermitidas(retenido, null), []);
});
