document.addEventListener('DOMContentLoaded', () => {
    const filtroPeriodo = document.getElementById('filtro-periodo');
    const listaMotivos = document.getElementById('lista-motivos');
    const btnExportar = document.getElementById('btn-exportar');

    // Datos simulados por periodo
    const datosPeriodos = {
        'hoy': {
            totales: '184',
            efectividad: '89.1%',
            derivadas: '20',
            tiempo: '0.8 min'
        },
        '7dias': {
            totales: '1,248',
            efectividad: '84.2%',
            derivadas: '197',
            tiempo: '1.4 min'
        },
        'mes': {
            totales: '5,890',
            efectividad: '82.7%',
            derivadas: '1,019',
            tiempo: '1.8 min'
        }
    };

    const motivosDerivacion = [
        { motivo: 'Siniestro pesado / Choque grave', cantidad: 84, porcentaje: '42%' },
        { motivo: 'Solicitud de descuento o bonificación', cantidad: 52, porcentaje: '26%' },
        { motivo: 'Socio con deuda en Cta. Cte.', cantidad: 38, porcentaje: '19%' },
        { motivo: 'Falta de documentación requerida', cantidad: 23, porcentaje: '13%' }
    ];

    function actualizarKPIs(periodo) {
        const datos = datosPeriodos[periodo] || datosPeriodos['7dias'];
        
        document.getElementById('kpi-totales').textContent = datos.totales;
        document.getElementById('kpi-efectividad').textContent = datos.efectividad;
        document.getElementById('kpi-derivadas').textContent = datos.derivadas;
        document.getElementById('kpi-tiempo').textContent = datos.tiempo;
    }

    function renderizarMotivos() {
        if (!listaMotivos) return;
        listaMotivos.innerHTML = '';

        motivosDerivacion.forEach(m => {
            const li = document.createElement('li');
            li.className = 'list-group-item d-flex justify-content-between align-items-center px-0 py-2 border-0';
            li.innerHTML = `
                <div>
                    <span class="d-block small fw-semibold">${m.motivo}</span>
                    <small class="text-muted">${m.cantidad} casos</small>
                </div>
                <span class="badge bg-light text-dark border">${m.porcentaje}</span>
            `;
            listaMotivos.appendChild(li);
        });
    }

    if (filtroPeriodo) {
        filtroPeriodo.addEventListener('change', (e) => {
            actualizarKPIs(e.target.value);
        });
    }

    if (btnExportar) {
        btnExportar.addEventListener('click', () => {
            alert('Generando reporte PDF/CSV de métricas...');
        });
    }

    // Inicializar
    actualizarKPIs('7dias');
    renderizarMotivos();
});