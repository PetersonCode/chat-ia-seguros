-- Vínculos estables: cambiar una patente no debe crear otro vehículo al emitir.
BEGIN;
ALTER TABLE interesados ADD COLUMN IF NOT EXISTS vehiculo_id BIGINT REFERENCES vehiculos(id) ON DELETE SET NULL;
ALTER TABLE interesados ADD COLUMN IF NOT EXISTS poliza_registrada_id BIGINT REFERENCES polizas(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_interesados_vehiculo ON interesados(vehiculo_id);
CREATE INDEX IF NOT EXISTS idx_interesados_poliza ON interesados(poliza_registrada_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_interesados_poliza_registrada ON interesados(poliza_registrada_id) WHERE poliza_registrada_id IS NOT NULL;
-- Solo se reconstruye una relación inequívoca; no se inventan contratos previos.
UPDATE interesados i SET vehiculo_id=v.id FROM vehiculos v
WHERE i.vehiculo_id IS NULL AND i.cliente_id=v.cliente_id
  AND upper(regexp_replace(i.datos->>'patente', '[^A-Za-z0-9]', '', 'g'))=v.patente;
COMMIT;
