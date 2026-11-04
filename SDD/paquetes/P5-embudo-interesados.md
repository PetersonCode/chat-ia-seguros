# P5 · Embudo de interesados y cotizaciones

**Branch:** `paquete-p5-embudo` · **SQL:** `SDD/sql/17_interesados.sql` · **Depende de:** P1 (vehículos y compañías), P2 (avisos) y P3 (renovaciones, para el comparador).
**Por qué (Roberto):** hoy veo clientes, pero no al que escribió ayer pidiendo precio. Lo atiende quien esté libre, se me olvida volver a llamarlo y no sé cuántos se nos fueron ni por qué. Quiero un tablero de venta nueva con dueño y próximo contacto, que el bot junte los datos para cotizar, seguimiento solo, y comparar lo que cotizan las compañías.

## 1. Esquema (`17_interesados.sql`)
```
interesados          id, nombre, apellido null, contacto_id → contactos_whatsapp null, cliente_id → clientes null,
                     origen (whatsapp, instagram, facebook, web, recomendacion, llamado, otro),
                     estado (consulta, cotizando, documentacion, emitida, perdida) default consulta,
                     responsable_id → funcionarios null, proximo_contacto date null, motivo_perdida text null,
                     datos jsonb default '{}'   -- dni, patente, marca, modelo, anio, uso, localidad, tipo_seguro
                     creado_en, actualizado_en
interesado_historial id, interesado_id, estado_anterior null, estado_nuevo, nota null, funcionario_id null, fecha
cotizaciones         id, interesado_id → interesados null, poliza_id → polizas null,   -- una o la otra, nunca ninguna ni las dos
                     compania_id → companias, cobertura (basica, intermedia, total), prima_mensual numeric(12,2) > 0,
                     vigencia_hasta date null, elegida bool default false, notas null, creada_por_id, creada_en
                     UNIQUE parcial: una sola elegida por interesado, una sola elegida por póliza
tipos_aviso          + seguimiento_cotizacion_2d, seguimiento_cotizacion_5d
```
CHECK: `perdida` exige `motivo_perdida` de 3 o más caracteres; `emitida` exige `cliente_id`. Un contacto puede tener **a lo sumo un** interesado abierto (ni `emitida` ni `perdida`).

## 2. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-38 | Dados `Interesado`, `InteresadoHistorial` y `Cotizacion`, entonces son `managed = False`; `EstadoInteresado`, `OrigenInteresado` y `Cobertura` coinciden con los `CHECK` (AC-T4-07); el SQL 17 está en `test_runner.py` y se aplica dos veces; las fábricas `crear_interesado` y `crear_cotizacion` crean objetos válidos; una `Cotizacion` sin interesado ni póliza, o con las dos, es rechazada por la base (test con SQL directo). |
| AC-T4-39 | Dadas las consultas nuevas, entonces `listar_interesados(estado=None, responsable_id=None, origen=None, q=None, seguimiento_vencido=False, hoy=None)` filtra y ordena (los de `proximo_contacto` vencido primero, luego por `actualizado_en` descendente; `q` busca en nombre, apellido, teléfono y patente de `datos`); `contar_por_estado(responsable_id=None)` devuelve `{estado: cantidad}` con los 5 estados; `cotizaciones_de(interesado_id=None, poliza_id=None)` ordena por `prima_mensual` ascendente con la compañía incluida; `interesado_abierto_de(contacto_id)`. Número fijo de consultas. |

## 3. Etapa B · Lógica (T3)
Archivos: `negocio/interesados.py` y `negocio/cotizaciones.py` (nuevos), `negocio/avisos.py`, `negocio/reglas.py`, `negocio/bot/` (reutilizar el alta de datos de `bot/registro.py`).

