# SDD · Seguros Castaño (bot de WhatsApp + dashboard de supervisión)

Spec Driven Development para **4 personas, 4 tareas, 4 branches**. Cada persona ejecuta **una sola tarea** con **su IA gratuita**, en orden, y la publica en su branch. Stack: Python + Django + Django REST Framework, PostgreSQL 17 (ya creada), JavaScript puro en el front.

## Qué hay en esta carpeta
| Archivo | Para qué |
|---|---|
| `00-comun.md` | Proyecto, stack, reglas inviolables, glosario. **Se pega siempre** en la IA |
| `T4-orm.md` · `T3-logica.md` · `T2-api.md` · `T1-frontend.md` | La spec de cada tarea, por etapas, con sus criterios de aceptación (`AC-Tn-xx`) |
| `contratos/modelos.md` · `servicios.md` · `api.md` | Lo que una capa le ofrece a la de arriba. Es lo que permite trabajar en orden sin adivinar |
| `sql/` | El esquema real de la base (ya aplicado en el servidor). T4 lo usa para los tests |
| `qa/T1.md` | Checklist de prueba manual de las pantallas |
| `entregas/` | Cada persona deja acá su entrega al terminar (plantilla: `_plantilla.md`) |
| `plantillas/env.example` | Base del `.env.example` del repo |
| `verificar.py` | Comprueba que cada AC tenga su test (`python SDD/verificar.py T3`) |

## Estado (2026-10-05)
Las cuatro tareas están integradas en este directorio y sus entregas están en `SDD/entregas/`.

| Tarea | AC con test | Suite |
|---|---|---|
| **T4 · ORM** | 28/28 | `python manage.py test datos` → 34 OK |
| **T3 · Lógica** | 46/46 | `python manage.py test negocio` → 129 OK |
| **T2 · API** | 21/21 | `python manage.py test api` → 75 OK |
| **T1 · Frontend** | 10/21 | `npm test` → 20 OK |

Total: **238 tests de Python + 20 de JavaScript, todos en verde** contra PostgreSQL 17.11 real.

Faltan dos cosas, las dos necesitan una persona:
1. **`python manage.py migrate`** — crea las tablas propias de Django (usuarios, sesiones) en `proyecto`.
   Es la única excepción que R8 permite y la corre **una sola persona, una sola vez**. Sin esto el login
   no funciona contra la base real. Después: `python manage.py crear_usuarios_funcionarios --clave <clave>`.
2. **El QA manual de `SDD/qa/T1.md`** — son los 11 AC de T1 marcados `**(QA)**`, que son de pantalla y
   no se pueden automatizar. Hay que hacerlos con el navegador, como Graciela y como Diego.

## Orden de ejecución (importante)
Se hace **de abajo hacia arriba**, porque cada capa usa la anterior:

| Turno | Tarea | Branch | Usa lo de | Deja listo para |
|---|---|---|---|---|
| 1.º | **T4 · ORM** | `tarea-4-orm` | la base (`sql/`) | T3 (`contratos/modelos.md`) |
| 2.º | **T3 · Lógica de negocio** | `tarea-3-logica` | T4 | T2 (`contratos/servicios.md`) |
| 3.º | **T2 · Conexión con el front (API)** | `tarea-2-api` | T3 (y lecturas de T4) | T1 (`contratos/api.md`) |
| 4.º | **T1 · Frontend** | `tarea-1-frontend` | T2 | la demo |

> Los números de tarea son los que eligieron; el orden de ejecución es 4 → 3 → 2 → 1. Si se hiciera al revés, el front se construiría contra una API que todavía no existe.

## Flujo de git (cada persona)
```bash
git checkout main && git pull                 # trae lo que integraron las tareas anteriores
git checkout -b tarea-N-nombre                # tu branch
# ... trabajás etapa por etapa con tu IA, commiteando al terminar cada una ...
git commit -m "feat(tN): etapa A - <resumen> [AC-TN-01..04]"
git push -u origin tarea-N-nombre             # publicás tu branch
# PR a main -> lo revisa la persona de la tarea siguiente -> merge -> recién ahí arranca la siguiente
```
Quien sigue revisa el PR de quien termina (T3 revisa a T4, T2 a T3, T1 a T2, T4 a T1): así lee lo que va a usar.

