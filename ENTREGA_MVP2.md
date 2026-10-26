# MVP 2 corregido — Seguros Castaño

Este paquete contiene el sistema completo basado en la versión final recibida, con correcciones funcionales, interfaz documental, finalización de gestiones externas y pruebas. Conserva Django, PostgreSQL y el diseño existente.

## Para empezar

1. Descomprimir y abrir esta carpeta en VS Code.
2. Seguir `README.md` para crear `.venv`, instalar `requirements.txt` y completar una copia de `.env.example` llamada `.env`.
3. En una base PostgreSQL nueva, aplicar los scripts **01 a 11**, en ese orden, y ejecutar `python manage.py migrate`.
4. Ejecutar explícitamente `python manage.py crear_usuarios_funcionarios --clave "una-clave-local-elegida"`. Este comando asigna esa contraseña a los funcionarios ficticios activos; repetirlo restablece esas contraseñas.
5. Opcionalmente, ejecutar `python manage.py cargar_demo_mvp2`. Requiere desarrollo, WhatsApp simulado y LLM desactivado. Carga un cliente ficticio actual con dos pólizas, solicitudes de revisión y una fuente académica aprobada. Repetirlo no duplica la muestra ni modifica contraseñas.
6. Ejecutar `python manage.py runserver` y abrir `http://127.0.0.1:8000/`. Ingresar, por ejemplo, con `graciela@seguroscastano.example` y la clave que eligieron.
7. Para recibir mensajes de un webhook y procesar reintentos, mantener otra terminal con `python manage.py reprocesar_pendientes --continuo`.

El cliente de la muestra se llama **Cliente Demostración**, tiene DNI ficticio **90000001** y número simulado **+5491199990001**. El histórico original sigue separado de los nuevos ejemplos por sus propios clientes y fechas.

## Si ya tienen la base de la versión anterior

