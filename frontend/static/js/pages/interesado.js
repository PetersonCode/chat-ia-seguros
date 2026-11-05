import { api } from "../api.js?v=20261105revision10";
import { inicializarNav } from "../nav.js?v=20261105revision10";
import {
    COBERTURAS,
    datosDelInteresado,
    estadoSeguimiento,
    etiquetaCobertura,
    etiquetaEtapa,
    etapaAnterior,
    etiquetaOrigen,
    hoyIso,
    idMasBarata,
    nombreCompleto,
    siguienteEtapa,
    validarCotizacion,
    validarMotivoPerdida,
} from "../lib/embudo.js?v=20261105revision10";
import { formatearFecha, formatearFechaHora, formatearMonto } from "../lib/formato.js?v=20261105revision10";
import { patenteValida } from "../lib/patente.js?v=20261105revision10";
import { ANIO_MINIMO, USOS, CLASES } from "../lib/vehiculos.js?v=20261105revision10";
import { formatearPorcentaje } from "../lib/companias.js?v=20261105revision10";

const $ = (id) => document.getElementById(id);
const mensajePagina = $("mensaje-pagina");
const idInteresado = Number(new URLSearchParams(globalThis.location.search).get("id"));

let interesado = null;
let esAprobador = false;

function crearElemento(etiqueta, clase, texto) {
    const elemento = document.createElement(etiqueta);
    if (clase) {
        elemento.className = clase;
    }
    if (texto !== undefined) {
        elemento.textContent = texto;
    }
    return elemento;
}

function mostrarAviso(nodo, mensaje, error = false) {
    nodo.textContent = mensaje;
    nodo.classList.toggle("d-none", !mensaje);
    nodo.classList.toggle("alert-danger", error);
    nodo.classList.toggle("alert-success", Boolean(mensaje) && !error);
}

function textoError(error, porDefecto) {
    return error.mensaje ?? error.message ?? porDefecto;
}

function llenarSelector(selector, opciones, { vacio } = {}) {
    selector.replaceChildren();
    if (vacio !== undefined) {
        const opcion = crearElemento("option", "", vacio);
        opcion.value = "";
        selector.append(opcion);
    }
    for (const [valor, etiqueta] of opciones) {
        const opcion = crearElemento("option", "", etiqueta);
        opcion.value = String(valor);
        selector.append(opcion);
    }
}

/** Ejecuta una acción de la ficha: muestra su error o vuelve a pintar con lo que devolvió la API. */
async function ejecutar(boton, accion) {
    if (boton) {
        boton.disabled = true;
    }
    mostrarAviso(mensajePagina, "");
    try {
        const resultado = await accion();
        if (resultado) {
            interesado = resultado;
            pintar();
        }
        return true;
    } catch (error) {
        mostrarAviso(mensajePagina, textoError(error, "No se pudo completar la acción."), true);
        return false;
    } finally {
        if (boton) {
            boton.disabled = false;
        }
    }
}

// --- Cabecera ---------------------------------------------------------------

function pintarCabecera() {
    document.title = `${nombreCompleto(interesado)} | Seguros Castaño`;
    $("titulo").textContent = nombreCompleto(interesado);
    const chat = $("ver-conversacion");
    chat.hidden = !interesado.conversacion_id;
    chat.removeAttribute('href');
    if (interesado.conversacion_id) {
        chat.href = `/panel/conversacion/?id=${interesado.conversacion_id}`;
        chat.title = 'Abrir la conversación más reciente de este interesado';
    }
    $("sin-conversacion").hidden = Boolean(interesado.conversacion_id);

    const insignias = [crearElemento("span", "pildora pildora-activa", etiquetaEtapa(interesado.estado)),
        crearElemento("span", "pildora", `Llegó por ${etiquetaOrigen(interesado.origen)}`)];
    if (interesado.cliente) {
        const enlace = crearElemento("a", "pildora", `Cliente: ${interesado.cliente.nombre} ${interesado.cliente.apellido}`);
        enlace.href = `/panel/cliente/?id=${interesado.cliente.id}`;
        insignias.push(enlace);
    }
    $("insignias").replaceChildren(...insignias);
    if (interesado.poliza_registrada_id) {
        const contrato = crearElemento('a', 'btn btn-outline-primary mt-2', 'Ver contrato registrado en el cliente');
        contrato.href = `/panel/cliente/?id=${interesado.cliente.id}`;
        $("insignias").append(contrato);
    }

    $("contacto").textContent = interesado.contacto
        ? `WhatsApp: ${interesado.contacto.whatsapp}${interesado.contacto.nombre_perfil ? ` (perfil: ${interesado.contacto.nombre_perfil})` : ""}`
        : "Sin WhatsApp cargado.";
    if (interesado.estado === "perdida") {
        $("contacto").textContent += ` · Motivo: ${interesado.motivo_perdida ?? "—"}`;
    }
}

