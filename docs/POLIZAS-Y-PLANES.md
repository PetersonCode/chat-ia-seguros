# Planes por compañía y consultas de pólizas

## Organización

Compañía → plan de cobertura → póliza del cliente → vehículo.

En **Compañías**, un aprobador carga una vez cada plan: nombre comercial, qué cubre, exclusiones, límites de referencia y teléfono de asistencia. Ejemplo ficticio: «Compañía de prueba → Terceros completo». No se deducen coberturas por el nombre «básica», «total» o por la marca del vehículo.

En **Pólizas**, se busca por cliente, número, patente o compañía y se abre **Ver / cargar cobertura**. Se elige un plan de esa compañía; los campos se completan para revisarlos y, si hace falta, ajustar límites, franquicia o excepciones de ese contrato. Guardar crea una copia de las condiciones confirmadas para esa póliza. También se pueden cargar condiciones particulares sin plan.

No hay que volver a escribir la descripción por cada auto o moto. Sí hay que **elegir y confirmar el plan correcto de cada contrato**; una coincidencia de compañía o de nombre comercial no alcanza para asignarlo automáticamente. Los datos del vehículo, vigencia, prima y suma asegurada continúan en la ficha. El importe mensual de un alta por chat sigue ingresándolo el humano al aprobarla.

Editar un plan crea una versión nueva y **no cambia las pólizas ya confirmadas**. Para actualizar un contrato, se vuelve a elegir expresamente la versión actual y se guardan sus particularidades. Desactivar un plan impide asignarlo a nuevos contratos, sin quitar condiciones a contratos existentes. Si la compañía de una póliza cambia y su plan anterior ya no corresponde, se bloquean esas condiciones hasta revisarlas.

## Cómo responde el bot

1. Reconoce al cliente por el WhatsApp asociado en la cartera; no pide una validación manual de identidad.
2. Consulta solo sus pólizas automotor vigentes. Las motos se registran con tipo `automotor` y clase de vehículo `moto`.
3. Si tiene varias, pide número, vehículo o patente; admite los formatos de patente de autos y motos.
4. Lee la copia confirmada de las condiciones de la póliza seleccionada. Para consultas particulares usa conceptos y sinónimos controlados, y exige respaldo de todos los temas específicos preguntados: un pasaje sobre cristales no responde inundación. Un resumen de un único documento vinculado admite descripciones breves sin palabras clave obligatorias. La biblioteca general conserva la búsqueda semántica local existente; no se usa su parecido como prueba suficiente de un contrato particular.
5. Responde con un extracto respaldado; conserva las exclusiones, límites y fuente. El teléfono específico de asistencia, cuando fue cargado, reemplaza la plantilla general; no se afirma un horario no informado.
6. Si falta respaldo, explica qué falta y deriva. Si ocurrió un siniestro, deriva aunque exista documentación. Un chat tomado por un asesor no contesta automáticamente hasta devolverlo al bot.

Ejemplos probados sin modelo generativo ni API paga: «qué cubre mi póliza», «qué póliza tengo y qué cubre», «mi seguro incluye daños por pedrisco» con exclusión de granizo, y «necesito el número de la grúa».

La batería específica incluye 60 preguntas independientes con distintas formulaciones, temas ausentes, asistencia y hechos ocurridos (`api/tests/test_parafrasis_poliza.py`). Se controla tanto responder lo informado como negarse a inventar lo ausente. No se equiparan automáticamente términos como robo, hurto y sustracción. Estas pruebas no garantizan comprender cualquier frase ni todos los errores de escritura posibles.

No es un modelo entrenado nuevamente por cada carga. Guardar deja una fuente consultable dentro de la misma transacción: no hay un tiempo de aprendizaje ni una aprobación documental separada. El aprobador que guarda confirma esos datos; se registra auditoría y las versiones anteriores se conservan. El bot no certifica un siniestro, emite una póliza ni decide indemnizaciones.

## Documentación anterior

La carga de conocimiento se realiza en **Compañías → planes** y en las condiciones particulares de **Pólizas**. La ruta antigua `/panel/documentos/` redirige a Compañías para evitar un segundo circuito de carga. Se conservan internamente los documentos, estados y vínculos existentes como respaldo para el bot y las pólizas históricas; no se eliminan contratos ni sus fuentes.

La ficha del cliente incluye **Condiciones que puede leer el bot**, con las condiciones confirmadas del contrato y un enlace a Pólizas para revisarlas; se retiró el selector documental anterior para evitar vincular por error condiciones de otro contrato. Tener un documento aprobado no lo convierte automáticamente en condiciones de todos los contratos de la compañía.

## Actualización histórica desde main e8b1b46

Para la revisión del 5/11/2026 se requiere llegar hasta SQL 32. Ver [arranque de esta entrega](ARRANQUE-REVISION-20261105.md); los pasos siguientes describen únicamente la incorporación histórica de SQL 26.

Respaldar la base. Aplicar `SDD/sql/26_condiciones_en_poliza.sql` a la base de la aplicación **antes** de levantar el código nuevo y reiniciar web/worker. Es aditivo e idempotente; no vuelve a cargar catálogos ni borra contratos. No ejecutar SQL 00 ni seeds sobre una base existente.

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\26_condiciones_en_poliza.sql
python manage.py check
python manage.py test --noinput
npm test
```

Adaptar la conexión al despliegue real; las credenciales no están en esta guía. Reiniciar tanto web como worker con la misma versión. Los estáticos llevan un token nuevo para evitar mezclar pantallas viejas con APIs nuevas.

Para verificar: crear un plan ficticio en Compañías, aplicarlo a una póliza de prueba en Pólizas, consultar desde su WhatsApp asociado y revisar la conversación en modo bot. Probar también dos vehículos, una exclusión, un dato ausente y un siniestro. Usar simulación durante las pruebas; la validación local no demuestra que el servidor publicado esté actualizado.

## Correcciones de integración

- Pedir un precio/cotización ya no inicia accidentalmente el alta de póliza; se conserva el embudo P5 del main recibido.
- Una consulta explícita de cobertura puede responderse durante una cotización sin consumirla como datos del vehículo.
- Buscar interesados funciona también con mayúsculas acentuadas; se normaliza la búsqueda en PostgreSQL sin depender de su locale.
- Los motivos seguros de derivación llegan al cliente; no se descartan por el cambio a modo humano. Se mantiene la lista de avisos permitidos, sin habilitar respuestas automáticas arbitrarias durante la atención humana.
- No se usa información de pólizas de otro titular ni documentos generales como prueba de un contrato particular.
