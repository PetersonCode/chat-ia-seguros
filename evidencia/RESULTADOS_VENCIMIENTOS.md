# Vencimientos y recordatorios · 4/11/2026

- Suite Django completa: **645 pruebas aprobadas**, incluyendo 20 nuevas del incremento (645 = 625 anteriores + 20).
- Frontend: **42 pruebas aprobadas** (40 anteriores + 2 de plazos/enlaces).
- `manage.py check`: sin observaciones. `git diff --check`: sin errores.
- Bandit sobre los tres módulos Python nuevos: sin hallazgos ni errores de análisis.
- No se cambió CSS global ni logo. Se versionaron las URLs de estáticos para que el menú nuevo aparezca sin depender de cachés anteriores.

Se probaron el orden de vencimientos, filtros y paginación, saldo por póliza, cuotas vencidas primero desde la fecha más antigua, distinción entre deuda vencida y cuotas futuras, pago que elimina la condición de atraso, cuota que vence hoy, cuenta inactiva, número de otro cliente, varios números, lectura auditada y consulta del listado sin N+1. También vista previa sin envío, recálculo posterior a un pago, envío simulado en conversación sin tomar control, doble clic idempotente, ventana cerrada, registro manual, fallo de transporte conservado como fallo y SQL 23 reaplicado sin perder registros.

En navegador se verificó login, identidad visual, listado y diálogo. Se envió **solo de forma simulada** un aviso de POL-90202, con vencimiento a siete días y saldo $25.000. Reabrir su diálogo mostró el envío y deshabilitó un duplicado ese día. Tras el ajuste de prioridad, Lucía aparece primero por una cuota del 15/10/2026, aunque su póliza vence después: saldo total $96.000, de los cuales $48.000 vencidos. Ese desglose también aparece en su mensaje preparado. La evidencia de base está en `flujo-vencimientos.json`.

Capturas actuales:

- `vencimientos-pantalla.png`: orden final con pagos atrasados primero y estilo del panel.
- `vencimientos-mensaje.png`: ejemplo de siete días preparado para el envío simulado.
- `vencimientos-atrasos.png`: mensaje que distingue saldo total y deuda vencida.

Los logs completos son `vencimientos-django.txt` y `vencimientos-javascript.txt`; el análisis estático está en `vencimientos-bandit.json`. Son verificaciones locales con datos ficticios, no un envío real a Meta ni una prueba de carga. Los resultados de hardening anteriores se conservan en RESULTADOS.md como antecedente de esa entrega.

Para actualizar desde el PR anterior aplicar **SQL 23**, ejecutar `migrate` y reiniciar web/worker. El motor programado completo de P2, las renovaciones de P3 y los siniestros ampliados de P7 siguen pendientes; esta entrega es el listado y contacto iniciado por el asesor que pidió el usuario.
