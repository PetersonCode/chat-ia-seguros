# Operación y actualización

## Exposición académica

Preparar con anticipación las dependencias, PostgreSQL, el modelo local y los documentos ficticios vinculados a pólizas. Usar `.env.demo.example` y ejecutar `cargar_demo_exposicion`. La sesión del panel dura 8 horas. El equipo puede alternar entre operadores y aprobadores para demostrar permisos sin configurar cuentas reales de Meta ni servicios pagos.

El número de Lucía ya queda vinculado automáticamente a su cuenta ficticia. No hay botón ni plazo de verificación manual. El contexto de selección de póliza dura 4 horas y se renueva automáticamente. Las operaciones críticas y la preparación de documentos conservan aprobación y auditoría. Usar la urgencia al final: cualquier siniestro ocurrido deriva y pausa el bot. El asesor asignado puede devolver la conversación al bot.

## Actualización de una instalación existente

1. Guardar un respaldo probado de la base y del volumen de imágenes. Conservar una copia del código y las variables del despliegue anterior.
2. Detener o drenar web/worker durante el cambio de esquema.
3. Instalar dependencias nuevas, aplicar SQL 12 (charla) y 22 (seguridad) si existen 01–11 y ejecutar migraciones Django. SQL 22 es aditivo y transaccional; no es un script de limpieza y se aplica una vez.
4. Preparar el modelo y vincular fuentes contractuales desde el panel o API. La preparación del modelo no transmite documentos de clientes: descarga pesos públicos.
5. Comprobar la configuración normal o de producción según el entorno, iniciar web/worker y probar login, roles, adjuntos, documentos y un flujo de mensajes ficticios.
6. Ante un problema, detener la versión nueva y evaluar recuperación desde el respaldo. No ejecutar `00_drop_all.sql` para revertir una actualización.

Las tablas nuevas no son creadas por `manage.py migrate`: los modelos del negocio mantienen `managed=False`.

SQL 12 es la actualización de charla del segundo ZIP; SQL 22 agrega seguridad y coberturas. Si 12 ya está aplicado, agregar solo 22. Los números 13–21 corresponden a planes futuros que no se implementaron todavía. Ver `INTEGRACION.md`.

## Variables y servidor productivo

- `DJANGO_DEBUG=false` y `MODO_DEMOSTRACION=false`.
- `DJANGO_SECRET_KEY`: aleatoria, propia, al menos 50 caracteres, fuera del repositorio.
- `DJANGO_ALLOWED_HOSTS`: dominios concretos, sin `*`.
- `DB_SSLMODE=require` como mínimo. Para validar identidad del servidor, usar `verify-full` y una CA configurada en libpq/infraestructura.
- Credenciales Meta propias, tokens secretos y `phone_number_id` de la línea correcta. El webhook rechaza mensajes de otra línea en modo real.
- `BUSQUEDA_SEMANTICA=true` después de preparar el modelo. `MODELO_BUSQUEDA_DIR` debe ser privado y persistente.
- El proveedor generativo es opcional y no participa en la cita documental. Para la facultad puede quedar `LLM_PROVIDER=none`. Revisar privacidad antes de conectar un proveedor externo; la redacción de prompts no anonimiza todos los datos personales.

`config.settings_docker` asume un proxy que reemplaza X-Forwarded-Proto y que la aplicación solo es accesible por la red privada. No publicar directamente el puerto de Gunicorn a Internet. `USE_X_FORWARDED_HOST` queda desactivado. El compose existente depende de las redes externas del equipo y no es una instalación autónoma de PostgreSQL.

La raíz del contenedor es de solo lectura. Los volúmenes `private_media` y `modelos` conservan sus datos y son escribibles por el usuario de la app. Para preparar el modelo:

```powershell
docker compose run --rm web python manage.py preparar_busqueda
```

El proxy debe servir `/static/` desde los archivos estáticos de esta versión (o un resultado de `collectstatic` preparado antes de poner el sistema en servicio), sin exponer `/private_media/`, `.env`, `.modelos/` ni el árbol del proyecto. No se agregó un servidor público de archivos privados.

Ejecutar `python manage.py check --deploy --settings=config.settings_docker` con las variables reales. La revisión aislada del perfil productivo dejó dos advertencias intencionales: HSTS sin `includeSubDomains` y sin `preload`. No se activaron sobre un dominio cuyos subdominios y compromiso de precarga no se comprobaron. El responsable del dominio debe decidirlo; no significa que se haya probado el TLS del servidor publicado.

Configurar en el proxy límites de cuerpo y tiempo, protección de autenticación en el borde, rotación de logs y exclusión de query strings del webhook que contienen tokens de verificación. La cuota por IP de la aplicación usa la dirección de conexión, por lo que detrás de un proxy puede ser compartida; calibrar sin habilitar cabeceras de clientes no confiables.

## Mantenimiento mínimo

- Diariamente: revisar fallos de envío, alertas y capacidad; ejecutar `python manage.py purgar_temporales`. Este comando elimina solo contextos de selección vencidos y cuotas de acceso de más de un día.
- Al cambiar personal: desactivar su cuenta y revisar permisos y responsables de casos.
- Al cambiar el teléfono de un cliente: revisar y actualizar las asociaciones de su cartera. La selección se invalida si cambia el cliente del contacto y cada consulta verifica titularidad. No vincular cuentas a partir de un DNI escrito en el chat.
- Al cambiar una póliza: revisar documentos y adicionales asociados. Retirar fuentes que ya no correspondan y aprobar versiones revisadas.
- Periódicamente: actualizar y auditar dependencias, ensayar restauración y repetir pruebas sobre staging.

La retención de mensajes, expedientes y auditoría debe definirse con la agencia. El sistema no elimina automáticamente documentación contractual. La inmutabilidad por trigger no protege contra el dueño/superusuario de la base: respaldos, roles restringidos y exportación a un repositorio de logs separado son controles operativos pendientes.

El botón Borrar conversación del compañero es una acción crítica final: solo un aprobador puede confirmarla. Borra el chat sin posibilidad de deshacer; se rechaza con acciones pendientes, siniestros o fotos dependientes. Las acciones ya resueltas no lo impiden: el caso que las respalda queda sin chat como auditoría y solo salen de la bandeja el chat, sus mensajes y sus alertas. Para empezar otra charla conservando el historial usar Vaciar chat. Borrar un chat no elimina la auditoría de seguridad. El descarte de alertas conserva las filas, el autor y la resolución; no debe emplearse para ocultar un incidente pendiente de revisión.

## Cómo consultar la auditoría

Desde una cuenta administrativa de base con permiso de solo lectura:

```sql
SELECT fecha, usuario_id, evento, recurso, estado
FROM auditoria_seguridad
ORDER BY id DESC
LIMIT 100;
```

`usuario_id` corresponde al usuario Django; el funcionario se identifica por su email en el modelo existente. Se guardan fechas, recursos y resultados, no el contenido del mensaje ni la contraseña. Conservar evidencias de acceso y cambios conforme a la política acordada.
