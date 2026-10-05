# T4 · ORM con la base de datos ya creada

**Se ejecuta:** 1.º (primera tarea) · **Branch:** `tarea-4-orm`
**Pegarle a la IA:** `SDD/00-comun.md` + este archivo + `SDD/contratos/modelos.md` + (en la etapa B) `SDD/sql/01_schema.sql`, `03_whatsapp.sql`, `04_mensaje_descartado.sql`.
**Produce:** lo que define `SDD/contratos/modelos.md`. T3 lo usa.

## 1. Objetivo
Dejar el proyecto Django funcionando contra la base PostgreSQL **existente**, con todos los modelos, las consultas de lectura que usará la lógica, fábricas para tests, la limpieza de datos sucios y el importador del CSV de consultas. **Esta tarea no crea ni modifica tablas.**

## 2. Archivos que podés crear o modificar
`manage.py`, `requirements.txt`, `.env.example`, `.gitignore`, `config/` (todo), `datos/` (todo), y los paquetes vacíos `negocio/__init__.py`, `negocio/apps.py`, `api/__init__.py`, `api/apps.py`, `api/urls.py` (con `urlpatterns = []`).
**No toques:** `SDD/` (salvo `SDD/entregas/T4.md`), `frontend/`.

## 3. Etapas y criterios de aceptación

### Etapa A · Proyecto, configuración y conexión
| ID | Criterio |
|---|---|
| AC-T4-01 | Dado un `.env` válido, cuando se corre `python manage.py check`, entonces no hay errores y en `INSTALLED_APPS` están `rest_framework`, `datos`, `negocio` y `api`. |
| AC-T4-02 | Dado que falta una variable obligatoria (`DJANGO_SECRET_KEY` o alguna `DB_*`), cuando se cargan los settings, entonces falla con `ImproperlyConfigured` y un mensaje en español que nombra la variable. |
| AC-T4-03 | Dados los settings, entonces la base usa `ENGINE` postgresql, los valores de `DB_*`, `OPTIONS={"sslmode": "require"}`; `TIME_ZONE="America/Argentina/Buenos_Aires"`, `USE_TZ=True`, `LANGUAGE_CODE="es-ar"`. |
| AC-T4-04 | Dado el repositorio, entonces `.env.example` es copia de `SDD/plantillas/env.example`, `.gitignore` excluye `.env`, `__pycache__/`, `.venv/`, `node_modules/`, y `requirements.txt` fija versión exacta (`==`) de **solo** `Django`, `djangorestframework`, `psycopg[binary]` y `python-dotenv`. |

### Etapa B · Modelos
| ID | Criterio |
|---|---|
| AC-T4-05 | Dado `datos/models.py`, entonces existen los 15 modelos de tabla del contrato con su `db_table`, `managed = False`, los campos, FK y `related_name` indicados. |
| AC-T4-06 | Dados los 3 modelos de vista, entonces son `managed = False`, tienen la PK indicada y `save()`/`delete()` lanzan `TypeError("Es una vista de solo lectura")`. |
| AC-T4-07 | Dadas las clases `TextChoices` del contrato, cuando un test lee las restricciones `CHECK` de la base (`pg_constraint` / `pg_get_constraintdef`), entonces cada clase tiene **exactamente** los mismos valores que su columna. |
| AC-T4-08 | Dado cada modelo de tabla, cuando un test compara con `information_schema.columns`, entonces toda columna del modelo existe en la tabla y la nulabilidad coincide (`null=True` ⇔ columna `NULL`). |
| AC-T4-09 | Dado un campo con `DEFAULT` en la base, entonces el modelo tiene un default equivalente; crear cada modelo con su fábrica, pasando solo los campos obligatorios sin default, no falla. |

### Etapa C · Runner de tests y fábricas
| ID | Criterio |
|---|---|
| AC-T4-10 | Dado `python manage.py test`, entonces `config/test_runner.py` (configurado en `TEST_RUNNER`) crea `test_proyecto`, ejecuta `SDD/sql/01_schema.sql`, `03_whatsapp.sql` y `04_mensaje_descartado.sql` (no el seed) y la elimina al final; un test verifica que el nombre de la base en uso empieza con `test_`. |
| AC-T4-11 | Dado `datos/fabricas.py`, entonces cada fábrica del contrato crea un objeto válido con valores únicos por defecto; `crear_catalogos()` crea 5 tipos de seguro y 12 tipos de consulta (con sus políticas, iguales a `02_seed.sql`) y llamarlo dos veces no duplica; `crear_funcionario` crea además un `User` con el mismo email. |

