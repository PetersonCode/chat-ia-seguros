# 00 · Documento común (pegar SIEMPRE junto con tu tarea)

> Sos una IA ayudando a **una persona** a completar **una sola tarea** (T1, T2, T3 o T4) de este proyecto.
> Leé este documento completo y después la spec de tu tarea. **La spec manda.** No decidís requisitos ni diseño.

## 1. El proyecto
**Seguros Castaño** es una agencia de seguros chica (Roberto, el dueño; Graciela, administración; Diego, operador). Queremos:
- un **bot de WhatsApp** que atienda consultas de rutina (saldo, vencimiento, cómo denunciar un siniestro) **con datos reales de la base**;
- un **dashboard** donde el equipo ve todo lo que dijo el bot, con lo dudoso **marcado en colores y retenido** antes de llegar al cliente;
- que el bot **nunca** ejecute solo acciones contractuales (bajas, agregar conductor, reembolsos): las **solicita** y un humano las aprueba;
- que derive lo complicado a una persona y avise.

## 2. Stack (fijo, no se cambia)
| Capa | Tecnología |
|---|---|
| Base de datos | PostgreSQL 17, **ya creada** (remota, compartida, SSL). Esquema en `SDD/sql/` |
| Back | Python 3.12 · Django 5.x · Django REST Framework |
| Front | **JavaScript puro** (módulos ES), HTML, CSS. Sin frameworks, sin bundler, sin npm. Bootstrap solo CSS por CDN |
| Tests | `python manage.py test` (back) · `node --test` sin argumentos (front, Node ≥ 20) |

Dependencias de Python permitidas (**solo estas**, versiones fijas en `requirements.txt`): `Django`, `djangorestframework`, `psycopg[binary]`, `python-dotenv`. Nada más.

## 3. Las 4 tareas y quién toca qué
| Tarea | Qué hace | Carpeta que posee (solo esa se toca) | Orden de ejecución |
|---|---|---|---|
| **T4 · ORM** | Proyecto Django, conexión, modelos sobre la base existente, consultas de lectura, limpieza de datos, importador | `config/`, `datos/`, archivos raíz (`manage.py`, `requirements.txt`, `.env.example`, `.gitignore`) | **1.º** |
| **T3 · Lógica de negocio** | Bot, guardrails, WhatsApp, supervisión, acciones, derivaciones, reglas | `negocio/` | **2.º** |
| **T2 · Conexión con el front** | API REST, sesión, permisos, errores, webhook HTTP, servir páginas | `api/`, y en `config/` solo lo indicado en su spec | **3.º** |
| **T1 · Frontend** | Páginas, JS, CSS, tests de JS | `frontend/`, `package.json`, `SDD/qa/T1.md` (tildar) | **4.º** |

Se ejecutan **de abajo hacia arriba** (T4 → T3 → T2 → T1). Cada tarea **usa** lo que dejó la anterior, **a través de los contratos**:

```
T1 Frontend ──usa──► contratos/api.md ◄──implementa── T2 API
T2 API      ──usa──► contratos/servicios.md ◄──implementa── T3 Lógica
T3 Lógica   ──usa──► contratos/modelos.md ◄──implementa── T4 ORM
T4 ORM      ──usa──► SDD/sql/ (la base ya existe)
```

## 4. Estructura final del repositorio
```
manage.py  requirements.txt  package.json  .env.example  .gitignore
config/    settings.py · urls.py · test_runner.py                                   (T4; T2 agrega lo suyo)
datos/     models.py · selectors.py · fabricas.py · limpieza.py · management/ · tests/  (T4)
negocio/   errores.py · reglas.py · sesion.py · whatsapp.py · acciones.py · supervision.py
           bot/ (orquestador, guardrails, clasificador, llm, plantillas, prompts) · management/ · tests/  (T3)
api/       permisos.py · errores.py · serializers.py · views.py · webhook.py · paginas.py · urls.py · management/ · tests/  (T2)
frontend/  pages/*.html · static/css/app.css · static/js/{api.js, nav.js, lib/*.js, pages/*.js} · tests/*.test.js  (T1)
SDD/       esta documentación, los contratos, los SQL, las entregas y el QA
```

## 5. Reglas inviolables
**Proceso**
- **R1.** Una persona = una tarea = una branch. Solo se tocan los archivos de tu carpeta (tabla de la sección 3) y los que tu spec nombre explícitamente.
- **R2.** **La spec manda.** Si algo no está especificado o dos documentos se contradicen: escribí `NO ESPECIFICADO: …`, frená y la persona lo anota en su entrega como pregunta. No inventes.
- **R3.** **Por etapas.** Tu spec tiene etapas (A, B, C…). Hacé **una etapa por vez**; al terminarla, frená y esperá que la persona corra los tests y te diga "OK, siguiente".
- **R4.** **Tests primero.** Cada criterio `AC-Tn-xx` tiene al menos un test que lo cita en un comentario (`# AC-T3-14` en Python, `// AC-T1-08` en JS). Los de pantalla que no se pueden automatizar se verifican a mano en `SDD/qa/T1.md`.
- **R5.** **Los contratos (`SDD/contratos/`) son la verdad.** Usá solo las funciones, modelos, campos y endpoints que figuran ahí. Si la tarea anterior dejó algo distinto al contrato, **no lo arregles en su carpeta**: anotalo en tu entrega y avisá a su dueño.
- **R6.** **Antes de escribir código**, en cada etapa respondé solo: (1) qué etapa y qué AC cubre, (2) qué archivos vas a crear/modificar, (3) dudas. Esperá el OK.
- **R7.** Al terminar la tarea se completa `SDD/entregas/Tn.md` (plantilla en `SDD/entregas/_plantilla.md`). La próxima persona lo lee antes de empezar.

