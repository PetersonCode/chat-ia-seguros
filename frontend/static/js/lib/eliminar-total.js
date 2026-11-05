/**
 * Confirmación de un borrado físico (solo rol administrador).
 * La página tiene que incluir el <dialog id="dialog-eliminar-total">.
 */
let accionPendiente = null;
const $ = (id) => document.getElementById(id);

export function confirmarEliminacion(titulo, texto, accion) {
    $("eliminar-total-titulo").textContent = titulo;
    $("eliminar-total-texto").textContent = texto;
    $("eliminar-total-error").textContent = "";
    accionPendiente = accion;
    $("dialog-eliminar-total").showModal();
}

export function inicializarEliminacion() {
    $("eliminar-total-cancelar").addEventListener("click", () => $("dialog-eliminar-total").close());
    $("eliminar-total-confirmar").addEventListener("click", async () => {
        if (!accionPendiente) return;
        const boton = $("eliminar-total-confirmar");
        boton.disabled = true;
        $("eliminar-total-error").textContent = "";
        try {
            await accionPendiente();
            $("dialog-eliminar-total").close();
        } catch (error) {
            $("eliminar-total-error").textContent = error.mensaje ?? error.message ?? "No se pudo eliminar.";
        } finally {
            boton.disabled = false;
        }
    });
}
