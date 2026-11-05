/**
 * Vehículos asegurados: textos y validación previa a la API.
 *
 * Las reglas son copia deliberada de `negocio/vehiculos.py`: avisan antes de
 * pedirle nada al servidor, que es el que decide (R17).
 */

import { patenteValida } from "./patente.js?v=20261105revision10";

export const ANIO_MINIMO = 1950;

export const CLASES = [
    ["sin_especificar", "Sin especificar"], ["auto", "Auto"], ["camioneta", "Camioneta"],
    ["utilitario", "Utilitario"], ["moto", "Moto"], ["camion", "Camión"],
];

export const USOS = [
    ["particular", "Particular"],
    ["comercial", "Comercial"],
    ["remis_taxi", "Remis o taxi"],
    ["carga", "Carga"],
];

/**
 * @param {string} uso
 * @returns {string} Texto para mostrar; lo desconocido, un guion.
 */
export function etiquetaUso(uso) {
    return USOS.find(([codigo]) => codigo === uso)?.[1] ?? "—";
}

/**
 * «Toyota Corolla 2020 (AB123CD)».
 * @param {{marca?: string, modelo?: string, anio?: number, patente?: string}|null|undefined} vehiculo
 * @returns {string}
 */
export function descripcionVehiculo(vehiculo) {
    if (!vehiculo) {
        return "—";
    }
    return `${vehiculo.marca} ${vehiculo.modelo} ${vehiculo.anio} (${vehiculo.patente})`;
}

/**
 * Valida el alta o la edición de un vehículo. Objeto vacío = válido.
 *
 * Con `parcial` solo se validan los campos presentes, porque el PATCH
 * actualiza únicamente lo que se manda.
 * @param {{patente?: string, marca?: string, modelo?: string, anio?: string|number, valor_asegurado?: string}} datos
 * @param {{parcial?: boolean, anioMaximo?: number}} opciones
 * @returns {Record<string, string>}
 */
export function validarVehiculo(
    datos = {},
    { parcial = false, anioMaximo = new Date().getFullYear() + 1 } = {},
) {
    const errores = {};
    const presente = (clave) => datos[clave] !== undefined && String(datos[clave]).trim() !== "";

    if (!parcial || presente("patente")) {
        if (!patenteValida(datos.patente)) {
            errores.patente = "La patente no tiene un formato válido (ej.: ABC123 o AB123CD).";
        }
    }
    if (!parcial || presente("marca")) {
        if (!String(datos.marca ?? "").trim()) {
            errores.marca = "La marca es obligatoria.";
        }
    }
    if (!parcial || presente("modelo")) {
        if (!String(datos.modelo ?? "").trim()) {
            errores.modelo = "El modelo es obligatorio.";
        }
    }
    if (!parcial || presente("anio")) {
        const texto = String(datos.anio ?? "").trim();
        const anio = Number(texto);
        if (!/^\d{4}$/.test(texto) || anio < ANIO_MINIMO || anio > anioMaximo) {
            errores.anio = `El año tiene que estar entre ${ANIO_MINIMO} y ${anioMaximo}.`;
        }
    }
    if (presente("valor_asegurado")) {
        const valor = Number(String(datos.valor_asegurado).replace(",", "."));
        if (Number.isNaN(valor) || valor <= 0) {
            errores.valor_asegurado = "El valor asegurado tiene que ser mayor que cero.";
        }
    }
    return errores;
}
