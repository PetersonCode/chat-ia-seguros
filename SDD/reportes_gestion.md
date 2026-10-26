# Reportes de gestión

El endpoint `GET /api/reportes/gestion/` y la pantalla `/panel/reportes/`
requieren sesión de funcionario activo. El período se envía con `desde` y
`hasta` (`AAAA-MM-DD`), ambas inclusivas; la fecha final no puede ser anterior
a la inicial. `formato=csv` exporta los mismos agregados que entrega JSON.

## Indicadores y fechas

| Indicador | Definición | Fecha que filtra |
|---|---|---|
| Consultas | Número de filas de `consultas_bot` en el período | `fecha_hora`, interpretada en la zona horaria local configurada |
| Cerradas | Consultas cuyo estado actual es `cerrado` | `fecha_hora` de la consulta, no el día en que cambió el estado |
| Pendientes | Consultas cuyo estado actual es `abierto`, `pendiente_revision` o `derivado` | `fecha_hora` de la consulta, no `fecha_resolucion` |
| Motivos | Consultas agrupadas por código/nombre de `tipo_consulta` | `fecha_hora` de la consulta |
| Derivaciones urgentes | Filas de `derivaciones` con `prioridad=urgente`, atendidas o no | `creada_en` |
| Cobros | Cantidad y suma de movimientos existentes en `pagos` | `fecha_pago` |

Las categorías de estado son disjuntas y cubren los estados permitidos por el
esquema; por eso consultas totales = cerradas + pendientes. No se infiere
ningún pago del estado de una cuota: se cuentan solo movimientos registrados.
El importe suma los movimientos sin convertir monedas. No se calcula una tasa
de resolución ni una tasa de éxito de IA.

## Muestra para cálculo manual

El test de integración usa del 10 al 11 de mayo de 2026 e incluye cuatro
consultas (una cerrada y tres pendientes), más una consulta del día 9 que queda
afuera. Los motivos dentro del período son Saldo pendiente: 2, Saludo: 1 y
Denuncia de siniestro: 1. Hay dos derivaciones urgentes creadas dentro del
período; una urgente creada el día 9 queda afuera y una normal del día 11 no
cuenta. Hay dos cobros de $1.000,00 y $234,50; un cobro de $500,00 del día 9
queda afuera. Resultado esperado: **4 consultas, 1 cerrada, 3 pendientes,
2 derivaciones urgentes y 2 cobros por $1.234,50**.