Transiciones válidas: `consulta → cotizando → documentacion → emitida` (una etapa por vez, y **se puede volver una etapa atrás**: `cotizando → consulta`, `documentacion → cotizando`), `cualquiera abierta → perdida` y `perdida → consulta`. `emitida` es final. *(Volver atrás: decidido por Daniel el 2026-11-04.)*
| ID | Criterio |
|---|---|
| AC-T3-81 | Dado `crear_interesado(funcionario_id, nombre, origen, telefono=None, apellido=None, datos=None)`, entonces crea el interesado en `consulta` con responsable el que lo creó, y deja el primer registro de historial (`estado_anterior` nulo); el teléfono pasa por `normalizar_telefono` y **reutiliza** el contacto de WhatsApp si ya existe (o lo crea sin cliente); un origen inválido o un nombre vacío es `DatosInvalidos`; si el número ya tiene un interesado abierto devuelve ese en vez de duplicar; si pertenece a un cliente activo lo crea igual con `cliente_id` precargado (venta cruzada). |
| AC-T3-82 | Dado `mover_interesado(id, estado_nuevo, funcionario_id, nota=None, motivo_perdida=None)`, entonces aplica solo las transiciones válidas (saltear una etapa o salir de `emitida` es `EstadoInvalido`), registra el historial, actualiza `actualizado_en`, exige `motivo_perdida` de 3 o más caracteres para `perdida`, y para `emitida` exige `cliente_id` y que ese cliente tenga una póliza creada después del interesado (si no, `EstadoInvalido`). Cualquier funcionario activo puede usarlo. |
| AC-T3-83 | Dado `convertir_en_cliente(interesado_id, funcionario_id, dni, nombre, apellido, email=None)` por un aprobador, sobre un interesado en `documentacion`, entonces llama a `alta_cliente` (adoptando el contacto existente, AC-T3-47) o, si ya existe un cliente con ese DNI, lo reutiliza, y guarda `cliente_id`; no cambia el estado (pasar a `emitida` es `mover_interesado`); un operador, `PermisoDenegado`. |
| AC-T3-84 | Dados `asignar_interesado(id, responsable_id, funcionario_id)`, `programar_contacto(id, fecha, funcionario_id)` (fecha de hoy o futura; vacía la borra) y `actualizar_datos_interesado(id, datos, funcionario_id)` (mezcla con lo existente y normaliza `patente` y `dni`), entonces cada uno registra quién y cuándo, y todos son de cualquier funcionario activo; asignar a un funcionario inactivo es `DatosInvalidos`. |
| AC-T3-85 | Dada una consulta `cotizacion` de un contacto, entonces antes de derivar el bot pide, en este orden, `patente`, `marca y modelo`, `año`, `uso` (particular, comercial…) y `localidad` (hasta `MAX_PEDIDOS` intentos, con el mismo mecanismo de `bot/registro.py`), guarda lo que logró juntar en `Interesado.datos` (crea el interesado con origen `whatsapp` si no existía, con `proximo_contacto` de **hoy** si no tenía fecha; decidido por Daniel el 2026-11-04), responde `COTIZACION_REGISTRADA` («¡Gracias! Con estos datos un asesor te prepara la cotización y te escribe por acá.») y deriva a Graciela con el id del interesado en el motivo. Sin datos completos igual deriva, sin inventar nada (R12). |
| AC-T3-86 | Dado el generador `seguimiento_interesados` (registrado en P2), cuando se ejecuta, entonces programa `seguimiento_cotizacion_2d` y `seguimiento_cotizacion_5d` para los interesados que llevan 2 y 5 días en `cotizando` **sin que el contacto haya escrito después**, con `referencia = "interesado:<id>:<hito>:<fecha de entrada al estado>"` y `asignado_a_id` = el responsable del interesado (a esa altura la ventana de 24 h suele estar cerrada, así que le llega como tarea en «Para contactar»); los cancela cuando el interesado cambia de estado o el contacto responde; no programa nada para contactos sin `acepta_avisos`. Texto: «Hola {nombre}, ¿pudiste ver la cotización que te pasamos? Si tenés dudas o querés ajustar algo, contanos.» |
| AC-T3-87 | Dados `cargar_cotizacion(funcionario_id, compania_id, cobertura, prima_mensual, interesado_id=None, poliza_id=None, vigencia_hasta=None, notas=None)`, `elegir_cotizacion(id, funcionario_id)` y `quitar_cotizacion(id, funcionario_id)`, entonces la primera exige **exactamente uno** de interesado o póliza, una compañía activa y prima > 0; `elegir` marca la elegida y desmarca la anterior del mismo destino en una transacción; `quitar` borra solo una no elegida (si es la elegida, `EstadoInvalido`); cualquier funcionario activo. |
| AC-T3-88 | Dada la regla pura `reglas.aumento_significativo(actual, nueva, umbral=Decimal("15"))`, entonces es `True` si `nueva` supera a `actual` en `umbral` por ciento o más (con `Decimal`, sin redondeos binarios); dada `variacion_renovacion(poliza_id)`, devuelve el porcentaje de variación entre `prima_mensual` de la póliza y la cotización elegida para ella, o `None` si no hay elegida. |

