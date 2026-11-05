-- Un siniestro grave derivado a una persona genera una alerta crítica, para que
-- quede en el panel de alertas además de en las derivaciones.
BEGIN;
ALTER TABLE alertas DROP CONSTRAINT IF EXISTS alertas_tipo_check;
ALTER TABLE alertas ADD CONSTRAINT alertas_tipo_check CHECK (tipo IN (
    'prompt_injection', 'fuga_datos', 'accion_sin_aprobacion',
    'dato_inventado', 'dato_inconsistente', 'dato_no_verificado',
    'siniestro_grave'
));
COMMIT;
