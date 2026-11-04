# Guion breve para la exposición

Idea para recordar: **el bot resuelve lo habitual; el asesor decide lo crítico y atiende derivaciones**.

1. “Automatizamos las consultas habituales de seguros automotores. El número registrado permite localizar al cliente sin pedirle al asesor que valide cada conversación.”
2. “El saldo sale de la base y las condiciones de documentos aprobados vinculados a la póliza. Si hay varias, el bot pregunta cuál; no adivina.”
3. “El modelo gratuito local entiende otras formas de preguntar. Si falta respaldo no inventa. Si ocurrió un siniestro, registra el aviso y deriva, con prioridad cuando es urgente.”
4. “Reforzamos accesos, permisos, registros y configuración tomando ISO 27001, ISO 27701 y los criterios de SOC 2 como referencias. No estamos certificados ni contamos con un informe SOC 2.”

## Orden de la demo

Usar el perfil académico y los datos ficticios de `cargar_demo_exposicion`:

| Consulta simulada de Lucía | Resultado esperado |
|---|---|
| Necesito el número de la grúa | Teléfono ficticio 0800-333-1003 de la cobertura total. No llamar. |
| Qué saldo tengo pendiente | Saldo inicial de $96.000 calculado con sus dos cuotas impagas. |
| Qué cubre mi póliza | Condiciones de POL-90101 con su fuente aprobada, sin validar manualmente. |
| Qué protección tengo si se quiebra el vidrio frontal del coche | Busca conceptos/ significado y cita las condiciones de cristales. |
| Me chocaron en la autopista | Registra la consulta, deriva a Roberto con prioridad urgente y pausa el bot. |

Mostrar la urgencia al final, porque la conversación queda en atención humana. Para seguir, usar Devolver al bot. Otro siniestro relatado, aunque no sea urgente, también debe derivarse.

## Seguridad que se puede explicar sin memorizar normas

- ISO 27001: organizar la seguridad, por ejemplo roles y configuración.
- ISO 27701: gestionar privacidad, por ejemplo no mandar DNI o cuotas al buscador documental ni registrarlos en logs generales.
- SOC 2: trabajar con controles y evidencias, por ejemplo probar que un operador no pueda aprobar un reembolso.

La protección se ejecuta por detrás. Se conservan aprobaciones para decisiones críticas, no para cada respuesta informativa.

## Qué aclarar

Los datos, documentos y teléfonos son ficticios. El número registrado no es una prueba fuerte de identidad. El modelo consulta fuentes, no aprende pesos nuevos ni decide indemnizaciones. Las cuentas externas, el servidor real, respaldos y MFA no están certificados por esta revisión. El equipo debe repetir la demo en su computadora y declarar el uso de IA conforme a la consigna.
