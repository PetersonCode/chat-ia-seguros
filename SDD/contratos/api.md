# Contrato · API REST (`/api/`)

**Lo implementa:** T2 · **Lo usa:** T1.
Cambiar un endpoint o una forma de respuesta requiere acuerdo de las 4 personas.

## Convenciones

### Extensiones de cierre del MVP 2 (26/10/2026)

- `GET /api/documentos/?estado=&pagina=`: listado paginado. Un operador solo
  obtiene fuentes aprobadas; un aprobador también ve borradores y retiradas.
- `GET /api/documentos/<id>/`: metadatos y `contenido` completo; aplica el
  mismo filtro de visibilidad. El POST de creación y las operaciones de
  aprobar/retirar conservan sus rutas y permisos anteriores.
- `POST /api/acciones/<id>/finalizar/`: requiere aprobador activo, estado
  `aprobada` y tipo `reembolso` o `modificar_poliza`. Recibe `referencia`
  (3–100 caracteres) y `motivo` (mínimo 3). Devuelve la acción completada.
  Una repetición o estado incompatible devuelve 409; faltantes, 400.
- La representación de acción agrega `finalizacion`, nulo o un objeto con
  `funcionario`, `fecha`, `referencia` y `motivo`. La aprobación original en
  `resuelta_por`/`resuelta_en` se conserva.
- Los resultados documentales incluyen `fragmento_id`, que permite comprobar
  el respaldo de una cita exacta sin confiar en valores creados por el modelo.

Estas extensiones se apoyan en `11_finalizaciones_acciones.sql`. El detalle
de entrega y las reglas de prima cero están en `ENTREGA_MVP2.md`.

### Convenciones generales
- Mismo origen que el front (Django sirve ambos; sin CORS). JSON UTF-8. Campos en `snake_case`, en español.
- **Sesión** de Django. El front llama `GET /api/auth/csrf/` al cargar y manda `X-CSRFToken` (valor de la cookie `csrftoken`) en todo `POST`/`PATCH`.
- **Fechas y horas:** ISO 8601 en UTC (`"2024-04-01T12:15:00Z"`). Fechas sin hora: `"2024-11-30"`.
- **Dinero:** string con 2 decimales (`"12500.00"`). Nunca número.
- **Listados paginados:** `?pagina=1` (25 por página) → `{"total": 57, "pagina": 1, "por_pagina": 25, "resultados": [...]}`.
- **Errores:** siempre `{"error": {"codigo": "<slug>", "mensaje": "<texto en español para mostrar>"}}`.

| HTTP | Cuándo | `codigo` |
|---|---|---|
| 400 | datos inválidos / incompletos | `datos_invalidos`, `parametros_incompletos` |
| 401 | sin sesión | `no_autenticado` |
| 403 | sin permiso / sin CSRF | `permiso_denegado` |
| 404 | no existe | `no_encontrado` |
| 405 | método no permitido | `metodo_no_permitido` |
| 409 | el estado no permite la operación | `estado_invalido`, `ventana_24h_cerrada` |

**Aprobador** = funcionario con `puede_aprobar=true`. Lo hace cumplir el back; el front solo oculta botones.

