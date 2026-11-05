-- Preparación inicial limpia: únicamente equipo y catálogos.
-- No carga clientes, vehículos, pólizas, consultas ni pagos.
BEGIN;

-- Equipo ------------------------------------------------------------
INSERT INTO funcionarios (nombre, email, rol, puede_aprobar) VALUES
    ('Roberto',  'roberto@seguroscastano.example',  'propietario',    true),
    ('Graciela', 'graciela@seguroscastano.example', 'administracion', true),
    ('Diego',    'diego@seguroscastano.example',    'operador',       false);

-- Catálogos ---------------------------------------------------------
INSERT INTO tipos_seguro (codigo, nombre) VALUES
    ('automotor', 'Automotor'),
    ('hogar',     'Hogar'),
    ('vida',      'Vida'),
    ('comercio',  'Comercio'),
    ('moto',      'Moto');

INSERT INTO tipos_consulta (codigo, nombre, politica) VALUES
    ('saludo',            'Saludo',                         'bot_responde'),
    ('saldo',             'Saldo pendiente',                'bot_responde'),
    ('vencimiento',       'Vencimiento de póliza',          'bot_responde'),
    ('siniestro',         'Denuncia de siniestro',          'bot_responde'),
    ('siniestro_urgente', 'Siniestro urgente',              'derivar_humano'),
    ('cotizacion',        'Cotización',                     'derivar_humano'),
    ('consulta_cobertura','Consulta de cobertura',          'derivar_humano'),
    ('reclamo',           'Reclamo',                        'requiere_aprobacion'),
    ('baja',              'Baja de póliza',                 'requiere_aprobacion'),
    ('modificacion',      'Modificación de póliza',         'requiere_aprobacion'),
    ('prompt_injection',  'Intento de manipulación del bot','seguridad'),
    ('otro',              'Otra consulta',                  'derivar_humano'),
    ('registro',          'Alta de cliente',                'requiere_aprobacion'),
    ('asistencia',        'Asistencia en el camino',        'bot_responde'),
    ('pago',              'Pagos y cuotas',                 'derivar_humano');


COMMIT;
