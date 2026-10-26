-- Finalización manual auditable de gestiones externas. Aplicar después de 10.
BEGIN;
-- La firma de aprobación es histórica. Una baja posterior del aprobador no
-- impide que otro aprobador activo complete una gestión ya autorizada.
CREATE OR REPLACE FUNCTION acciones_pendientes_control() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.estado <> 'pendiente' THEN
            RAISE EXCEPTION 'Una acción nueva debe crearse pendiente' USING ERRCODE='check_violation';
        END IF;
    ELSE
        IF OLD.estado <> 'pendiente' AND (
            NEW.resuelta_por_id IS DISTINCT FROM OLD.resuelta_por_id OR
            NEW.resuelta_en IS DISTINCT FROM OLD.resuelta_en OR
            NEW.motivo IS DISTINCT FROM OLD.motivo
        ) THEN
            RAISE EXCEPTION 'La aprobación o rechazo original es inmutable' USING ERRCODE='check_violation';
        END IF;
        IF NOT (
            (OLD.estado='pendiente' AND NEW.estado IN ('pendiente','aprobada','rechazada')) OR
            (OLD.estado='aprobada' AND NEW.estado IN ('aprobada','ejecutada')) OR
            (OLD.estado IN ('rechazada','ejecutada') AND NEW.estado=OLD.estado)
        ) THEN
            RAISE EXCEPTION 'Transición de acción no permitida' USING ERRCODE='check_violation';
        END IF;
        IF OLD.estado='pendiente' AND NEW.estado <> 'pendiente' AND NOT EXISTS (
            SELECT 1 FROM funcionarios WHERE id=NEW.resuelta_por_id AND puede_aprobar AND activo
        ) THEN
            RAISE EXCEPTION 'La resolución requiere un aprobador activo' USING ERRCODE='check_violation';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TABLE acciones_finalizaciones (
    accion_id bigint PRIMARY KEY REFERENCES acciones_pendientes(id),
    funcionario_id bigint NOT NULL REFERENCES funcionarios(id),
    fecha timestamptz NOT NULL DEFAULT now(),
    referencia varchar(100) NOT NULL CHECK (length(btrim(referencia)) >= 3),
    motivo text NOT NULL CHECK (length(btrim(motivo)) >= 3)
);

CREATE FUNCTION finalizacion_accion_control() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    actual acciones_pendientes%ROWTYPE;
BEGIN
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
CREATE TRIGGER finalizacion_accion_control_trg BEFORE INSERT OR UPDATE OR DELETE
ON acciones_finalizaciones FOR EACH ROW EXECUTE FUNCTION finalizacion_accion_control();

CREATE FUNCTION finalizacion_accion_aplicar() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE acciones_pendientes SET estado='ejecutada' WHERE id=NEW.accion_id;
    RETURN NEW;
END $$;
CREATE TRIGGER finalizacion_accion_aplicar_trg AFTER INSERT ON acciones_finalizaciones
FOR EACH ROW EXECUTE FUNCTION finalizacion_accion_aplicar();

-- No se puede afirmar que una gestión externa terminó sin su evidencia.
CREATE FUNCTION accion_externa_exige_finalizacion() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.tipo_accion IN ('reembolso','modificar_poliza') AND NEW.estado='ejecutada'
       AND NOT EXISTS (SELECT 1 FROM acciones_finalizaciones WHERE accion_id=NEW.id) THEN
        RAISE EXCEPTION 'La gestión externa requiere un registro de finalización' USING ERRCODE='check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER accion_externa_exige_finalizacion_trg BEFORE UPDATE ON acciones_pendientes
FOR EACH ROW EXECUTE FUNCTION accion_externa_exige_finalizacion();
COMMIT;
