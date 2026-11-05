-- Después de 36. Lo que se le informa al cliente como saldo es lo que tiene
-- que pagar ahora: las cuotas vencidas más la próxima cuota (todas las que
-- vencen ese mismo día). Las cuotas de los meses siguientes no son deuda
-- todavía. El total de cuotas impagas del contrato queda en `saldo_total`.
-- La fecha es la de Buenos Aires, igual que `timezone.localdate()` en Django.
BEGIN;
CREATE OR REPLACE VIEW v_polizas_resumen AS
SELECT p.id AS poliza_id,
       p.numero_poliza,
       cl.apellido || ', ' || cl.nombre AS cliente,
       cl.dni,
       ts.nombre AS tipo_seguro,
       p.cobertura,
       p.estado,
       p.fecha_vencimiento,
       COALESCE(sum(q.importe) FILTER (
           WHERE q.estado IN ('pendiente', 'vencida')
             AND q.vencimiento <= COALESCE(
                 (SELECT min(q2.vencimiento) FROM cuotas q2
                   WHERE q2.poliza_id = p.id
                     AND q2.estado IN ('pendiente', 'vencida')
                     AND q2.vencimiento >= (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date),
                 (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date - 1)
       ), 0) AS saldo_pendiente,
       min(q.vencimiento) FILTER (WHERE q.estado IN ('pendiente', 'vencida')) AS proximo_vencimiento_pago,
       COALESCE(sum(q.importe) FILTER (WHERE q.estado IN ('pendiente', 'vencida')), 0) AS saldo_total
FROM polizas p
JOIN clientes cl     ON cl.id = p.cliente_id
JOIN tipos_seguro ts ON ts.id = p.tipo_seguro_id
LEFT JOIN cuotas q   ON q.poliza_id = p.id
GROUP BY p.id, cl.id, ts.id;
COMMIT;
