# P8 · Panel del día, equipo y reporte mensual

**Branch:** `paquete-p8-panel` · **SQL:** `SDD/sql/20_equipo.sql` · **Depende de:** P2 (avisos), P3 (renovaciones), P4 (cobranza), P5 (interesados) y P7 (siniestros ampliados). P1 mejora el reporte (comisión por compañía).
**Por qué (Roberto):** entre Graciela, Diego y yo nos pasamos las tareas de boca. Quiero abrir el sistema a la mañana y ver **lo que hay que hacer hoy** sin recorrer ocho pantallas, repartir tareas con fecha, dejar notas sobre un cliente («pidió descuento, llamarlo en marzo») y tener a fin de mes un reporte simple de cuánto vendimos, cobramos y nos corresponde de comisión.

## 1. Esquema (`20_equipo.sql`)
```
notas_internas  id, texto (3 a 2000 caracteres), cliente_id → clientes null, interesado_id → interesados null,
                poliza_id → polizas null, autor_id → funcionarios, fijada bool default false, creada_en
                CHECK: al menos uno de cliente, interesado o póliza. Las notas no se editan ni se borran.
tareas          id, titulo (3 a 200), detalle null, cliente_id null, interesado_id null, poliza_id null,
                asignada_a_id → funcionarios, creada_por_id → funcionarios, vence date null,
                estado (pendiente, hecha, cancelada) default pendiente, completada_en null, creada_en
                CHECK: hecha exige completada_en
```

## 2. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-44 | Dados `NotaInterna` y `Tarea`, `EstadoTarea` coincidente con el `CHECK` (AC-T4-07), el SQL 20 en `test_runner.py` (aplicable dos veces) y las fábricas `crear_nota` y `crear_tarea`, entonces todo se crea sin error; una nota sin cliente, interesado ni póliza, o una tarea `hecha` sin `completada_en`, es rechazada por la base (SQL directo). |
| AC-T4-45 | Dadas `notas_de(cliente_id=None, interesado_id=None, poliza_id=None)` (fijadas primero, luego las más nuevas, con el autor incluido), `listar_tareas(asignada_a=None, estado="pendiente", vencidas=False, hoy=None)` (vencidas primero, luego por fecha de vencimiento, las sin fecha al final) y `resumen_del_dia(funcionario_id, hoy)`, entonces la última devuelve las cantidades `{renovaciones_7, renovaciones_vencidas, cuotas_vencen_hoy, morosos_riesgo, comprobantes_pendientes, interesados_a_contactar, avisos_para_contactar, siniestros_parados, tareas_mias, tareas_vencidas, conversaciones_sin_respuesta, acciones, derivaciones, alertas_criticas}` reutilizando los selectores de P2, P3, P4, P5 y P7 (`avisos_para_contactar` cuenta los asignados al funcionario y los sin asignar) y `contar_pendientes`, en 20 consultas o menos (`assertNumQueries`). |

## 3. Etapa B · Lógica (T3)
Archivos: `negocio/equipo.py` y `negocio/reportes.py` (nuevos).
| ID | Criterio |
|---|---|
| AC-T3-100 | Dados `agregar_nota(autor_id, texto, cliente_id=None, interesado_id=None, poliza_id=None)` y `fijar_nota(nota_id, funcionario_id, fijada)`, entonces la nota se guarda con su autor y fecha, el texto se recorta y debe tener entre 3 y 2000 caracteres, exige al menos un destino válido (`NoEncontrado` si no existe), y cualquier funcionario activo puede agregar y fijar; **no hay editar ni borrar** (se verifica que el módulo no los expone). |
| AC-T3-101 | Dadas `crear_tarea(creador_id, titulo, asignada_a_id, vence=None, detalle=None, cliente_id=None, interesado_id=None, poliza_id=None)`, `completar_tarea(id, funcionario_id)`, `reasignar_tarea(id, nuevo_id, funcionario_id)` y `cancelar_tarea(id, funcionario_id)`, entonces `vence` no puede ser anterior a hoy, la asignada debe ser un funcionario activo, completar y cancelar las pueden hacer la persona asignada, quien la creó o un aprobador (otro funcionario, `PermisoDenegado`), y una tarea que ya no está `pendiente` es `EstadoInvalido`. |
| AC-T3-102 | Dado `reporte_mensual(mes, funcionario_id)` con `mes = "AAAA-MM"`, entonces devuelve `{mes, polizas_nuevas, renovadas, bajas, cobrado, interesados: {nuevos, emitidos, perdidos, conversion_pct}, por_compania: [{compania, polizas_nuevas, cobrado, comision}], comision_total}` calculado así: nuevas = pólizas creadas en el mes sin `renovada_de`; renovadas = con `renovada_de`; bajas = acciones `baja_poliza` ejecutadas en el mes; cobrado = suma de `Pago.importe` con `fecha_pago` en el mes; comisión de un pago = `importe × comision_pct de la póliza / 100` (`Decimal`, 2 decimales, 0 si la póliza no tiene `comision_pct`); `conversion_pct` = emitidos / nuevos, 0 si no hubo nuevos. **La comisión solo se calcula para un aprobador**; para un operador `comision`, `por_compania[].comision` y `comision_total` son `None`. Un `mes` mal formado es `DatosInvalidos`. |

