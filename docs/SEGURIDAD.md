# Endurecimiento de Seguros Castaño

Fecha de revisión: 4 de noviembre de 2026. Fuente: ZIP final `chat-ia-seguros-daniel-orm-bdd (1).zip`. Los cambios se hicieron en una copia. No se modificó el sitio publicado ni su base de datos.

## Qué cambió y por qué

| Riesgo encontrado | Medida aplicada | Alcance y comprobación |
|---|---|---|
| Django 5.2.4 desactualizado | Django 5.2.19, DRF 3.18.2 y Pillow 13.0.0; Gunicorn 26.2.0 en Docker | Suite funcional sobre las nuevas dependencias. Consultar evidencia del análisis de dependencias; no equivale a ausencia de vulnerabilidades. |
| Intentos ilimitados de contraseña | Cuotas atómicas en PostgreSQL: 10 intentos por cuenta y 60 por dirección de conexión cada 15 minutos | Compartidas entre workers. Devuelve HTTP 429. No se confía en X-Forwarded-For enviado por el cliente. Una red detrás del mismo proxy comparte la cuota por conexión; ajustar con pruebas y sin confiar en cabeceras arbitrarias. |
| Configuración productiva incompleta | Se exige secreto de al menos 50 caracteres y TLS a PostgreSQL; rechazo de host comodín; HTTPS y cookies Secure fuera de desarrollo | `check --deploy` y verificaciones de configuración. TLS `require` cifra; para autenticar el servidor usar `verify-full` y CA del proveedor. |
| Caché de información privada | Sesión de 8 horas, cierre al terminar navegador, SameSite y no-store en API/panel | Duración proporcional a la jornada académica; no-store protege frente a cachés, no elimina descargas hechas por el usuario. |
| Falta de registro transversal | Auditoría de escrituras y lecturas sensibles, con usuario, recurso, resultado y fecha | Sin cuerpos, consultas, contraseñas, DNI, teléfonos ni IP en claro; IP con HMAC. PostgreSQL impide UPDATE/DELETE de sus filas. El dueño de la base puede alterar los triggers: requiere separación real de roles y respaldos externos. |
| Consulta de una póliza ajena o cliente inactivo | Reconocimiento automático del número vinculado a un cliente activo; filtro por titularidad en cada consulta | No se exige validación manual al asesor. Escribir un DNI o una póliza ajena no cambia el vínculo. El número registrado no es prueba fuerte de identidad; la cartera debe mantener sus asociaciones actualizadas. |
| Una guía general podía confundirse con el contrato | Asociación explícita documento-póliza y selección por titularidad y vigencia | Sin vínculo o sin evidencia suficiente, deriva. Una fuente vinculada queda fuera de la búsqueda general. El estado de selección se renueva automáticamente, sin intervención humana. |
| Dos versiones aprobadas del mismo título podían competir | Se exige retirar la versión aprobada anterior antes de aprobar la siguiente | El retiro excluye la fuente inmediatamente de consultas nuevas. No elimina respuestas históricas. |
| Interpretación de preguntas limitada a palabras exactas | Conceptos del dominio y embeddings multilingües gratuitos ejecutados localmente | No se envían consultas ni documentos al proveedor de embeddings. El modelo requiere preparación explícita; sin él queda activo el camino por conceptos. |
| Incidente confundido con consulta informativa | Los siniestros relatados se derivan y pausan el bot; las urgencias tienen prioridad | Se comprueban preguntas hipotéticas, incidentes con otras palabras y siniestros durante la selección de póliza. La clasificación tiene límites: revisar ejemplos nuevos de la agencia. |
| Riesgos de contenido web | CSP, protección de frames, nosniff, Referrer-Policy y Permissions-Policy | Se mantienen CSS de Bootstrap/íconos de jsDelivr. La CSP no autoriza scripts remotos; el sitio externo de la agencia se abre con noopener/noreferrer. |
| Solicitudes grandes | Límite general de cuerpo, campos y archivos; límite de 1 MB en webhook; cadenas acotadas en API | Requiere además límites de cuerpo y tiempo en el proxy para cubrir tráfico lento y cuerpos sin Content-Length. |
| Webhook aplicado a una línea equivocada | Firma HMAC existente preservada y coincidencia de `phone_number_id` en modo real | Pruebas de firma y payloads. No se enviaron mensajes reales a Meta. |
| Datos en registros y prompts | Logs simulados sin cuerpo; errores de Meta con código técnico; redacción de identificadores numéricos/correos antes de prompts | La redacción no es anonimización completa: los nombres o relatos pueden seguir siendo personales. Preferir Ollama local; no habilitar proveedores externos sin revisión de privacidad. |
| Contenedores con mayor superficie de escritura | Usuario sin privilegios, cap_drop, no-new-privileges, raíz de solo lectura y volúmenes privados | Configuración entregada; construcción y despliegue Docker no certificados en este entorno. El proxy debe ser la única entrada y reemplazar X-Forwarded-Proto. |

