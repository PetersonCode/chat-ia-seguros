# Vehículos, compañías y comisiones

## Qué se integró

Se partió del `main` del 4/11/2026, commit `11d6b19` (PR #5). Ya contenía el P1 de vehículos y compañías de Daniel y nuestro módulo de vencimientos, hardening y bot. Antes de modificarlo pasaron **704 pruebas Django y 51 JavaScript**. Se conserva esa implementación, sus documentos y su atribución.

P1 ya aportaba patente, marca, modelo, año, uso, chasis, valor asegurado, compañía emisora y porcentaje de comisión guardado en cada póliza. Esta ampliación completa:

- Clase de vehículo opcional: auto, camioneta, utilitario, moto o camión. Los históricos quedan «Sin especificar»; no se adivina que una Hilux es camioneta.
- Búsqueda por patente normalizada, chasis, marca, modelo y nombre/apellido, con palabras combinadas y sin exigir tildes. Ejemplos: `la camioneta de Perez`, `Hilux Pérez`, `AB-123-CD`, `VIN1234`. La búsqueda une datos de un mismo vehículo con su titular; no combina la marca de un auto con el modelo de otro.
- Chasis opcional normalizado a mayúsculas, sin espacios ni guiones. Se evita cargarlo nuevamente bajo otra patente. No se exige un VIN de 17 caracteres para permitir vehículos antiguos y datos ficticios.
- Prevención de pólizas superpuestas para el mismo vehículo, aunque cambie la compañía. Se valida en negocio y en PostgreSQL, también frente a dos altas simultáneas. Las fechas de vigencia son **inclusivas**: si una termina el 31/12, la renovación comienza el 1/1. Las pólizas dadas de baja no bloquean su reemplazo.
- Bot: identifica la patente o el vehículo entre las pólizas del cliente reconocido, ofrece descripciones útiles y no repite la patente en el listado. Conserva la consulta de fuentes aprobadas y la derivación de siniestros.
- Vencimientos usa los datos actuales del vehículo y muestra la compañía. Conserva la prioridad de pagos atrasados y el funcionamiento de recordatorios.
- Ficha: comisión mensual estimada en pesos y botón **Completar vehículo y compañía** para pólizas existentes. Las cuotas, fechas, prima y saldo se conservan.
- Reportes: totales y agrupaciones por compañía y cliente, filtro de fechas y exportación CSV protegida contra fórmulas.
- Comando de diagnóstico de solo lectura: `python manage.py auditar_cartera`.

Se reutilizan colores, logo, CSS y componentes del panel. Se versionaron las URLs de estáticos para evitar que el navegador mezcle versiones.

## Actualizar una base existente

Respaldar la base y detener temporalmente web/worker para actualizar ambos junto con el esquema. Usar los datos de conexión propios. **No ejecutar SQL 00 ni volver a cargar el seed 02 sobre una base existente.**

- Si ya tiene P1, seguridad y recordatorios (13, 22 y 23), aplicar `24_cartera_vehiculos.sql` y luego `25_altas_por_chat.sql`, incluido en esta entrega.
- Si viene de nuestra versión anterior a P1, aplicar primero `13_vehiculos_companias.sql` y luego `24_cartera_vehiculos.sql` y `25_altas_por_chat.sql`; conservar 22 y 23 ya aplicados.
- Para una instalación nueva, seguir el README: 01 a 13 y luego 22, 23, 24 y 25. Los modelos de negocio son `managed=False`: `migrate` por sí solo no agrega estas columnas.

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\24_cartera_vehiculos.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\25_altas_por_chat.sql
python manage.py migrate
python manage.py check
python manage.py auditar_cartera
```

SQL 24 es aditivo e idempotente. No requiere extensiones adicionales. No borra ni intenta interpretar el texto histórico de «bien asegurado». Sus triggers controlan las nuevas escrituras; las superposiciones antiguas deben revisarse con el diagnóstico, sin borrar historial automáticamente. La concurrencia se verificó con PostgreSQL 17 y su aislamiento READ COMMITTED, el usado por Django. Referencias técnicas: [snapshots de funciones VOLATILE](https://www.postgresql.org/docs/17/xfunc-volatility.html) y [bloqueos de filas](https://www.postgresql.org/docs/17/explicit-locking.html).

## Completar los datos desde el panel

1. **Compañías:** registrar el nombre real de la aseguradora y su porcentaje de referencia.
2. **Clientes → ficha → Agregar vehículo:** completar patente, marca, modelo, año, clase, uso, chasis y valor. Chasis y valor siguen siendo opcionales; desconocido no significa cero.
3. **Pólizas:** al emitir, elegir el vehículo del cliente y la compañía. En una póliza antigua usar **Completar vehículo y compañía**. El porcentaje se toma de la compañía o se puede indicar uno particular, incluido 0 %.
4. **Clientes:** buscar por patente, chasis o combinación de vehículo y apellido. **Vencimientos** ofrece también esa búsqueda y mantiene primero los pagos atrasados.
5. **Reportes:** seleccionar período y pulsar Generar. Ver comisiones por compañía y cliente; el nombre del cliente abre su ficha.

Cambiar el porcentaje general de una compañía **no** modifica lo guardado en pólizas emitidas. Corregir explícitamente la compañía o comisión de una póliza sí recalcula sus reportes, incluidos períodos anteriores; el formulario lo advierte antes de guardar. No se implementó un libro de liquidaciones cerrado por mes.

## Fórmulas y límites

- **Comisión mensual estimada en la ficha:** prima mensual × porcentaje guardado / 100.
- **Estimada en un período:** suma de importe de cada cuota cuyo vencimiento está dentro del período × porcentaje de su póliza / 100. Excluye pólizas dadas de baja actualmente. Incluye cuotas pagadas y pendientes, no solo deuda.
- **Sobre cobros en un período:** suma de los movimientos `Pago` cuya fecha de pago está dentro del período × porcentaje guardado en la póliza / 100. Incluye pagos registrados incluso si después se dio de baja la póliza. No se infiere un cobro a partir de una cuota marcada pagada sin movimiento `Pago`.
- Redondeo a dos decimales, mitad hacia arriba, por cuota o pago. ARS; no hay conversión de moneda.
- Sin porcentaje se muestra un aviso y no se inventa una comisión. Un 0 % explícito es un dato conocido. Los importes representan comisión bruta calculada; no ganancia neta, acreditación de la aseguradora, impuestos ni ajuste por anulaciones/devoluciones.

Los históricos sin vínculo a vehículo siguen disponibles para no romper la cartera anterior. **La prevención de superposición por vehículo requiere ese vínculo**; por eso el diagnóstico y el botón para completarlo. Una descripción libre no permite identificar un vehículo de forma fiable.

## Permisos y contratos nuevos

Se respetan los permisos de P1: leer vehículos y compañías requiere sesión de funcionario; administrar y ver comisiones requiere `puede_aprobar`. Diego sigue sin recibir porcentajes ni importes de comisión, y obtiene 403 al intentar consultar el reporte, incluido CSV. Las escrituras y consultas de reportes quedan en la auditoría HTTP existente, sin guardar cuerpos ni credenciales. No se agregaron verificaciones manuales de identidad ni pasos de aprobación extra.

- `PATCH /api/polizas/{id}/cartera/`: `vehiculo_id`, `compania_id`, `comision_pct`, todos opcionales. Ausente conserva; vínculo `null` lo quita; comisión vacía recupera la de la compañía o queda sin dato. Verifica titularidad y superposición. No admite modificar cuotas ni fechas.
- `GET /api/reportes/comisiones/?desde=AAAA-MM-DD&hasta=AAAA-MM-DD[&formato=csv]`: totales, `por_compania`, `por_cliente`, bases y número de pólizas sin porcentaje. Fechas obligatorias, inclusivas y validadas.
- Vehículos incluye `clase`; pólizas incluye `comision_mensual_estimada` (null cuando el usuario no tiene permiso o no hay porcentaje).

## Recorrido breve para exponer

Con datos ficticios, cargar a Pérez, una Toyota Hilux clase Camioneta, una aseguradora al 12,5 % y una prima mensual de $48.000. Buscar «la camioneta de Perez»: abre la ficha correcta. La comisión mensual estimada es $6.000. Intentar emitir otra póliza para ese vehículo en las mismas fechas: aparece el rechazo y no se generan cuotas nuevas. Al registrar un pago completo de $48.000, el reporte del período del pago calcula $6.000 sobre cobros. Terminar mostrando Vencimientos con el mismo vehículo y compañía.

La aplicación conserva modo WhatsApp simulado y búsqueda local gratuita para las pruebas. No se enviaron mensajes reales ni se modificó una base de producción durante esta integración.

## Validación del módulo de cartera — 4/11/2026

- 727 pruebas Django aprobadas; 51 pruebas JavaScript aprobadas.
- Python 3.12.14, Django 5.2.19, psycopg 3.2.10 y PostgreSQL 17.11; base de pruebas aislada creada y destruida por el runner.
- `manage.py check`, sintaxis de los JavaScript modificados y `git diff --check`, sin errores.
- SQL 24 reaplicado y probado sin pérdida del histórico. Prueba con dos conexiones y commits reales: dos pólizas simultáneas para el mismo vehículo dejan una sola registrada.
- Navegador: frase «la camioneta de Perez», patente con guiones, chasis compacto, edición de vehículo, formulario de cartera, comisión mensual en pesos, agrupaciones y enlace de exportación CSV. Vencimientos conserva saldo, atraso y preparación del recordatorio. Consola sin errores ni advertencias en las pantallas verificadas.
- Las pruebas de API comprueban también CSV sin fórmulas ejecutables, bloqueo de acceso a comisiones para operadores y ausencia de cambios parciales ante un rechazo.
- Validación realizada localmente antes de publicar esta ampliación para revisión del equipo.

La entrega completa con altas por acciones pasa **738 pruebas Django y 51 JavaScript**; ver [Altas por chat](ALTAS-POR-CHAT.md).
