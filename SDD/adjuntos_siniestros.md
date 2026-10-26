# Documentación privada de siniestros

## Alcance y controles

- La carga desde el panel y la descarga usan endpoints de sesión de funcionario;
  no hay ruta pública de `MEDIA_URL`.
- Desde el panel se aceptan imágenes JPEG, PNG y WebP, hasta 10 MiB y 20
  megapíxeles. Se
  decodifican y re-encodan para detectar contenido falso y quitar metadatos.
  Animaciones, formatos distintos y archivos corruptos se rechazan.
- El nombre original no se guarda. El almacenamiento genera una clave UUID
  bajo `PRIVATE_MEDIA_ROOT/siniestros/<id>/`; el directorio predeterminado
  `private_media` está excluido de Git.
- Los metadatos viven en `siniestro_adjuntos`, creada por
  `08_adjuntos_siniestros.sql` después de `07_expediente_siniestros.sql`.
  Django mantiene `managed=False`; agregar el modelo no crea la tabla con
  `migrate`. El runner de tests aplica el SQL incremental.
- La asociación por panel usa el expediente seleccionado. La asociación desde
  WhatsApp requiere `SIN-AAAA-NNNNN` en el caption, un contacto vinculado y que
  la póliza del expediente pertenezca al cliente del contacto. Sin todos esos
  controles no se descarga ni se asocia.
- Desde WhatsApp se admiten solo JPEG o PNG de hasta 5 MiB, de acuerdo con los
  tipos y límites publicados por Meta para imágenes.
- Una foto puede incorporarse durante atención humana si el expediente es
  verificable; no se emite respuesta automática mientras el chat esté tomado.
  Una incorporación no cambia el estado del siniestro ni confirma cobertura,
  aceptación o indemnización.
- El proceso se ejecuta desde `trabajos_whatsapp`, una cola durable en
  PostgreSQL. El worker y la recuperación al reiniciar se documentan en
  `README.md`; un fallo durante descarga deja el trabajo reintentable y, tras
  ocho intentos, en estado terminal para revisión.

## Meta WhatsApp Cloud

El webhook conserva el ID de media y el checksum del mensaje entrante. El
proceso consulta `GET /{MEDIA-ID}` autenticado para solicitar una URL fresca y
descarga el binario con Bearer token. Comprueba ID, MIME, tamaño y SHA-256 antes
de guardar; restringe las descargas y redirecciones a HTTPS de dominios Meta.
Nunca se toma una URL arbitraria del payload. Los errores de red no incluyen
tokens ni URLs en el mensaje que se guarda en el chat.

Meta documenta que los IDs de media de mensajes entrantes expiran a los 7 días
y sus URLs de descarga a los 5 minutos. El SHA-256 del webhook está codificado
en Base64 y se verifica contra los bytes descargados.

Referencias oficiales vigentes consultadas:

- [WhatsApp Cloud API — Media](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media)
- [WhatsApp Cloud API — Image messages webhook](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages/image)

En un despliegue real se requiere un token de acceso con permisos de mensajería
de WhatsApp, `WHATSAPP_PHONE_NUMBER_ID` y una versión de Graph API soportada
configurada como `WHATSAPP_API_VERSION`. No hay credenciales de Meta configuradas en desarrollo,
por lo que los tests simulan las respuestas HTTP y no acreditan conectividad
con una cuenta real.
