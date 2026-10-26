# Consulta documental local

## Alcance

La pantalla `/panel/documentos/` busca en fuentes generales que un funcionario
con permiso de aprobación cargó y aprobó. Esa misma recuperación se consulta
en el bot para preguntas clasificadas como cobertura/documentación, pero no se
envía el contenido al LLM ni se generan respuestas libres. No es entrenamiento
ni un servicio semántico.

La versión corregida agrega la administración en esa misma pantalla: carga de
texto como borrador, listado paginado por estado, lectura del contenido,
aprobación y retiro. Los operadores ven únicamente fuentes aprobadas; el
servidor también restringe las escrituras. `cargar_demo_mvp2` puede agregar
una fuente académica ficticia, identificada como tal, en desarrollo.

El control de salida recibe el identificador del fragmento y comprueba que
siga aprobado. Solo su cita exacta respalda importes, fechas y cláusulas;
las afirmaciones agregadas fuera de ella no heredan esa evidencia. Los
controles de identidad, datos ajenos y URLs siguen evaluando todo el mensaje.

Cada fuente guarda título, versión, referencia, estado y responsables/fechas de
creación, aprobación y retiro. El flujo es unidireccional:

1. Un aprobador carga título, versión, referencia y contenido; la fuente queda
   como `borrador` y no participa de búsquedas.
2. Un aprobador la pasa a `aprobado`; quedan registradas persona y hora.
3. Un aprobador puede retirarla; `retirado` queda excluido de nuevas búsquedas.
   Para publicar una corrección se crea otra versión.

La tabla `documentos_generales` no tiene relación con clientes, pólizas,
conversaciones ni adjuntos. Solo admite fuentes generales; no se deben copiar
historias clínicas, denuncias, identificadores ni documentación privada a esta
biblioteca. El contenido es texto que se incorpora manualmente desde una fuente
autorizada. El sistema registra quién lo carga y quién lo aprueba, pero la
autorización material del contenido debe verificarse por el equipo antes de
aprobarlo.
La biblioteca inicia vacía: cargar y aprobar al menos una fuente autorizada es
un paso operativo previo a obtener resultados.

## Recuperación y abstención

La implementación es **recuperación lexical por palabras**, local y exacta
después de normalizar mayúsculas y acentos. Ignora un conjunto pequeño de
palabras funcionales en español y puntúa cada fragmento por la proporción de
términos significativos distintos de la consulta que aparecen en él. Requiere
al menos la mitad de los términos (redondeada hacia arriba); una consulta con
un solo término significativo requiere que aparezca ese término. Devuelve hasta
cinco fragmentos mejor puntuados con título, versión y referencia. No calcula
vectores, no usa embeddings ni búsqueda semántica y no redacta respuestas.

El bot solo cita el pasaje recuperado como información general e identifica
título, versión y referencia. Siempre aclara que no confirma la cobertura o
condición de la póliza particular. La existencia de un pasaje coincidente no
se interpreta como prueba de que una cobertura aplique a la cuenta del cliente.
Saldo y vencimiento siguen consultándose exclusivamente desde la cuenta
verificada; no consultan ni se infieren de esta biblioteca.

Si ningún fragmento de una fuente aprobada alcanza ese umbral, la API devuelve
`respaldo_suficiente=false`, una explicación de abstención y una lista vacía.
En el bot, esto conserva la derivación normal a un asesor sin inventar una
respuesta. Las fuentes retiradas se excluyen en cada consulta posterior. La
selección lexical puede no encontrar sinónimos o formulaciones equivalentes;
el personal debe leer el pasaje y verificar que corresponda a la consulta.

No se agrega tarifador, cálculo comercial ni proveedor pago. Para usar el
esquema en una base nueva, aplicar `09_documentos_generales.sql` después de
`08_adjuntos_siniestros.sql`, siguiendo el orden del [README](../README.md).

## Pruebas

`negocio.tests.test_documentos` verifica normalización y fragmentación de forma
aislada. `negocio.tests.test_bot.ConsultaDocumentalBotTests` cubre recuperación
aprobada, fuente irrelevante, retiro, consulta de documentación, pausa humana y
separación del saldo. `api.tests.test_documentos` cubre el ciclo de
aprobación/retiro, la exclusión de borradores y retirados, citas de fuente y
abstención. Las pruebas de integración requieren PostgreSQL y la aplicación del
esquema de prueba.