// --- Seguimiento ------------------------------------------------------------

function pintarSeguimiento() {
    $("responsable").value = interesado.responsable ? String(interesado.responsable.id) : "";
    $("proximo-contacto").value = interesado.proximo_contacto ?? "";
    $("proximo-contacto").min = hoyIso();

    const seguimiento = estadoSeguimiento(interesado);
    const estado = $("estado-contacto");
    estado.textContent = seguimiento.texto;
    estado.className = {
        vencido: "small fw-semibold text-danger",
        hoy: "small fw-semibold",
        proximo: "small text-muted",
        ninguno: "small text-muted",
    }[seguimiento.nivel];

    const acciones = $("acciones-etapa");
    acciones.replaceChildren();
    if (esAprobador && interesado.cliente && interesado.estado === 'documentacion') {
        const elegida = interesado.cotizaciones?.find(c=>c.elegida);
        const registrar = crearElemento('button','btn btn-success','Registrar póliza con la cotización elegida');
        registrar.type='button';registrar.disabled=!elegida;
        registrar.onclick=()=>abrirRegistroPoliza(elegida);
        acciones.append(registrar);
        const existente = crearElemento('button','btn btn-outline-primary','Usar póliza ya registrada');
        existente.type='button';existente.onclick=()=>abrirVinculoPoliza(existente);acciones.append(existente);
    }
    const siguiente = siguienteEtapa(interesado.estado);
    if (siguiente && siguiente !== 'emitida') {
        const avanzar = crearElemento(
            "button",
            "btn btn-primary",
            siguiente === "emitida" ? "Marcar como emitida" : `Avanzar a ${etiquetaEtapa(siguiente)}`,
        );
        avanzar.type = "button";
        avanzar.addEventListener("click", () => mover(avanzar, siguiente));
        acciones.append(avanzar);
    }
    if (siguiente === 'emitida') {
        acciones.append(crearElemento('p', 'small text-muted mb-0 w-100',
            !esAprobador ? 'Un aprobador debe confirmar el cliente y registrar el contrato para completar esta venta.' :
            !interesado.cliente ? 'Primero confirmá «Convertir en cliente». Después registrá el contrato con la cotización elegida.' :
            'Elegir una cotización no crea una póliza. Confirmá su registro para guardar el contrato y las cuotas y cerrar la venta.'));
    }
    const anterior = etapaAnterior(interesado.estado);
    if (anterior) {
        const volver = crearElemento("button", "btn btn-outline-secondary", `Volver a ${etiquetaEtapa(anterior)}`);
        volver.type = "button";
        volver.addEventListener("click", () => mover(volver, anterior));
        acciones.append(volver);
    }
    if (interesado.estado === "perdida") {
        const reabrir = crearElemento("button", "btn btn-outline-primary", "Reabrir como consulta");
        reabrir.type = "button";
        reabrir.addEventListener("click", () => mover(reabrir, "consulta"));
        acciones.append(reabrir);
    }
    if (!["emitida", "perdida"].includes(interesado.estado)) {
        const perder = crearElemento("button", "btn btn-outline-danger", "Marcar como perdido");
        perder.type = "button";
        perder.addEventListener("click", abrirPerdida);
        acciones.append(perder);
    }
    if (esAprobador && interesado.estado === "documentacion" && !interesado.cliente) {
        const convertir = crearElemento("button", "btn btn-outline-success", "Convertir en cliente");
        convertir.type = "button";
        convertir.addEventListener("click", abrirConvertir);
        acciones.append(convertir);
    }
}

