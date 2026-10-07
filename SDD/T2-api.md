# T2 · Backend: conexión con el frontend (API REST)

**Se ejecuta:** 3.º (después de T3) · **Branch:** `tarea-2-api` (desde `main` con T4 y T3 integradas)
**Pegarle a la IA:** `SDD/00-comun.md` + este archivo + `SDD/contratos/api.md` + `SDD/contratos/servicios.md` + (como referencia de lectura) la sección 3 de `SDD/contratos/modelos.md` + `SDD/entregas/T4.md` y `T3.md`.
**Produce:** lo que define `SDD/contratos/api.md`. T1 lo usa.

## 1. Objetivo
Exponer el sistema por HTTP: la API JSON que consume el front, la sesión y los permisos, el formato común de errores, el webhook que recibe WhatsApp, y la entrega de las páginas y estáticos del front. **Esta capa no tiene reglas de negocio:** valida la entrada, llama a `negocio` (escrituras) o a `datos.selectors` (lecturas), y traduce resultados y errores a JSON y códigos HTTP.

## 2. Archivos que podés crear o modificar
Todo dentro de `api/`. En `config/settings.py`, **solo** agregar: el bloque `REST_FRAMEWORK`, `STATICFILES_DIRS = [BASE_DIR / "frontend" / "static"]`, `STATIC_URL = "/static/"` y las opciones de cookies (`CSRF_COOKIE_HTTPONLY = False`, `SESSION_COOKIE_HTTPONLY = True`). **No toques** `datos/`, `negocio/`, `frontend/`. Si necesitás algo que T3 o T4 no ofrecen, es una pregunta para la entrega.

## 3. Etapas y criterios de aceptación

### Etapa A · Configuración, permisos y errores
| ID | Criterio |
|---|---|
| AC-T2-01 | Dado `REST_FRAMEWORK`, entonces usa `SessionAuthentication`, permiso por defecto `api.permisos.EsFuncionario`, renderer solo JSON, y `EXCEPTION_HANDLER = "api.errores.manejar"`. |
| AC-T2-02 | Dado `EsFuncionario`, entonces un anónimo recibe 401 `no_autenticado` y un usuario sin funcionario activo 403 `permiso_denegado`. Dado `EsAprobador`, un operador recibe 403 `permiso_denegado`. El funcionario se obtiene con `negocio.sesion.funcionario_de` y queda en `request.funcionario`. |
| AC-T2-03 | Dado cualquier error, entonces la respuesta es `{"error": {"codigo", "mensaje"}}`: `DatosInvalidos`/`ParametrosIncompletos` → 400, `PermisoDenegado` → 403, `NoEncontrado` y `DoesNotExist`/`Http404` → 404, `EstadoInvalido` → 409 (con su `codigo`, p. ej. `ventana_24h_cerrada`), errores de validación de serializers → 400 `datos_invalidos`, método no permitido → 405 `metodo_no_permitido`. Un error inesperado → 500 con mensaje genérico, sin detalles internos. |
| AC-T2-04 | Dado un `POST`/`PATCH` con sesión sin header `X-CSRFToken` válido, entonces 403. `GET /api/auth/csrf/` responde 204 y entrega la cookie `csrftoken`. |
| AC-T2-05 | Dado un listado, entonces `?pagina=N` (25 por página) devuelve `{total, pagina, por_pagina, resultados}`; página fuera de rango → 404. Dinero como string con 2 decimales; fechas ISO; horas ISO en UTC con `Z`. |

