# Integración del último ZIP del equipo

Se compararon los archivos de los ZIP `(1)` y `(2)` del 4/11/2026, y se realizó una fusión de tres versiones: base original, trabajo de hardening y cambios del compañero. Se resolvieron manualmente los cruces en el runner, la bandeja y el orquestador; no se sustituyó el proyecto por una copia anterior.

## Cambios del compañero incorporados

- Agradecimientos y despedidas con sus tipos de consulta, plantillas y pruebas. No generan trámites ni derivaciones por sí mismos.
- Clasificación `ajeno`, instrucciones del modelo y respuesta controlada para pedidos fuera del servicio. Se agregó respaldo por reglas para ejemplos claros sin API generativa; lo ambiguo sigue pidiendo aclaración.
- Descarte de alertas por un aprobador: conserva el historial, firma la resolución y rechaza la operación si quedan respuestas retenidas. Descartar la alerta de insistencia también desbloquea ese número, con confirmación explícita en el panel.
- Borrado de conversaciones por un aprobador desde bandeja y detalle, con confirmación y bloqueo si hay acciones administrativas, siniestros o fotografías dependientes. Se integró la eliminación del contexto temporal para evitar errores de integridad. La auditoría de seguridad se conserva aunque se borre el chat.
- Navegación a Documentos, sin duplicar el enlace ya restaurado junto con Siniestros y Reportes.
- Fábricas, pruebas, contratos y planes de trabajo actualizados.

Los archivos Docker se mantienen versionables en la entrega porque forman parte de su operación. Los secretos, adjuntos, entornos y modelos descargados siguen excluidos. El segundo ZIP proponía ignorar Dockerfile/compose; esa exclusión no se aplicó para que el repositorio completo conserve su configuración revisada.

## Scripts SQL sin colisiones

- `01` a `11`: esquema anterior.
- `12_tipos_de_charla.sql`: incremento del compañero; permite volver a ejecutarlo.
- `13_vehiculos_companias.sql` (P1): tablas `companias` y `vehiculos` y tres columnas nuevas en `polizas`; aditivo e idempotente, se puede repetir. Aplicarlo a la base real **antes** de levantar esta versión, porque los modelos ya leen esas columnas.
- `17_interesados.sql` (P5): tablas `interesados`, `interesado_historial` y `cotizaciones`; aditivo e idempotente. Aplicarlo **antes** de levantar esta versión (los modelos nuevos leen esas tablas). Si el motor de avisos (P2) ya existe, también suma sus dos tipos de seguimiento.
- `14` a `16` y `18` a `21`: reservas de los planes P2–P4 y P6–P9, sin implementación.
- `29_rol_administrador.sql`: rol `administrador` (usuario de pruebas con ELIMINACION TOTAL). Aditivo.
- `30_nivel_en_planes.sql`: columna `nivel` (básica/intermedia/total) en `planes_cobertura`. La póliza toma el nivel de su plan: cobertura y plan dejan de cargarse por separado. Nullable: los planes existentes se completan al editarlos en Compañías. Aditivo e idempotente.
- `23_recordatorios_polizas.sql`: pantalla de vencimientos y registro de avisos manuales desde el panel. Se aplica después de 22. No implementa el motor P2/P3 completo.
- `22_seguridad_y_coberturas.sql`: incremento de esta revisión, aditivo y transaccional. Aplicarlo una sola vez.

Si ya estaba aplicado el 12 del compañero, no hay que rehacer los datos: agregar 13 y 22 y ejecutar `migrate`. Si la base solo llegaba a 11, agregar 12 y 22. Nunca utilizar `00_drop_all.sql` para actualizar una base con datos a conservar.

## Lo que son planes y aún no está desarrollado

`SDD/paquetes/` contiene las especificaciones P1–P9: vehículos/compañías, avisos, renovaciones, mora, embudo comercial, credenciales, ampliación de siniestros, tareas/reportes y fidelización. Se conservaron íntegramente como planificación. Están implementados P1 (vehículos y compañías, SQL 13) y P5 (embudo de interesados y cotizaciones, SQL 17; sin el seguimiento automático ni el comparador de renovaciones, que dependen de P2 y P3). De P2–P4 y P6–P9 no existen sus incrementos SQL ni los módulos descritos. No presentarlos como funcionalidades implementadas.

El verificador SDD del compañero cuenta también esos criterios futuros; sus pendientes no son el resultado de la suite funcional del MVP actual. README, `docs/` y la evidencia indican qué se implementó y probó realmente.

## Entrega para GitHub

Copiar el contenido del proyecto final en una copia actualizada del repositorio del equipo, conservando la carpeta `.git` de ese repositorio. Revisar `git status` y el diff, ejecutar las pruebas, crear el commit en su rama y usar el proceso de integración del equipo para `main`. Este ZIP no trae `.git`, `.env`, bases de datos ni credenciales. La publicación solicitada usa la rama `integrar-backend` y un pull request hacia `main`; no modifica el sitio publicado.
