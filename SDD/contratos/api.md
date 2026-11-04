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
| `POST /api/conversaciones/{id}/desbloquear/` | aprobador | Levanta el bloqueo de 48 h por insistencia del número; resuelve su alerta → `200 conversacion_detalle`. `409` si no está bloqueado |
| `POST /api/conversaciones/{id}/vaciar-alertas/` | aprobador | Descarta las alertas abiertas de la conversación (`descartada`, firmadas; no se borran) → `200 conversacion_detalle`. `409` si hay una respuesta retenida sin resolver |
| `POST /api/conversaciones/{id}/borrar/` | aprobador | Borra la conversación con sus mensajes, casos y alertas, sin vuelta atrás → `200 {id, borrados: {mensajes, casos, alertas}}`. `409` si tiene acciones administrativas, siniestros o fotos de siniestro asociados |
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
| `POST /api/clientes/` | aprobador | `{dni, nombre, apellido, telefono, email?}` → `201 cliente_detalle` |
| `GET /api/clientes/{id}/` | sesión | → `cliente_detalle` |
| `PATCH /api/clientes/{id}/` | aprobador | `{dni?, nombre?, apellido?, telefono?, email?}` → `200 cliente_detalle` |
| `POST /api/clientes/{id}/baja/` | aprobador | → `200 cliente_detalle` (baja lógica) |
| `POST /api/clientes/{id}/reactivar/` | aprobador | → `200 cliente_detalle` |
| `GET /api/polizas/{id}/` | sesión | → `poliza_detalle` |
| `POST /api/clientes/{id}/polizas/` | aprobador | `{tipo_seguro, cobertura, fecha_inicio, fecha_vencimiento, prima_mensual, bien_asegurado?, numero_poliza?, vehiculo_id?, compania_id?, comision_pct?}` → `201 poliza_detalle` (P1 agregó los tres últimos) |
| `GET /api/vehiculos/` | sesión | `?cliente=N` (obligatorio) → `{"resultados": [vehiculo…]}` (solo activos, por patente) |
| `POST /api/vehiculos/` | aprobador | `{cliente, patente, marca, modelo, anio, uso?, chasis?, valor_asegurado?}` → `201 vehiculo`. Patente repetida o inválida, año, marca/modelo vacíos, valor ≤ 0 o cliente inactivo → `400`; cliente inexistente → `404` |
| `PATCH /api/vehiculos/{id}/` | aprobador | cualquiera de los campos anteriores (menos `cliente`) → `200 vehiculo`. Ausente = no cambia; `chasis`/`valor_asegurado` vacíos o `null` lo borran |
| `POST /api/vehiculos/{id}/baja/` | aprobador | → `200 vehiculo` (baja lógica). `409` si tiene una póliza vigente o ya estaba de baja |
| `GET /api/companias/` | sesión | `?activas=1` → `{"resultados": [compania…]}` (por nombre; sin el filtro, también las desactivadas) |
| `POST /api/companias/` | aprobador | `{nombre, comision_pct}` → `201 compania`. Nombre repetido (sin distinguir mayúsculas ni espacios) o comisión fuera de 0–100 → `400` |
| `PATCH /api/companias/{id}/` | aprobador | `{nombre?, comision_pct?, activa?}` → `200 compania` (`activa` activa o desactiva) |

`PUT` y `DELETE` sobre `/api/vehiculos/…` y `/api/companias/…` → `405`.

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
{"nombre_perfil": "Daniel",   // nombre del perfil de WhatsApp, para prellenar el alta; null si no hay
 "bloqueado_hasta": "2024-04-07T03:00:05Z",   // hasta cuándo el bot ignora al número por insistir; null si no está bloqueado
 "cliente_info": {"id": 1, "dni": "27345678", "nombre": "Laura", "apellido": "Fernández",
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
{"id": 1, "dni": "27345678", "nombre": "Laura", "apellido": "Fernández", "email": "…", "activo": true, "polizas_vigentes": 2}

// cliente_detalle
{"id": 1, "dni": "…", "nombre": "…", "apellido": "…", "email": "…", "activo": true,
 "contactos": ["+5491155551001"], "polizas": [poliza_resumen + vehiculo/compania/comision_pct…],   // P1: ver más abajo
 "vehiculos": [vehiculo…],                                                                          // P1: solo los activos
 "siniestros": [siniestro…]}

// poliza_detalle = poliza_resumen + 
{"cliente": {"id","nombre","apellido"}, "fecha_inicio": "2023-06-01", "prima_mensual": "8000.00", "bien_asegurado": "…",
 "conductores": [{"nombre": "…", "dni": "…", "relacion": "titular"}],
 "cuotas": [{"periodo": "2024-04-01", "importe": "8000.00", "vencimiento": "2024-04-15", "estado": "pendiente"}],
 "siniestros": [siniestro…]}

// vehiculo (P1)
{"id": 3, "cliente": 1, "patente": "AB123CD", "marca": "Toyota", "modelo": "Corolla", "anio": 2020,
 "uso": "particular",            // particular | comercial | remis_taxi | carga
 "chasis": null, "valor_asegurado": "15000000.00" /* o null */, "activo": true}

// compania (P1)
{"id": 2, "nombre": "La Caja", "comision_pct": "12.50", "activa": true}   // comision_pct es null para un operador

// P1: toda póliza de cliente_detalle y de poliza_detalle suma
//   "vehiculo": vehiculo | null, "compania": compania | null, "comision_pct": "12.50" | null
// y `comision_pct` (el de la póliza y el de la compañía) es null si quien consulta no es aprobador: la comisión es del dueño.
// `GET /api/clientes/?q=` también encuentra por patente (con o sin espacios).

// siniestro
{"numero_siniestro": "SIN-2024-00001", "fecha_ocurrencia": "2024-03-31", "descripcion": "…", "estado": "denunciado"}
```
