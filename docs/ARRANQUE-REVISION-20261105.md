# Arranque de la revisión del 5 de noviembre de 2026

Esta entrega se basa en `origin/main` **1cbe23d** y conserva los aportes del grupo. El código de trabajo está en `integrar-backend`. No se publica ni se fusiona a `main` automáticamente.

## Si ya tienen la base del main actual

1. Respaldar la base y conservar su `.env` privado. Detener web y workers durante la actualización.
2. Actualizar el código y las dependencias con el Python del entorno virtual:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. Aplicar **solo las actualizaciones que falten**. Si ya llegaron a SQL 30, las nuevas son estas dos; adaptar host, puerto, usuario y base a su instalación:

   ```powershell
   psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\31_relaciones_interesados.sql
   if ($LASTEXITCODE -ne 0) { throw 'No continuar: falló SQL 31.' }
   psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\32_nombre_plan_historico.sql
   if ($LASTEXITCODE -ne 0) { throw 'No continuar: falló SQL 32.' }
   .\.venv\Scripts\python.exe manage.py migrate
   .\.venv\Scripts\python.exe manage.py check
   ```

   SQL 31 agrega los vínculos del interesado con vehículo y contrato. Solo reconstruye el vehículo cuando cliente y patente coinciden; no adivina pólizas históricas. SQL 32 conserva el nombre del plan confirmado; cuando una versión antigua ya perdió su nombre, se muestra como plan histórico en lugar de inventar el nombre anterior.

4. Reiniciar **web y todos los workers con el mismo código**. Las páginas usan versiones nuevas de estáticos para evitar mezclar JavaScript antiguo con las APIs corregidas.

**No ejecutar SQL 00 ni volver a cargar semillas en una base existente. No ejecutar el comando de usuarios para actualizar código: restablece sus contraseñas.** Los modelos de negocio son `managed=False`: ejecutar solo `migrate` no reemplaza los scripts SQL.

## Instalación nueva de demostración

Requiere Python 3.12, PostgreSQL 17 y una base/usuario propios. Node.js se necesita para las pruebas de JavaScript. El ZIP no incluye una base, credenciales, entornos virtuales ni archivos privados de clientes.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.demo.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

Editar `.env`: usar el secreto generado, conexión local correcta, `DJANGO_DEBUG=true`, `WHATSAPP_MODO=simulado`, `LLM_PROVIDER=none` y `DB_SSLMODE=disable` para PostgreSQL local sin TLS. El perfil de producción mantiene HTTPS y TLS; el perfil de demostración no debe usarse en producción.

En una **base nueva vacía**, aplicar los scripts SQL presentes en orden, salvo 00. El ejemplo reemplaza el seed histórico 02 por `SDD/plantillas/catalogos_iniciales.sql`, que crea únicamente catálogos y funcionarios ficticios. El 02 original se conserva para la importación histórica y también contiene clientes/consultas antiguos: no se utiliza en este arranque limpio. Las operaciones de la agencia se cargan desde las pantallas.

```powershell
Get-ChildItem .\SDD\sql\*.sql |
    Where-Object { $_.Name -notlike '00_*' } |
    Sort-Object Name |
    ForEach-Object {
        $archivoSql = if ($_.Name -like '02_*') { '.\SDD\plantillas\catalogos_iniciales.sql' } else { $_.FullName }
        & psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f $archivoSql
        if ($LASTEXITCODE -ne 0) { throw 'Se detuvo la preparación de la base.' }
    }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py crear_usuarios_funcionarios --clave "ElegiUnaClaveLocalSegura"
.\.venv\Scripts\python.exe manage.py check
```

Usar una clave propia. El comando de usuarios es una preparación inicial: volver a ejecutarlo restablece las claves de las cuentas ficticias activas. Graciela puede aprobar, Diego es operador y Roberto administra usuarios como propietario. La cuenta administrador se reserva para la gestión de prueba; no es necesaria para la atención diaria.

## Iniciar y operar

Terminal web:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Abrir **http://127.0.0.1:8000/** e ingresar con el usuario ficticio y la clave que eligieron. Crear compañías/planes, interesados, clientes, vehículos, pólizas, pagos y expedientes **desde las pantallas**. No hay que insertar registros por shell para completar esos flujos.

Segunda terminal, reintentos y agrupación del bot:

```powershell
.\.venv\Scripts\python.exe manage.py reprocesar_pendientes --continuo
```

Tercera terminal, programación de avisos cada hora:

```powershell
while ($true) {
    .\.venv\Scripts\python.exe manage.py procesar_gestion
    Start-Sleep -Seconds 3600
}
```

En **Inicio → Actualizar avisos** se puede hacer la misma actualización manualmente. Activar los automáticos es una decisión del aprobador. Se respetan consentimiento, horario, ventana de WhatsApp, modo de atención y máximo de un aviso al día por contacto. La simulación no envía nada a Meta ni a teléfonos reales.

## Bot sin servicios pagos

La ruta por conceptos/sinónimos funciona con `LLM_PROVIDER=none`. Para habilitar además el modelo multilingüe gratuito de búsqueda local:

```powershell
.\.venv\Scripts\python.exe manage.py preparar_busqueda
.\.venv\Scripts\python.exe manage.py verificar_busqueda_local
```

La primera descarga requiere Internet. Después la inferencia es local. Configurar `BUSQUEDA_SEMANTICA=true` y reiniciar web/worker. Los pesos quedan en `.modelos/`, excluidos de Git y del ZIP. El modelo ayuda a recuperar información; no autoriza inventar coberturas ni usar pólizas de otro cliente.

Para probar el canal de entrada sin WhatsApp real, usar un teléfono **ficticio que hayan registrado desde la interfaz**:

```powershell
.\.venv\Scripts\python.exe manage.py simular_whatsapp +5491100005508 "¿Qué cubre mi póliza?"
```

Este comando simula el canal del cliente: no es una pantalla del asesor. Antes de probar respuestas automáticas, comprobar que el chat esté en modo bot. Un siniestro relatado pausa y deriva la conversación.

## Comprobaciones del equipo

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test --noinput
npm.cmd test
```

Las pruebas usan una base separada `test_...`; el usuario de PostgreSQL necesita `CREATEDB`. Nunca apuntar la base de pruebas a una base existente. Para repetir las demostraciones, seguir la matriz del informe de revisión con datos ficticios propios; no reutilizar datos personales reales.