## Endpoints
| Método y ruta | Permiso | Cuerpo → Respuesta |
|---|---|---|
| `GET /api/auth/csrf/` | público | → `204` + cookie `csrftoken` |
| `POST /api/auth/login/` | público | `{email, password}` → `200 me`; malas credenciales `401`; sin funcionario activo `403` |
| `POST /api/auth/logout/` | sesión | → `204` |
| `GET /api/auth/me/` | sesión | → `me` |
| `GET /api/pendientes/` | sesión | → `{acciones, derivaciones, alertas_criticas}` |
| `GET /api/conversaciones/` | sesión | `?estado=abierta\|cerrada&con_alertas=1&esperando_humano=1&q=&pagina=` → página de `conversacion_resumen` |
| `GET /api/conversaciones/{id}/` | sesión | → `conversacion_detalle` |
| `GET /api/conversaciones/{id}/mensajes/` | sesión | `?despues_de={mensaje_id}` → `{"mensajes": [mensaje…]}` (cronológico) |
| `POST /api/conversaciones/{id}/tomar/` | sesión | → `200 conversacion_detalle` |
| `POST /api/conversaciones/{id}/devolver/` | sesión | → `200 conversacion_detalle` |
| `POST /api/conversaciones/{id}/responder/` | sesión | `{texto}` → `201 mensaje` |
| `POST /api/mensajes/{id}/liberar/` | aprobador | `{texto_corregido?}` → `200 mensaje` (el que sale al cliente) |
| `POST /api/mensajes/{id}/descartar/` | aprobador | `{motivo}` → `200 mensaje` |
| `GET /api/alertas/` | sesión | `?tipo=&severidad=&estado=` (por defecto `abierta`) → página de `alerta` |
| `GET /api/consultas/cerradas-con-alertas/` | sesión | → página de `consulta_resumen` |
| `POST /api/consultas/{id}/reabrir/` | aprobador | → `200 consulta_resumen` |
| `GET /api/acciones/` | sesión | `?estado=` (por defecto `pendiente`; admite `aprobada` para gestión externa) → página de `accion` |
| `GET /api/acciones/{id}/` | sesión | → `accion`; una baja pendiente sin póliza agrega `polizas_disponibles` del cliente validado o `poliza_no_disponible` |
| `PATCH /api/acciones/{id}/parametros/` | aprobador | `{parametros: {...}}` → `200 accion`; para una baja, `parametros.poliza` es el id real de una póliza del cliente validado y se guarda en `accion.poliza` |
| `POST /api/acciones/{id}/aprobar/` | aprobador | `{motivo?}` → `200 accion` |
| `POST /api/acciones/{id}/rechazar/` | aprobador | `{motivo}` → `200 accion` |
| `GET /api/derivaciones/` | sesión | `?atendidas=1` → página de `derivacion` (del usuario) |
| `POST /api/derivaciones/{id}/atender/` | sesión (el asignado) | → `200 derivacion` |
| `GET /api/clientes/` | sesión | `?q=&pagina=` → página de `cliente_resumen` |
| `POST /api/clientes/` | aprobador | `{dni, nombre, apellido, telefono, email?}` → `201 cliente_detalle` |
| `GET /api/clientes/{id}/` | sesión | → `cliente_detalle` |
| `PATCH /api/clientes/{id}/` | aprobador | `{dni?, nombre?, apellido?, telefono?, email?}` → `200 cliente_detalle` |
| `POST /api/clientes/{id}/baja/` | aprobador | → `200 cliente_detalle` (baja lógica) |
| `POST /api/clientes/{id}/reactivar/` | aprobador | → `200 cliente_detalle` |
| `GET /api/polizas/{id}/` | sesión | → `poliza_detalle` |
| `POST /api/polizas/{id}/pagos/` | aprobador | `{referencia, importe}` → `200 poliza_detalle` + movimiento `pago`; solo importe completo de la próxima cuota impaga. La referencia repetida con los mismos datos es idempotente; con póliza o importe distinto da `409 estado_invalido`. |
| `GET /api/siniestros/` | sesión | `?estado=denunciado\|en_evaluacion\|aprobado\|rechazado\|cerrado` → página de expedientes |
| `POST /api/siniestros/` | funcionario activo | `{cliente_id, poliza_id, fecha_ocurrencia, descripcion}` → `201 expediente`; valida titularidad y que la ocurrencia sea pasada y esté dentro de la cobertura |
| `GET /api/siniestros/{id}/` | sesión | → expediente con historial y responsable/fecha de cada registro |
| `POST /api/siniestros/{id}/transiciones/` | aprobador | `{estado, motivo}` → expediente actualizado; solo permite el estado siguiente válido y registra al responsable y fecha |
| `POST /api/siniestros/{id}/adjuntos/` | funcionario activo | multipart `archivo` → `201 expediente`; acepta JPEG, PNG o WebP de hasta 10 MiB, valida/re-encoda y guarda fuera de la web pública |
| `GET /api/siniestros/{id}/adjuntos/{adjunto_id}/` | sesión | → archivo descargable; solo si pertenece al expediente indicado |
| `GET /api/reportes/gestion/` | funcionario activo | `?desde=AAAA-MM-DD&hasta=AAAA-MM-DD&formato=json\|csv` → indicadores filtrados; JSON por defecto, CSV descargable con el mismo período |
| `GET /api/documentos/buscar/` | funcionario activo | `?q=` (hasta 300 caracteres) → coincidencias lexicales con título, versión, referencia y pasaje de fuentes aprobadas; sin respaldo responde con `respaldo_suficiente=false` y resultados vacíos |
| `POST /api/documentos/` | aprobador | `{titulo, version, referencia, contenido}` → `201` documento en borrador |
| `POST /api/documentos/{id}/aprobar/` | aprobador | → cambia un borrador a aprobado, con responsable y fecha |
| `POST /api/documentos/{id}/retirar/` | aprobador | → retira una fuente aprobada y la excluye de búsquedas |