function mover(boton, estado, extra = {}) {
    const nota = $("nota-etapa").value.trim();
    return ejecutar(boton, async () => {
        const ficha = await api.post(`/api/interesados/${idInteresado}/mover/`, { estado, nota: nota || null, ...extra });
        $("nota-etapa").value = "";
        return ficha;
    });
}

// --- Datos -------------------------------------------------------------------

const CAMPOS_DATOS = ["patente", "marca", "modelo", "anio", "uso", "clase", "chasis", "valor_asegurado", "localidad", "dni"];

function pintarDatos() {
    const filas = datosDelInteresado(interesado.datos);
    const lista = $("datos");
    lista.replaceChildren();
    for (const [rotulo, valor] of filas) {
        const par = crearElemento("div", "col-sm-6 col-lg-3 mb-2");
        par.append(crearElemento("dt", "small text-muted fw-normal", rotulo), crearElemento("dd", "mb-0", valor));
        lista.append(par);
    }
    $("sin-datos").hidden = filas.length > 0;
    const formulario = $("formulario-datos");
    $("editar-datos").hidden = interesado.estado === 'emitida';
    $("aviso-datos-vinculados").hidden = !interesado.vehiculo_id;
    for (const campo of CAMPOS_DATOS) {
        formulario.elements[campo].value = interesado.datos?.[campo] ?? "";
        formulario.elements[campo].disabled = Boolean(interesado.cliente && campo === 'dni') ||
            Boolean(interesado.vehiculo_id && !esAprobador && campo !== 'localidad');
    }
    pintarErroresDatos({});
}

function pintarErroresDatos(errores) {
    const formulario = $("formulario-datos");
    for (const campo of ["patente", "anio"]) {
        formulario.elements[campo].classList.toggle("is-invalid", Boolean(errores[campo]));
        const aviso = formulario.querySelector(`[data-error="${campo}"]`);
        if (aviso) {
            aviso.textContent = errores[campo] ?? "";
        }
    }
}

async function guardarDatos(evento) {
    evento.preventDefault();
    const formulario = $("formulario-datos");
    const cambios = {};
    for (const campo of CAMPOS_DATOS) {
        const nuevo = formulario.elements[campo].value.trim();
        const actual = String(interesado.datos?.[campo] ?? "");
        if (nuevo !== actual) {
            cambios[campo] = nuevo;
        }
    }
    const errores = {};
    if (cambios.patente && !patenteValida(cambios.patente)) {
        errores.patente = "La patente no tiene un formato válido (ej.: ABC123 o AB123CD).";
    }
    if (cambios.anio && !/^\d{4}$/.test(cambios.anio)) {
        errores.anio = `El año tiene que tener cuatro cifras (desde ${ANIO_MINIMO}).`;
    }
    pintarErroresDatos(errores);
    if (Object.keys(errores).length > 0) {
        mostrarAviso(mensajePagina, "Revisá los campos marcados.", true);
        return;
    }
    if (Object.keys(cambios).length === 0) {
        mostrarAviso(mensajePagina, "No hay cambios para guardar.");
        return;
    }
    const guardado = await ejecutar($("guardar-datos"), () =>
        api.patch(`/api/interesados/${idInteresado}/`, { datos: cambios }),
    );
    if (guardado) {
        mostrarAviso(mensajePagina, "Se guardaron los datos.");
    }
}

// --- Cotizaciones -------------------------------------------------------------

