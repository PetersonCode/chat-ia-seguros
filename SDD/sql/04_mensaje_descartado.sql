-- =====================================================================
-- Agrega el estado 'descartado' a mensajes.estado_envio
-- Uso (después de 03):
--   docker exec -i postgres-irusu psql -U irusu -d proyecto -v ON_ERROR_STOP=1 < 04_mensaje_descartado.sql
--
-- Motivo: cuando un supervisor corrige o rechaza una respuesta retenida del bot, el mensaje original
-- debe conservarse como evidencia (qué dijo el bot) pero sin quedar como "retenido" pendiente.
-- =====================================================================
BEGIN;

ALTER TABLE mensajes DROP CONSTRAINT mensajes_estado_envio_check;
ALTER TABLE mensajes ADD CONSTRAINT mensajes_estado_envio_check CHECK (estado_envio IN
    ('recibido', 'pendiente_envio', 'retenido', 'descartado', 'enviado', 'entregado', 'leido', 'fallido'));

COMMENT ON COLUMN mensajes.estado_envio IS
    'retenido = respuesta del bot frenada por supervisión, no se envía hasta que un humano la libere; '
    'descartado = un humano la rechazó o la reemplazó por otra (se conserva como evidencia, nunca se envía).';

COMMIT;