### Etapa D · Consultas de lectura (`selectors.py`)
| ID | Criterio |
|---|---|
| AC-T4-12 | Dadas las consultas de identidad (`funcionario_por_email`, `funcionario_por_nombre`, `cliente_por_dni`, `contacto_por_numero`, `conversacion_abierta`, `poliza_por_numero`, `siniestro_por_numero`, `tipo_consulta`), entonces devuelven el objeto o `None` (o `DoesNotExist` en `tipo_consulta`); las de funcionario ignoran mayúsculas y excluyen inactivos. |
| AC-T4-13 | Dados `mensajes_de` e `historial_reciente`, entonces devuelven en orden cronológico; con `despues_de=N` solo ids mayores a N; `historial_reciente` devuelve como máximo `limite` mensajes, los más recientes. |
| AC-T4-14 | Dados `polizas_vigentes` y `resumen_polizas`, entonces la primera excluye vencidas y dadas de baja; la segunda devuelve el saldo pendiente igual a la suma de cuotas `pendiente`+`vencida` y el próximo vencimiento de pago correcto. |
| AC-T4-15 | Dado `alertas_abiertas`, entonces devuelve solo estado `abierta` o `en_revision`, filtrando por consulta, conversación o mensaje. |
| AC-T4-16 | Dado `bandeja`, entonces cada conversación trae `alertas_abiertas`, `severidad_rango`, `retenidas`, `ultimo_texto`, `ultimo_emisor`, `ultimo_fecha_hora`; respeta los filtros `estado`, `con_alertas`, `esperando_humano`, `q`; y el orden pone primero las que tienen retenidas o alertas críticas y después por último mensaje descendente. |
| AC-T4-17 | Dados `listar_alertas` y `consultas_cerradas_con_alertas`, entonces filtran por tipo, severidad y estado, y la segunda devuelve solo consultas `cerrado` con alertas abiertas. |
| AC-T4-18 | Dados `listar_acciones` y `derivaciones_de`, entonces la primera filtra por estado (por defecto `pendiente`) con las más antiguas primero; la segunda trae solo las del funcionario, sin atender salvo `incluir_atendidas`, urgentes primero. |
| AC-T4-19 | Dados `buscar_clientes`, `detalle_cliente` y `detalle_poliza`, entonces `buscar_clientes("28.111.222")` encuentra al DNI `28111222`, `buscar_clientes("fernández")` encuentra a Fernández, cada resultado trae `polizas_vigentes`; `detalle_cliente` y `detalle_poliza` hacen como máximo 5 consultas SQL al recorrer todos sus datos relacionados (`assertNumQueries`). |
| AC-T4-20 | Dado `contar_pendientes`, con 2 acciones pendientes, 1 derivación sin atender del funcionario (y 1 de otro) y 3 alertas críticas abiertas (y 1 resuelta), entonces devuelve `{"acciones": 2, "derivaciones": 1, "alertas_criticas": 3}`. |

### Etapa E · Limpieza de datos (`limpieza.py`, funciones puras, tests sin base)
| ID | Criterio |
|---|---|
| AC-T4-21 | `normalizar_dni`: `'28.111.222'` → `'28111222'`; `' 28111222 '` → `'28111222'`; `'28-111-222'` → `'28111222'`; menos de 7 o más de 8 dígitos, o letras → `ValueError`. |
| AC-T4-22 | `normalizar_telefono`: `'+54 11 5555-1001'`, `'+54 11 55551001'` → `'+5491155551001'`; `'1155552002'` → `'+5491155552002'`; `'011 5555-1004'` → `'+5491155551004'`; `'+54911 5555 1005'` → `'+5491155551005'`; `'5491155551003'` y `'541155551003'` → `'+5491155551003'`. Vacío, con letras o que no queda en 10 dígitos → `ValueError`. Algoritmo: solo dígitos; quitar `54` inicial; quitar `0` inicial; si quedan 11 y empieza con `9`, quitarlo; exigir 10; devolver `'+549'` + dígitos. |
| AC-T4-23 | `parsear_fecha_hora`: `'2024-04-01 09:15'`, `'01/04/2024 10:30'`, `'April 1 2024 11:00'`, `'02-04-24 08:00'`, `'2024/04/02 14:20'`, `'3/4/24 09:00'`, `'04.04.2024 10:00'` dan la fecha correcta (día primero en los numéricos; año de 2 dígitos = 2000+) con hora; `'03-04-2024'`, `'2024-04-04'`, `'05/04/2024'` dan hora `None`; `'30/02/2024'` o texto → `ValueError`. Lista explícita de formatos con `datetime.strptime`. |
| AC-T4-24 | `normalizar_tipo_seguro`: `'Automotor'`, `'auto'`, `'AUTO'`, `' Auto '` → `'automotor'`; `'casa'`, `'vivienda'` → `'hogar'`; `'negocio'`, `'local'` → `'comercio'`; `'motocicleta'` → `'moto'`; `'vida'` → `'vida'`; desconocido → `ValueError`. |

