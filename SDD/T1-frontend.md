# T1 · Frontend (JavaScript puro)

**Se ejecuta:** 4.º (última) · **Branch:** `tarea-1-frontend` (desde `main` con T4, T3 y T2 integradas)
**Pegarle a la IA:** `SDD/00-comun.md` + este archivo + `SDD/contratos/api.md` + `SDD/entregas/T2.md`.
**Usa:** solo la API de `SDD/contratos/api.md`. No lee Python.

## 1. Objetivo
Las pantallas del dashboard para Roberto, Graciela y Diego: login, bandeja de conversaciones con colores, detalle tipo chat con las respuestas retenidas y las acciones de supervisión, alertas, casos cerrados con alertas, acciones pendientes, derivaciones y consulta de clientes. **Toda la seguridad la hace el back** (R17); el front muestra lo que la API calcula (colores, `sin_respuesta`, permisos).

## 2. Archivos que podés crear o modificar
`frontend/` (todo), `package.json` y tildar ítems en `SDD/qa/T1.md`. **No toques** nada de Python.

Estructura:
```
frontend/pages/       login.html bandeja.html conversacion.html alertas.html cerrados.html
                      acciones.html derivaciones.html clientes.html cliente.html
frontend/static/css/app.css
frontend/static/js/api.js      único lugar con fetch
frontend/static/js/nav.js      barra superior
frontend/static/js/lib/        funciones PURAS (sin DOM ni red) -> se prueban con node --test
frontend/static/js/pages/      un módulo por página (DOM + api.js + lib/)
frontend/tests/                *.test.js
```
Cada página: `<nav id="nav"></nav>`, un `<main>` y `<script type="module" src="/static/js/pages/<pagina>.js">`. Sin JS en línea. Bootstrap 5 **solo CSS** por CDN (`cdn.jsdelivr.net`).

## 3. Etapas y criterios de aceptación
Los AC marcados **(QA)** se verifican abriendo la página con el back corriendo y tildando su línea en `SDD/qa/T1.md`. El resto, con `node --test`.

### Etapa A · Base: proyecto JS, cliente de API, formatos, login y barra
| ID | Criterio |
|---|---|
| AC-T1-01 | Dado `package.json`, entonces tiene `"type": "module"`, `"private": true`, el script `"test": "node --test"` y **ninguna** dependencia. |
| AC-T1-02 | Dado `api.js`, entonces exporta `api.get(url)`, `api.post(url, cuerpo)`, `api.patch(url, cuerpo)` y la clase `ApiError {status, codigo, mensaje}`; envían `Accept`/`Content-Type: application/json` y `X-CSRFToken` (leído de la cookie `csrftoken`); ante una respuesta de error lanzan `ApiError` con el `codigo` y `mensaje` del cuerpo; ante 401 redirigen a `/`. `fetch`, `document.cookie` y la redirección son inyectables (`configurarApi({fetch, leerCookie, redirigir})`) para testear sin navegador. |
| AC-T1-03 | Dado `lib/formato.js`: `formatearMonto("12500.00")` → `"$12.500"`, `formatearMonto("12500.50")` → `"$12.500,50"`, `formatearFecha("2024-04-15")` → `"15/04/2024"`, `formatearFechaHora("2024-04-01T12:15:00Z")` → `"01/04/2024 09:15"` (hora de Buenos Aires), y `null`/inválido → `"—"`. |
| AC-T1-04 | Dado `lib/debounce.js`, `debounce(fn, ms)` ejecuta `fn` una sola vez, `ms` después de la última llamada, con los últimos argumentos (test con temporizador simulado de `node:test`). |
| AC-T1-05 | **(QA)** Dado `/` (login), cuando se envía el formulario, entonces llama `POST /api/auth/login/`; si sale bien va a `/panel/`; si no, muestra el `mensaje` del error sin recargar. |
| AC-T1-06 | **(QA)** Dado `nav.js` en cada página, entonces muestra el nombre del funcionario (`/api/auth/me/`), los contadores de `/api/pendientes/` enlazados a sus pantallas (refresco cada 30 s), y "Salir" (logout y vuelta a `/`). |
| AC-T1-07 | Dado `app.css`, entonces define las clases `fila-rojo`, `fila-naranja`, `fila-amarillo`, `fila-verde`, `msg-retenido` (borde rojo), `msg-descartado` (tachado), `msg-cliente` y `msg-saliente` (lados opuestos del chat). Un test lee el archivo y verifica que existan. |
| AC-T1-08 | Dado el código de `frontend/static/js/`, cuando un test lo recorre, entonces **no** aparece `innerHTML`, `outerHTML`, `insertAdjacentHTML` ni `document.write`, y `fetch(` solo aparece en `api.js` (R16, R17). |