function pintarCotizaciones() {
    const cotizaciones = interesado.cotizaciones ?? [];
    const cerrada = ['emitida','perdida'].includes(interesado.estado);
    $("cargar-cotizacion").hidden = cerrada;
    const masBarata = idMasBarata(cotizaciones);
    $("columna-comision").hidden = !esAprobador;
    const tabla = $("tabla-cotizaciones");
    tabla.replaceChildren();
    if (cotizaciones.length === 0) {
        const fila = document.createElement("tr");
        const celda = crearElemento("td", "text-muted", "Todavía no hay cotizaciones cargadas.");
        celda.colSpan = esAprobador ? 7 : 6;
        fila.append(celda);
        tabla.append(fila);
        return;
    }
    for (const cotizacion of cotizaciones) {
        const vencida = cotizacion.vigencia_hasta && cotizacion.vigencia_hasta < hoyIso();
        const fila = document.createElement("tr");
        if (cotizacion.elegida) {
            fila.classList.add("fila-elegida");
        }
        const compania = crearElemento("th", "fw-semibold", cotizacion.compania?.nombre ?? "—");
        compania.scope = "row";
        fila.append(
            compania,
            crearElemento("td", "", etiquetaCobertura(cotizacion.cobertura)),
            crearElemento("td", "fw-semibold", formatearMonto(cotizacion.prima_mensual)),
            crearElemento("td", "", cotizacion.vigencia_hasta ? formatearFecha(cotizacion.vigencia_hasta) : "—"),
            crearElemento("td", "small", cotizacion.notas ?? ""),
        );
        if (esAprobador) {
            fila.append(crearElemento("td", "", formatearPorcentaje(cotizacion.compania?.comision_pct)));
        }
        const estado = crearElemento("td", "text-end text-nowrap");
        if (vencida) {
            estado.append(crearElemento('span','sev sev-media me-2','Vencida · requiere nueva propuesta'));
        } else if (cotizacion.elegida) {
            estado.append(crearElemento("span", "sev sev-baja me-2", "Elegida"));
        } else if (cotizacion.id === masBarata && cotizaciones.length > 1) {
            estado.append(crearElemento("span", "pildora me-2", "Más barata"));
        }
        if (!cotizacion.elegida && !cerrada) {
            const elegir = crearElemento("button", "btn btn-sm btn-outline-primary me-2", "Elegir");
            elegir.type = "button";
            elegir.disabled = Boolean(vencida);
            elegir.setAttribute("aria-label", `Elegir la cotización de ${cotizacion.compania?.nombre ?? "la compañía"}`);
            elegir.addEventListener("click", () => elegirCotizacion(elegir, cotizacion.id));
            const quitar = crearElemento("button", "btn btn-sm btn-outline-danger", "Quitar");
            quitar.type = "button";
            quitar.setAttribute("aria-label", `Quitar la cotización de ${cotizacion.compania?.nombre ?? "la compañía"}`);
            quitar.addEventListener("click", () => quitarCotizacion(quitar, cotizacion.id));
            estado.append(elegir, quitar);
        }
        fila.append(estado);
        tabla.append(fila);
    }
}

const recargarFicha = () => api.get(`/api/interesados/${idInteresado}/`);

function elegirCotizacion(boton, id) {
    return ejecutar(boton, async () => {
        await api.post(`/api/cotizaciones/${id}/elegir/`);
        return recargarFicha();
    });
}

function quitarCotizacion(boton, id) {
    return ejecutar(boton, async () => {
        await api.post(`/api/cotizaciones/${id}/quitar/`);
        return recargarFicha();
    });
}

function pintarErroresCotizacion(errores) {
    const formulario = $("formulario-cotizacion");
    for (const campo of ["compania_id", "cobertura", "prima_mensual"]) {
        formulario.elements[campo].classList.toggle("is-invalid", Boolean(errores[campo]));
        const aviso = formulario.querySelector(`[data-error="${campo}"]`);
        if (aviso) {
            aviso.textContent = errores[campo] ?? "";
        }
    }
}

async function cargarCotizacion(evento) {
    evento.preventDefault();
    const formulario = $("formulario-cotizacion");
    const cuerpo = {
        interesado_id: idInteresado,
        compania_id: formulario.elements.compania_id.value,
        cobertura: formulario.elements.cobertura.value,
        prima_mensual: formulario.elements.prima_mensual.value.trim(),
        vigencia_hasta: formulario.elements.vigencia_hasta.value || null,
        notas: formulario.elements.notas.value.trim() || null,
    };
    const errores = validarCotizacion(cuerpo);
    pintarErroresCotizacion(errores);
    const estado = $("estado-cotizacion");
    if (Object.keys(errores).length > 0) {
        mostrarAviso(estado, "Revisá los campos marcados.", true);
        return;
    }
    cuerpo.compania_id = Number(cuerpo.compania_id);
    mostrarAviso(estado, "");
    const boton = $("guardar-cotizacion");
    boton.disabled = true;
    try {
        await api.post("/api/cotizaciones/", cuerpo);
        formulario.reset();
        interesado = await recargarFicha();
        pintar();
        mostrarAviso(estado, "Se cargó la cotización.");
    } catch (error) {
        mostrarAviso(estado, textoError(error, "No se pudo cargar la cotización."), true);
    } finally {
        boton.disabled = false;
    }
}

