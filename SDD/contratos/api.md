# Contrato · API REST (`/api/`)

**Lo implementa:** T2 · **Lo usa:** T1.
Cambiar un endpoint o una forma de respuesta requiere acuerdo de las 4 personas.

## Convenciones
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
| `GET /api/acciones/` | sesión | `?estado=` (por defecto `pendiente`) → página de `accion` |
| `GET /api/acciones/{id}/` | sesión | → `accion` |
| `PATCH /api/acciones/{id}/parametros/` | aprobador | `{parametros: {...}}` → `200 accion` |
| `POST /api/acciones/{id}/aprobar/` | aprobador | `{motivo?}` → `200 accion` |
| `POST /api/acciones/{id}/rechazar/` | aprobador | `{motivo}` → `200 accion` |
| `GET /api/derivaciones/` | sesión | `?atendidas=1` → página de `derivacion` (del usuario) |
| `POST /api/derivaciones/{id}/atender/` | sesión (el asignado) | → `200 derivacion` |
| `GET /api/clientes/` | sesión | `?q=&pagina=` → página de `cliente_resumen` |
| `GET /api/clientes/{id}/` | sesión | → `cliente_detalle` |
| `GET /api/polizas/{id}/` | sesión | → `poliza_detalle` |

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
 "color": "naranja",                                                    // rojo | naranja | amarillo | verde
 "respuestas_retenidas": 1, "sin_respuesta": false, "ventana_24h_abierta": true}

// conversacion_detalle = conversacion_resumen + 
{"cliente_info": {"id": 1, "dni": "27345678", "nombre": "Laura", "apellido": "Fernández",
                  "polizas": [poliza_resumen…]},                       // null si es desconocido
 "alertas": [alerta…]}

// poliza_resumen
{"id": 1, "numero_poliza": "POL-00101", "tipo_seguro": "Automotor", "cobertura": "intermedia", "estado": "vigente",
 "fecha_vencimiento": "2024-05-31", "saldo_pendiente": "8000.00", "proximo_vencimiento_pago": "2024-04-15"}

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

// derivacion
{"id": 1, "consulta_id": 8, "conversacion_id": 8, "prioridad": "urgente", "motivo": "…", "creada_en": "…", "atendida_en": null}

// cliente_resumen
{"id": 1, "dni": "27345678", "nombre": "Laura", "apellido": "Fernández", "email": "…", "polizas_vigentes": 2}

// cliente_detalle
{"id": 1, "dni": "…", "nombre": "…", "apellido": "…", "email": "…",
 "contactos": ["+5491155551001"], "polizas": [poliza_resumen…], "siniestros": [siniestro…]}

// poliza_detalle = poliza_resumen + 
{"cliente": {"id","nombre","apellido"}, "fecha_inicio": "2023-06-01", "prima_mensual": "8000.00", "bien_asegurado": "…",
 "conductores": [{"nombre": "…", "dni": "…", "relacion": "titular"}],
 "cuotas": [{"periodo": "2024-04-01", "importe": "8000.00", "vencimiento": "2024-04-15", "estado": "pendiente"}],
 "siniestros": [siniestro…]}

// siniestro
{"numero_siniestro": "SIN-2024-00001", "fecha_ocurrencia": "2024-03-31", "descripcion": "…", "estado": "denunciado"}
```