## Paso a paso para cada persona
1. **Antes de empezar:** `git pull` de `main` y leé `SDD/entregas/` de las tareas anteriores. Copiá `.env.example` a `.env`: ya trae los datos de conexión que funcionan en este equipo, no hay que completar nada para empezar. Si llegás a cargar un token real de WhatsApp o de LLM, va **solo** en tu `.env` (ignorado por git) y **no** se pega en la IA.
2. **Abrí una sesión nueva** de tu IA y pegá, en este orden: `00-comun.md`, tu `Tn-*.md`, los contratos que indica tu spec y las entregas anteriores.
3. **Arrancá con este mensaje** (una etapa por vez):
   ```
   Seguí 00-comun.md al pie de la letra. Vamos a hacer la ETAPA A de mi tarea.
   Antes de escribir código respondé solo: (1) qué AC cubre la etapa, (2) qué archivos vas a crear o
   modificar, (3) dudas o contradicciones. Esperá mi OK.
   ```
4. Con tu OK, pedí **primero los tests** de la etapa; después la implementación. La IA devuelve archivos completos y vos los copiás.
5. Corré los tests de tu spec (sección "Cómo comprobar"). Si algo falla, pegale **solo el error y el archivo**, no toda la conversación.
6. **Leé el diff** (`git diff`), commiteá la etapa, y pasá a la siguiente: `OK. Ahora la ETAPA B.`
7. Si la sesión se enreda (más de ~15 mensajes, repite errores, se olvida reglas), **abrí una sesión nueva**: volvé a pegar los documentos y decile por qué etapa vas. Conviene una sesión nueva por etapa.
8. **Al terminar:** `python SDD/verificar.py TN` sin faltantes, completá `SDD/entregas/TN.md`, push y PR con el registro de IA.

## Qué hacer cuando la IA…
| Situación | Respuesta |
|---|---|
| Inventa una función, campo, endpoint o librería | "Usá solo lo que está en el contrato." Pegale la sección exacta |
| Toca archivos fuera de tu carpeta | Rechazar. Recordarle la sección 2 de tu spec |
| Dice "listo" sin tests | No está listo: pedí los tests y corrélos vos |
| Propone cambiar el esquema, el contrato o el stack (React, requests, Celery…) | No. Anotarlo como pregunta en la entrega |
| Usa `innerHTML` o `fetch` fuera de `api.js` (T1) | Rechazar (R16, R17) |
| Escribe "NO ESPECIFICADO" | Bien: anotalo en tu entrega y consultá al equipo antes de decidir |

## Modelos de IA
Cualquier modelo gratuito sirve, pero conviene uno con **ventana de contexto de al menos 32k tokens**: el paquete de documentos de una tarea ronda los 8 a 14k tokens antes de empezar a escribir código. Si tu modelo tiene poca ventana, pegá solo `00-comun.md`, la etapa actual de tu spec y la sección del contrato que esa etapa usa.

## Datos de conexión (para el `.env`)
`postgresql://irusu:CONTRASEÑA@localhost:25432/proyecto?sslmode=require` — conexión local a la base publicada en este equipo; la base se borra en un mes y los datos son ficticios.

La contraseña real ya está puesta en `.env.example` (y en `SDD/plantillas/env.example`, que es su copia exacta): la base está abierta a propósito, corre en el mismo equipo que el código y solo tiene datos ficticios. El `sslmode=require` **no es opcional**: el servidor rechaza las conexiones sin SSL (`no pg_hba.conf entry`), así que `OPTIONS={"sslmode": "require"}` en `config/settings.py` tiene que quedar como está.

Para comprobar que tu `.env` quedó bien: `python manage.py verificar_conexion` (es de solo lectura, imprime la versión de PostgreSQL y las filas de cada tabla).