## 4. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-42 | Dado `GET /api/hoy/`, entonces devuelve `resumen_del_dia(request.funcionario.id, hoy)` más la lista `tareas` (las 10 más urgentes del usuario) con `{id, titulo, vence, cliente}`; la ruta `/panel/hoy/` y `/panel/tareas/` están en la lista blanca. |
| AC-T2-43 | Dados `GET /api/notas/?cliente=&interesado=&poliza=`, `POST /api/notas/`, `POST /api/notas/{id}/fijar/` `{fijada}`, `GET /api/tareas/?asignada_a=&estado=&vencidas=1`, `POST /api/tareas/`, y `POST /api/tareas/{id}/completar/`, `…/reasignar/` `{asignada_a}` y `…/cancelar/`, entonces llaman a las funciones de AC-T3-100 y 101 (cualquier funcionario) y traducen los errores según AC-T2-03; `cliente_detalle` e `interesado` suman sus `notas`. |
| AC-T2-44 | Dado `GET /api/reportes/mensual/?mes=2026-10`, entonces devuelve `reporte_mensual(mes, request.funcionario.id)`; `mes` ausente o mal formado → 400; para un operador las comisiones llegan en `null`; no reemplaza `GET /api/reportes/gestion/` (existente), que sigue igual. |

## 5. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-45 | Dado `lib/hoy.js`, entonces `tarjetasDelDia(resumen)` devuelve una lista ordenada por urgencia (alertas críticas, morosos en riesgo, renovaciones vencidas, avisos para contactar, siniestros parados, comprobantes, tareas vencidas, resto) con `{clave, titulo, cantidad, enlace, nivel}`; las cantidades en 0 se marcan `nivel: "ok"` y van al final; `nivel` es `"urgente"`, `"atencion"` u `"ok"`; no modifica la entrada. |
| AC-T1-46 | **(QA)** Dada `/panel/hoy/`, entonces hay una tarjeta por indicador (número grande, título, y **texto** del nivel además del color) que lleva a su pantalla, y debajo «Mis tareas de hoy» con «Completar»; `nav.js` agrega «Hoy» como primer enlace; el login sigue llevando a `/panel/` (AC-T1-05). |
| AC-T1-47 | **(QA)** Dado `/panel/tareas/` y las fichas de cliente e interesado, entonces se pueden crear, completar, reasignar y cancelar tareas (con fecha opcional, vencidas destacadas con texto), y ver, agregar y fijar notas internas con autor y fecha; las notas no tienen botón de editar ni borrar. |
| AC-T1-48 | **(QA)** Dada `/panel/reportes/`, entonces suma la sección «Mensual» con selector de mes, las cifras de AC-T3-102 y la tabla por compañía; para Diego las columnas de comisión no aparecen (o dicen «No disponible») y no hay error en la consola. |

## 6. Terminado cuando
Los 12 AC con prueba, contratos actualizados, SQL 20 aplicado y a mano: como Graciela y como Diego, abrir `/panel/hoy/` con datos de los otros paquetes y comprobar que cada tarjeta lleva a donde dice. `SDD/entregas/P8.md`.