// --- Historial -----------------------------------------------------------------

function pintarHistorial() {
    const lista = $("historial");
    lista.replaceChildren();
    // Lo más nuevo primero: lo último que pasó es lo que se quiere leer.
    for (const linea of [...(interesado.historial ?? [])].reverse()) {
        const item = crearElemento("li", "list-group-item");
        const cambio = linea.estado_anterior === null
            ? "Alta"
            : linea.estado_anterior === linea.estado_nuevo
                ? ""
                : `${etiquetaEtapa(linea.estado_anterior)} → ${etiquetaEtapa(linea.estado_nuevo)}`;
        const cabecera = crearElemento("div", "small text-muted");
        cabecera.textContent = `${formatearFechaHora(linea.fecha)} · ${linea.funcionario?.nombre ?? "Bot"}`;
        item.append(cabecera);
        if (cambio) {
            item.append(crearElemento("div", "fw-semibold", cambio));
        }
        if (linea.nota) {
            item.append(crearElemento("div", "", linea.nota));
        }
        lista.append(item);
    }
}

// --- Diálogos --------------------------------------------------------------------

const dialogoPerdida = $("dialog-perdida");

function abrirPerdida() {
    $("perdida-motivo").value = "";
    $("perdida-error").textContent = "";
    dialogoPerdida.showModal();
}

async function confirmarPerdida(evento) {
    evento.preventDefault();
    const motivo = $("perdida-motivo").value.trim();
    const problema = validarMotivoPerdida(motivo);
    if (problema) {
        $("perdida-error").textContent = problema;
        return;
    }
    const hecho = await ejecutar($("perdida-confirmar"), async () => {
        const nota = $("nota-etapa").value.trim();
        const ficha = await api.post(`/api/interesados/${idInteresado}/mover/`, {
            estado: "perdida",
            motivo_perdida: motivo,
            nota: nota || null,
        });
        $("nota-etapa").value = "";
        return ficha;
    });
    if (hecho) {
        dialogoPerdida.close();
    } else {
        $("perdida-error").textContent = mensajePagina.textContent;
        mostrarAviso(mensajePagina, "");
    }
}

const dialogoConvertir = $("dialog-convertir");

function abrirConvertir() {
    $("conv-dni").value = interesado.datos?.dni ?? "";
    $("conv-nombre").value = interesado.nombre ?? "";
    $("conv-apellido").value = interesado.apellido ?? "";
    $("conv-email").value = "";
    $("conv-telefono").value = "";
    $("conv-telefono-grupo").hidden = Boolean(interesado.contacto);
    $("convertir-error").textContent = "";
    dialogoConvertir.showModal();
}

async function confirmarConversion(evento) {
    evento.preventDefault();
    const cuerpo = {
        dni: $("conv-dni").value.trim(),
        nombre: $("conv-nombre").value.trim(),
        apellido: $("conv-apellido").value.trim(),
        email: $("conv-email").value.trim() || null,
    };
    if (!interesado.contacto) {
        cuerpo.telefono = $("conv-telefono").value.trim();
    }
    if (!cuerpo.dni || !cuerpo.nombre || !cuerpo.apellido) {
        $("convertir-error").textContent = "El DNI, el nombre y el apellido son obligatorios.";
        return;
    }
    const hecho = await ejecutar($("convertir-confirmar"), () =>
        api.post(`/api/interesados/${idInteresado}/convertir/`, cuerpo),
    );
    if (hecho) {
        dialogoConvertir.close();
        mostrarAviso(mensajePagina, "Cliente y vehículo guardados. El siguiente paso es registrar la póliza con la cotización elegida; se generarán sus cuotas y la venta quedará Emitida.");
    } else {
        $("convertir-error").textContent = mensajePagina.textContent;
        mostrarAviso(mensajePagina, "");
    }
}

// --- Arranque --------------------------------------------------------------------

function pintar() {
    pintarCabecera();
    pintarSeguimiento();
    pintarDatos();
    pintarCotizaciones();
    pintarHistorial();
    $("contenido").hidden = false;
}

