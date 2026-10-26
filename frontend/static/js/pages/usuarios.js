document.addEventListener('DOMContentLoaded', () => {
    const tabla = document.getElementById('tabla-usuarios');
    const formUsuario = document.getElementById('form-usuario');

    let usuarios = [
        { id: 1, nombre: 'Roberto Castaño', email: 'roberto@castano.com', rol: 'admin', estado: 'Activo' },
        { id: 2, nombre: 'Graciela Supervisor', email: 'graciela@castano.com', rol: 'supervisor', estado: 'Activo' },
        { id: 3, nombre: 'Carlos Operador', email: 'carlos@castano.com', rol: 'operador', estado: 'Activo' }
    ];

    function renderizarUsuarios() {
        if (!tabla) return;
        tabla.innerHTML = '';

        usuarios.forEach(u => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="fw-semibold">${u.nombre}</td>
                <td>${u.email}</td>
                <td>${obtenerBadgeRol(u.rol)}</td>
                <td><span class="badge bg-success-subtle text-success">${u.estado}</span></td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-secondary me-1" onclick="alert('Editar usuario ${u.id}')">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="eliminarUsuario(${u.id})">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            `;
            tabla.appendChild(tr);
        });
    }

    function obtenerBadgeRol(rol) {
        switch (rol) {
            case 'admin':
                return '<span class="badge bg-danger">Administrador</span>';
            case 'supervisor':
                return '<span class="badge bg-warning text-dark">Supervisor</span>';
            default:
                return '<span class="badge bg-info text-dark">Operador</span>';
        }
    }

    if (formUsuario) {
        formUsuario.addEventListener('submit', (e) => {
            e.preventDefault();
            const nuevo = {
                id: Date.now(),
                nombre: document.getElementById('usr-nombre').value,
                email: document.getElementById('usr-email').value,
                rol: document.getElementById('usr-rol').value,
                estado: 'Activo'
            };

            usuarios.push(nuevo);
            renderizarUsuarios();

            const modalEl = document.getElementById('modalUsuario');
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            formUsuario.reset();
        });
    }

    window.eliminarUsuario = (id) => {
        if (confirm('¿Seguro que querés desactivar este usuario?')) {
            usuarios = usuarios.filter(u => u.id !== id);
            renderizarUsuarios();
        }
    };

    renderizarUsuarios();
});