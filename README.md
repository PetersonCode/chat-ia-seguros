# Seguros Castaño — MVP 2 final para la facultad

Integra el `main` del equipo al 4/11/2026, incluidos P1 (vehículos y compañías), vencimientos y recordatorios, y su ampliación de búsqueda, comisiones y control de duplicados. Conserva el diseño y la gestión del equipo, incorpora hardening y un bot que consulta automáticamente al cliente reconocido por su número. El alcance actual es **solo automotor**.

## Recorrido final

- Número de WhatsApp ya vinculado a un cliente activo: el bot consulta saldo, vencimientos, asistencia y las condiciones de su póliza sin pedir validación del asesor.
- Varias pólizas automotor: pregunta al cliente cuál quiere consultar. No requiere que el asesor elija por él.
- Condiciones: solo documentos aprobados vinculados a la póliza elegida. Entiende conceptos y, con el modelo preparado, preguntas redactadas con otras palabras.
- Siniestro ocurrido: registra la consulta, deriva y pausa el bot. Choques, robos y otras urgencias tienen prioridad urgente; otros incidentes se derivan normalmente.
- Asesor: interviene ante derivación o en decisiones críticas finales (baja, modificación, reembolso, alta de cliente y revisión de información de la agencia).

No hay botón ni requisito de validación manual de identidad. Reconocer un número de la cartera no constituye una certificación de identidad: la firma de Meta y la asociación número-cliente son la base del acceso. Escribir un DNI o una póliza ajena no vincula una cuenta.

## Instalación

Requisitos: Python 3.12, PostgreSQL 17 y Node.js/npm para las pruebas del frontend. No se usa SQL Server.

Crear previamente una base `proyecto` y un usuario propio con acceso a ella mediante pgAdmin o PostgreSQL; adaptar las variables a esa instalación. Para ejecutar tests ese usuario necesita poder crear una base de pruebas. Los scripts siguientes no instalan ni crean el servicio PostgreSQL.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.demo.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

Editar `.env` con el secreto generado y la conexión de una base propia. Usar `.venv` para los comandos siguientes (activar el entorno o llamar su `python.exe`). No subir `.env` a GitHub.

En una base nueva de demostración aplicar SQL **01 a 13, 17 y 22 a 26 en orden**, incluyendo 02 para cargar funcionarios y catálogos ficticios. SQL 12 agrega la charla; SQL 13 agrega vehículos y compañías; SQL 17 agrega interesados y cotizaciones; SQL 22 incorpora el hardening, SQL 23 los recordatorios, SQL 24 la cartera, SQL 25 las altas por chat y SQL 26 los planes y las condiciones de póliza. Los números 14–16 y 18–21 están reservados para especificaciones futuras. Nunca ejecutar 00 sobre datos que quieran conservar. Ejemplo PowerShell, adaptando la conexión a `.env`:

```powershell
Get-ChildItem .\SDD\sql\*.sql |
    Where-Object { $_.Name -notlike '00_*' } |
    Sort-Object Name |
    ForEach-Object {
        & psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f $_.FullName
        if ($LASTEXITCODE -ne 0) { throw 'Se detuvo la preparación de la base.' }
    }
python manage.py migrate
python manage.py crear_usuarios_funcionarios --clave "ElegiUnaClaveLocalSegura"
python manage.py cargar_demo_exposicion
python manage.py preparar_busqueda
python manage.py verificar_busqueda_local
python manage.py runserver
```

Abrir `http://127.0.0.1:8000/`. Entrar como `graciela@seguroscastano.example` con la clave local elegida. Diego es operador y Roberto propietario. El comando `crear_usuarios_funcionarios` restablece las contraseñas de los funcionarios ficticios activos si se vuelve a ejecutar; no corre automáticamente.

Mantener otra terminal con la misma configuración:

```powershell
python manage.py reprocesar_pendientes --continuo
```

### Base existente del ZIP final recibido

