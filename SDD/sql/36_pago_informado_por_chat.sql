-- Después de 35. El cliente avisa por el chat que pagó y pasa la referencia del
-- comprobante: el bot deja la acción `registrar_pago` y el pago se registra
-- recién cuando un aprobador la confirma (misma regla que `registrar_pago`).
BEGIN;
ALTER TABLE acciones_pendientes DROP CONSTRAINT IF EXISTS acciones_pendientes_tipo_accion_check;
ALTER TABLE acciones_pendientes ADD CONSTRAINT acciones_pendientes_tipo_accion_check CHECK
    (tipo_accion IN ('baja_poliza','agregar_conductor','modificar_poliza','reembolso',
                    'apertura_siniestro','alta_cliente','alta_poliza','registrar_pago'));
COMMIT;
