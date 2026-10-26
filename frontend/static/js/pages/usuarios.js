import { api } from "../api.js?v=20261020b";
import { inicializarNav } from "../nav.js?v=20261020b";
import { crearInsignia, crearTarjeta, crearTarjetaVacia } from "../lib/tarjetas.js?v=20261020b";

const ROLES = {
    propietario: "Propietario",
    administracion: "Administración",
    operador: "Operador",
};

const mensajePagina = document.getElementById("mensaje-pagina");
const contenido = document.getElementById("contenido-usuarios");
const tabla = document.getElementById("tabla-usuarios");
const formularioAlta = document.getElementById("formulario-alta-usuario");
const estadoAlta = document.getElementById("estado-alta-usuario");
const botonGuardar = document.getElementById("alta-guardar");
const dialogo = document.getElementById("dialog-usuario");
const formularioDialogo = document.getElementById("formulario-dialogo");
const dialogoTitulo = document.getElementById("dialog-titulo");
const dialogoCampos = document.getElementById("dialog-campos");
const dialogoError = document.getElementById("dialog-error");
const dialogoCancelar = document.getElementById("dialog-cancelar");
const dialogoConfirmar = document.getElementById("dialog-confirmar");

let alConfirmar = null;

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

function campo(etiqueta, control) {
    const grupo = crearElemento("div", "mb-3");
    const label = crearElemento("label", "form-label", etiqueta);
    label.htmlFor = control.id;
    grupo.append(label, control);
    return grupo;
}

function selectorRol(valor) {
    const select = crearElemento("select", "form-select");
    select.id = "dialog-rol";
    for (const rol of ["operador", "administracion"]) {
        const opcion = crearElemento("option", "", ROLES[rol]);
        opcion.value = rol;
        opcion.selected = rol === valor;
        select.append(opcion);
    }
    return select;
}

function abrirDialogo(titulo, campos, accion) {
    dialogoTitulo.textContent = titulo;
    dialogoCampos.replaceChildren(...campos);
    dialogoError.textContent = "";
    alConfirmar = accion;
    dialogo.showModal();
}

function editarUsuario(usuario) {
    const nombre = crearElemento("input", "form-control");
    nombre.id = "dialog-nombre";
    nombre.value = usuario.nombre;
    const rol = selectorRol(usuario.rol);
    const aprobar = crearElemento("input", "form-check-input");
    aprobar.type = "checkbox";
    aprobar.id = "dialog-aprobar";
    aprobar.checked = usuario.puede_aprobar;
    const check = crearElemento("div", "form-check mb-3");
    const etiquetaAprobar = crearElemento("label", "form-check-label", "Puede aprobar acciones");
    etiquetaAprobar.htmlFor = aprobar.id;
    check.append(aprobar, etiquetaAprobar);

    abrirDialogo(`Editar ${usuario.nombre}`, [campo("Nombre", nombre), campo("Rol", rol), check], async () => {
        await api.patch(`/api/usuarios/${usuario.id}/`, {
            nombre: nombre.value.trim(),
            rol: rol.value,
            puede_aprobar: aprobar.checked,
        });
        return `Se actualizó a ${nombre.value.trim()}.`;
    });
}

function cambiarClave(usuario) {
    const clave = crearElemento("input", "form-control");
    clave.id = "dialog-clave";
    clave.type = "password";
    clave.autocomplete = "new-password";
    abrirDialogo(`Contraseña de ${usuario.nombre}`, [campo("Contraseña nueva", clave)], async () => {
        await api.post(`/api/usuarios/${usuario.id}/clave/`, { clave: clave.value });
        return `Se cambió la contraseña de ${usuario.nombre}.`;
    });
}

function cambiarEstado(usuario) {
    const activar = !usuario.activo;
    const aviso = crearElemento(
        "p",
        "",
        activar
            ? `${usuario.nombre} va a poder volver a iniciar sesión.`
            : `${usuario.nombre} no va a poder iniciar sesión. Su historial (mensajes, derivaciones, acciones) se conserva.`,
    );
    abrirDialogo(activar ? "Reactivar usuario" : "Desactivar usuario", [aviso], async () => {
        await api.patch(`/api/usuarios/${usuario.id}/`, { activo: activar });
        return activar ? `${usuario.nombre} está activo.` : `${usuario.nombre} quedó desactivado.`;
    });
}

