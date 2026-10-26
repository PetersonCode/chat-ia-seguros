/**
 * Tarjetas para las grillas del panel: bandeja, alertas, derivaciones,
 * clientes, usuarios… Todas se arman igual para que se lean igual:
 *
 *   ┌───────────────────────────────┐  ← filo superior con el color de la
 *   │ Título            [insignias] │    urgencia (y fondo apenas teñido)
 *   │ subtítulo                     │
 *   │ texto (recortado a 3 líneas)  │
 *   │ ETIQUETA   valor              │
 *   │ ETIQUETA   valor              │
 *   │ ───────────────────────────── │
 *   │                     [acciones]│
 *   └───────────────────────────────┘
 */

const clasesPorColor = new Map([
    ["rojo", "tarjeta-rojo"],
    ["naranja", "tarjeta-naranja"],
    ["amarillo", "tarjeta-amarillo"],
    ["verde", "tarjeta-verde"],
]);

/**
 * El color de supervisión (`rojo`/`naranja`/`amarillo`/`verde`) como clase de
 * tarjeta. Lo desconocido queda en verde, igual que `claseDeColor`.
 * @param {string|null|undefined} color
 * @returns {string}
 */
export function claseTarjeta(color) {
    return clasesPorColor.get(color) ?? "tarjeta-verde";
}

const colorPorSeveridad = new Map([
    ["critica", "rojo"],
    ["alta", "naranja"],
    ["media", "amarillo"],
    // Igual que el servidor: una alerta baja sigue siendo algo que mirar.
    ["baja", "amarillo"],
]);

/**
 * Para lo que trae severidad y no color (alertas, casos cerrados): la misma
 * escala que usa el servidor en `color_por_severidad`; sin severidad, verde.
 * @param {string|null|undefined} severidad
 * @returns {string}
 */
export function claseTarjetaSeveridad(severidad) {
    return claseTarjeta(colorPorSeveridad.get(severidad));
}

function crearElemento(etiqueta, clase, texto) {
    const elemento = document.createElement(etiqueta);
    if (clase) {
        elemento.className = clase;
    }
    if (texto !== undefined && texto !== null) {
        elemento.textContent = texto;
    }
    return elemento;
}

/** Una etiqueta corta (estado, modo, rol…). */
export function crearInsignia(texto, clase = "pildora") {
    return crearElemento("span", clase, texto);
}

/**
 * @param {object} opciones
 * @param {string} opciones.titulo
 * @param {string} [opciones.enlace]   Si viene, el título es un enlace y toda la
 *                                     tarjeta se puede cliquear.
 * @param {string} [opciones.subtitulo]
 * @param {Node[]} [opciones.insignias]
 * @param {string} [opciones.texto]    Párrafo principal (mensaje, descripción).
 * @param {Array<[string, string|Node]>} [opciones.datos]
 * @param {Node[]} [opciones.acciones]
 * @param {string} [opciones.clase]    Color u otras clases de la tarjeta.
 * @returns {HTMLElement}
 */
export function crearTarjeta({
    titulo,
    enlace,
    subtitulo,
    insignias = [],
    texto,
    datos = [],
    acciones = [],
    clase = "",
}) {
    const tarjeta = crearElemento("article", `tarjeta ${clase}`.trim());

    const encabezado = crearElemento("header", "tarjeta-encabezado");
    const cabecera = crearElemento("div", "tarjeta-cabecera");
    const nodoTitulo = crearElemento("h3", "tarjeta-titulo");
    if (enlace) {
        const vinculo = crearElemento("a", "tarjeta-enlace", titulo);
        vinculo.href = enlace;
        nodoTitulo.append(vinculo);
        tarjeta.classList.add("tarjeta-cliqueable");
    } else {
        nodoTitulo.textContent = titulo;
    }
    cabecera.append(nodoTitulo);
    if (subtitulo) {
        cabecera.append(crearElemento("p", "tarjeta-subtitulo", subtitulo));
    }
    encabezado.append(cabecera);
    const conInsignias = insignias.filter(Boolean);
    if (conInsignias.length > 0) {
        const grupo = crearElemento("div", "tarjeta-insignias");
        grupo.append(...conInsignias);
        encabezado.append(grupo);
    }
    tarjeta.append(encabezado);

    if (texto) {
        tarjeta.append(crearElemento("p", "tarjeta-texto", texto));
    }

    if (datos.length > 0) {
        const lista = crearElemento("dl", "tarjeta-datos");
        for (const [etiqueta, valor] of datos) {
            lista.append(crearElemento("dt", "", etiqueta));
            const definicion = crearElemento("dd");
            if (valor instanceof Node) {
                definicion.append(valor);
            } else {
                definicion.textContent = valor ?? "—";
            }
            lista.append(definicion);
        }
        tarjeta.append(lista);
    }

    const conAcciones = acciones.filter(Boolean);
    if (conAcciones.length > 0) {
        const pie = crearElemento("footer", "tarjeta-pie");
        pie.append(...conAcciones);
        tarjeta.append(pie);
    }
    return tarjeta;
}

/** El aviso de "no hay nada", ocupando todo el ancho de la grilla. */
export function crearTarjetaVacia(texto) {
    return crearElemento("p", "grilla-vacia", texto);
}
