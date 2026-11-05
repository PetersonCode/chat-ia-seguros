# Verificación local de gestión familiar — 04/11/2026

Base de trabajo: commit `3eae4fa`, ampliación del PR #8. Rama local `gestion-familiar-actual`. Verificación local previa a publicar la ampliación en integrar-backend; no se actualizó producción.

## Resultados ejecutados

- Suite completa Django: **1009 pruebas aprobadas**, PostgreSQL 17 local, base de pruebas separada. El registro de algunos errores simulados es parte de los escenarios de fallo; el resultado del runner es `OK`.
- Después de los ajustes finales de credencial y envío: **24 pruebas específicas aprobadas** de gestión diaria y fidelización.
- JavaScript: **66 pruebas aprobadas**, sin fallos ni omisiones.
- `manage.py check`: sin incidencias en la ejecución de pruebas.
- `git diff --check`: sin errores de espacios.
- SQL 27 y 28 aplicados dos veces en la base ficticia local, sin duplicar estructura ni configuración. No se ejecutó SQL 00.

## Recorridos observados en navegador

- Inicio carga renovaciones, morosos, seguimiento, tareas, avisos, reporte mensual y encuestas desde la API.
- Se creó una tarea ficticia asignada a Graciela y se verificó su aparición junto a la tarea de Diego.
- En una póliza ficticia, Renovar abre la revisión de fechas, exige la prima mensual y permite cancelar sin registrar una renovación. Las pruebas verifican el registro, los permisos y la prevención de duplicados.
- La ficha de Lucía Ejemplo muestra la nota interna, las preferencias de cumpleaños, los referidos y los enlaces de credencial.
- La descarga de credencial devuelve una imagen PNG de 1080 × 1240. Se revisó su representación y se corrigieron los caracteres acentuados con DejaVu Sans, incluida con su licencia.
- Se comprobó que el botón Menú despliega los enlaces con el ancho móvil configurado y se restableció el tamaño normal del navegador.
- Se aumentó el texto del menú lateral a 16 px, con mayor peso y contraste. El escalado de la vista previa puede suavizar el texto de la captura; no se aplican filtros de desenfoque al menú.

Las imágenes en `docs/capturas/` utilizan datos ficticios. No son pruebas de una entrega real de WhatsApp.

## Límites de esta verificación

WhatsApp estuvo en modo simulado y el proveedor LLM desactivado. No se enviaron avisos a personas, no se validó la entrega real de Meta y no se modificó irusu.com.ar. La activación de envíos automáticos permanece apagada en la demostración.

Los saludos requieren consentimiento; los automatismos dependen de que el worker esté activo y respetan horarios, ventana de atención y modo humano. Fuera de la ventana queda el contacto manual. El estado preparado no confirma entrega. Las bajas históricas ajenas a acciones y las renovaciones históricas sin vínculo explícito no se reconstruyen automáticamente en el reporte.

La credencial es informativa y no sustituye el certificado de la compañía. Su imagen limita los textos muy extensos al espacio disponible; la versión HTML conserva el texto completo.

Instalación, reglas y demostración: [GESTION-FAMILIAR.md](../docs/GESTION-FAMILIAR.md).

## Unificación visual posterior

Tema compartido incorporado exactamente una vez a las 20 páginas HTML. Se observaron en navegador Clientes, Interesados, Vencimientos, Bandeja, detalle de conversación e ingreso; se corrigieron las etiquetas blancas heredadas del login. Las 66 pruebas JavaScript volvieron a pasar. Esta ampliación visual no modifica lógica de negocio ni base de datos. Captura ficticia: `docs/capturas/tema-clientes.png`.

## Chat flotante

68 pruebas JavaScript aprobadas, incluidas validación del estado persistido y condiciones de respuesta (conversación propia, abierta, humana y ventana abierta). En navegador se abrió el chat ficticio 19 desde el interesado 1 sin abandonar su ficha, se tomó la conversación, se escribió un borrador sin enviar, se minimizó, se navegó a Compañías y se amplió: el borrador se conservó. Se comprobó la restauración después de recargar. Se limpió el borrador de prueba y se devolvió la atención al bot. No se enviaron mensajes desde esta prueba de interfaz. La API y sus restricciones no se modificaron.

Ajuste posterior del chat: se comprobó que Ver detalle completo restaura el flotante minimizado. Con datos ficticios y sin envío externo, se desplazó el historial al inicio y se insertó un mensaje local: el sondeo movió scrollTop a 1664, igual a scrollHeight 2239 menos clientHeight 575. Pasaron nuevamente las 68 pruebas JavaScript.

Bandeja por contacto: suite completa inicial 1015 pruebas Django OK. Tras ajustar el acuse del bot, cinco pruebas específicas OK (agrupación, bot sin pendientes, respuesta humana, derivaciones repetidas, cerradas y acuse de derivación). JavaScript: 68 aprobadas. En navegador se verificó vista inicial Necesitan atención, contadores por contactos y listado Todos los contactos sin duplicar el historial. Sin borrado de datos históricos.

Verificación final previa a publicación del PR: **1016 pruebas Django aprobadas** (79,369 s), 68 pruebas JavaScript aprobadas y `git diff --cached --check` sin errores.

Corrección de datos de cotización: una ejecución completa en serie terminó con 1020 pruebas Django aprobadas. JavaScript: 68 aprobadas. Se verificó en navegador la ficha compartida y la extracción exacta de Santiago. Se descartaron dos ejecuciones que interfirieron al usar simultáneamente la misma base de pruebas. El ajuste final de prefijos se verificó con la suite específica de cotización. No se enviaron WhatsApps reales.

Corrección de conversión: 37 pruebas API aprobadas, incluyendo vehículo propio idempotente y rechazo con rollback de patente ajena; 68 pruebas JavaScript aprobadas. Se recuperó en la demo el vehículo de Mateo sin emitir póliza. En navegador se verificó la cotización elegida precargada, con fechas vacías para revisión humana.

Registro directo desde cotización elegida: 1025 pruebas Django aprobadas y 68 JavaScript aprobadas. Se verificó en navegador el resumen contractual y las fechas vacías de Valentina; se canceló la revisión sin crear póliza. Las pruebas verifican selección de compañía/precio/vehículo desde la base, cambio a Emitida, rechazo de duplicados, permisos y fechas faltantes.