function boton(texto, clase, alHacerClic) {
    const elemento = crearElemento("button", `btn btn-sm ${clase}`, texto);
    elemento.type = "button";
    elemento.addEventListener("click", alHacerClic);
    return elemento;
}

function iniciales(nombre) {
    return (nombre || "")
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((palabra) => palabra[0].toUpperCase())
        .join("");
}

function crearTarjetaUsuario(usuario) {
    const propietario = usuario.rol === "propietario";
    const acciones = propietario
        ? [crearElemento("span", "small text-muted", "No se modifica desde acá")]
        : [
            boton("Editar", "btn-outline-primary", () => editarUsuario(usuario)),
            boton("Contraseña", "btn-outline-secondary", () => cambiarClave(usuario)),
            boton(
                usuario.activo ? "Desactivar" : "Reactivar",
                usuario.activo ? "btn-outline-danger" : "btn-outline-success",
                () => cambiarEstado(usuario),
            ),
        ];
    const tarjeta = crearTarjeta({
        titulo: usuario.nombre,
        subtitulo: usuario.email,
        clase: !usuario.activo ? "tarjeta-apagada" : propietario ? "tarjeta-azul" : "",
        insignias: [
            crearInsignia(ROLES[usuario.rol] ?? usuario.rol, propietario ? "pildora pildora-activa" : "pildora"),
            usuario.activo ? null : crearInsignia("Desactivado", "pildora pildora-aviso"),
        ],
        datos: [["Aprueba acciones", usuario.puede_aprobar ? "Sí" : "No"]],
        acciones,
    });
    const avatar = crearElemento("span", "nav-avatar tarjeta-avatar", iniciales(usuario.nombre) || "—");
    avatar.setAttribute("aria-hidden", "true");
    tarjeta.querySelector(".tarjeta-encabezado").prepend(avatar);
    return tarjeta;
}

function renderizarUsuarios(usuarios) {
    tabla.replaceChildren();
    if (usuarios.length === 0) {
        tabla.append(crearTarjetaVacia("No hay usuarios."));
        return;
    }
    tabla.append(...usuarios.map(crearTarjetaUsuario));
}

async function cargarUsuarios() {
    const respuesta = await api.get("/api/usuarios/");
    renderizarUsuarios(respuesta.resultados ?? []);
}

async function crearUsuario(evento) {
    evento.preventDefault();
    const datos = new FormData(formularioAlta);
    botonGuardar.disabled = true;
    mostrarAviso(estadoAlta, "");
    try {
        const usuario = await api.post("/api/usuarios/", {
            nombre: String(datos.get("nombre") ?? "").trim(),
            email: String(datos.get("email") ?? "").trim(),
            rol: String(datos.get("rol") ?? "operador"),
            clave: String(datos.get("clave") ?? ""),
            puede_aprobar: datos.get("puede_aprobar") === "on",
        });
        formularioAlta.reset();
        mostrarAviso(estadoAlta, `Se creó el usuario ${usuario.email}.`);
        await cargarUsuarios();
    } catch (error) {
        mostrarAviso(estadoAlta, textoError(error, "No se pudo crear el usuario."), true);
    } finally {
        botonGuardar.disabled = false;
    }
}

async function confirmarDialogo(evento) {
    evento.preventDefault();
    if (!alConfirmar) {
        return;
    }
    dialogoConfirmar.disabled = true;
    dialogoError.textContent = "";
    try {
        const mensaje = await alConfirmar();
        dialogo.close();
        mostrarAviso(mensajePagina, mensaje);
        await cargarUsuarios();
    } catch (error) {
        dialogoError.textContent = textoError(error, "No se pudo completar la acción.");
    } finally {
        dialogoConfirmar.disabled = false;
    }
}

async function iniciar() {
    inicializarNav();
    try {
        await cargarUsuarios();
        contenido.hidden = false;
    } catch (error) {
        // Un 403 es lo esperable para cualquiera que no sea el propietario.
        mostrarAviso(
            mensajePagina,
            error.status === 403
                ? "Esta sección es solo para el propietario."
                : textoError(error, "No se pudieron cargar los usuarios."),
            true,
        );
    }
}

formularioAlta.addEventListener("submit", crearUsuario);
formularioDialogo.addEventListener("submit", confirmarDialogo);
dialogoCancelar.addEventListener("click", () => dialogo.close());

iniciar();
