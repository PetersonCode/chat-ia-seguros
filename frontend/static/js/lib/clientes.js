/**
 * Validación de los datos de un cliente, del lado del navegador.
 *
 * Es una copia deliberada de las reglas de `negocio/clientes.py`: sirve para
 * avisar antes de pedirle nada al servidor, no para reemplazarlo. La API valida
 * igual y es la que manda, porque la unicidad de DNI y teléfono solo se puede
 * resolver contra la base.
 */

const SOLO_DIGITOS = /[.\-\s]/g;
const TIENE_DIGITOS = /\d/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Deja un DNI como lo espera la API: solo dígitos.
 * @param {string} valor
 * @returns {string}
 */
export function limpiarDni(valor) {
    return String(valor ?? "").replace(SOLO_DIGITOS, "");
}

/**
 * Cuenta los dígitos nacionales de un teléfono, descartando prefijos.
 * Acepta las mismas formas que `normalizar_telefono`: con o sin +54, con o sin
 * el 9 de los móviles, con o sin el 0 inicial.
 * @param {string} valor
 * @returns {string}
 */
export function digitosNacionales(valor) {
    let digitos = String(valor ?? "").replace(/[^0-9]/g, "");
    if (digitos.startsWith("54")) {
        digitos = digitos.slice(2);
    }
    if (digitos.startsWith("0")) {
        digitos = digitos.slice(1);
    }
    if (digitos.length === 11 && digitos.startsWith("9")) {
        digitos = digitos.slice(1);
    }
    return digitos;
}

/**
 * Parte el nombre de perfil de WhatsApp en nombre y apellido.
 *
 * Es una conveniencia para el formulario, no un dato que se guarde solo: lo que
 * llega de WhatsApp es un texto libre que la persona eligió, así que el humano
 * lo corrige antes de guardar. Sin espacios, todo va a `nombre`.
 * @param {string} perfil
 * @returns {{nombre: string, apellido: string}}
 */
export function separarNombrePerfil(perfil) {
    const partes = String(perfil ?? "").trim().split(/\s+/).filter(Boolean);
    if (partes.length === 0) {
        return { nombre: "", apellido: "" };
    }
    if (partes.length === 1) {
        return { nombre: partes[0], apellido: "" };
    }
    return { nombre: partes[0], apellido: partes.slice(1).join(" ") };
}

/**
 * Lee de la query string los datos con los que abrir el alta prellenada.
 * @param {string} busqueda
 * @returns {{telefono: string, nombre: string, apellido: string, hayDatos: boolean}}
 */
export function prellenadoDesdeUrl(busqueda) {
    const parametros = new URLSearchParams(busqueda ?? "");
    const telefono = (parametros.get("telefono") ?? "").trim();
    const { nombre, apellido } = separarNombrePerfil(parametros.get("perfil"));
    return { telefono, nombre, apellido, hayDatos: Boolean(telefono || nombre) };
}

function validarNombre(valor, campo, errores, clave) {
    const texto = String(valor ?? "").trim();
    if (!texto) {
        errores[clave] = `El ${campo} es obligatorio.`;
    } else if (TIENE_DIGITOS.test(texto)) {
        errores[clave] = `El ${campo} no puede contener números.`;
    }
}

/**
 * Valida un cliente y devuelve los errores por campo. Objeto vacío = válido.
 *
 * Con `parcial` en true (modificación) solo se validan los campos presentes y
 * no vacíos, porque el PATCH actualiza únicamente lo que se manda.
 * @param {{dni?: string, nombre?: string, apellido?: string, telefono?: string, email?: string}} datos
 * @param {{parcial?: boolean}} opciones
 * @returns {Record<string, string>}
 */
export function validarCliente(datos, { parcial = false } = {}) {
    const errores = {};
    const presente = (clave) => {
        const valor = datos?.[clave];
        return valor !== undefined && String(valor).trim() !== "";
    };

    if (!parcial || presente("dni")) {
        const dni = limpiarDni(datos?.dni);
        if (!/^[0-9]{7,8}$/.test(dni)) {
            errores.dni = "El DNI debe contener 7 u 8 dígitos.";
        }
    }
    if (!parcial || presente("nombre")) {
        validarNombre(datos?.nombre, "nombre", errores, "nombre");
    }
    if (!parcial || presente("apellido")) {
        validarNombre(datos?.apellido, "apellido", errores, "apellido");
    }
    if (!parcial || presente("telefono")) {
        if (digitosNacionales(datos?.telefono).length !== 10) {
            errores.telefono = "El teléfono debe contener 10 dígitos nacionales.";
        }
    }
    // El email es opcional: vacío borra el dato, no es un error.
    const email = String(datos?.email ?? "").trim();
    if (email && !EMAIL.test(email)) {
        errores.email = "El email no tiene un formato válido.";
    }
    return errores;
}