### Etapa B · Bandeja (`/panel/`)
| ID | Criterio |
|---|---|
| AC-T1-09 | Dados `lib/color.js` y `lib/consulta.js`: `claseDeColor("rojo")` → `"fila-rojo"` (y los otros tres), desconocido → `"fila-verde"`; `armarQuery({estado:"abierta", con_alertas:true, q:"fer nández", pagina:2})` → `"?estado=abierta&con_alertas=1&q=fer+n%C3%A1ndez&pagina=2"` (omite vacíos y `false`; usa `URLSearchParams`). |
| AC-T1-10 | **(QA)** Dada la bandeja, entonces hay una fila por conversación con número, cliente (o "Contacto desconocido"), último mensaje, estado, modo y quién la atiende; la fila tiene la clase de su `color` **y** el texto de la severidad; aparece "sin respuesta" cuando la API lo indica; los filtros y la búsqueda (con `debounce` de 300 ms) recargan la lista; hay paginación; cada fila abre su detalle. |

### Etapa C · Detalle de conversación (`/panel/conversacion/?id=N`)
| ID | Criterio |
|---|---|
| AC-T1-11 | Dado `lib/mensajes.js`: `fusionarMensajes(actuales, nuevos)` devuelve la lista sin ids repetidos, ordenada por `fecha_hora` y luego `id`, sin modificar las entradas; `accionesPermitidas(mensaje, me)` devuelve `["liberar","corregir","descartar"]` solo si `me.puede_aprobar` y `mensaje.estado_envio === "retenido"`, si no `[]`. |
| AC-T1-12 | **(QA)** Dado el detalle, entonces muestra los mensajes como chat (cliente de un lado, bot/funcionario del otro) con hora y estado de envío; `retenido` con borde rojo y `descartado` tachado; un panel lateral con cliente, pólizas (saldo con `formatearMonto`) y alertas. Un mensaje con el texto `<img src=x onerror=alert(1)>` se ve como texto y no ejecuta nada. |
| AC-T1-13 | **(QA)** Dado el detalle abierto, entonces cada 5 s pide `…/mensajes/?despues_de=<último id>` y agrega solo lo nuevo (con `fusionarMensajes`), sin parpadear; con la pestaña oculta (`document.hidden`) no hace pedidos. |
| AC-T1-14 | **(QA)** Dados los botones de `accionesPermitidas`, entonces "Liberar", "Corregir" (con texto editable precargado) y "Descartar" (motivo obligatorio) piden confirmación en un `<dialog>` y muestran el `mensaje` de la API si falla (403, 409…); un operador no los ve; el botón se deshabilita mientras espera. |
| AC-T1-15 | **(QA)** Dado el detalle, entonces "Tomar conversación" / "Devolver al bot" cambian el modo; el formulario "Responder" solo aparece en modo `humano` y está deshabilitado con una explicación si `ventana_24h_abierta` es `false`. |

### Etapa D · Alertas y cerrados con alertas
| ID | Criterio |
|---|---|
| AC-T1-16 | **(QA)** Dada `/panel/alertas/`, entonces lista las alertas con filtros por tipo y severidad y un enlace a su conversación. Dada `/panel/cerrados/`, lista los casos cerrados con alertas abiertas y un botón "Reabrir" solo para aprobadores. |

