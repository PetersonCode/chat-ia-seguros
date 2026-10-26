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

## Línea base histórica (2026-10-05)
Las cifras de esta tabla corresponden únicamente al estado de ese día; no son
evidencia del estado actual tras las entregas posteriores.

| Tarea | AC con test | Suite |
|---|---|---|
| **T4 · ORM** | 28/28 | `python manage.py test datos` → 34 OK |
| **T3 · Lógica** | 46/46 | `python manage.py test negocio` → 129 OK |
| **T2 · API** | 21/21 | `python manage.py test api` → 75 OK |
| **T1 · Frontend** | 10/21 | `npm test` → 20 OK |

Total histórico: **238 tests de Python + 20 de JavaScript**, registrados como
verdes contra PostgreSQL 17.11. Estos números no incluyen las tareas posteriores
ni deben tomarse como resultado de la suite actual. La verificación más reciente
de esta preparación (incluidos los límites del entorno local y los pendientes
del equipo) está en [`entregas/T15.md`](./entregas/T15.md).

## Pendientes operativos
La base de cada instalación necesita las migraciones Django y la creación
explícita de cuentas de funcionarios después de cargar el esquema SQL. Los pasos
vigentes están en [`README.md`](../README.md); las contraseñas no se restablecen
al iniciar la aplicación. La revisión visual con perfiles de aprobador y
operador y los recorridos operativos quedan pendientes hasta que una persona
complete el QA y lo registre en `entregas/T15.md`.

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
1. **Antes de empezar:** `git pull` de `main` y leé `SDD/entregas/` de las tareas anteriores. Para preparar la aplicación en una clonación nueva, seguí [`README.md`](../README.md): crea una base local, configura `.env` y aplica los scripts SQL en orden. La plantilla contiene valores de ejemplo, no credenciales. Si cargás un token real de WhatsApp o de LLM, va **solo** en tu `.env` (ignorado por git) y **no** se pega en la IA.
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

## Preparar el entorno local
La configuración de desarrollo y producción, la creación de la base local, el
orden de aplicación de `SDD/sql/01_schema.sql` a
`10_trabajos_whatsapp.sql`, las
migraciones y los comandos de verificación están documentados en
[`README.md`](../README.md). En desarrollo se usa `DB_SSLMODE=disable`; en
producción debe usarse `DB_SSLMODE=require` con un servidor PostgreSQL que ofrezca TLS.
Los adjuntos privados y el flujo de media de WhatsApp están descritos en
[`adjuntos_siniestros.md`](./adjuntos_siniestros.md).
La consulta documental local está descrita en
[`documentos_generales.md`](./documentos_generales.md).
