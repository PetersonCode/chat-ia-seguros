# P3 · Renovaciones

**Branch:** `paquete-p3-renovaciones` · **SQL:** `SDD/sql/15_renovaciones.sql` · **Depende de:** P2 (motor de avisos). P1 mejora los textos (patente) pero no es obligatorio.
**Por qué (Roberto):** cuando una póliza vence y nadie se entera, el cliente se va a otra compañía y la plata se pierde sin ruido. Quiero una lista de «lo que vence», avisos solos a 60, 30 y 7 días, y renovar con un clic.

## 1. Decisión de diseño
**Renovar = crear una póliza nueva** (nuevo `POL-#####` con `proximo_numero_poliza`, vigencia desde el día siguiente al vencimiento, con su plan de cuotas) enlazada a la anterior por `renovada_de_id`. La vieja no se edita: queda su historial de cuotas y siniestros intacto.

## 2. Esquema (`15_renovaciones.sql`)
```
polizas              + renovada_de_id → polizas null (UNIQUE: una póliza se renueva una sola vez)
                     + no_renueva_motivo text null, + no_renueva_en timestamptz null   (el cliente decidió no renovar)
acciones_pendientes  el CHECK de tipo_accion admite también 'renovar_poliza'   (DROP + ADD CONSTRAINT, como 05_acciones_del_bot.sql)
tipos_consulta       + ('renovacion', 'Renovación', 'requiere_aprobacion')
tipos_aviso          + renovacion_60, renovacion_30, renovacion_7, renovacion_gracias
```
CHECK: `no_renueva_motivo` y `no_renueva_en` van juntos (los dos o ninguno).

## 3. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-34 | Dados `Poliza.renovada_de` (`related_name="renovacion"`), `no_renueva_motivo`, `no_renueva_en` y `TipoAccion.RENOVAR_POLIZA`, entonces los `TextChoices` siguen coincidiendo con los `CHECK` (AC-T4-07), `crear_catalogos()` agrega el tipo de consulta `renovacion`, el SQL 15 está en `test_runner.py` y se puede aplicar dos veces. |
| AC-T4-35 | Dado `polizas_por_renovar(dias=60, hoy=None, incluir_vencidas=False)`, entonces devuelve las pólizas `vigente` con `fecha_vencimiento` entre hoy y hoy + `dias` que **no** tienen renovación ni `no_renueva_motivo`, anotadas con `dias_restantes` y `saldo_pendiente`, ordenadas por vencimiento ascendente; con `incluir_vencidas=True` suma las vencidas hace 30 días o menos. Trae cliente, vehículo (si existe P1) y compañía en un número fijo de consultas (`assertNumQueries`). |

## 4. Etapa B · Lógica (T3)
Archivos: `negocio/polizas.py` (o `negocio/renovaciones.py`), `negocio/acciones.py`, `negocio/avisos.py` (generadores y textos), `negocio/bot/`.

Textos de aviso nuevos (se suman a `TEXTOS_AVISO`; son texto libre, sin plantillas de Meta):
| Tipo | Texto |
|---|---|
| `renovacion_60` | Hola {nombre}, tu póliza {numero_poliza}{vehiculo} vence el {fecha}. Si querés renovarla, escribinos y lo dejamos listo. |
| `renovacion_30` | Hola {nombre}, a 30 días del vencimiento de tu póliza {numero_poliza}{vehiculo} ({fecha}). ¿La renovamos? Respondé «quiero renovar» y nos ocupamos. |
| `renovacion_7` | {nombre}, tu póliza {numero_poliza}{vehiculo} vence el {fecha}, en una semana. Para no quedarte sin cobertura, respondé «quiero renovar». |
| `renovacion_gracias` | ¡Gracias por renovar con nosotros, {nombre}! Tu póliza {numero_poliza} ya está vigente hasta el {fecha}. |

