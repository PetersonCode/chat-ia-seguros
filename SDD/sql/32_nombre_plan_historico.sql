-- El nombre confirmado también pertenece a la copia del contrato.
BEGIN;
ALTER TABLE condiciones_poliza ADD COLUMN IF NOT EXISTS plan_nombre TEXT NOT NULL DEFAULT '';
UPDATE condiciones_poliza c SET plan_nombre=p.nombre FROM planes_cobertura p
WHERE c.plan_id=p.id AND c.plan_version=p.version AND c.plan_nombre='';
COMMIT;
