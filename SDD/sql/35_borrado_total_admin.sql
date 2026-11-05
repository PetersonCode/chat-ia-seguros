-- Borrado total del administrador (fase de pruebas): permite DELETE físico de lo
-- que la base declaraba inmutable (historial de siniestros y finalizaciones de
-- acciones), pero SOLO dentro de una transacción que lo habilitó con
-- set_config('app.borrado_total', 'on', true). Sin esa marca todo sigue igual:
-- el historial y las finalizaciones no se pueden borrar ni modificar.
BEGIN;

CREATE OR REPLACE FUNCTION siniestro_historial_inmutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('app.borrado_total', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'El historial de siniestros es inmutable';
END;
$$;

CREATE OR REPLACE FUNCTION finalizacion_accion_control() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    actual acciones_pendientes%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('app.borrado_total', true) = 'on' THEN
        RETURN OLD;
    END IF;
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'El registro de finalización es inmutable' USING ERRCODE='check_violation';
    END IF;
    SELECT * INTO actual FROM acciones_pendientes WHERE id=NEW.accion_id FOR UPDATE;
    IF NOT FOUND OR actual.estado <> 'aprobada'
       OR actual.tipo_accion NOT IN ('reembolso', 'modificar_poliza') THEN
        RAISE EXCEPTION 'Solo puede finalizarse una gestión externa aprobada' USING ERRCODE='check_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM funcionarios WHERE id=NEW.funcionario_id AND activo AND puede_aprobar) THEN
        RAISE EXCEPTION 'La finalización requiere un aprobador activo' USING ERRCODE='check_violation';
    END IF;
    RETURN NEW;
END $$;

COMMIT;
