import test from "node:test";
import assert from "node:assert/strict";

import { armarQuery } from "../static/js/lib/consulta.js";

test("AC-T1-09: armarQuery codifica valores y conserva el orden de los parámetros", () => {
    assert.equal(
        armarQuery({
            estado: "abierta",
            con_alertas: true,
            q: "fer nández",
            pagina: 2,
        }),
        "?estado=abierta&con_alertas=1&q=fer+n%C3%A1ndez&pagina=2",
    );
});

test("AC-T1-09: armarQuery omite campos vacíos, nulos y falsos", () => {
    assert.equal(
        armarQuery({
            estado: "",
            con_alertas: false,
            esperando_humano: null,
            q: undefined,
            pagina: 1,
        }),
        "?pagina=1",
    );
    assert.equal(armarQuery({}), "");
});