async function iniciar() {
    inicializarNav();
    if (!Number.isInteger(idInteresado) || idInteresado < 1) {
        mostrarAviso(mensajePagina, "Falta el interesado. Volvé al tablero y elegí uno.", true);
        return;
    }
    llenarSelector($("dato-uso"), USOS, { vacio: "Sin dato" });
    llenarSelector($("dato-clase"), CLASES, { vacio: "Sin dato" });
    llenarSelector($("cot-cobertura"), COBERTURAS, { vacio: "Elegí…" });
    try {
        const [me, funcionarios, companias, ficha] = await Promise.all([
            api.get("/api/auth/me/"),
            api.get("/api/funcionarios/"),
            api.get("/api/companias/?activas=1"),
            recargarFicha(),
        ]);
        esAprobador = Boolean(me?.puede_aprobar);
        llenarSelector(
            $("responsable"),
            (funcionarios.resultados ?? []).map((f) => [f.id, f.nombre]),
            { vacio: "Sin responsable" },
        );
        llenarSelector(
            $("cot-compania"),
            (companias.resultados ?? []).map((c) => [c.id, c.nombre]),
            { vacio: "Elegí…" },
        );
        interesado = ficha;
        pintar();
    } catch (error) {
        mostrarAviso(mensajePagina, textoError(error, "No se pudo cargar el interesado."), true);
    }
}

$("asignar").addEventListener("click", () => {
    const responsable = Number($("responsable").value);
    if (!responsable) {
        mostrarAviso(mensajePagina, "Elegí a quién se lo asignás.", true);
        return;
    }
    ejecutar($("asignar"), () => api.patch(`/api/interesados/${idInteresado}/`, { responsable_id: responsable }));
});
$("guardar-contacto").addEventListener("click", () => {
    const fecha = $("proximo-contacto").value;
    if (!fecha) {
        mostrarAviso(mensajePagina, "Elegí la fecha del próximo contacto o usá «Quitar».", true);
        return;
    }
    ejecutar($("guardar-contacto"), () => api.patch(`/api/interesados/${idInteresado}/`, { proximo_contacto: fecha }));
});
$("quitar-contacto").addEventListener("click", () => {
    ejecutar($("quitar-contacto"), () => api.patch(`/api/interesados/${idInteresado}/`, { proximo_contacto: null }));
});
$("formulario-datos").addEventListener("submit", guardarDatos);
$("formulario-cotizacion").addEventListener("submit", cargarCotizacion);
$("formulario-perdida").addEventListener("submit", confirmarPerdida);
$("perdida-cancelar").addEventListener("click", () => dialogoPerdida.close());
$("formulario-convertir").addEventListener("submit", confirmarConversion);
$("convertir-cancelar").addEventListener("click", () => dialogoConvertir.close());

iniciar();