Si esa base ya tiene aplicados los scripts 01 a 10, no vuelvan a ejecutarlos. Con un respaldo previo, apliquen solamente:

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\11_finalizaciones_acciones.sql
python manage.py check
```

Adapten host, puerto, usuario y nombre a su instalación. El script 11 agrega el registro de finalizaciones y sus controles, conservando clientes, conversaciones, pólizas y aprobaciones existentes. Se aplica una sola vez. No ejecuten `00_drop_all.sql` para actualizar.

## Cambios que deben entender y contemplar

### Atención y derivación

- Se detectan más variantes de choques, robos y hospitalización como urgencias, sin depender del modelo. Se mantienen diferenciadas preguntas generales y negaciones.
- Al pasar al modo humano, siguen llegando los avisos controlados de derivación y confirmación de datos. Las respuestas automáticas ordinarias continúan bloqueadas.
- Se preservan la retención de respuestas inseguras, la titularidad de las pólizas y los permisos de aprobación.

### Biblioteca documental

- Un aprobador puede cargar texto autorizado con título, versión y referencia; revisar el contenido; aprobarlo; y retirarlo desde Documentos.
- Los operadores consultan únicamente fuentes aprobadas. Los borradores y las fuentes retiradas quedan fuera del bot.
- La cita exacta de un fragmento aprobado respalda sus importes, fechas y cláusulas. Los datos agregados fuera de la cita siguen pasando por los controles habituales. La verificación de identidad, datos ajenos y URLs no se desactiva.
- Una cita general nunca confirma por sí sola que una cobertura se aplique al contrato de una persona.

### Gestiones externas

- Reembolsos y modificaciones quedan aprobados hasta que se registra que su gestión externa se completó.
- En **Acciones → Aprobadas → Ver detalle → Registrar gestión completada**, un aprobador ingresa referencia y motivo.
- Se conservan por separado la aprobación original y la finalización: responsables, fechas y evidencia. El registro de finalización es inmutable.
- La base impide completar estas gestiones sin evidencia. Dos finalizaciones concurrentes registran una sola.
- El caso puede cerrarse después de completar sus gestiones y resolver otros pendientes. Registrar una finalización no ejecuta una transferencia bancaria ni cambia un contrato en una aseguradora externa.

### Pólizas y cuotas

- Las primas rechazan valores no finitos, fuera de rango y fracciones de centavo con un error de validación, sin guardar datos parciales.
- Se conserva la posibilidad previa de prima cero: ahora no genera cuotas ni pagos ficticios. La vista previa lo explica.
- Se conserva la regla de ciclos mensuales por aniversario de inicio y cobro completo del ciclo parcial final. El campo `periodo` sigue identificando el primer día del mes; el vencimiento corresponde al inicio del ciclo.
- La búsqueda de la bandeja reconoce mayúsculas y acentos también en instalaciones PostgreSQL con configuración regional C.

### Pruebas y preparación

- Se actualizaron expectativas de fechas, vencimientos, dependencias y columnas nuevas.
- Se corrigieron la lectura del CSV de prueba y el cierre de imágenes en Windows.
- Las pruebas unitarias que ejecutan workers conservan su conexión envolvente; pruebas separadas verifican commits reales, cierres de conexiones y concurrencia.
- Se agregó una carga de demo optativa y se actualizaron las versiones de los estáticos para evitar que el navegador conserve JavaScript anterior.
- El ZIP de distribución excluye entornos virtuales, cachés, historial Git y credenciales reales.

## Verificar en sus computadoras

```powershell
python manage.py check
python manage.py test --noinput
npm test
```

Los tests requieren permiso `CREATEDB` para crear y destruir `test_proyecto`. El runner fuerza WhatsApp simulado, LLM desactivado y espera de agrupación cero; los tests de integraciones específicas usan dobles de prueba. La configuración normal de ejecución conserva sus propias opciones.

El runner acelera la creación de usuarios ficticios con un hasher de prueba
(MD5), limitado al proceso de tests y restaurado al terminar. La aplicación
normal conserva PBKDF2; una prueba específica y el login de navegador verifican
también ese camino. Esto no cambia cómo se guardan las contraseñas al ejecutar
el sistema normalmente.

Los resultados ejecutados para este paquete se documentan en `evidencia/RESULTADOS.md`. Esa evidencia se debe complementar con la prueba humana del equipo en la computadora de exposición.

## Guion de demostración

1. Entrar como aprobador y localizar Cliente Demostración.
2. Abrir sus dos pólizas. Registrar un cobro con referencia; repetir la misma referencia para verificar que no se cobre otra cuota.
3. Revisar la solicitud de baja y seleccionar la póliza correcta antes de aprobar.
4. Completar el importe del reclamo, aprobarlo y comprobar que todavía requiere gestión externa. Registrar referencia y motivo al finalizarlo.
5. Registrar un siniestro desde el panel, adjuntar una foto, revisar el historial y avanzar por los estados permitidos.
6. En Documentos, cargar una versión nueva, buscarla como borrador, aprobarla, buscar su cita y retirarla.
7. Simular una urgencia desde otra conversación ficticia con `python manage.py simular_whatsapp +5491199990002 "Me robaron la moto"`. Ver la prioridad y la atención humana en la bandeja.
8. Tomar el control, responder como asesor y devolver la conversación al bot.
9. Resolver los pendientes y cerrar los casos. Generar y exportar un reporte del período.
10. Entrar como Diego y comprobar que puede atender, pero no aprobar ni administrar fuentes.

## Alcance real de esta entrega

- La base implementada es **PostgreSQL**. El proyecto no incorpora un adaptador para SQL Server; la propuesta académica debe reflejar o justificar esta elección.
- El modo local puede ejecutarse sin servicios pagos: WhatsApp es simulado y la clasificación por reglas funciona sin modelo. La configuración de un proveedor LLM compatible ya existente se conserva.
- La biblioteca recupera pasajes por coincidencia de palabras y cita la fuente. No se presenta como entrenamiento de un modelo ni como búsqueda semántica con embeddings.
- Las cotizaciones contractuales se derivan a un asesor; no se inventan tarifas. La denuncia completa se registra en el panel y las imágenes por WhatsApp se vinculan a un expediente existente.
- WhatsApp real requiere cuenta, número y credenciales propios de Meta; el proveedor LLM real requiere sus opciones de conexión. El paquete no contiene claves reales y sus pruebas no certifican esas cuentas ni una instalación de producción.
- Los textos académicos de la demo son ficticios, están identificados como tales y no describen coberturas reales.

## Archivos de referencia

- `README.md`: instalación y configuración.
- `SDD/sql/11_finalizaciones_acciones.sql`: actualización de base adicional.
- `evidencia/`: resultados y comprobaciones de esta entrega.
- `SDD/entregas/T15.md`: recorrido y documentación previa, con la actualización del cierre.

El equipo debe comprender los cambios, comprobar las reglas con la cátedra y presentar el uso de IA según la consigna.
