import test from "node:test";
import assert from "node:assert/strict";

import { debounce } from "../static/js/lib/debounce.js";

test("AC-T1-04: debounce ejecuta una vez tras la última llamada y usa sus argumentos", (context) => {
    context.mock.timers.enable({ apis: ["setTimeout"] });
    const llamadas = [];
    const debounced = debounce((...argumentos) => llamadas.push(argumentos), 100);

    debounced("primero");
    context.mock.timers.tick(70);
    debounced("último", 2);
    context.mock.timers.tick(99);
    assert.deepEqual(llamadas, []);

    context.mock.timers.tick(1);
    assert.deepEqual(llamadas, [["último", 2]]);
});
