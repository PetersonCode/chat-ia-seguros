# Seguros Castaño

Aplicación Django + Django REST Framework con PostgreSQL y frontend en JavaScript puro.
Esta guía prepara una instalación local nueva en Windows y VS Code. No requiere
tokens externos: WhatsApp queda simulado y el bot usa reglas (`LLM_PROVIDER=none`).

## Versión corregida del MVP 2

Leé `ENTREGA_MVP2.md` para ver cambios, pruebas, actualización de una base existente y límites de las integraciones. Se conserva el diseño y PostgreSQL.

## Requisitos

- Windows 10/11, VS Code y extensión **Python** de Microsoft.
- Python 3.10–3.13 (compatible con las versiones fijadas en `requirements.txt`).
- Node.js para ejecutar las pruebas del frontend.
- PostgreSQL local (recomendado PostgreSQL 17), con `psql` disponible en PATH.

## Preparación de una clonación nueva

Abrí la carpeta del repositorio en VS Code y ejecutá los comandos siguientes en
una terminal PowerShell, desde la raíz:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Si PowerShell bloquea la activación del entorno, podés invocar directamente
`.venv\Scripts\python.exe` en los pasos siguientes. No hace falta cambiar la
política de ejecución global.

Editá `.env` y reemplazá `DJANGO_SECRET_KEY`, `DB_PASSWORD` y cualquier valor de
conexión para tu instalación local. La plantilla no contiene credenciales reales.
El perfil local usa `DB_SSLMODE=disable` porque PostgreSQL local estándar
normalmente no ofrece TLS.

## Crear una base PostgreSQL vacía y cargar el esquema

Con PostgreSQL instalado y el servicio iniciado, abrí PowerShell. El ejemplo
supone el rol local `postgres`; podés reemplazarlo por un rol propio. Creá una
base vacía y otorgá permisos de creación de bases al usuario que ejecutará las
pruebas (`CREATEDB` es necesario para que Django prepare `test_proyecto`):

```powershell
psql -U postgres -d postgres
```

En el prompt de `psql`:

```sql
CREATE ROLE seguros_dev LOGIN PASSWORD 'elegir-una-clave-local' CREATEDB;
CREATE DATABASE proyecto OWNER seguros_dev;
\q
```