Respaldar. Si ya se aplicaron 01 a 11, aplicar **SQL 12 (charla), 13 (vehículos/compañías), 17 (interesados), 22 (seguridad), 23 (recordatorios), 24 (cartera), 25 (altas por chat) y 26 (planes y condiciones por póliza)**, y ejecutar `migrate`. No volver a ejecutar el seed ni 00.

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\12_tipos_de_charla.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\13_vehiculos_companias.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\17_interesados.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\22_seguridad_y_coberturas.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\23_recordatorios_polizas.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\24_cartera_vehiculos.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\25_altas_por_chat.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\26_condiciones_en_poliza.sql
python manage.py migrate
python manage.py check
```

Instalar las nuevas dependencias, preparar el modelo y reiniciar web/worker. Django no crea las tablas del negocio con `migrate`, porque son `managed=False`.

## Altas de clientes y pólizas por acciones

El bot reúne los datos del chat y deja una solicitud preparada en la base. El asesor revisa y confirma el cliente; para una póliza ingresa únicamente la **prima mensual acordada** y confirma. El cliente no fija precios ni comisiones. Se crean los registros y sus cuotas al confirmar, y se prepara automáticamente el aviso al cliente, también ante rechazo o finalización de una gestión externa.

[Flujo, datos solicitados, actualización SQL 25 y pruebas](docs/ALTAS-POR-CHAT.md). Se mantienen WhatsApp simulado para la exposición, la derivación inmediata de siniestros y la identidad visual del panel.

## Vehículos, compañías y comisiones

La ficha permite completar datos estructurados del vehículo y asociar la compañía emisora y su comisión. Clientes y Vencimientos buscan por patente, chasis, marca/modelo o «la camioneta de Pérez». Se impiden pólizas superpuestas para el mismo vehículo, incluso ante altas simultáneas. Reportes muestra comisión estimada y calculada sobre pagos registrados por compañía y cliente, con exportación CSV restringida a aprobadores.

Para actualizar desde el `main` que ya tiene 13, 22 y 23, aplicar **SQL 24 y 25** y reiniciar web/worker. Después ejecutar `python manage.py auditar_cartera` y completar vínculos históricos desde la ficha. [Guía, fórmulas, permisos y recorrido para exponer](docs/VEHICULOS-Y-COMISIONES.md).

## Vencimientos y recordatorios

Desde **Vencimientos** se ven primero las pólizas con cuotas atrasadas, desde el atraso más antiguo; luego las de vencimiento más cercano. Incluye saldo total, importe vencido y un botón que prepara el aviso. Se conserva la identidad visual del panel. Para actualizar una instalación que ya tiene SQL 22, aplicar solo SQL 23 y reiniciar web/worker. [Guía y ejemplo de siete días](docs/VENCIMIENTOS.md).

```powershell
python manage.py cargar_demo_vencimientos
```

Este lote opcional habilita datos ficticios y un chat simulado para exponer; no corre al arrancar. El envío directo respeta la ventana de WhatsApp. Fuera de ella ofrece texto para contacto manual; no marca como enviado al abrir el enlace.

## Exposición lista con el PDF ficticio

`cargar_demo_exposicion` prepara a **Lucía Rivas**, teléfono simulado **+5491100009001**, póliza **POL-90101**, cobertura automotor total, dos cuotas pendientes por un total inicial de **$96.000** y condiciones vinculadas. No modifica contraseñas ni reinicia pagos existentes. Usa información de automotor de las páginas 2 y 4 del PDF aportado; los ejemplos de moto no forman parte de este alcance.

```powershell
python manage.py simular_whatsapp +5491100009001 "Necesito el número de la grúa"
python manage.py simular_whatsapp +5491100009001 "¿Qué saldo tengo pendiente?"
python manage.py simular_whatsapp +5491100009001 "¿Qué cubre mi póliza?"
python manage.py simular_whatsapp +5491100009001 "¿Qué protección tengo si se quiebra el vidrio frontal del coche?"
python manage.py simular_whatsapp +5491100009001 "Me chocaron en la autopista"
```

**Dejar la urgencia para el final:** pausa el bot y deriva al equipo. Para continuar, el asesor usa Devolver al bot. Todos los siniestros relatados activan derivación; una pregunta hipotética sobre condiciones no es un siniestro ya ocurrido.

Los teléfonos son ejemplos ficticios: no llamar ni enviar mensajes reales. El lote tiene vigencia durante 2026; actualizar datos ficticios si se demuestra después. El PDF original se conserva en `datos_demo/` como referencia histórica y tiene reglas anteriores que no describen el bot actualizado.

## Seguridad sin entorpecer la demo

`.env.demo.example` habilita un aviso visible y exige WhatsApp simulado, LLM generativo desactivado y desarrollo. `.env.example` deja desactivado el aviso. Las sesiones duran 8 horas y se cierran al terminar el navegador. Roles, validación, auditoría y protección de datos permanecen activos en ambos perfiles.

En producción: `DJANGO_DEBUG=false`, `MODO_DEMOSTRACION=false`, secreto propio, TLS a PostgreSQL, HTTPS y proxy confiable. El perfil académico no arranca en producción. No se modificó el servidor publicado.

## Cargar información de la agencia

Entrar como aprobador en **Compañías → Planes por compañía**. Cargar una vez qué cubre cada plan, sus exclusiones, límites de referencia y asistencia. En **Pólizas**, elegir el plan de esa compañía, revisar las particularidades del contrato y guardar: el bot ya puede consultar esa copia, sin un trámite documental separado. Editar un plan no modifica contratos existentes. La pantalla histórica de Documentos se conserva fuera del menú, junto con sus datos y vínculos. No hay importador automático de PDF/Word.

Para actualizar desde `main` e8b1b46, aplicar **solo SQL 26** y reiniciar web y worker. [Flujo de planes, actualización y límites del bot](docs/POLIZAS-Y-PLANES.md).

El modelo gratuito de FastEmbed/ONNX se descarga con `preparar_busqueda` una sola vez y corre localmente. Los pesos no están dentro del ZIP para evitar cientos de MB; se conservan en `.modelos/` o en el volumen Docker `modelos`. Si falta, sigue la búsqueda por conceptos. No hace falta una API paga.

## Pruebas y documentos

```powershell
python manage.py check
python manage.py test --noinput
npm test
python manage.py verificar_busqueda_local
```

La suite crea y destruye `test_proyecto`, requiere CREATEDB y fuerza simulación, modelo desactivado y perfil normal. El hasher rápido se limita a los tests; la app usa PBKDF2 y hay una prueba explícita de ese login. La prueba del modelo real se ejecuta por separado.

- `docs/SEGURIDAD.md`: medidas y riesgos pendientes, alineación temática con ISO 27001, ISO 27701 y SOC 2.
- `docs/BOT_Y_DOCUMENTOS.md`: funcionamiento del bot y de sus fuentes.
- `docs/EXPOSICION.md`: guion breve y ejemplos para cuatro integrantes.
- `docs/OPERACION.md`: actualización, servidor y mantenimiento.
- `docs/REFERENCIAS.md`: fuentes y herramientas utilizadas.
- `docs/CAMBIOS.md`: diferencias frente al ZIP recibido.
- `docs/INTEGRACION.md`: cambios del segundo ZIP incorporados y planes aún pendientes.
- `evidencia/RESULTADOS.md`: pruebas realmente ejecutadas y sus límites.

Los SDD previos se conservan como antecedentes; README y `docs/` describen esta versión. P1 y P5 están entregados (P5 sin el seguimiento automático ni el comparador de renovaciones, que esperan a P2 y P3); P2–P4 y P6–P9 son especificaciones futuras, no funcionalidades entregadas: el verificador SDD también cuenta sus criterios pendientes. Esto no constituye una certificación ISO ni un informe SOC 2. Repetir la exposición en la computadora del equipo y declarar la asistencia de IA conforme a la consigna.
