# Mejoras de la entrega integrada

## Atención y resultado para el cliente

1. Alcance automotor aplicado al bot y a las altas nuevas. Se mantienen los datos históricos del equipo.
2. Reconocimiento automático del número ya vinculado al cliente activo. Se eliminaron el botón y la exigencia de verificación manual para saldo, vencimientos, grúa y cobertura.
3. Consulta de condiciones de la póliza correcta: titularidad, vigencia, selección por el cliente cuando tiene varias, contexto temporal y documentos vinculados explícitamente.
4. Búsqueda por conceptos y modelo multilingüe local gratuito. Una respuesta cita el pasaje aprobado y su versión; sin evidencia deriva, sin inventar condiciones.
5. Derivación de todos los siniestros relatados, con prioridad para urgencias. El bot se pausa y conserva el aviso; una pregunta hipotética de cobertura continúa como consulta informativa.
6. Seguimientos sobre la póliza elegida y conservación del historial con el rol de quien habló. Respuestas de cortesía sin abrir trámites.
7. Lote de exposición reproducible basado en el PDF ficticio: Lucía, una póliza automotor total, dos cuotas iniciales impagas y condiciones/asistencia aprobadas.

## Panel y trabajo del asesor

8. Acceso visible a Documentos, Siniestros y Reportes; formulario para asociar condiciones a una póliza. Preparación/aprobación del conocimiento una vez, no por consulta.
9. Identificación visible de la derivación urgente y del asesor asignado. El botón permite tomar el chat cuando lo tiene otra persona; solo quien lo tiene puede devolverlo al bot, conforme al backend.
10. Perfil académico con aviso visible, WhatsApp simulado, modelo generativo opcional desactivado y sesión de ocho horas. Mantiene roles y controles por detrás.
11. Se conservaron las nuevas funciones del compañero: descarte firmado de alertas y borrado de chats con permisos, confirmación y protección de expedientes. Ver `INTEGRACION.md`.

## Endurecimiento

12. Dependencias actualizadas y revisadas; versiones de ejecución documentadas. El análisis automatizado tiene límites registrados en evidencia.
13. Intentos de login limitados con cuotas atómicas compartidas entre procesos en PostgreSQL.
14. Auditoría de accesos/cambios sin cuerpos de mensajes ni secretos; trigger que impide modificar/borrar sus filas desde el flujo normal.
15. Separación desarrollo/producción, secreto propio, TLS a la base, cookies protegidas, HTTPS, CSP, control de caché y límites de solicitudes.
16. Firma del webhook conservada, validación de la línea Meta y payloads, y protección de destinos/redirecciones del modelo opcional.
17. Reducción de datos en logs y prompts; se conservan almacenamiento privado, validación de imágenes, metadatos eliminados y descargas con permisos.
18. Contenedor sin privilegios, raíz de solo lectura y persistencia separada para adjuntos/modelo. La instalación real y el proxy requieren validación en su infraestructura.

## Validación y documentación

19. Suite funcional original conservada y ampliada con titularidad, fuentes, perfiles, auditoría, carga de documentos, parafraseo y derivaciones. Modelo real probado por separado.
20. Guía de instalación/actualización, guion para cuatro integrantes, mapa temático ISO/SOC 2, referencias y resultados reproducibles. Inventario de archivos y huellas en `evidencia/`.

Se trabajó sobre copias aisladas. No se cambió el servidor del equipo ni se mandaron mensajes reales. No se incorporaron MFA, un importador automático de PDF/Word ni los módulos futuros P1–P9. No se afirma certificación ISO ni informe SOC 2.
