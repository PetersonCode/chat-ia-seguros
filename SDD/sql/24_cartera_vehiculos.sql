-- Ejecutar después de 13, 22 y 23. Aditivo e idempotente, no borra históricos.
BEGIN;
ALTER TABLE vehiculos ADD COLUMN IF NOT EXISTS clase text NOT NULL DEFAULT 'sin_especificar'
    CHECK (clase IN ('sin_especificar','auto','camioneta','utilitario','moto','camion'));
CREATE INDEX IF NOT EXISTS idx_poliza_vehiculo_fechas
    ON polizas (vehiculo_id, fecha_inicio, fecha_vencimiento)
    WHERE estado <> 'dada_de_baja' AND vehiculo_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_vehiculo_chasis_normalizado
    ON vehiculos (upper(regexp_replace(chasis, '[[:space:]-]', '', 'g')));
-- No modifica chasis históricos. Impide registrar nuevamente el mismo vehículo
-- con una patente distinta, aun en dos altas concurrentes.
CREATE OR REPLACE FUNCTION validar_chasis_vehiculo() RETURNS trigger
LANGUAGE plpgsql VOLATILE AS $$
DECLARE normalizado text;
BEGIN
    normalizado := upper(regexp_replace(NEW.chasis, '[[:space:]-]', '', 'g'));
    IF normalizado IS NULL OR normalizado = '' THEN RETURN NEW; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('vehiculo-chasis:' || normalizado, 0));
    IF EXISTS (SELECT 1 FROM vehiculos v WHERE v.id <> NEW.id AND
        upper(regexp_replace(v.chasis, '[[:space:]-]', '', 'g')) = normalizado) THEN
        RAISE EXCEPTION 'Ya existe un vehículo con ese chasis'
            USING ERRCODE = '23505', CONSTRAINT = 'vehiculo_chasis_unico';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_validar_chasis_vehiculo ON vehiculos;
CREATE TRIGGER trg_validar_chasis_vehiculo BEFORE INSERT OR UPDATE OF chasis ON vehiculos
    FOR EACH ROW EXECUTE FUNCTION validar_chasis_vehiculo();

-- La fila del vehículo serializa altas concurrentes. VOLATILE toma un snapshot
-- nuevo al consultar conflictos después del lock (READ COMMITTED de Django).
CREATE OR REPLACE FUNCTION validar_vehiculo_poliza() RETURNS trigger
LANGUAGE plpgsql VOLATILE AS $$
DECLARE titular bigint;
BEGIN
    IF NEW.vehiculo_id IS NULL THEN RETURN NEW; END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.vehiculo_id, NEW.cliente_id, NEW.fecha_inicio, NEW.fecha_vencimiento, NEW.estado)
           IS NOT DISTINCT FROM
           ROW(OLD.vehiculo_id, OLD.cliente_id, OLD.fecha_inicio, OLD.fecha_vencimiento, OLD.estado)
        THEN RETURN NEW; END IF;
    END IF;
    SELECT cliente_id INTO titular FROM vehiculos WHERE id = NEW.vehiculo_id FOR UPDATE;
    IF titular IS DISTINCT FROM NEW.cliente_id THEN
        RAISE EXCEPTION 'El vehículo debe pertenecer al cliente de la póliza'
            USING ERRCODE = '23514', CONSTRAINT = 'poliza_vehiculo_titular';
    END IF;
    IF NEW.estado <> 'dada_de_baja' AND EXISTS (
        SELECT 1 FROM polizas p WHERE p.vehiculo_id = NEW.vehiculo_id
        AND p.id <> NEW.id AND p.estado <> 'dada_de_baja'
        AND p.fecha_inicio <= NEW.fecha_vencimiento
        AND p.fecha_vencimiento >= NEW.fecha_inicio
    ) THEN
        RAISE EXCEPTION 'El vehículo ya tiene una póliza en ese período'
            USING ERRCODE = '23514', CONSTRAINT = 'poliza_vehiculo_sin_solapamiento';
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_validar_vehiculo_poliza ON polizas;
CREATE TRIGGER trg_validar_vehiculo_poliza BEFORE INSERT OR UPDATE OF
    vehiculo_id, cliente_id, fecha_inicio, fecha_vencimiento, estado ON polizas
    FOR EACH ROW EXECUTE FUNCTION validar_vehiculo_poliza();
COMMIT;