### Etapa B · Sesión y utilidades
| ID | Criterio |
|---|---|
| AC-T2-06 | Dado `POST /api/auth/login/` con email y clave correctos de un funcionario activo, entonces 200 con `me` y sesión abierta; clave incorrecta → 401; usuario sin funcionario activo → 403. |
| AC-T2-07 | Dado `GET /api/auth/me/` con sesión → 200 `me`; sin sesión → 401. `POST /api/auth/logout/` → 204 y la sesión se cierra. |
| AC-T2-08 | Dado `GET /api/pendientes/`, entonces responde `contar_pendientes(request.funcionario.id)`. |
| AC-T2-09 | Dado `python manage.py crear_usuarios_funcionarios --clave <clave>`, entonces crea o actualiza un `User` por cada funcionario activo (username = email), sin imprimir la clave; sin `--clave` falla con un mensaje claro. |

### Etapa C · Supervisión
| ID | Criterio |
|---|---|
| AC-T2-10 | Dado `GET /api/conversaciones/`, entonces usa `selectors.bandeja(...)` con los filtros de la query y devuelve `conversacion_resumen`, con `severidad_maxima = severidad_por_rango(...)`, `color = color_por_severidad(...)`, `sin_respuesta` y `ventana_24h_abierta` calculados con `negocio.reglas` (con `ahora = timezone.now()`). |
| AC-T2-11 | Dado `GET /api/conversaciones/{id}/`, entonces devuelve `conversacion_detalle`: `cliente_info` con las pólizas de `resumen_polizas` (o `null` si el contacto no tiene cliente) y las alertas abiertas de la conversación. Inexistente → 404. |
| AC-T2-12 | Dado `GET /api/conversaciones/{id}/mensajes/?despues_de=N`, entonces devuelve `{"mensajes": [...]}` de `mensajes_de(id, N)`, cada uno con los ids de sus alertas. |
| AC-T2-13 | Dados `POST …/tomar/`, `…/devolver/`, `…/responder/`, `/api/mensajes/{id}/liberar/`, `/api/mensajes/{id}/descartar/` y `/api/consultas/{id}/reabrir/`, entonces cada uno llama a la función de `negocio.supervision` correspondiente con `request.funcionario.id` y devuelve el objeto del contrato (`responder` → 201). Los marcados "aprobador" en el contrato exigen `EsAprobador`. |
| AC-T2-14 | Dados `GET /api/alertas/` y `GET /api/consultas/cerradas-con-alertas/`, entonces usan `listar_alertas` y `consultas_cerradas_con_alertas` con los filtros de la query, paginados. |

### Etapa D · Acciones y derivaciones
| ID | Criterio |
|---|---|
| AC-T2-15 | Dados `GET /api/acciones/` y `GET /api/acciones/{id}/`, entonces devuelven `accion` desde `listar_acciones` (filtro `estado`). |
| AC-T2-16 | Dados `POST …/aprobar/`, `POST …/rechazar/` y `PATCH …/parametros/`, entonces exigen aprobador y llaman a `aprobar_accion`, `rechazar_accion` y `completar_parametros`; los errores se traducen según AC-T2-03 (p. ej. faltan parámetros → 400 `parametros_incompletos`, ya resuelta → 409). |
| AC-T2-17 | Dados `GET /api/derivaciones/` (`?atendidas=1`) y `POST /api/derivaciones/{id}/atender/`, entonces usan `derivaciones_de(request.funcionario.id, …)` y `atender_derivacion`; atender una ajena → 403. |

### Etapa E · Clientes y pólizas (solo lectura)
| ID | Criterio |
|---|---|
| AC-T2-18 | Dados `GET /api/clientes/?q=`, `GET /api/clientes/{id}/` y `GET /api/polizas/{id}/`, entonces devuelven `cliente_resumen`, `cliente_detalle` y `poliza_detalle` desde `buscar_clientes`, `detalle_cliente` (+ `resumen_polizas`) y `detalle_poliza`; sobre `/api/polizas/{id}/` cualquier escritura → 405, y sobre clientes `PUT`/`DELETE` → 405 (el ABM usa `POST` en la colección y `PATCH` en el detalle: AC-T2-22 y AC-T2-23). |

