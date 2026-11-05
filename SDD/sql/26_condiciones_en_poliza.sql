BEGIN;
CREATE TABLE IF NOT EXISTS planes_cobertura (
 id bigserial PRIMARY KEY,
 compania_id bigint NOT NULL REFERENCES companias(id),
 nombre text NOT NULL CHECK (length(trim(nombre)) BETWEEN 1 AND 120),
 cubre text NOT NULL CHECK (length(trim(cubre)) > 0),
 no_cubre text NOT NULL DEFAULT '', limites text NOT NULL DEFAULT '', asistencia text NOT NULL DEFAULT '',
 activo boolean NOT NULL DEFAULT true, version integer NOT NULL DEFAULT 1 CHECK (version > 0),
 actualizado_por_id bigint NOT NULL REFERENCES funcionarios(id), actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_planes_compania_nombre ON planes_cobertura(compania_id,lower(trim(nombre)));
CREATE TABLE IF NOT EXISTS condiciones_poliza (
 poliza_id bigint PRIMARY KEY REFERENCES polizas(id),
 cubre text NOT NULL DEFAULT '', no_cubre text NOT NULL DEFAULT '', limites text NOT NULL DEFAULT '',
 asistencia text NOT NULL DEFAULT '', documento_id bigint REFERENCES documentos_generales(id),
 actualizado_por_id bigint NOT NULL REFERENCES funcionarios(id), actualizado_en timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE condiciones_poliza ADD COLUMN IF NOT EXISTS plan_id bigint REFERENCES planes_cobertura(id);
ALTER TABLE condiciones_poliza ADD COLUMN IF NOT EXISTS plan_version integer;
COMMIT;
