import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const raiz = dirname(dirname(fileURLToPath(import.meta.url)));
const rutaCss = join(raiz, "static", "css", "app.css");
const raizJs = join(raiz, "static", "js");
const rutaPaquete = join(raiz, "..", "package.json");

async function archivosRecursivos(directorio) {
    const entradas = await readdir(directorio, { withFileTypes: true });
    const grupos = await Promise.all(entradas.map(async (entrada) => {
        const ruta = join(directorio, entrada.name);
        return entrada.isDirectory() ? archivosRecursivos(ruta) : [ruta];
    }));
    return grupos.flat();
}

test("AC-T1-07: app.css define las clases visuales requeridas", async () => {
    const css = await readFile(rutaCss, "utf8");
    for (const clase of [
        "fila-rojo",
        "fila-naranja",
        "fila-amarillo",
        "fila-verde",
        "msg-retenido",
        "msg-descartado",
        "msg-cliente",
        "msg-saliente",
    ]) {
        assert.match(css, new RegExp(`\\.${clase}\\b`));
    }
});

test("AC-T1-01: package.json configura módulos ES, proyecto privado y tests sin dependencias", async () => {
    const paquete = JSON.parse(await readFile(rutaPaquete, "utf8"));
    assert.equal(paquete.type, "module");
    assert.equal(paquete.private, true);
    assert.equal(paquete.scripts.test, "node --test");
    assert.equal(paquete.dependencies, undefined);
    assert.equal(paquete.devDependencies, undefined);
});

test("AC-T1-08: los módulos JS no usan HTML inseguro ni hacen fetch fuera de api.js", async () => {
    const archivos = await archivosRecursivos(raizJs);
    const usosFetch = [];
    const htmlInseguro = /\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write)\b/;

    for (const ruta of archivos.filter((archivo) => archivo.endsWith(".js"))) {
        const codigo = await readFile(ruta, "utf8");
        assert.doesNotMatch(codigo, htmlInseguro, relative(raizJs, ruta));
        if (/\bfetch\s*\(/.test(codigo)) {
            usosFetch.push(relative(raizJs, ruta));
        }
    }

    assert.deepEqual(usosFetch, ["api.js"]);
});
