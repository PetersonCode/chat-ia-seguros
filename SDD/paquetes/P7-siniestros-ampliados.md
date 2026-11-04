# P7 · Siniestros ampliados

**Branch:** `paquete-p7-siniestros` · **SQL:** `SDD/sql/19_siniestros_ampliados.sql` · **Depende de:** P2 (avisos) y del expediente de siniestros que ya existe (`07_expediente_siniestros.sql`, `08_adjuntos_siniestros.sql`, `negocio/siniestros.py`).
**Por qué (Roberto):** un siniestro es el momento en que el cliente más nos necesita y más fácil se va si lo dejamos tirado. Hoy se denuncia y se suben fotos, pero no sé qué documentación falta según el tipo de siniestro, cuáles están frenados, ni le avisamos al cliente cuando algo cambia.

## 1. Esquema (`19_siniestros_ampliados.sql`)
```
siniestros          + tipo (choque, robo, incendio, granizo, cristales, danos_terceros, otro) default 'otro'
                    + taller_id → talleres null
                    + ultima_actividad_en timestamptz default now()   (se actualiza con cada cambio de estado, adjunto o requisito)
talleres            id, nombre, telefono null, direccion null, tipo (taller, grua, cristalero) default taller, activo bool default true
siniestro_requisitos id, siniestro_id → siniestros, codigo text, descripcion text, cumplido bool default false,
                    cumplido_en null, cumplido_por_id → funcionarios null     UNIQUE (siniestro_id, codigo)
tipos_aviso         + siniestro_estado, siniestro_faltantes
```
Los siniestros existentes quedan con `tipo = 'otro'`, sin requisitos y con `ultima_actividad_en` = su `creado_en`.

## 2. Checklists por tipo (constante `CHECKLISTS` en `negocio/siniestros.py`)
| Tipo | Requisitos (`codigo`: descripción) |
|---|---|
| `choque` | `dni`: DNI del conductor · `cedula`: cédula verde o azul · `carnet`: carnet de conducir vigente · `fotos`: fotos del daño · `tercero`: datos del tercero (nombre, patente, compañía) · `denuncia`: denuncia policial (si hay lesionados) |
| `robo` | `denuncia`: denuncia policial · `dni` · `cedula` · `llaves`: copia de las llaves |
| `incendio` | `denuncia`: denuncia policial o de bomberos · `dni` · `cedula` · `fotos` |
| `granizo` | `fotos` · `dni` · `cedula` |
| `cristales` | `fotos` · `dni` · `cedula` |
| `danos_terceros` | `dni` · `cedula` · `tercero` · `fotos` · `denuncia` |
| `otro` | `dni` · `cedula` · `fotos` · `descripcion`: descripción de lo ocurrido |

## 3. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-42 | Dados `Taller`, `SiniestroRequisito` y los campos nuevos de `Siniestro` (`tipo`, `taller`, `ultima_actividad_en`), entonces son `managed = False`; `TipoSiniestro` y `TipoTaller` coinciden con los `CHECK` (AC-T4-07); el SQL 19 está en `test_runner.py` y se aplica dos veces; las fábricas `crear_taller` y `crear_requisito` crean objetos válidos; los siniestros previos conservan sus datos. |
| AC-T4-43 | Dadas las consultas nuevas, entonces `siniestros_parados(hoy, dias=7)` devuelve los que no están `cerrado` ni `rechazado` y cuya `ultima_actividad_en` es anterior a `hoy - dias`, con `dias_sin_actividad`, la póliza, el cliente y el taller; `requisitos_de(siniestro_id)` (cumplidos al final, luego por `id`); `listar_talleres(tipo=None, solo_activos=True)`; `listar_siniestros` (existente) acepta los filtros `tipo` y `parados`. Número fijo de consultas. |

## 4. Etapa B · Lógica (T3)
Archivos: `negocio/siniestros.py`, `negocio/adjuntos_siniestros.py` (solo el enganche de AC-T3-95), `negocio/talleres.py` (nuevo), `negocio/reglas.py`, `negocio/avisos.py`.

