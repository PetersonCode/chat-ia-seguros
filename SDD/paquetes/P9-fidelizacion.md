# P9 · Fidelización

**Branch:** `paquete-p9-fidelizacion` · **SQL:** `SDD/sql/21_fidelizacion.sql` · **Depende de:** P2 (avisos), P4 (`nivel_de_mora`), P5 (interesados, para referidos) y P7 (siniestros cerrados, para la encuesta).
**Por qué (Roberto):** conseguir un cliente nuevo cuesta mucho más que conservar uno. Quiero saludar en el cumpleaños, premiar al que nos trae gente, ofrecerle otro seguro al que solo tiene el auto, y saber si quedó contento después de un siniestro, **antes** de que se vaya.

## 1. Esquema (`21_fidelizacion.sql`)
```
clientes             + fecha_nacimiento date null, + referido_por_id → clientes null
interesados          + referido_por_cliente_id → clientes null
beneficios_referido  id, referente_id → clientes, referido_id → clientes UNIQUE (un referido da un solo beneficio),
                     estado (pendiente, otorgado, anulado) default pendiente, detalle null,
                     resuelto_por_id → funcionarios null, resuelto_en null, motivo null, creado_en
encuestas            id, cliente_id → clientes, contacto_id → contactos_whatsapp, siniestro_id → siniestros null,
                     estado (enviada, respondida, vencida) default enviada, puntaje smallint null (1 a 5),
                     comentario null, enviada_en, respondida_en null
                     CHECK: respondida exige puntaje y respondida_en. UNIQUE (siniestro_id) cuando no es nulo.
tipos_aviso          + cumpleanos (prioridad 5), venta_cruzada (5), encuesta_siniestro (4)
tipos_consulta       + ('respuesta_encuesta', 'Respuesta a una encuesta', 'bot_responde')
```

## 2. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-46 | Dados `Encuesta`, `BeneficioReferido` y los campos nuevos (`Cliente.fecha_nacimiento`, `Cliente.referido_por`, `Interesado.referido_por_cliente`), `EstadoEncuesta` y `EstadoBeneficio` coincidentes con los `CHECK` (AC-T4-07), `crear_catalogos()` con el tipo `respuesta_encuesta`, el SQL 21 en `test_runner.py` (aplicable dos veces) y las fábricas `crear_encuesta` y `crear_beneficio`, entonces todo se crea sin error; un puntaje fuera de 1 a 5 o una encuesta `respondida` sin puntaje es rechazada por la base. |
| AC-T4-47 | Dadas las consultas nuevas, entonces `cumpleanos_del(fecha)` devuelve los clientes activos que cumplen ese día y mes (el 29/02 se trata como 28/02 en años no bisiestos); `clientes_para_venta_cruzada(hoy)` devuelve los clientes activos con al menos una póliza vigente, sin póliza (de ningún estado vigente) de algún tipo de seguro del catálogo, con la lista `tipos_faltantes` en el orden `hogar, moto, vida, comercio`; `encuesta_pendiente_de(contacto_id)` (la `enviada` más reciente, o `None`); `listar_beneficios(estado=None)`; y `resumen_satisfaccion(desde, hasta)` → `{respondidas, promedio, por_puntaje: {1..5}}` (promedio `None` si no hay). |

## 3. Etapa B · Lógica (T3)
Archivos: `negocio/clientes.py`, `negocio/interesados.py` (solo el enganche de AC-T3-106), `negocio/fidelizacion.py` (nuevo), `negocio/avisos.py`, `negocio/bot/`.

Textos de aviso nuevos (se suman a `TEXTOS_AVISO`; son texto libre, sin plantillas de Meta):
| Tipo | Texto |
|---|---|
| `cumpleanos` | ¡Feliz cumpleaños, {nombre}! 🎂 De parte de todo el equipo de Seguros Castaño, que tengas un gran día. |
| `venta_cruzada` | Hola {nombre}, ya cuidamos tu {tipo_actual}. ¿Sabías que también podemos asegurar tu {tipo_ofrecido}? Si querés saber cuánto sale, escribinos «quiero cotizar». |
| `encuesta_siniestro` | Hola {nombre}, esperamos que ya esté resuelto tu siniestro {numero_siniestro}. ¿Cómo calificás nuestra atención del 1 (mala) al 5 (excelente)? Respondé solo con el número. |