**Datos**
- **R8.** La base `proyecto` es **compartida y ya existe**. Prohibido crear, alterar o borrar tablas (`CREATE/ALTER/DROP/TRUNCATE`), `DELETE` sin `WHERE`, y `makemigrations`/`migrate` sobre la app `datos`. Única excepción: `python manage.py migrate` crea las tablas propias de Django (usuarios, sesiones); lo corre **una persona, una vez**, al terminar T4. Los tests corren en una base aparte (`test_proyecto`).
- **R9.** La configuración va en `.env` (ignorado por git), a partir de `.env.example`. Los datos de la base están en el ejemplo a propósito: la base es local, abierta, con datos ficticios y se borra en un mes. Los tokens de WhatsApp y de LLM sí son secretos: van solo en tu `.env` y **nunca** se pegan en un chat de IA.
- **R10.** Solo datos ficticios.

**Negocio** (vienen del cliente)
- **R11.** El bot **nunca ejecuta** acciones contractuales: crea una `AccionPendiente`; la aprueba un funcionario con `puede_aprobar`.
- **R12.** **El LLM nunca es fuente de datos.** Saldos, fechas, números de póliza/siniestro y montos salen de la base y se insertan en plantillas fijas.
- **R13.** Todo lo que dice el bot se guarda. Si una respuesta dispara una alerta, queda **retenida** (`estado_envio='retenido'`) hasta que un humano la libere o la reemplace.
- **R14.** Solo se envía por WhatsApp un mensaje en estado `pendiente_envio`. Nunca `retenido` ni `descartado`.

**Front**
- **R15.** JavaScript puro, módulos ES. Sin frameworks, librerías ni CDNs de JS.
- **R16.** **Nunca** `innerHTML`, `outerHTML`, `insertAdjacentHTML` ni `document.write` con datos: se usa `textContent` y `createElement`. (Los mensajes vienen de terceros: es la defensa contra XSS.)
- **R17.** Toda llamada al back pasa por `frontend/static/js/api.js`. El front no decide permisos ni reglas: el back las hace cumplir; el front solo oculta botones.

**Código**
- **R18.** Nombres de dominio en español (como en la base); técnicos en inglés. Type hints en funciones públicas de Python; JSDoc en funciones exportadas de JS. Funciones chicas.
- **R19.** Respuesta de la IA: **archivos completos**, uno por bloque, con la ruta como título (sin `...`). Al final, el comando de tests y los AC cubiertos.
- **R20.** Quien abre el PR responde por cada línea, la haya escrito una IA o no. El PR lleva el **registro de IA** (modelo, qué se pidió, qué se corrigió a mano).

## 6. Glosario mínimo
| Término | Significado |
|---|---|
| Funcionario | Roberto, Graciela, Diego. `puede_aprobar=true` = **aprobador** (Roberto, Graciela); `false` = **operador** (Diego) |
| Contacto | Un número de WhatsApp (`+549` + 10 dígitos). Puede no ser cliente |
| Conversación | Hilo con un contacto; `modo` = `bot` o `humano` (si es humano, el bot no responde) |
| Mensaje | Entrante (cliente) o saliente (bot o funcionario), con `estado_envio` |
| Consulta / caso | Una intención detectada por el bot (`CASO-###`). Una por mensaje entrante |
| Política | Qué puede hacer el bot según el tipo de consulta: `bot_responde`, `requiere_aprobacion`, `derivar_humano`, `seguridad` |
| Alerta | Problema detectado en lo que entra o sale del bot; severidad `baja` < `media` < `alta` < `critica` |
| Retenido / descartado | Respuesta frenada (espera a un humano) / rechazada o reemplazada por un humano (se guarda, nunca sale) |
| Acción pendiente | Cambio contractual solicitado que espera aprobación |
| Derivación | Pase de un caso a un funcionario, `normal` o `urgente` |
| Ventana de 24 h | WhatsApp solo deja enviar texto libre hasta 24 h después del último mensaje del cliente |

## 7. Variables de entorno
Definidas en `.env.example` (lo crea T4 copiando `SDD/plantillas/env.example`). Ninguna tarea agrega variables nuevas.
`DJANGO_SECRET_KEY, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD, WHATSAPP_MODO, WHATSAPP_VERIFY_TOKEN, WHATSAPP_APP_SECRET, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_API_VERSION, LLM_PROVIDER, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, BOT_URLS_PERMITIDAS`
