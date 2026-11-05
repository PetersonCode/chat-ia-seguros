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
| `POST /api/conversaciones/{id}/borrar/` | aprobador | Borra la conversación con sus mensajes, casos y alertas, sin vuelta atrás → `200 {id, borrados: {mensajes, casos, alertas}}`. `409` si tiene acciones administrativas **pendientes**, siniestros o fotos de siniestro asociados. Las acciones ya resueltas no bloquean: su caso se conserva sin chat como auditoría |
| `POST /api/conversaciones/{id}/eliminacion-total/` | **administrador** (rol `administrador`; ni el propietario) | DELETE físico de todo el rastro del número: todas sus conversaciones, mensajes, casos, alertas, derivaciones, acciones (cualquier estado), borradores, avisos/encuestas/tareas de gestión, recordatorios, interesados (con historial y cotizaciones) y el contacto de WhatsApp. No toca al cliente ni a sus pólizas → `200 {id, borrados: {conversaciones, mensajes, casos, alertas, acciones, interesados, contacto}}`. `403` si no es administrador; `409` (sin borrar nada) si hay siniestros, fotos de siniestro o acciones finalizadas, que la base declara inmutables |
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
| `POST /api/clientes/{id}/eliminar-definitivo/` | **administrador** (rol `administrador`) | DELETE físico del cliente con sus vehículos, pólizas (cuotas, pagos, condiciones, documentos vinculados, acciones, renovaciones, recordatorios, avisos), notas, tareas, perfil, referidos, encuestas, interesados y el rastro de cada número de WhatsApp vinculado → `200 {id, borrados: {polizas, vehiculos, cuotas, interesados, numeros}}`. `403` si no es administrador; `409` (sin borrar nada) si hay siniestros, fotos de siniestro o acciones finalizadas |
| `POST /api/polizas/{id}/eliminar-definitivo/` | **administrador** | DELETE físico de la póliza con cuotas, pagos, conductores, condiciones y sus documentos generados, vínculos documentales, acciones, avisos, recordatorios, renovaciones y cotizaciones de renovación. Cliente y vehículo quedan → `200 {id, borrados: {polizas, cuotas}}`. `409` sin borrar nada si hay siniestros o acciones finalizadas |
| `POST /api/planes-cobertura/{id}/eliminar/` | **administrador** | DELETE del plan. Las pólizas que lo usaban conservan sus condiciones como particulares (sin plan) → `200 {id, borrados: {planes, polizas_con_condiciones_particulares}}` |
| `POST /api/companias/{id}/eliminar-definitivo/` | **administrador** | DELETE en cascada: todas sus pólizas (como arriba), sus planes y sus cotizaciones; los clientes quedan sin esas pólizas → `200 {id, borrados: {polizas, cuotas, planes, cotizaciones}}`. `409` sin borrar nada si alguna póliza tiene siniestros o acciones finalizadas |
| `POST /api/clientes/{id}/reactivar/` | aprobador | → `200 cliente_detalle` |
| `GET /api/polizas/{id}/` | sesión | → `poliza_detalle` |
| `POST /api/clientes/{id}/polizas/` | aprobador | `{tipo_seguro, cobertura, fecha_inicio, fecha_vencimiento, prima_mensual, bien_asegurado?, numero_poliza?, vehiculo_id?, compania_id?, comision_pct?, plan_id?}` → `201 poliza_detalle` (P1 agregó vehículo, compañía y comisión). `plan_id` debe ser de `compania_id`: copia sus condiciones a la póliza (documento aprobado para el bot) y, si el plan tiene `nivel`, la póliza toma ese nivel e ignora `cobertura`. `400` sin crear nada si el plan es de otra compañía. `poliza_detalle` incluye `plan {id, nombre, version}` o `null` y `condiciones_cargadas` |
| `GET /api/vehiculos/` | sesión | `?cliente=N` (obligatorio) → `{"resultados": [vehiculo…]}` (solo activos, por patente) |
| `POST /api/vehiculos/` | aprobador | `{cliente, patente, marca, modelo, anio, uso?, chasis?, valor_asegurado?}` → `201 vehiculo`. Patente repetida o inválida, año, marca/modelo vacíos, valor ≤ 0 o cliente inactivo → `400`; cliente inexistente → `404` |
| `PATCH /api/vehiculos/{id}/` | aprobador | cualquiera de los campos anteriores (menos `cliente`) → `200 vehiculo`. Ausente = no cambia; `chasis`/`valor_asegurado` vacíos o `null` lo borran |
| `POST /api/vehiculos/{id}/baja/` | aprobador | → `200 vehiculo` (baja lógica). `409` si tiene una póliza vigente o ya estaba de baja |
| `GET /api/companias/` | sesión | `?activas=1` → `{"resultados": [compania…]}` (por nombre; sin el filtro, también las desactivadas) |
| `POST /api/companias/` | aprobador | `{nombre, comision_pct}` → `201 compania`. Nombre repetido (sin distinguir mayúsculas ni espacios) o comisión fuera de 0–100 → `400` |
| `PATCH /api/companias/{id}/` | aprobador | `{nombre?, comision_pct?, activa?}` → `200 compania` (`activa` activa o desactiva) |