Usá ese rol y contraseña en `DB_USER` y `DB_PASSWORD` de `.env`. Aplicá los
archivos desde la raíz del repositorio, exactamente en este orden:

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\01_schema.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\02_seed.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\03_whatsapp.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\04_mensaje_descartado.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\05_acciones_del_bot.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\06_pagos_con_referencia.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\07_expediente_siniestros.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\08_adjuntos_siniestros.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\09_documentos_generales.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\10_trabajos_whatsapp.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\11_finalizaciones_acciones.sql
```

No ejecutes `SDD\sql\00_drop_all.sql`: es destructivo. Estos scripts construyen
el esquema de negocio y cargan filas ficticias. Los modelos Django de negocio
usan `managed=False`, por lo que `migrate` **no** crea esas tablas. Una vez
aplicados los once scripts, crea las tablas internas de Django (usuarios,
sesiones y demás):

```powershell
python manage.py migrate
```

`migrate` se ejecuta después del esquema de negocio. En particular, permite
guardar usuarios Django aunque los modelos de negocio no sean administrados por
el ORM.

## Usuarios ficticios y login

`02_seed.sql` agrega funcionarios ficticios. Después de `migrate`, crea para
ellos usuarios Django con una contraseña local elegida por vos:

```powershell
python manage.py crear_usuarios_funcionarios --clave "elegir-una-clave-local"
```

El comando sincroniza los funcionarios activos y asigna la contraseña indicada
a todas las cuentas correspondientes. Es una operación manual y explícita: no
se ejecuta al iniciar Django. Ejecutala una vez al preparar la base; volver a
ejecutarla restablece las contraseñas de esas cuentas. No reutilices contraseñas
reales. El correo de inicio de sesión es el correo ficticio insertado en
`02_seed.sql` (por ejemplo, `graciela@seguroscastano.example`).

## Demo actual opcional

Con `DJANGO_DEBUG=true`, `WHATSAPP_MODO=simulado` y `LLM_PROVIDER=none`, después de cargar el esquema y crear usuarios:

```powershell
python manage.py cargar_demo_mvp2
```

Agrega un cliente ficticio con dos pólizas vigentes, acciones para revisar y una fuente documental marcada como académica. Es idempotente y no restablece contraseñas ni altera el histórico. No corresponde cargar esta muestra en producción.

## Ejecutar y verificar

Iniciá el servidor:

```powershell
python manage.py runserver
```

Abrí <http://127.0.0.1:8000/> para ver el login. Los estáticos se sirven desde
`frontend/static` por `runserver` en desarrollo (`DJANGO_DEBUG=true`). Ingresá
con el correo ficticio y la contraseña que asignaste manualmente.

En otra terminal, desde la raíz:

```powershell
python manage.py test
npm.cmd test
```

El runner de pruebas prepara una base PostgreSQL llamada `test_proyecto`, aplica
las migraciones propias de Django y crea el esquema de negocio necesario para
las pruebas. Requiere permisos `CREATEDB` y `DROP DATABASE` para esa base. No
carga `02_seed.sql`: las pruebas crean los datos que necesitan. WhatsApp se
fuerza a simulado durante la suite. `npm.cmd test` ejecuta las pruebas de
JavaScript con Node.js sin instalar dependencias npm externas.

## Atención humana y concurrencia

Cualquier funcionario activo puede tomar una conversación o reasignarla; la
persona que figura como responsable es la única que puede responder desde el
panel o devolver el chat al bot. Mientras el chat está en modo humano, las
respuestas automáticas comunes pendientes se descartan. Se conservan avisos de
derivación, respuestas liberadas expresamente por un aprobador y mensajes
escritos por funcionarios. Los adjuntos no reciben una respuesta automática
durante la atención humana.

La toma, el guardado final del bot y el envío serializan por la fila de
`conversaciones` con `SELECT FOR UPDATE`. Por eso un envío que ya tomó el lock
termina antes de que se confirme la toma; el asesor puede esperar hasta el
timeout de 10 segundos de WhatsApp real. La prueba de toma durante la
clasificación fuerza ese intercalado y comprueba que no se guarde una respuesta
automática. No equivale a una prueba de dos conexiones concurrentes: esa
concurrencia y el comportamiento de `SELECT FOR UPDATE` deben verificarse con
una base PostgreSQL activa. La suite Django corre contra PostgreSQL y no se
debe tomar SQLite ni la prueba secuencial como evidencia de concurrencia real.

## Procesador durable de WhatsApp

El webhook guarda el mensaje entrante y su trabajo en PostgreSQL antes de
responder a Meta; no deja el procesamiento en un hilo daemon del servidor web.
Para consumir la cola y enviar mensajes salientes pendientes, iniciá el
procesador en una segunda terminal junto al servidor:

```powershell
python manage.py reprocesar_pendientes --continuo
```

El comando sin `--continuo` hace un único ciclo y termina. Los trabajos tienen
estado, contador de intentos, espera exponencial y un lease de 15 minutos para
que otro procesador recupere una tarea cuyo proceso murió. Tras ocho fallos,
la tarea queda `fallido`; revisá el registro antes de rehabilitarla con:

```powershell
python manage.py reprocesar_pendientes --reintentar-fallidos
```

Los salientes se guardan primero en la tabla `mensajes` como
`pendiente_envio`; el procesador los encuentra incluso si el proceso se detuvo
después de guardar una respuesta y antes de enviarla. Los fallos de envío se
reintentan con espera creciente, hasta ocho intentos. El estado y el detalle
del último error quedan en la base.

La persistencia evita perder trabajo entrante tras confirmar el webhook y la
idempotencia de la consulta evita duplicar respuestas locales al reprocesar.
No puede garantizarse exactamente una entrega externa: si Meta acepta un
mensaje y el proceso cae antes de registrar ese resultado en PostgreSQL, el
reintento podría enviar un duplicado. El lock por fila evita que procesadores
simultáneos reclamen el mismo trabajo; no elimina esa ventana de envío externo.

## Motor de base de datos y propuesta SQL Server

La aplicación implementada usa PostgreSQL; no tiene una configuración ni una
traducción automática a SQL Server. No cambies `DB_ENGINE` o una variable
similar esperando que cambie el motor: esa opción no existe. El esquema de
negocio y varias operaciones usan sintaxis y capacidades propias de
PostgreSQL, entre ellas `jsonb`, índices parciales, expresiones regulares,
triggers PL/pgSQL y `SELECT FOR UPDATE SKIP LOCKED`. SQL Server requiere otro
esquema, adaptaciones de consultas y una estrategia propia para reclamos
concurrentes; la compatibilidad debe estimarse e implementarse como un proyecto
separado. La aplicación sigue con PostgreSQL hasta que se apruebe y verifique
explícitamente una migración.

## Evidencia de verificación de esta entrega

En el entorno de trabajo de esta entrega se pudieron compilar los módulos
Python, ejecutar `git diff --check` y pasar `npm.cmd test` (47 pruebas). La
suite Django/PostgreSQL debe ejecutarse en un entorno preparado según las
instrucciones anteriores. En particular, el recorrido de clonación,
login y roles, cobro, baja, urgencia, pausa humana, adjuntos y reportes no se
debe considerar verificado hasta pasar la lista de comprobación de
[cierre y evidencia](SDD/entregas/T15.md). El proveedor, la cuenta y los
webhooks reales de Meta tampoco forman parte de la verificación local simulada.

La lista incluye un guion de 10–15 minutos para una persona del equipo; el
resultado debe registrarse con la fecha y el entorno en que se ejecutó, sin
marcar como hecho lo que no se haya probado.

## Documentación privada de siniestros

El detalle del expediente permite adjuntar JPEG, PNG o WebP (máximo 10 MiB y
20 megapíxeles), y descargarlos desde una ruta que exige sesión de funcionario.
El servidor valida y decodifica la imagen, elimina metadatos al re-encodarla y
asigna un nombre aleatorio; no conserva el nombre que envió el usuario. No se
publica `MEDIA_URL`: `PRIVATE_MEDIA_ROOT` apunta por defecto a
`private_media` dentro del repositorio y esa carpeta está excluida de Git. En
producción configurá un directorio privado fuera del webroot, con permisos
restringidos, respaldos protegidos y una política de retención acorde al uso de
documentos de clientes.

Para recibir una foto por WhatsApp, se admiten JPEG o PNG de hasta 5 MB y el
cliente debe incluir en el texto/caption el número exacto `SIN-AAAA-NNNNN`.
El contacto debe estar vinculado a un cliente
y la póliza del expediente debe pertenecer a ese cliente. Si falta esa
referencia o no se puede verificar la titularidad, la imagen no se descarga ni
se adjunta. Una foto recibida durante atención humana puede incorporarse si el
expediente es inequívoco, pero el bot no responde mientras el asesor tiene el
chat. La descarga real requiere `WHATSAPP_ACCESS_TOKEN`,
`WHATSAPP_PHONE_NUMBER_ID` y una versión vigente en `WHATSAPP_API_VERSION`;
el webhook sigue siendo simulado en desarrollo.
Meta vence los IDs de media recibidos por webhook a los 7 días y las URLs de
descarga a los 5 minutos, por eso la aplicación pide una URL nueva al procesar
cada ID y descarga enseguida. Si falla la descarga, pedile al cliente que
reenvíe la foto o que continúe con un asesor.

La implementación sigue la [Media API oficial de WhatsApp Cloud](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media)
y la [referencia oficial del webhook de imágenes](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/image).
La suite valida el protocolo con respuestas HTTP simuladas; no se probaron
credenciales, webhooks ni descargas reales de Meta en esta instalación.

## Consulta documental

La consulta documental local permite buscar pasajes de fuentes generales
cargadas y aprobadas por personal con permiso. La búsqueda compara palabras
normalizadas, no es semántica ni entrenamiento. El bot consulta esos pasajes
para preguntas de cobertura/documentación sin enviarlos al LLM; cita la fuente
y aclara que no confirma cobertura de una póliza particular. Ante respaldo
insuficiente deriva a un asesor. Las fuentes privadas de clientes no pertenecen
a esta biblioteca. El proceso y límites están en
[documentos generales](SDD/documentos_generales.md).

## Reportes de gestión

El panel `/panel/reportes/` permite seleccionar un período inclusivo y consultar
cantidad de consultas, estados actuales, motivos por tipo de consulta,
derivaciones urgentes y movimientos de cobro. El endpoint y el enlace de
exportación CSV requieren un funcionario autenticado. Cada indicador usa la
fecha del registro indicada en las [definiciones y muestra manual](SDD/reportes_gestion.md);
no se calcula una tasa de resolución de IA.

## Producción y SSL

No uses el perfil local de `.env.example` en producción. Configurá variables de
entorno de producción por separado, `DJANGO_DEBUG=false`, dominios permitidos,
una clave secreta segura, credenciales no incluidas en el repositorio y
`DB_SSLMODE=require` para exigir TLS en PostgreSQL. El ajuste por defecto del
código también es `require` si `DB_SSLMODE` no está definido. Configurá
WhatsApp real y un proveedor LLM solo cuando corresponda; no guardes esos
secretos en archivos versionados.

## VS Code (opcional)

Los archivos de `.vscode` incluyen tareas para pruebas, desarrollo y depuración.
Seleccioná `.venv\Scripts\python.exe` como intérprete de Python
(**Python: Select Interpreter**) para que VS Code use las dependencias del
proyecto.
