# P4 · Cobranza y mora

**Branch:** `paquete-p4-cobranza` · **SQL:** `SDD/sql/16_cobranza.sql` · **Depende de:** P2 (motor de avisos).
**Por qué (Roberto):** hoy las cuotas existen y los pagos se registran, pero nadie le avisa al cliente que tiene que pagar ni a nosotros quién se está atrasando. Una póliza que cae por falta de pago es plata y cliente perdidos. Quiero recordatorios solos, una lista de morosos con días de atraso, y que el cliente pueda ver cómo pagar y mandar el comprobante por WhatsApp.

## 1. Esquema (`16_cobranza.sql`)
```
datos_de_pago        id, titulo, detalle, activo bool default true, creado_por_id → funcionarios, creado_en
                     (ej.: «Transferencia» / «Alias: CASTANO.SEGUROS · CBU …»; los carga un aprobador)
comprobantes_pago    id, cuota_id → cuotas, mensaje_id → mensajes null, archivo text (ruta privada),
                     estado (pendiente, confirmado, rechazado) default pendiente,
                     revisado_por_id → funcionarios null, revisado_en null, motivo text null, creado_en
tipos_aviso          + cuota_recordatorio (prioridad 3), cuota_vencida (2), mora_7 (1), mora_15 (1),
                       pago_confirmado (2), comprobante_rechazado (2)
tipos_consulta       + ('datos_pago', 'Datos para pagar', 'bot_responde')
```
CHECK: `confirmado`/`rechazado` exigen `revisado_por_id` y `revisado_en`; `rechazado` exige `motivo` de 5 o más caracteres.

## 2. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-36 | Dados `DatoDePago` y `ComprobantePago` (`related_name="comprobantes"` en `Cuota`), `EstadoComprobante` coincidente con el `CHECK` (AC-T4-07), `crear_catalogos()` con el tipo `datos_pago`, el SQL 16 en `test_runner.py` (aplicable dos veces) y las fábricas `crear_dato_de_pago` y `crear_comprobante`, entonces todo se crea sin error con sus defaults. |
| AC-T4-37 | Dadas las consultas nuevas, entonces `cuotas_a_vencer(hoy, dias)` devuelve las `pendiente` que vencen entre hoy y hoy + `dias`; `cuotas_en_mora(hoy)` las `pendiente` o `vencida` con vencimiento anterior a hoy, anotadas con `dias_atraso`; `morosos(hoy)` agrupa por cliente activo con `saldo_vencido`, `cuotas_vencidas`, `max_dias_atraso`, ordenado por `max_dias_atraso` descendente; `datos_de_pago_activos()` y `comprobantes_de(cuota_id=None, estado=None)`. Las pólizas dadas de baja no cuentan. Todas con número fijo de consultas. |

## 3. Etapa B · Lógica (T3)
Archivos: `negocio/cobranza.py` (nuevo), `negocio/reglas.py`, `negocio/avisos.py`, `negocio/whatsapp.py` y `negocio/bot/`.

Textos de aviso nuevos (se suman a `TEXTOS_AVISO`; son texto libre, sin plantillas de Meta):
| Tipo | Texto |
|---|---|
| `cuota_recordatorio` | Hola {nombre}, te recordamos que el {fecha} vence tu cuota de {monto} ({detalle}). Si necesitás los datos para pagar, escribí «cómo pago». |
| `cuota_vencida` | Hola {nombre}, tu cuota de {monto} venció el {fecha}. Si ya pagaste, mandanos el comprobante por acá; si no, escribí «cómo pago». |
| `mora_7` | {nombre}, tenés {monto} vencido hace una semana. Regularizalo para no perder la cobertura; escribí «cómo pago» o contanos si necesitás ayuda. |
| `mora_15` | {nombre}, tu saldo vencido es de {monto} y lleva 15 días. Para evitar la baja de tu póliza, comunicate con nosotros hoy. |