### Etapa F · Importador y comando de diagnóstico
| ID | Criterio |
|---|---|
| AC-T4-25 | Dado `python manage.py importar_consultas_csv <ruta>` con un CSV de columnas `caso_id,fecha_hora,numero_whatsapp,mensaje_usuario,respuesta_bot_ia,tipo_consulta_detectado,estado_caso,funcionario_asignado,fecha_resolucion`, entonces por cada fila con número crea o reutiliza el contacto (sin cliente), la conversación, el mensaje entrante (`recibido`), el mensaje del bot (`enviado`) y la `ConsultaBot` con `datos_origen` = la fila original. Sin número: solo la consulta. |
| AC-T4-26 | Dadas las reglas de limpieza: `ALERTA_SEGURIDAD`/`ALERTA_ACCION` → estado `pendiente_revision`; `PROMPT_INJECTION` → tipo `prompt_injection`; funcionario por `funcionario_por_nombre` (`'ROBERTO'` → Roberto); fecha sin hora → 00:00 de Buenos Aires con nota; `fecha_resolucion` anterior a la consulta → `NULL` con nota en `notas_importacion`. |
| AC-T4-27 | Dado un `codigo_caso` existente, entonces se omite; dada una fila inválida, se informa con su código y las demás se importan (una transacción por fila); con `--dry-run` no escribe nada; al final imprime `creadas / omitidas / con error`. |
| AC-T4-28 | Dado `python manage.py verificar_conexion`, entonces se conecta a la base configurada en **modo solo lectura** (`SET TRANSACTION READ ONLY`), imprime la cantidad de filas de cada tabla del contrato y la versión de PostgreSQL, y no escribe nada. |

## 4. Diseño (guía para la IA)
- Settings con `python-dotenv` (`load_dotenv(BASE_DIR / ".env")`) y una función `requerida(nombre)` que lanza `ImproperlyConfigured`.
- `config/urls.py`: `path("", include("api.urls"))`. Nada más (T2 completa `api/urls.py`).
- Modelos: se puede partir de `python manage.py inspectdb` **pero hay que limpiarlo a mano** contra el contrato: nombres de clase, `managed=False`, FK y `related_name`, `TextChoices`, defaults. Sin comentarios autogenerados.
- **No** crear carpeta `datos/migrations/` (los modelos no se migran). `python manage.py migrate` solo crea las tablas propias de Django (auth, sesiones) en `proyecto`; lo corre la persona una vez, no la IA.
- `test_runner.py`: subclase de `DiscoverRunner`; en `setup_databases`, después de `super()`, ejecutar cada SQL con `connection.cursor().execute(open(...).read())`.
- `bandeja`: usar `Subquery`/`OuterRef` para el último mensaje y `Count(..., filter=Q(...))` / `Max(Case(...))` para las anotaciones.
- Importador: `datos/management/commands/importar_consultas_csv.py`; un CSV de muestra de 5 filas en `datos/tests/fixtures/consultas_muestra.csv` (fecha sin hora, estado ALERTA, resolución anterior, fila inválida, número sin cliente).

## 5. Cómo comprobar
```bash
python manage.py check
python manage.py test datos
python manage.py verificar_conexion          # contra la base real, solo lectura
python SDD/verificar.py T4                   # cada AC con su test
```
**Terminado cuando:** todos los AC-T4 tienen test en verde, `verificar.py T4` no marca faltantes y `SDD/entregas/T4.md` está completo.
