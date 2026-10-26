document.addEventListener('DOMContentLoaded', () => {
    const btnRegistrarPago = document.getElementById('btn-registrar-pago');
    const btnNuevaPoliza = document.getElementById('btn-nueva-poliza');

    if (btnRegistrarPago) {
        btnRegistrarPago.addEventListener('click', () => {
            const monto = prompt('Ingrese el monto abonado por el cliente ($):', '45000');
            if (monto) {
                alert(`Pago de $${monto} registrado exitosamente en la Cta. Cte. El saldo se actualizó.`);
                const badge = document.getElementById('cli-saldo-badge');
                if (badge) {
                    badge.className = 'badge bg-success-subtle text-success fs-6 fw-bold';
                    badge.textContent = 'Al día ($0)';
                }
            }
        });
    }

    if (btnNuevaPoliza) {
        btnNuevaPoliza.addEventListener('click', () => {
            // Simulación de control de cupo y solapamiento
            const tieneCupo = true;
            if (!tieneCupo) {
                alert('ERROR: Se ha alcanzado el límite de stock/cupo para este tipo de póliza en esta zona.');
                return;
            }

            alert('Abriendo formulario de alta con validación de fechas anti-solapamiento...');
        });
    }
});