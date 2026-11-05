-- Rol "administrador": usuario de pruebas con la ELIMINACION TOTAL de chats.
-- Aditivo e idempotente. Solo amplía el CHECK de funcionarios.rol.
BEGIN;
ALTER TABLE funcionarios DROP CONSTRAINT IF EXISTS funcionarios_rol_check;
ALTER TABLE funcionarios ADD CONSTRAINT funcionarios_rol_check
  CHECK (rol IN ('propietario','administracion','operador','administrador'));
COMMIT;
