-- =====================================================================
-- Tipos de consulta que no son una consulta: agradecer y salirse de tema
-- Uso: después de 11_finalizaciones_acciones.sql. Se puede correr más de una vez.
--
--   agradecimiento : "gracias", "chau" -> el bot contesta y cierra, sin repreguntar
--                    "no entendí" ni derivar a una persona
--   ajeno          : recetas, clima, cuentas -> el bot aclara que solo atiende
--                    temas del seguro, sin derivar. El código es "ajeno" y no
--                    "fuera_de_tema" porque el modelo traducía el segundo al inglés.
-- =====================================================================
BEGIN;

INSERT INTO tipos_consulta (codigo, nombre, politica) VALUES
    ('agradecimiento', 'Agradecimiento o despedida', 'bot_responde'),
    ('ajeno',          'Fuera de tema',              'bot_responde')
ON CONFLICT (codigo) DO UPDATE
    SET nombre = EXCLUDED.nombre, politica = EXCLUDED.politica;

COMMIT;