`{vehiculo}` es ` (<patente>)` solo si la póliza tiene vehículo. Los datos van en `datos_verificados`.
| ID | Criterio |
|---|---|
| AC-T3-68 | Dado el generador `renovaciones` (registrado en P2), cuando se ejecuta para una fecha `hoy`, entonces por cada póliza de `polizas_por_renovar` que vence exactamente en 60, 30 o 7 días programa un aviso para **cada** contacto del cliente con `referencia = "poliza:<id>:<vencimiento>:<dias>"`; si el sistema estuvo apagado, programa solo el hito más cercano que todavía corresponde (no los vencidos); no programa nada para clientes inactivos, pólizas con `no_renueva_motivo` o ya renovadas; ejecutarlo dos veces no duplica. |
| AC-T3-69 | Dada una consulta de tipo `renovacion` («quiero renovar», “renovar mi seguro”, «se me vence el seguro, ¿qué hago?»), entonces el clasificador por reglas la reconoce **antes** de `vencimiento` (y «cuándo vence mi póliza» sigue siendo `vencimiento`), el bot responde `SOLICITUD_REGISTRADA` y llama `solicitar_accion(..., 'renovar_poliza', poliza_id, {})` con la póliza si el cliente tiene **exactamente una** en `polizas_por_renovar(dias=90)` (si no, `poliza_id=None` y `parametros={"aclaracion": …}`); no cambia ninguna póliza (R11). Contacto sin cliente → `SIN_CLIENTE` y derivación a Graciela. |
| AC-T3-70 | Dado `renovar_poliza(poliza_id, funcionario_id, prima_mensual, meses=12, compania_id=None, cobertura=None)` por un aprobador, entonces en una transacción crea la póliza nueva (número nuevo, `fecha_inicio` = día siguiente al vencimiento de la anterior, o hoy si ya venció; mismo cliente, tipo, vehículo, conductores activos; compañía y cobertura de la anterior salvo que se pasen; `comision_pct` de la compañía), genera su plan de cuotas con `plan_de_cuotas` y la enlaza con `renovada_de`; son `DatosInvalidos` una prima ≤ 0 o `meses` fuera de 1 a 24; `EstadoInvalido` si la póliza no está `vigente` ni vencida hace ≤ 30 días, si ya fue renovada o si tiene `no_renueva_motivo`; un operador, `PermisoDenegado`. |
| AC-T3-71 | Dada la acción `renovar_poliza` aprobada, entonces se ejecuta `renovar_poliza` con sus parámetros (`prima_mensual` obligatoria; sin ella, `ParametrosIncompletos` y la acción sigue `pendiente`, como AC-T3-18), todo en la misma transacción que la aprobación; el aviso al cliente dice «renovación de la póliza {numero}» (se suma a las descripciones de `ACCION_APROBADA`). |
| AC-T3-72 | Dados `marcar_no_renueva(poliza_id, funcionario_id, motivo)` (motivo de 3 o más caracteres) y `reactivar_renovacion(poliza_id, funcionario_id)`, ambos de aprobador, entonces el primero guarda motivo y fecha y **cancela los avisos `pendiente` de renovación de esa póliza**, y el segundo limpia motivo y fecha (los avisos de hitos que ya pasaron no se recrean; los futuros los vuelve a programar el generador); repetir cualquiera es `EstadoInvalido`; una póliza ya renovada no puede marcarse. |
| AC-T3-73 | Dado que se renueva una póliza **antes** de su vencimiento, entonces se programa para cada contacto un aviso `renovacion_gracias` (referencia `"renovacion:<poliza_nueva_id>"`); si se renueva ya vencida, no. |

## 5. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-31 | Dado `GET /api/renovaciones/?dias=60&incluir_vencidas=1&pagina=`, entonces devuelve una página de `renovacion_item` `{poliza: {id, numero_poliza, tipo_seguro, vehiculo, compania, fecha_vencimiento, prima_mensual}, cliente: {id, nombre, whatsapp}, dias_restantes, saldo_pendiente, avisos: [{tipo, estado}], no_renueva_motivo}` desde `polizas_por_renovar`; cualquier funcionario lo ve; `dias` fuera de 1 a 365 → 400; la ruta `/panel/renovaciones/` está en la lista blanca. |
| AC-T2-32 | Dados `POST /api/polizas/{id}/renovar/` `{prima_mensual, meses?, compania_id?, cobertura?}` (→ 201 `poliza_detalle` de la nueva), `POST /api/polizas/{id}/no-renueva/` `{motivo}` y `POST /api/polizas/{id}/reactivar-renovacion/`, entonces llaman a las funciones de AC-T3-70 y AC-T3-72, exigen aprobador y traducen los errores según AC-T2-03. |

## 6. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-30 | Dado `lib/renovaciones.js`, entonces `urgenciaDe(diasRestantes)` → `"vencida"` (< 0), `"critica"` (0 a 7), `"proxima"` (8 a 30), `"normal"` (más) y `claseUrgencia` los mapea a `fila-rojo`, `fila-rojo`, `fila-amarillo`, `fila-verde`; el texto de la urgencia se muestra siempre además del color. |
| AC-T1-31 | **(QA)** Dada `/panel/renovaciones/`, entonces lista las pólizas por renovar con cliente, vehículo, vencimiento, días restantes, saldo y el estado de sus avisos (enviado, pendiente, «para contactar a mano» con enlace a `/panel/avisos/`); filtros de 7, 30 y 60 días y «incluir vencidas»; aprobadores ven «Renovar» (diálogo con prima mensual y meses; muestra la póliza nueva al terminar) y «No renueva» (motivo obligatorio); el operador no ve esos botones; los errores de la API se muestran. |

## 7. Terminado cuando
Los 12 AC con prueba, contratos actualizados, SQL 15 aplicado, y una renovación de punta a punta probada a mano (aviso → «quiero renovar» → acción → aprobar → póliza nueva con cuotas). `SDD/entregas/P3.md`.
