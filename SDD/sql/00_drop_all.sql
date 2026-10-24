-- =====================================================================
-- DESTRUCTIVO: borra todas las tablas del proyecto (y sus datos).
-- NO ejecutar sin confirmar con el equipo. Sirve para recrear desde cero:
--   00_drop_all.sql -> 01_schema.sql -> 02_seed.sql -> 03_whatsapp.sql
-- No toca tablas de Django (auth_*, django_*), solo las del dominio.
-- =====================================================================
DROP VIEW  IF EXISTS v_bandeja_conversaciones, v_consultas_supervision, v_polizas_resumen;
DROP TABLE IF EXISTS acciones_pendientes, derivaciones, alertas, siniestros, mensajes, conversaciones, consultas_bot,
                     cuotas, conductores_poliza, polizas, contactos_whatsapp, clientes,
                     tipos_consulta, tipos_seguro, funcionarios CASCADE;
DROP FUNCTION IF EXISTS acciones_pendientes_control();