`{tipo_actual}` es el nombre del tipo de seguro de su póliza vigente más antigua; `{tipo_ofrecido}`, el primero de `tipos_faltantes`.
| ID | Criterio |
|---|---|
| AC-T3-103 | Dados `alta_cliente` y `modificar_cliente` (AC-T3-47/48) con `fecha_nacimiento` opcional (`AAAA-MM-DD` o `dd/mm/aaaa`), entonces se guarda; una fecha futura o anterior a 1900 es `DatosInvalidos`; en `modificar_cliente` el valor vacío la borra y la ausente la deja igual. **Enmienda a AC-T3-47/48.** |
| AC-T3-104 | Dado el generador `cumpleanos` (registrado en P2), cuando se ejecuta para `hoy`, entonces programa un aviso `cumpleanos` para cada contacto de cada cliente de `cumpleanos_del(hoy)` con `referencia = "cumple:<cliente_id>:<año>"`; el texto no incluye edad ni otros datos; no programa para clientes inactivos. |
| AC-T3-105 | Dado el generador `venta_cruzada` (registrado en P2), cuando se ejecuta, entonces programa un aviso por cliente de `clientes_para_venta_cruzada(hoy)` ofreciendo el primer tipo faltante, con `referencia = "cruzada:<cliente_id>:<tipo>"`, **a lo sumo uno cada 90 días por cliente** y **nunca el mismo tipo dos veces dentro de los 180 días**; excluye clientes cuyo contacto no acepta avisos, con `nivel_de_mora` distinto de `"al_dia"` (P4) o con un siniestro `denunciado` o `en_evaluacion`. Si el cliente contesta «quiero cotizar», sigue el flujo de AC-T3-85 (P5) con `tipo_seguro` precargado en los datos del interesado. |
| AC-T3-106 | Dado `crear_interesado` (P5) con origen `recomendacion` y `referido_por_cliente_id` de un cliente activo, y luego `convertir_en_cliente`, entonces el cliente nuevo queda con `referido_por` y se crea un `BeneficioReferido` `pendiente` (único por referido; repetir no duplica); un referente inexistente o inactivo es `DatosInvalidos`; un cliente que se refiere a sí mismo es `DatosInvalidos`. Dados `otorgar_beneficio(id, funcionario_id, detalle)` y `anular_beneficio(id, funcionario_id, motivo)`, ambos de aprobador, entonces el primero exige `detalle` de 3 o más caracteres, el segundo `motivo` de 5 o más, ambos solo desde `pendiente` (si no, `EstadoInvalido`), con quién y cuándo. |
| AC-T3-107 | Dado el generador `encuestas` (registrado en P2), cuando se ejecuta, entonces para cada siniestro que pasó a `cerrado` hace 2 días o más y todavía no tiene encuesta, crea la `Encuesta` `enviada` y programa un aviso `encuesta_siniestro` (`referencia = "encuesta:<siniestro_id>"`); una encuesta `enviada` con más de 7 días pasa a `vencida`; no manda encuestas a clientes que ya recibieron una en los últimos 30 días. |
| AC-T3-108 | Dado un mensaje entrante cuyo contacto tiene una `encuesta_pendiente_de` y cuyo texto, sin espacios ni puntuación, es un número del 1 al 5 (o «un 4», «5 estrellas», «cuatro»), entonces **antes de clasificar** el bot registra puntaje y `respondida_en`, responde `GRACIAS_ENCUESTA` («¡Gracias por tu opinión!») y no crea otra consulta; con puntaje 1 o 2 además deriva a Roberto (`urgente`) con el siniestro en el motivo; un número fuera de rango, o una encuesta `vencida`, se procesa como un mensaje común; el texto libre posterior no se toma como respuesta. |

## 4. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-45 | Dados `GET /api/encuestas/resumen/?desde=&hasta=` (`resumen_satisfaccion`; fechas ausentes = últimos 90 días) y `GET /api/encuestas/?puntaje_max=2&pagina=` (respondidas, más nuevas primero, con cliente, siniestro y comentario), entonces cualquier funcionario los ve; fechas mal formadas → 400; la ruta `/panel/satisfaccion/` está en la lista blanca. |
| AC-T2-46 | Dados `GET /api/beneficios/?estado=`, `POST /api/beneficios/{id}/otorgar/` `{detalle}` y `POST …/anular/` `{motivo}` (aprobador), entonces llaman a las funciones de AC-T3-106; `cliente_detalle` suma `fecha_nacimiento`, `referido_por` `{id, nombre}` y sus `beneficios`. |
| AC-T2-47 | Dados `PATCH /api/clientes/{id}/` (acepta `fecha_nacimiento`) y `POST /api/interesados/` (acepta `referido_por_cliente_id`), entonces pasan los datos a `modificar_cliente` y `crear_interesado` y los errores siguen AC-T2-03. |

## 5. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-49 | Dado `lib/encuestas.js`, entonces `promedio(puntajes)` devuelve el promedio con un decimal (`4.3`) o `null` si no hay datos, `clasePuntaje(p)` → `fila-verde` (4 o 5), `fila-amarillo` (3), `fila-rojo` (1 o 2), y `etiquetaPuntaje(p)` → «Excelente», «Buena», «Regular», «Mala», «Muy mala» (fuera de 1 a 5 → «—»), sin depender solo del color. |
| AC-T1-50 | **(QA)** Dada `/panel/satisfaccion/`, entonces muestra el promedio, la cantidad de respuestas, el reparto por puntaje y la lista de respuestas bajas (1 o 2) con el comentario y un enlace al cliente y al siniestro. |
| AC-T1-51 | **(QA)** Dada la ficha de cliente, entonces se puede cargar y borrar la fecha de nacimiento (aprobadores), se ve «Referido por» con enlace y la lista de beneficios con «Otorgar» (detalle obligatorio) y «Anular» (motivo obligatorio); dado el formulario de nuevo interesado, el origen «Recomendación» muestra un campo para elegir al cliente que lo recomendó (búsqueda con `debounce`). |

## 6. Terminado cuando
Los 14 AC con prueba, contratos actualizados, SQL 21 aplicado y a mano: cumpleaños (simulando la fecha), un referido convertido que genera su beneficio, un siniestro cerrado que dispara la encuesta, responder «5» y «2» con `simular_whatsapp` (el 2 deriva a Roberto). `SDD/entregas/P9.md`.