Textos de aviso nuevos (se suman a `TEXTOS_AVISO`; son texto libre, sin plantillas de Meta):
| Tipo | Texto |
|---|---|
| `siniestro_estado` | Hola {nombre}, novedades de tu siniestro {numero_siniestro}: {novedad}{taller} — `novedad`: en_evaluacion → «lo estamos evaluando»; aprobado → «fue aprobado»; rechazado → «no fue aprobado, un asesor te va a contar los motivos»; cerrado → «quedó cerrado». `taller` es ` Taller: <nombre> (<teléfono>).` solo si hay uno asignado. |
| `siniestro_faltantes` | Hola {nombre}, para avanzar con tu siniestro {numero_siniestro} todavía nos falta:\n{lineas}\nPodés mandarlo por acá. |
| ID | Criterio |
|---|---|
| AC-T3-94 | Dado `registrar_denuncia` (y la acción `apertura_siniestro`), cuando recibe un `tipo` opcional (por defecto `otro`), entonces crea el siniestro con los requisitos de `CHECKLISTS[tipo]` en la misma transacción; un tipo inválido es `DatosInvalidos`; `registrar_denuncia` sin `tipo` se comporta como antes salvo por el checklist de `otro`. |
| AC-T3-95 | Dados `marcar_requisito(requisito_id, funcionario_id, cumplido)` y `agregar_requisito(siniestro_id, funcionario_id, descripcion)` (de cualquier funcionario activo; `descripcion` de 3 o más caracteres, código generado `extra-N`), entonces el primero guarda `cumplido_en` y `cumplido_por` y actualiza `ultima_actividad_en`; en un siniestro `cerrado` o `rechazado` ambos son `EstadoInvalido`; además, cuando se agrega un adjunto de imagen al siniestro (flujo existente), el requisito `fotos` se marca cumplido solo, con el funcionario nulo. |
| AC-T3-96 | Dado `transicionar_siniestro` (existente), cuando pasa a `en_evaluacion`, `aprobado`, `rechazado` o `cerrado`, entonces actualiza `ultima_actividad_en` y programa un aviso `siniestro_estado` para cada contacto del cliente con `referencia = "siniestro:<id>:<estado>"`; el pasaje a `denunciado` no avisa; ejecutarlo en un estado repetido no duplica. |
| AC-T3-97 | Dado el generador `siniestros_faltantes` (registrado en P2), cuando se ejecuta, entonces programa un aviso para cada siniestro `denunciado` o `en_evaluacion` con requisitos sin cumplir y 3 o más días sin actividad, con la lista de los pendientes (hasta 5 líneas, con «y N más» si hay más), a lo sumo 3 veces por siniestro (`referencia = "siniestro:<id>:faltantes:<n>"`, separados por 3 días); no avisa si todos los requisitos están cumplidos. |
| AC-T3-98 | Dados `alta_taller`, `modificar_taller` y `desactivar_taller` (aprobador; nombre único sin distinguir mayúsculas) y `asignar_taller(siniestro_id, taller_id, funcionario_id)` (cualquier funcionario; el taller debe estar activo; actualiza `ultima_actividad_en`), entonces cada uno cumple su regla y un taller inexistente es `NoEncontrado`. |
| AC-T3-99 | Dada la regla pura `reglas.semaforo_siniestro(dias_sin_actividad, estado)`, entonces `cerrado` y `rechazado` → `None`; 0 a 3 días → `"verde"`; 4 a 7 → `"amarillo"`; más de 7 → `"rojo"`; las constantes `DIAS_SINIESTRO_AMARILLO = 4` y `DIAS_SINIESTRO_ROJO = 8` están en `reglas.py`. |

## 5. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-40 | Dados `GET /api/siniestros/?tipo=&parados=1` y `GET /api/siniestros/{id}/`, entonces cada siniestro suma `tipo`, `taller`, `dias_sin_actividad`, `semaforo` (de `reglas.semaforo_siniestro`) y `requisitos` `[{id, codigo, descripcion, cumplido, cumplido_en}]` con `progreso {cumplidos, total}`; `POST /api/siniestros/` acepta `tipo`; la ruta `/panel/talleres/` está en la lista blanca. |
| AC-T2-41 | Dados `POST /api/siniestros/{id}/requisitos/` `{descripcion}`, `POST /api/requisitos/{id}/marcar/` `{cumplido}`, `POST /api/siniestros/{id}/taller/` `{taller_id}` (cualquier funcionario), `GET /api/talleres/?tipo=&activos=1` (cualquier funcionario) y `POST /api/talleres/`, `PATCH /api/talleres/{id}/` (aprobador), entonces llaman a las funciones de AC-T3-95 y 98 y traducen los errores según AC-T2-03. |

## 6. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-42 | Dado `lib/siniestros.js`, entonces `claseSemaforo("rojo"…)` → `fila-rojo`, `fila-amarillo`, `fila-verde` (`null` → sin clase), `etiquetaSemaforo` → «Parado», «Con demora», «Al día», y `progresoRequisitos(requisitos)` → `{cumplidos, total, porcentaje}` (lista vacía → 0 de 0, 0 %), sin modificar la entrada. |
| AC-T1-43 | **(QA)** Dada `/panel/siniestros/`, entonces la lista muestra el semáforo con texto, el tipo y el progreso del checklist («3 de 6»), tiene el filtro «Solo parados» y por tipo; el detalle muestra el checklist con casillas para marcar, «Agregar requisito», el taller asignado (selector) y el historial existente; todo se actualiza sin recargar y los errores de la API se muestran. |
| AC-T1-44 | **(QA)** Dada `/panel/talleres/`, entonces los aprobadores pueden crear, editar y desactivar talleres, grúas y cristaleros; los demás los ven sin botones. |

## 7. Terminado cuando
Los 13 AC con prueba, contratos actualizados, SQL 19 aplicado y a mano: denuncia por WhatsApp de un choque → checklist de 6 puntos → subir foto (se tilda sola) → pasar a `en_evaluacion` → el cliente recibe el aviso → 3 días sin actividad → aviso de faltantes. `SDD/entregas/P7.md`.