### Etapa F · Webhook de WhatsApp y páginas del front
| ID | Criterio |
|---|---|
| AC-T2-19 | Dado `GET /webhook/whatsapp/` con `hub.mode`, `hub.verify_token` y `hub.challenge`, entonces responde 200 con el challenge como `text/plain` si `verificar_suscripcion` lo devuelve; si no, 403. |
| AC-T2-20 | Dado `POST /webhook/whatsapp/`, entonces (sin CSRF, sin sesión) verifica la firma con `verificar_firma(request.body, header)` **antes** de parsear: inválida → 403 y no se llama a nada; JSON inválido → 400; válido → llama `procesar_webhook(payload)` y responde 200 aunque el payload no tenga mensajes. |
| AC-T2-21 | Dadas las rutas `/` (login), `/panel/` (bandeja), `/panel/conversacion/`, `/panel/alertas/`, `/panel/cerrados/`, `/panel/acciones/`, `/panel/derivaciones/`, `/panel/clientes/`, `/panel/cliente/`, entonces Django devuelve el archivo correspondiente de `frontend/pages/` (`login.html`, `bandeja.html`, `conversacion.html`, `alertas.html`, `cerrados.html`, `acciones.html`, `derivaciones.html`, `clientes.html`, `cliente.html`) con una lista blanca fija; otra ruta → 404; si el archivo todavía no existe (T1 no lo hizo), 404. Los JS/CSS se sirven en `/static/`. Las páginas no necesitan sesión (no contienen datos). |
| AC-T2-22 | Dado `POST /api/clientes/` con `{dni, nombre, apellido, telefono, email?}`, entonces responde **201** con `cliente_detalle`; los datos sucios o repetidos son 400 `datos_invalidos` y falta de un campo obligatorio también; un funcionario sin `puede_aprobar` recibe 403 `permiso_denegado` y sin sesión 401, mientras que los `GET` de clientes siguen abiertos a cualquier funcionario. |
| AC-T2-23 | Dados `PATCH /api/clientes/{id}/`, `POST /api/clientes/{id}/baja/` y `POST /api/clientes/{id}/reactivar/`, entonces responden 200 con `cliente_detalle`; el PATCH actualiza solo lo recibido y con datos inválidos es 400 sin cambiar nada; la baja con pólizas vigentes y la reactivación de un cliente activo son 409 `estado_invalido`; un id inexistente es 404; las tres exigen `puede_aprobar`. |

## 4. Diseño (guía para la IA)
- `api/permisos.py`, `api/errores.py` (manejador), `api/serializers.py` (solo traducen; nada de reglas), `api/views.py` (`APIView` o vistas de función con `@api_view`), `api/webhook.py`, `api/paginas.py` (`FileResponse` de `BASE_DIR / "frontend" / "pages" / <archivo>`), `api/paginacion.py`, `api/urls.py`.
- Para `conversacion_resumen` el `ultimo_mensaje` sale de las anotaciones de `bandeja` (`ultimo_texto`, `ultimo_emisor`, `ultimo_fecha_hora`); si no hay mensajes, `null`.
- Login: `django.contrib.auth.authenticate(username=email, password=…)` + `login()`; vista con `@ensure_csrf_cookie` en `csrf`.
- El webhook es una vista de Django común (`@csrf_exempt`), no de DRF.
- Tests con `rest_framework.test.APIClient` y las fábricas de T4; `APIClient(enforce_csrf_checks=True)` en el test de CSRF. Para `procesar_webhook` y el envío por WhatsApp, `WHATSAPP_MODO=simulado` y `unittest.mock.patch` de `en_segundo_plano`.

## 5. Cómo comprobar
```bash
python manage.py test api
python manage.py runserver
#   GET http://localhost:8000/api/auth/me/  -> 401 en JSON con el formato de error
python SDD/verificar.py T2
```
**Terminado cuando:** todos los AC-T2 tienen test en verde y `SDD/entregas/T2.md` está completo, con la lista de endpoints probados a mano.