### Etapa E · Acciones y derivaciones
| ID | Criterio |
|---|---|
| AC-T1-17 | Dado `lib/acciones.js`: `describirAccion(accion)` devuelve un texto legible por tipo (p. ej. `"Baja de la póliza POL-00107"`, `"Agregar conductor a la póliza POL-00123"`, `"Reembolso de $3.200"`, y `"Sin póliza asociada"` cuando `poliza` es `null`); `faltantes(accion)` devuelve los parámetros que faltan para ejecutar (`agregar_conductor` → `nombre`, `dni`; `reembolso` → `importe`; `modificar_poliza` → `detalle`; `apertura_siniestro` → `fecha_ocurrencia`, `descripcion`; `baja_poliza` sin póliza → `poliza`). |
| AC-T1-18 | **(QA)** Dada `/panel/acciones/`, entonces lista las pendientes con `describirAccion`, cliente y antigüedad; el detalle muestra los parámetros, permite completar los `faltantes` (`PATCH …/parametros/`) y, para aprobadores, "Aprobar" y "Rechazar" (motivo obligatorio) con `<dialog>`; los errores de la API se muestran. |
| AC-T1-19 | **(QA)** Dada `/panel/derivaciones/`, entonces lista las derivaciones del usuario (urgentes destacadas y primero), con enlace a la conversación y "Marcar atendida". |

### Etapa F · Clientes y pólizas
| ID | Criterio |
|---|---|
| AC-T1-20 | Dado `lib/polizas.js`: `ordenarPolizas(polizas)` deja vigentes primero y luego por `fecha_vencimiento` ascendente, sin modificar la lista original; `etiquetaEstadoPoliza("vigente"|"vencida"|"dada_de_baja")` → `"Vigente"`/`"Vencida"`/`"Dada de baja"`, desconocido → `"—"`. |
| AC-T1-21 | **(QA)** Dada `/panel/clientes/`, entonces hay una tabla con búsqueda (`debounce` 300 ms) por apellido, nombre o DNI (también con puntos) y paginación; cada fila abre la ficha. Dada `/panel/cliente/?id=N`, entonces muestra datos, pólizas (ordenadas, con etiqueta de estado en texto, vencimiento y saldo), cuotas y siniestros, con los formatos de `formato.js`. |
| AC-T1-22 | Dada `/panel/clientes/`, entonces hay un formulario de alta desplegable (`<details>`, porque la página solo carga el CSS de Bootstrap) con DNI, nombre, apellido, WhatsApp y correo opcional; `validarCliente` de `lib/clientes.js` marca los campos inválidos antes de llamar a la API, y los errores que solo la API conoce (DNI o teléfono repetidos) se muestran con el mensaje que ella devuelve. Al guardar se limpia el formulario y se recarga el listado, que incluye una columna de estado. Desde una conversación de contacto desconocido, el botón "Dar de alta como cliente" abre esta página con `?telefono=&perfil=` y `prellenadoDesdeUrl` deja cargados el teléfono y el nombre de perfil separado en nombre y apellido; **no se crea ningún cliente hasta que la persona completa los datos reales y guarda**. |
| AC-T1-23 | Dada `/panel/cliente/?id=N`, entonces se puede editar el cliente —solo viaja lo que tiene valor, y vaciar el correo lo borra— y darlo de baja o reactivarlo; el estado se muestra como insignia y el botón que corresponde; el 409 por pólizas vigentes se muestra con el mensaje de la API. |

## 4. Cómo comprobar
```bash
node --test                       # sin argumentos (pasar un directorio falla desde Node 22)
python manage.py runserver        # y abrir http://localhost:8000/
python SDD/verificar.py T1
```
Usuarios para el QA: crear con `python manage.py crear_usuarios_funcionarios --clave <clave>` (uno aprobador: Graciela; uno operador: Diego). Con la consola del navegador (F12) abierta: sin errores en rojo.
**Terminado cuando:** `node --test` en verde, todos los ítems de `SDD/qa/T1.md` tildados y `SDD/entregas/T1.md` completo.
