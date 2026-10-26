-- =====================================================================
-- El bot deja más trabajo listo para aprobar, y menos para hacer a mano
-- Uso (después de 04):
--   docker exec -i postgres-irusu psql -U irusu -d proyecto -v ON_ERROR_STOP=1 < 05_acciones_del_bot.sql
--
-- Motivo: la maquinaria de `acciones_pendientes` ya existía completa —con sus
-- parámetros, su ejecución real y el trigger que impide que alguien sin permiso
-- resuelva— pero el bot solo creaba dos de los cinco tipos. Todo lo demás caía
-- en una derivación, y el funcionario tenía que cargar a mano algo que el bot
-- ya sabía. Este incremento agrega el alta de cliente como acción, pasa los
-- reclamos de cobro a una acción de reembolso, y suma los tres tipos de
-- consulta que faltaban para cubrir lo que la gente pregunta de verdad.
--
-- Es idempotente: se puede correr dos veces sin romper nada.
-- =====================================================================
BEGIN;

-- --------------------------------------------------------------------
-- 1. Alta de cliente como acción
-- --------------------------------------------------------------------
-- Un desconocido que quiere registrarse ya no genera "derivá y cargalo vos":
-- el bot junta nombre y DNI, deja la acción armada y un funcionario la aprueba.
-- El alta real la hace `negocio.clientes.alta_cliente` al aprobarse.
ALTER TABLE acciones_pendientes DROP CONSTRAINT acciones_pendientes_tipo_accion_check;
ALTER TABLE acciones_pendientes ADD CONSTRAINT acciones_pendientes_tipo_accion_check CHECK (tipo_accion IN
    ('baja_poliza', 'agregar_conductor', 'modificar_poliza', 'reembolso', 'apertura_siniestro', 'alta_cliente'));

COMMENT ON COLUMN acciones_pendientes.tipo_accion IS
    'alta_cliente = el bot juntó los datos de un contacto desconocido y los deja listos; '
    'al aprobar se crea el Cliente y se le vincula el contacto de WhatsApp.';

-- --------------------------------------------------------------------
-- 2. Tipos de consulta nuevos
-- --------------------------------------------------------------------
--   registro   : "quiero darme de alta"  -> acción de alta de cliente
--   asistencia : "¿a qué número pido la grúa?" -> lo contesta el bot con el
--                teléfono que corresponde a la cobertura de la póliza
--   pago       : "quiero adelantar cuotas" -> lo decide una persona, porque
--                toca la cobranza y no hay nada que el bot pueda resolver solo
INSERT INTO tipos_consulta (codigo, nombre, politica) VALUES
    ('registro',   'Alta de cliente',        'requiere_aprobacion'),
    ('asistencia', 'Asistencia en el camino', 'bot_responde'),
    ('pago',       'Pagos y cuotas',          'derivar_humano')
ON CONFLICT (codigo) DO UPDATE
    SET nombre = EXCLUDED.nombre, politica = EXCLUDED.politica;

-- --------------------------------------------------------------------
-- 3. Un reclamo de cobro nace como pedido de reembolso
-- --------------------------------------------------------------------
-- Antes derivaba y el asesor abría el reembolso a mano. Ahora el bot crea la
-- acción sin importe —el monto lo pone quien revisa, con `completar_parametros`—
-- así el pedido queda registrado desde el primer mensaje en vez de vivir
-- adentro de una conversación.
UPDATE tipos_consulta SET politica = 'requiere_aprobacion' WHERE codigo = 'reclamo';

COMMIT;
