import { api, ApiError } from "../api.js";

const formulario = document.getElementById("formulario-login");
const aviso = document.getElementById("mensaje-login");
const boton = document.getElementById("boton-ingresar");

function mostrarMensaje(mensaje) {
    aviso.textContent = mensaje;
    aviso.classList.remove("d-none");
}

const csrfPreparado = api.get("/api/auth/csrf/").catch((error) => {
    mostrarMensaje(error.mensaje ?? "No se pudo preparar el inicio de sesión.");
    return error;
});

formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    boton.disabled = true;
    aviso.classList.add("d-none");

    try {
        const errorCsrf = await csrfPreparado;
        if (errorCsrf instanceof Error) {
            mostrarMensaje(errorCsrf.mensaje ?? "No se pudo preparar el inicio de sesión.");
            return;
        }

        const datos = new FormData(formulario);
        await api.post("/api/auth/login/", {
            email: datos.get("email"),
            password: datos.get("password"),
        });
        globalThis.location.assign("/panel/");
    } catch (error) {
        if (error instanceof ApiError) {
            mostrarMensaje(error.mensaje);
        } else {
            mostrarMensaje("No se pudo conectar con el servidor. Intentá nuevamente.");
        }
    } finally {
        boton.disabled = false;
    }
});