## 4. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-36 | Dados `GET /api/interesados/` (filtros `estado`, `responsable`, `origen`, `q`, `seguimiento_vencido=1`, paginado), `POST /api/interesados/`, `GET /api/interesados/{id}/` (con `historial`, `cotizaciones` y `contacto`), `PATCH /api/interesados/{id}/` (`responsable_id`, `proximo_contacto`, `datos`), `POST …/mover/` `{estado, nota?, motivo_perdida?}` y `POST …/convertir/` (aprobador), entonces llaman a las funciones de AC-T3-81 a 84 y traducen los errores según AC-T2-03; las rutas `/panel/interesados/` y `/panel/interesado/` están en la lista blanca. |
| AC-T2-37 | Dados `GET /api/interesados/embudo/?responsable=` (devuelve `{conteos: {estado: n}, convertidos_mes, perdidos_mes}`), `GET /api/cotizaciones/?interesado=N` o `?poliza=N`, `POST /api/cotizaciones/`, `POST …/{id}/elegir/` y `POST …/{id}/quitar/`, entonces usan las funciones de AC-T3-87; y `renovacion_item` (de P3) suma `variacion_pct` y `aumento_alto` (`reglas.aumento_significativo`). |

## 5. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-35 | Dado `lib/embudo.js`, entonces `ETAPAS` es la lista ordenada `consulta, cotizando, documentacion, emitida, perdida` con su etiqueta, `agruparPorEstado(interesados)` devuelve las 5 columnas aunque estén vacías sin modificar la original, y `siguienteEtapa(estado)` devuelve la próxima o `null` en `emitida` y `perdida`, y `etapaAnterior(estado)` la anterior o `null` en `consulta`, `emitida` y `perdida`. |
| AC-T1-36 | **(QA)** Dada `/panel/interesados/`, entonces hay un tablero por columnas (consulta, cotizando, documentación, emitida, perdida) con tarjetas (nombre, origen, responsable, próximo contacto —vencido en rojo **con texto**—), filtros por responsable y origen, búsqueda con `debounce`, y un `<details>` «Nuevo interesado»; cada tarjeta abre su ficha. |
| AC-T1-37 | **(QA)** Dada `/panel/interesado/?id=N`, entonces muestra los datos juntados (patente, marca, año…), el historial, la tabla comparativa de cotizaciones (ordenada por prima, la elegida resaltada, compañía y cobertura), y permite cargar cotización, elegir una, avanzar de etapa, asignar, fijar próximo contacto, marcar como perdido (motivo obligatorio en `<dialog>`) y, para aprobadores, «Convertir en cliente». Los errores de la API se muestran. |
| AC-T1-38 | **(QA)** Dada `/panel/renovaciones/` (P3), entonces cada fila con cotización elegida muestra la variación de precio y una insignia con texto «Aumento alto» cuando `aumento_alto` es verdadero. |

## 6. Fuera de alcance (anotar en la entrega si se pide)
Guardar la foto del título verde y del DNI del interesado como adjuntos. Se resuelve igual que los comprobantes de P4 (tabla de adjuntos propia y almacenamiento privado compartido); queda para un paquete aparte para no inflar este.

## 7. Terminado cuando
Los 16 AC con prueba, contratos actualizados, SQL 17 aplicado, y un recorrido a mano: mensaje «cuánto sale asegurar mi auto» → datos juntados → interesado en el tablero → cotizaciones de dos compañías → elegir → seguimiento a los 2 días → convertir → `emitida`. `SDD/entregas/P5.md`.