## Perfil académico para facilitar la exposición

`MODO_DEMOSTRACION=true` requiere desarrollo, WhatsApp simulado y proveedor generativo desactivado. Muestra una advertencia visible para usar datos ficticios. No omite permisos, aprobación documental, titularidad, vigencia, límites de entrada ni auditoría. Producción rechaza este perfil al arrancar. La sesión dura 8 horas en ambos perfiles.

La demo usa datos ficticios y no acredita una verificación real de identidad. El bot reconoce automáticamente números de la cartera tanto en el perfil normal como en la demo. El asesor interviene ante derivaciones o decisiones críticas finales. No usar el perfil de demostración con datos reales.

## Protección de adjuntos conservada

Se mantienen validación real de imágenes con Pillow, límites de bytes y píxeles, normalización y eliminación de metadatos, nombres aleatorios, almacenamiento privado, descarga autenticada, verificación de titularidad del expediente y destinos permitidos para descargar desde Meta. No se permite usar el módulo documental como depósito de fotografías de DNI. No se agregó un antivirus ni se afirma detección universal de archivos maliciosos.

## Relación con las referencias solicitadas

Este es un mapa temático de controles técnicos. No es una auditoría completa por cláusula ni una declaración de conformidad.

| Referencia | Aplicación en esta entrega | Medidas organizacionales que faltan |
|---|---|---|
| ISO/IEC 27001:2022 | Accesos, configuración segura, registros, gestión de dependencias y pruebas | Evaluación y tratamiento formal de riesgos, responsables, continuidad, revisión de accesos, evidencias de operación y auditoría del sistema de gestión. |
| ISO/IEC 27701:2025 | Minimización de logs/prompts y acceso limitado a los datos del cliente reconocido | Finalidades, base legal, avisos, contratos con encargados, conservación por tipo documental y procedimiento de derechos de titulares. La norma por sí sola no define cuántos días conservar cada póliza. |
| SOC 2, criterios de servicios de confianza | Autorización, trazabilidad, cambios verificables y pruebas de funcionamiento | Definir alcance y compromisos del servicio, monitorear y conservar evidencias operativas; examen independiente si se busca un informe SOC 2. |

No existe certificación ISO ni informe SOC 2 por haber aplicado estos cambios.

## Antes de usar datos reales

1. Cambiar las credenciales de desarrollo y revisar si alguna clave estuvo expuesta en ramas o historiales anteriores. Este ZIP no contiene `.env`.
2. Separar al dueño/migrador de PostgreSQL del usuario de ejecución; el usuario web no debe ser superusuario ni poder alterar tablas/triggers. Otorgar solo permisos necesarios sobre tablas, secuencias y funciones, y probar el conjunto en staging.
3. Configurar HTTPS, certificados, proxy confiable, límites de subida, rate limiting en el borde y logs sin query strings sensibles. El token de verificación de Meta viaja en query: no registrar esa URL completa en el proxy.
4. Proteger y cifrar los discos/volúmenes y backups. Ensayar una restauración, restringir sus accesos y definir responsables. Esto no puede acreditarse con una revisión del código.
5. Establecer conservación, eliminación y acceso a mensajes, imágenes y expedientes. La entrega no borra automáticamente documentación contractual ni auditoría histórica.
6. Planificar MFA para personal, revisión de altas/bajas y recuperación de acceso. MFA no está implementado en esta entrega.
7. Revisar las decisiones de derivación con el equipo. Ninguna respuesta documental decide una indemnización ni garantiza cobertura de un hecho concreto.
8. Ejecutar `purgar_temporales` diariamente y acordar monitoreo de alertas/errores. No instalar un proceso de borrado masivo sin política aprobada.

## Límites de la revisión

Las pruebas se ejecutan con información ficticia en una base aislada y WhatsApp simulado. Se prueban componentes de integraciones con dobles de prueba. No se ejecuta un pentest contra `irusu.com.ar`, ni se valida la configuración efectiva del servidor, la cuenta Meta, el modelo generativo remoto o servicios externos. Los análisis automáticos aportan evidencia y pueden producir falsos positivos o dejar fallas sin detectar.
