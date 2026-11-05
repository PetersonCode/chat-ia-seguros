-- Nivel (básica / intermedia / total) de cada plan de cobertura.
-- Con esto la póliza toma su nivel del plan de la compañía y no se carga dos
-- veces. Nullable: los planes ya creados no tienen un nivel que se pueda
-- deducir; se completa al editarlos en Compañías. Aditivo e idempotente.
BEGIN;
ALTER TABLE planes_cobertura ADD COLUMN IF NOT EXISTS nivel text;
ALTER TABLE planes_cobertura DROP CONSTRAINT IF EXISTS planes_cobertura_nivel_check;
ALTER TABLE planes_cobertura ADD CONSTRAINT planes_cobertura_nivel_check
  CHECK (nivel IS NULL OR nivel IN ('basica','intermedia','total'));
COMMIT;