`PUT` y `DELETE` sobre `/api/vehiculos/…` y `/api/companias/…` → `405`.

**P5 · Embudo de interesados y cotizaciones.** Todo es de cualquier funcionario con sesión, salvo `convertir` (aprobador).
| Método y ruta | Permiso | Cuerpo → Respuesta |
|---|---|---|
| `GET /api/funcionarios/` | sesión | → `{"resultados": [{id, nombre, rol}…]}` (activos, por nombre). Para elegir responsable; no trae correo ni permisos |
| `GET /api/interesados/` | sesión | `?estado=&responsable=N\|me&origen=&q=&seguimiento_vencido=1&pagina=` → página de `interesado_item` (los de seguimiento vencido primero). Filtro inválido `400` |
| `POST /api/interesados/` | sesión | `{nombre, origen, telefono?, apellido?, datos?}` → `201 interesado_detalle + "ya_existia": false`; si el número ya tenía uno abierto, `200` con ese y `"ya_existia": true` |
| `GET /api/interesados/embudo/` | sesión | `?responsable=N\|me` → `{"conteos": {consulta, cotizando, documentacion, emitida, perdida}, "convertidos_mes", "perdidos_mes"}` |
| `GET /api/interesados/{id}/` | sesión | → `interesado_detalle` |
| `PATCH /api/interesados/{id}/` | sesión | `{responsable_id?, proximo_contacto?, datos?}` → `200 interesado_detalle`. Todo o nada. `proximo_contacto` `null` o `""` lo borra; fecha pasada `400` |
| `POST /api/interesados/{id}/mover/` | sesión | `{estado, nota?, motivo_perdida?}` → `200 interesado_detalle`. Transición inválida `409`; perder sin motivo `400` |
| `POST /api/interesados/{id}/convertir/` | aprobador | `{dni, nombre, apellido, email?, telefono?}` → `200 interesado_detalle`. Fuera de `documentacion` `409` |
| `GET /api/cotizaciones/` | sesión | `?interesado=N` **o** `?poliza=N` (uno solo) → `{"resultados": [cotizacion…]}` (de la más barata) |
| `POST /api/cotizaciones/` | sesión | `{interesado_id? \| poliza_id?, compania_id, cobertura, prima_mensual, vigencia_hasta?, notas?}` → `201 cotizacion` |
| `POST /api/cotizaciones/{id}/elegir/` | sesión | → `200 cotizacion` (desmarca la anterior del mismo destino) |
| `POST /api/cotizaciones/{id}/quitar/` | sesión | → `204`. La elegida: `409` |

Páginas nuevas en la lista blanca de `api/paginas.py`: `/panel/interesados/` y `/panel/interesado/?id=N`. **Pendiente de P3:** `renovacion_item` aún no existe, así que `variacion_pct` y `aumento_alto` (AC-T2-37) no están.

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

// interesado_item (P5) · `seguimiento_vencido` lo decide el servidor: proximo_contacto < hoy y el interesado sigue abierto
{"id": 7, "nombre": "Marta", "apellido": "Gómez" /* o null */, "origen": "web", "estado": "cotizando",
 "responsable": {"id": 2, "nombre": "Diego"} /* o null */, "proximo_contacto": "2026-11-06" /* o null */, "seguimiento_vencido": false,
 "motivo_perdida": null, "datos": {"patente": "AB123CD", "marca": "Toyota", "modelo": "Corolla", "anio": 2020, "uso": "particular", "localidad": "Rosario"},
 "cliente_id": null,
 "contacto": {"id": 4, "whatsapp": "+5491155550101", "nombre_perfil": null, "cliente_id": null} /* o null */,
 "creado_en": "2026-11-04T15:42:00Z", "actualizado_en": "2026-11-04T15:42:00Z"}

// interesado_detalle (P5) = interesado_item +
{"cliente": {"id","nombre","apellido"} /* o null */,
 "historial": [{"id", "estado_anterior": null | "consulta", "estado_nuevo": "consulta", "nota": null | "…", "funcionario": {"id","nombre"} | null /* el bot */, "fecha"}],  // viejo → nuevo
 "cotizaciones": [cotizacion…]}                                                                                                                                    // de la más barata

// cotizacion (P5)
{"id": 3, "interesado": 7 /* o null */, "poliza": null /* o id */, "compania": compania, "cobertura": "intermedia",   // basica | intermedia | total
 "prima_mensual": "16200.50", "vigencia_hasta": "2026-12-31" /* o null */, "elegida": false, "notas": null,
 "creada_por": {"id","nombre"}, "creada_en": "…"}                                                                       // compania.comision_pct es null para un operador

// siniestro
{"numero_siniestro": "SIN-2024-00001", "fecha_ocurrencia": "2024-03-31", "descripcion": "…", "estado": "denunciado"}
```