async function abrirRegistroPoliza(c) {
    const d=document.createElement('dialog');d.className='dialog-accion';
    d.append(document.getElementById('plantilla-registrar-poliza').content.cloneNode(true));
    d.querySelector('[data-resumen]').textContent=`${c.compania.nombre} · ${etiquetaCobertura(c.cobertura)} · ${formatearMonto(c.prima_mensual)} mensuales · ${interesado.datos.patente}. Revisá las fechas del contrato antes de confirmar.`;
    d.querySelector('[data-cancelar]').onclick=()=>d.close();d.onclose=()=>d.remove();
    const f=d.querySelector('form');
    const label=document.createElement('label');label.className='form-label';label.htmlFor='emitir-plan';label.textContent='Plan de cobertura de la compañía';
    const select=document.createElement('select');select.id='emitir-plan';select.name='plan_id';select.className='form-select mb-3';select.disabled=true;
    const ayuda=document.createElement('p');ayuda.className='small text-muted';ayuda.textContent='Las condiciones del plan se copian al contrato y quedan disponibles para el bot.';
    const inicio=f.querySelector('label');inicio.before(label,select,ayuda);
    const confirmar=f.querySelector('[type=submit]');confirmar.disabled=true;
    let planes=[];
    f.onsubmit=async e=>{
        e.preventDefault();const b=f.querySelector('[type=submit]');b.disabled=true;
        const cuerpo=Object.fromEntries(new FormData(f));
        const plan=planes.find(p=>String(p.id)===select.value);
        cuerpo.plan_id=plan?.id??null;cuerpo.plan_version=plan?.version??null;
        try{interesado=await api.post(`/api/interesados/${idInteresado}/registrar-poliza/`,cuerpo);pintar();d.close();mostrarAviso(mensajePagina,'Póliza y cuotas registradas. El interesado quedó como Emitido.');}
        catch(e){d.querySelector('[role=alert]').textContent=textoError(e,'No se pudo registrar la póliza.');}
        finally{b.disabled=false;}
    };
    document.body.append(d);d.showModal();
      try {
          let pagina=1,hayMas=true;
          while(hayMas){const r=await api.get(`/api/planes-cobertura/?compania_id=${c.compania.id}&pagina=${pagina}`);planes.push(...(r.resultados??[]).filter(p=>p.activo));hayMas=pagina*r.por_pagina<r.total;pagina++;}
          const compatibles=planes.filter(p=>!p.nivel||p.nivel===c.cobertura);
          select.add(new Option(planes.length?'Elegí el plan acordado':'Sin plan cargado: completar condiciones desde Pólizas',''));
          for(const p of compatibles)select.add(new Option(`${p.nombre} · v${p.version}`,String(p.id)));
          select.disabled=!planes.length;select.required=Boolean(planes.length);
          if(planes.length&&!compatibles.length){ayuda.textContent='No hay planes compatibles con la cobertura elegida. Revisá la cotización o cargá el plan correcto en Compañías.';return;}
          confirmar.disabled=false;
      } catch(e) {d.querySelector('[role=alert]').textContent=textoError(e,'No se pudieron cargar los planes. Cerrá y reintentá.');}
}

async function abrirVinculoPoliza(boton) {
    boton.disabled=true;
    try {
        const cliente=await api.get(`/api/clientes/${interesado.cliente.id}/`);
        const opciones=(cliente.polizas??[]).filter(p=>p.estado!=='dada_de_baja' &&
            (!interesado.vehiculo_id || p.vehiculo?.id===interesado.vehiculo_id));
        if(!opciones.length) { mostrarAviso(mensajePagina,'No hay un contrato de este vehículo para vincular. Usá «Registrar póliza con la cotización elegida».',true);return; }
        const d=crearElemento('dialog','dialog-accion'),f=crearElemento('form','p-4');
        f.append(crearElemento('h2','h5','Usar póliza ya registrada'),crearElemento('p','','Seleccioná el contrato confirmado de esta venta. Se vincula el mismo registro; no se crean otra póliza ni cuotas nuevas.'));
        const label=crearElemento('label','form-label','Contrato registrado');label.htmlFor='vincular-contrato';
        const select=crearElemento('select','form-select mb-3');select.id='vincular-contrato';select.required=true;
        llenarSelector(select,opciones.map(p=>[p.id,`${p.numero_poliza} · ${p.compania?.nombre??'Sin compañía'} · vence ${formatearFecha(p.fecha_vencimiento)}`]),{vacio:'Elegí el contrato de esta venta'});
        const error=crearElemento('p','small text-danger');error.setAttribute('role','alert');
        const cancelar=crearElemento('button','btn btn-outline-secondary me-2','Cancelar');cancelar.type='button';cancelar.onclick=()=>d.close();
        const guardar=crearElemento('button','btn btn-success','Confirmar vínculo y completar venta');guardar.type='submit';
        f.append(label,select,error,cancelar,guardar);d.append(f);document.body.append(d);d.onclose=()=>d.remove();d.showModal();
        f.onsubmit=async e=>{e.preventDefault();if(guardar.disabled)return;guardar.disabled=true;
            try{interesado=await api.post(`/api/interesados/${idInteresado}/vincular-poliza/`,{poliza_id:Number(select.value)});d.close();pintar();mostrarAviso(mensajePagina,'Contrato vinculado. La venta quedó Emitida sin duplicar datos.');}
            catch(e){error.textContent=textoError(e,'No se pudo vincular el contrato.');}finally{guardar.disabled=false;}};
    } catch(e) { mostrarAviso(mensajePagina,textoError(e,'No se pudieron cargar las pólizas.'),true); }
    finally {boton.disabled=false;}
}