La búsqueda devuelve `{"respaldo_suficiente": true|false, "mensaje": "...",
"resultados": [...]}`. Cada resultado incluye `documento_id`, `titulo`,
`version`, `referencia`, `pasaje`, `coincidencias` y `terminos_consulta`.
Cuando no hay respaldo suficiente, `resultados` es `[]`; no se genera una
respuesta alternativa.

**No son de la API JSON pero también los hace T2:** `GET /webhook/whatsapp/` (verificación de Meta, responde el `hub.challenge` como texto) y `POST /webhook/whatsapp/` (mensajes entrantes); y las páginas del front (ver spec T2).

## Objetos
```jsonc
// me
{"id": 2, "nombre": "Graciela", "email": "graciela@…", "rol": "administracion", "puede_aprobar": true}

// conversacion_resumen
{"id": 4, "whatsapp": "+5491155551001",
 "cliente": {"id": 1, "nombre": "Laura", "apellido": "Fernández"},     // null si es desconocido
 "estado": "abierta", "modo": "bot",
 "atendida_por": {"id": 2, "nombre": "Graciela"},                       // null
 "ultimo_mensaje": {"texto": "…", "emisor": "bot", "fecha_hora": "2024-04-05T03:00:05Z"},   // null si no hay
 "alertas_abiertas": 3, "severidad_maxima": "alta",                     // null si no hay alertas
 "derivacion_urgente": false, "color": "naranja",                      // urgencia sin atender pinta rojo sin inventar alerta
 "respuestas_retenidas": 1, "sin_respuesta": false, "ventana_24h_abierta": true}

// conversacion_detalle = conversacion_resumen + 
{"nombre_perfil": "Daniel",   // nombre del perfil de WhatsApp, para prellenar el alta; null si no hay
 "cliente_info": {"id": 1, "dni": "27345678", "nombre": "Laura", "apellido": "Fernández",
                  "polizas": [poliza_resumen…]},                       // null si es desconocido
 "alertas": [alerta…]}

// poliza_resumen
{"id": 1, "numero_poliza": "POL-00101", "tipo_seguro": "Automotor", "cobertura": "intermedia", "estado": "vigente",
 "fecha_vencimiento": "2024-05-31", "saldo_pendiente": "8000.00", "proximo_vencimiento_pago": "2024-04-15"}

// `POST /api/polizas/{id}/pagos/` body y campo agregado a poliza_detalle
{"referencia": "POS-845102", "importe": "8000.00"}
{"pago": {"id": 4, "referencia": "POS-845102", "cuota_id": 13, "importe": "8000.00",
          "fecha_pago": "2024-04-15", "responsable": {"id": 2, "nombre": "Graciela"}}}

// mensaje
{"id": 21, "direccion": "saliente", "emisor": "bot", "funcionario": null,   // {"id","nombre"} si emisor funcionario
 "texto": "…", "estado_envio": "retenido", "fecha_hora": "…", "alertas": [7, 8]}

// alerta
{"id": 7, "conversacion_id": 4, "consulta_id": 11, "mensaje_id": 21, "tipo": "dato_inventado",
 "severidad": "alta", "descripcion": "…", "estado": "abierta", "creada_en": "…"}

// consulta_resumen
{"id": 4, "codigo_caso": "CASO-004", "conversacion_id": 9, "cliente": {"id","nombre","apellido"} | null,
 "tipo_consulta": "vencimiento", "estado": "cerrado", "alertas_abiertas": 1, "severidad_maxima": "alta"}

// accion
{"id": 1, "tipo_accion": "baja_poliza", "estado": "pendiente", "consulta_id": 5, "conversacion_id": 6,
 "cliente": {"id","nombre","apellido"} | null, "poliza": {"id": 7, "numero_poliza": "POL-00107"} | null,
 "parametros": {}, "solicitada_en": "…", "resuelta_por": {"id","nombre"} | null, "resuelta_en": null, "motivo": null}
// `estado` = `pendiente` (espera aprobación), `aprobada` (aún requiere gestión externa),
// `ejecutada` (efecto comprobado) o `rechazada`. El contador incluye `pendiente` y `aprobada`.
// Para una baja pendiente sin póliza, `GET /api/acciones/{id}/` agrega:
// {"polizas_disponibles": [{"id": 7, "numero_poliza": "POL-00107", "estado": "vigente",
//                           "bien_asegurado": "…"}]}
// Si no hay contacto vinculado o pólizas, devuelve `polizas_disponibles: []` y
// `poliza_no_disponible` con el motivo. La selección por PATCH valida existencia y titularidad.

// derivacion
{"id": 1, "consulta_id": 8, "conversacion_id": 8, "prioridad": "urgente", "motivo": "…", "creada_en": "…", "atendida_en": null}

// cliente_resumen
{"id": 1, "dni": "27345678", "nombre": "Laura", "apellido": "Fernández", "email": "…", "activo": true, "polizas_vigentes": 2}

// cliente_detalle
{"id": 1, "dni": "…", "nombre": "…", "apellido": "…", "email": "…", "activo": true,
 "contactos": ["+5491155551001"], "polizas": [poliza_resumen…], "siniestros": [siniestro…]}

// poliza_detalle = poliza_resumen + 
{"cliente": {"id","nombre","apellido"}, "fecha_inicio": "2023-06-01", "prima_mensual": "8000.00", "bien_asegurado": "…",
 "conductores": [{"nombre": "…", "dni": "…", "relacion": "titular"}],
 "cuotas": [{"periodo": "2024-04-01", "importe": "8000.00", "vencimiento": "2024-04-15", "estado": "pendiente"}],
 "siniestros": [siniestro…]}

// siniestro
{"numero_siniestro": "SIN-2024-00001", "fecha_ocurrencia": "2024-03-31", "descripcion": "…", "estado": "denunciado"}

// expediente de siniestro: respuesta de listado, detalle, registro y transición
{"id": 7, "numero_siniestro": "SIN-2024-00001",
 "cliente": {"id": 1, "nombre": "Laura", "apellido": "Fernández"},
 "poliza": {"id": 2, "numero_poliza": "POL-00101"},
 "fecha_ocurrencia": "2024-03-31", "descripcion": "Daño por granizo",
 "estado": "en_evaluacion", "creado_en": "2024-04-01T12:15:00Z",
 "adjuntos": [{"id": 4, "content_type": "image/jpeg", "tamano": 12345,
               "origen": "panel", "creado_en": "2024-04-01T12:15:00Z",
               "descarga_url": "/api/siniestros/7/adjuntos/4/"}],
 "historial": [{"estado_anterior": "denunciado", "estado_nuevo": "en_evaluacion",
                "motivo": "Inicia la revisión documental.",
                "responsable": {"id": 2, "nombre": "Graciela"},
                "fecha": "2024-04-01T12:15:00Z"}],
 "aclaracion_decision": "Las decisiones del expediente son internas y no confirman ni prometen una indemnización de la aseguradora."}
```

El grafo permitido es `denunciado → en_evaluacion → aprobado|rechazado →
cerrado`; no se permiten saltos ni modificaciones una vez cerrado. Todo
funcionario activo puede registrar una denuncia; los cambios de estado requieren
un aprobador activo y un motivo de al menos tres caracteres. La fecha del evento
se asigna en el servidor. La evaluación o aprobación interna no decide ni promete
una indemnización.

La carga desde panel admite JPEG, PNG o WebP (hasta 10 MiB y 20 megapíxeles).
No se conserva el nombre original ni se publica una URL de medios; tanto carga
como descarga requieren sesión de funcionario. WhatsApp admite JPEG o PNG de
hasta 5 MiB; exige el número exacto del expediente en el caption y titularidad
validada entre contacto, cliente y póliza. Ver
[adjuntos privados](../adjuntos_siniestros.md) para los detalles de
almacenamiento y recepción de media.

El reporte define períodos inclusivos y fechas distintas para consultas,
derivaciones y cobros. Las métricas y una muestra calculada a mano están en
[reportes de gestión](../reportes_gestion.md).

La consulta documental y sus límites están descritos en
[consulta documental local](../documentos_generales.md).