`{detalle}` es `<número de póliza>` o, con varias, `N cuotas`. Montos y fechas salen de la base y van en `datos_verificados`.
| ID | Criterio |
|---|---|
| AC-T3-74 | Dado `marcar_cuotas_vencidas(hoy)`, entonces pasa a `vencida` toda cuota `pendiente` con vencimiento anterior a `hoy` y devuelve cuántas; no toca `pagada`; repetirla no cambia nada; el generador la llama antes de programar avisos; `registrar_pago` sigue cobrando la cuota impaga más vieja aunque esté `vencida`. |
| AC-T3-75 | Dados los generadores de cobranza (registrados en P2), cuando se ejecutan para `hoy`, entonces hay un aviso `cuota_recordatorio` para las cuotas que vencen en 3 días, `cuota_vencida` para las que vencieron ayer, `mora_7` y `mora_15` para las que llevan 7 y 15 días de atraso; no se programa para pólizas dadas de baja, clientes inactivos ni cuotas ya pagadas; cuando una cuota se paga, los avisos `pendiente` que dependían de ella se cancelan. |
| AC-T3-76 | Dado un cliente con varias cuotas que caen en el mismo hito el mismo día, entonces recibe **un solo** aviso por contacto, con el total y el detalle (`referencia = "cobranza:<cliente_id>:<hito>:<fecha>"`, `datos` con los ids de las cuotas), y el monto es la suma real; ejecutar dos veces no duplica. |
| AC-T3-77 | Dada una consulta `datos_pago` («cómo pago», «alias», «cbu», «a dónde transfiero», «datos para pagar»), entonces el clasificador por reglas la reconoce **antes** de `pago`, y el bot responde `DATOS_DE_PAGO` («Podés pagar por:\n{lineas}\nSi ya pagaste, mandanos el comprobante por acá.») con una línea por dato de pago activo; sin datos activos (R12: no se inventa nada) responde `DERIVACION` y deriva a Graciela. **Enmienda a AC-T3-50/54:** `pago` queda solo para adelantar cuotas, refinanciar y descuentos; «medios de pago» pasa a `datos_pago`. |
| AC-T3-78 | Dada una imagen entrante de un contacto con cliente que tiene cuotas impagas y **sin** una denuncia de siniestro esperando fotos (ese flujo existente tiene prioridad), entonces se guarda como `ComprobantePago` `pendiente` ligado a la cuota impaga más vieja, reutilizando la validación y el almacenamiento privado de `negocio/adjuntos_siniestros.py` (sin duplicarlos), se responde `COMPROBANTE_RECIBIDO` («Recibimos tu comprobante. Lo revisamos y te confirmamos por acá.») y se deriva a Graciela (`normal`). Un contacto sin cliente o sin cuotas impagas sigue el comportamiento actual. |
| AC-T3-79 | Dado `revisar_comprobante(comprobante_id, funcionario_id, confirmar, motivo=None)` por un aprobador, entonces `confirmar=True` verifica que la cuota del comprobante sea la que `registrar_pago` va a cobrar (la impaga más vieja de la póliza; si no, `EstadoInvalido`), llama a `registrar_pago` con `referencia = "COMP-<id>"` e importe de la cuota **en la misma transacción** (idempotente: confirmar dos veces es `EstadoInvalido`), deja el comprobante `confirmado` y avisa al cliente con `pago_confirmado` («¡Gracias! Registramos tu pago de {monto}.»), que sale como mensaje si la ventana de 24 h sigue abierta y si no queda en «Para contactar» (P2); `confirmar=False` exige motivo de 5 o más caracteres, lo deja `rechazado` y avisa con `comprobante_rechazado` («No pudimos validar tu comprobante. Un asesor se va a comunicar con vos.») por el mismo camino; un operador, `PermisoDenegado`. |
| AC-T3-80 | Dada la regla pura `reglas.nivel_de_mora(dias_atraso)`, entonces 0 o menos → `"al_dia"`, 1 a 7 → `"leve"`, 8 a 29 → `"media"`, 30 o más → `"riesgo"`, y `color_por_nivel_mora` los mapea a `verde`, `amarillo`, `naranja`, `rojo`. `DIAS_MORA_RIESGO = 30` es una constante del módulo. Nada da de baja una póliza solo: la baja sigue siendo `baja_poliza` con aprobación (R11). |

## 4. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-33 | Dado `GET /api/morosos/?nivel=&pagina=`, entonces devuelve una página de `moroso` `{cliente: {id, nombre, dni, whatsapp}, saldo_vencido, cuotas_vencidas, max_dias_atraso, nivel, color, ultimo_aviso}` con `nivel` y `color` de `reglas`; cualquier funcionario; `nivel` inválido → 400; las rutas `/panel/cobranza/` y `/panel/datos-de-pago/` están en la lista blanca. |
| AC-T2-34 | Dados `GET /api/comprobantes/?estado=pendiente&pagina=`, `GET /api/comprobantes/{id}/archivo/` (descarga protegida por sesión, `Content-Type` real, `Cache-Control: private, no-store`, nunca una ruta del servidor en el JSON), `POST /api/comprobantes/{id}/confirmar/` y `POST /api/comprobantes/{id}/rechazar/` `{motivo}` (aprobador), entonces llaman a `revisar_comprobante` y traducen los errores según AC-T2-03. |
| AC-T2-35 | Dados `GET /api/datos-de-pago/` (cualquier funcionario), `POST` y `PATCH /api/datos-de-pago/{id}/` (aprobador, `titulo` y `detalle` no vacíos, `activo`), entonces devuelven `dato_de_pago` `{id, titulo, detalle, activo}`. |

## 5. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-32 | Dado `lib/mora.js`, entonces `etiquetaNivel("al_dia"…)` → «Al día», «Atraso leve», «Atraso medio», «En riesgo de baja» (desconocido → «—»), `claseNivel` → `fila-verde`, `fila-amarillo`, `fila-naranja`, `fila-rojo`, y `ordenarMorosos(lista)` ordena por días de atraso descendente sin modificar la original. |
| AC-T1-33 | **(QA)** Dada `/panel/cobranza/`, entonces tiene dos pestañas: «Morosos» (tabla con color y texto del nivel, saldo, días de atraso, último aviso, enlace a la ficha) y «Comprobantes» (pendientes con la imagen visible, «Confirmar» y «Rechazar» con motivo obligatorio en `<dialog>`, solo aprobadores); Diego ve las listas pero no los botones; los errores de la API se muestran. |
| AC-T1-34 | **(QA)** Dada `/panel/datos-de-pago/`, entonces aprobadores pueden crear, editar y desactivar datos de pago (alias, CBU, etc.); los demás los ven sin botones. |

## 6. Terminado cuando
Los 15 AC con prueba, contratos actualizados, SQL 16 aplicado y una cobranza de punta a punta probada con `simular_whatsapp` (aviso → «cómo pago» → comprobante → confirmar → cuota `pagada`). `SDD/entregas/P4.md`.
