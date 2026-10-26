import test from "node:test";
import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const raiz = dirname(dirname(fileURLToPath(import.meta.url)));
const rutaCss = join(raiz, "static", "css", "app.css");
const raizJs = join(raiz, "static", "js");
const rutaConversacion = join(raizJs, "pages", "conversacion.js");
const rutaConversacionHtml = join(raiz, "pages", "conversacion.html");
const rutaCliente = join(raizJs, "pages", "cliente.js");
const rutaSiniestros = join(raizJs, "pages", "siniestros.js");
const rutaSiniestrosHtml = join(raiz, "pages", "siniestros.html");
const rutaReportes = join(raizJs, "pages", "reportes.js");
const rutaReportesHtml = join(raiz, "pages", "reportes.html");
const rutaDocumentos = join(raizJs, "pages", "documentos.js");
const rutaDocumentosHtml = join(raiz, "pages", "documentos.html");
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

test("el formulario de pagos pide referencia e importe completo de cuota", async () => {
    const [html, codigo] = await Promise.all([
        readFile(rutaConversacionHtml, "utf8"),
        readFile(rutaConversacion, "utf8"),
    ]);
    assert.match(html, /Referencia del comprobante/);
    assert.match(html, /Importe completo de la cuota/);
    assert.match(codigo, /Solo se admiten pagos completos/);
    assert.match(codigo, /referencia,\s*importe/);
});

test("el detalle de conversación expone acciones pendientes y bloquea el cierre", async () => {
    const [html, codigo] = await Promise.all([
        readFile(rutaConversacionHtml, "utf8"),
        readFile(rutaConversacion, "utf8"),
    ]);
    assert.match(html, /id="panel-casos"/);
    assert.match(codigo, /Aprobada; pendiente de gestión externa/);
    assert.match(codigo, /Pendiente de aprobación/);
    assert.match(codigo, /botonCerrarCasos\.disabled = accionesPendientes/);
    assert.match(codigo, /\/panel\/acciones\/\?estado=/);
    const acciones = await readFile(join(raizJs, "pages", "acciones.js"), "utf8");
    assert.match(acciones, /new URLSearchParams\(globalThis\.location\.search\)/);
});

test("la vista previa anuncia cuotas por aniversario y vencimiento al inicio del ciclo", async () => {
    const codigo = await readFile(rutaCliente, "utf8");
    assert.match(codigo, /mesesDeCobertura\(inicio,\s*vencimiento\)/);
    assert.match(codigo, /vencimiento al inicio de cada ciclo mensual/);
});

test("el expediente permite registrar y documenta decisiones internas", async () => {
    const [html, codigo] = await Promise.all([
        readFile(rutaSiniestrosHtml, "utf8"),
        readFile(rutaSiniestros, "utf8"),
    ]);
    assert.match(html, /Registrar denuncia/);
    assert.match(html, /no confirma ni promete una indemnización/);
    assert.match(html, /Historial de decisiones/);
    assert.match(codigo, /\/api\/siniestros\//);
    assert.match(codigo, /datosDetalle\.dataset\.id = String\(siniestro\.id\)/);
    assert.match(codigo, /transiciones\//);
    assert.match(codigo, /document\.createElement\("li"\)/);
});

test("los reportes muestran filtros de período e indicadores sin afirmar tasa de resolución", async () => {
    const [html, codigo] = await Promise.all([
        readFile(rutaReportesHtml, "utf8"),
        readFile(rutaReportes, "utf8"),
    ]);
    assert.match(html, /type="date"/);
    assert.match(html, /Exportar CSV/);
    assert.match(codigo, /\/api\/reportes\/gestion\//);
    assert.match(codigo, /derivaciones_urgentes/);
    assert.match(codigo, /importe_total/);
    assert.doesNotMatch(`${html}\n${codigo}`, /tasa de resolución|resolución de IA/i);
});

test("la consulta documental cita fragmentos y explicita abstención y búsqueda lexical", async () => {
    const [html, codigo] = await Promise.all([
        readFile(rutaDocumentosHtml, "utf8"),
        readFile(rutaDocumentos, "utf8"),
    ]);
    assert.match(html, /compara palabras/);
    assert.match(html, /no incluye documentación privada de clientes/);
    assert.match(codigo, /fuente\.referencia/);
    assert.match(codigo, /fuente\.pasaje/);
    assert.match(codigo, /respaldo_suficiente/);
    assert.doesNotMatch(`${html}\n${codigo}`, /entrenamiento|semántica/i);
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

test("todas las URLs de estáticos llevan versión, para que la caché no sirva lo viejo", async () => {
    // Los estáticos se sirven con max-age de horas: un archivo que cambia y
    // conserva su URL se sigue leyendo viejo. Peor todavía, un `import` sin
    // versión puede traer una librería vieja que ya no exporta lo que el
    // script nuevo le pide, y ahí la página entera deja de cargar.
    // `python manage.py versionar_estaticos` los pone todos de una.
    const paginas = join(raiz, "pages");
    const sinVersion = [];

    for (const ruta of await archivosRecursivos(paginas)) {
        if (!ruta.endsWith(".html")) {
            continue;
        }
        const html = await readFile(ruta, "utf8");
        for (const [, url] of html.matchAll(/(?:href|src)="(\/static\/[^"]+)"/g)) {
            if (!url.includes("?v=")) {
                sinVersion.push(`${relative(raiz, ruta)} -> ${url}`);
            }
        }
    }

    for (const ruta of await archivosRecursivos(raizJs)) {
        if (!ruta.endsWith(".js")) {
            continue;
        }
        const codigo = await readFile(ruta, "utf8");
        for (const [, especificador] of codigo.matchAll(/from "(\.{1,2}\/[^"]+)"/g)) {
            if (!especificador.includes("?v=")) {
                sinVersion.push(`${relative(raizJs, ruta)} -> ${especificador}`);
            }
        }
    }

    assert.deepEqual(sinVersion, []);
});
