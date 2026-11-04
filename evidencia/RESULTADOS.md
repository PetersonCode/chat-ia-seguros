# Resultados comprobados · 4/11/2026

Entrega integrada con los dos ZIP del equipo, sobre una base PostgreSQL aislada. No se modificó el servidor publicado, no se ejecutó 00 y no se enviaron mensajes reales.

## Pruebas finales

| Verificación | Resultado | Evidencia |
|---|---|---|
| Suite Django completa | **625 aprobadas**, cero fallos; crea y destruye test_proyecto | pruebas-django.txt |
| Frontend Node | **40 aprobadas**, cero fallos | pruebas-javascript.txt |
| Configuración de desarrollo | Sin observaciones de Django | check-django.txt |
| Configuración productiva aislada | 2 advertencias HSTS deliberadas, W005/W021 | check-produccion.txt |
| Modelo ONNX real, sin API generativa | Paráfrasis 0,5049; pregunta de oficina -0,0166 | modelo-local.txt |
| Flujo simulado completo | 8 consultas; fuentes correctas; siniestros normal/urgente; pausa efectiva | flujo-completo.json |
| Atención automática | Grúa, saldo, cobertura, paráfrasis, agradecimiento y alcance; modo bot | flujo-automatico.json |
| Avisos de dependencias en PyPI | 39 paquetes consultados, cero avisos publicados y cero errores de consulta | avisos-pypi.json |
| Bandit, código de aplicación | 1 aviso medio B310 revisado; sin errores de análisis | bandit.json |
| Integridad de fuentes | 107 Python parseados, 36 JS con sintaxis válida; JSON válido; plantillas .env sincronizadas; sin conflictos de fusión | integridad-previa.json |
| Comparación con ZIP 2 | Ningún archivo del compañero ausente; cambios integrados/adaptados | inventario-cambios.json y docs/INTEGRACION.md |

Python 3.12.14, Node v24.21.0, PostgreSQL 17.11. Django 5.2.19, DRF 3.18.2, Pillow 13.0.0, FastEmbed 0.9.1. Las versiones transitivas resueltas se conservan como fotografía del entorno Windows; no se presentan como un lock universal para Linux/macOS. Gunicorn 26.2.0 está incluido en las 39 consultas, para la configuración productiva.

La suite conserva las pruebas del compañero y añade cobertura de titularidad, fuentes retiradas, selección entre pólizas, cuentas inactivas, permisos, auditoría, límites, configuración y derivaciones. El hasher rápido solo se activa en tests; la app conserva PBKDF2 y existe prueba explícita de ese login. El modelo real se comprueba por separado para que la suite no necesite descargarlo ni llamar servicios externos.

## Ejemplos solicitados, ejecutados

Cliente/póliza/cuotas ficticios: Lucía Rivas, POL-90101, automotor total, saldo inicial $96.000. Teléfono de asistencia de ejemplo 0800-333-1003: no llamar. El saldo sale de la base, no del RAG.

| Pregunta | Tipo · modo resultante · envío simulado | Segundos locales |
|---|---|---|
| Necesito el número de la grúa | asistencia · bot · enviado | 0.052 |
| ¿Qué saldo tengo pendiente? | saldo · bot · enviado | 0.026 |
| ¿Qué cubre mi póliza? | consulta_cobertura · bot · enviado | 0.035 |
| ¿Qué protección tengo si se quiebra el vidrio frontal del coche? | consulta_cobertura · bot · enviado | 1.905 |
| Gracias por tu ayuda | agradecimiento · bot · enviado | 0.022 |
| Pasame una receta de tortilla | ajeno · bot · enviado | 0.021 |
| Se me astilló el vidrio delantero del auto, ¿mi seguro lo cubre? | siniestro · humano · enviado | 0.031 |
| Me chocaron en la autopista | siniestro_urgente · humano · enviado | 0.026 |

Se comprobó que el siniestro normal deriva con prioridad normal; el choque en autopista deriva a Roberto con prioridad urgente. La consulta siguiente no genera una respuesta automática mientras el chat está en modo humano. Un operador no puede administrar documentos y ya no existe un endpoint de validación manual de identidad. El detalle del panel respondió HTTP 200.

Los tiempos son una observación en este proceso local, con ocho consultas; no son una prueba de carga ni una comparación controlada con la versión anterior. El primer uso del modelo añade carga de pesos e inferencia. No se garantiza igual latencia en otra computadora ni comprensión de cualquier frase.

## Resultados de seguridad que requieren interpretación

- B310 señala `urlopen` en el envío a Meta. Se revisó que construye una URL con esquema HTTPS y host fijo graph.facebook.com; no toma una URL de un mensaje. Se conserva el hallazgo y su contexto, sin afirmar que Bandit haya demostrado una vulnerabilidad explotable ni que su análisis descarte todos los riesgos. La integración real con Meta no se ejecutó.
- W005/W021: no se activaron includeSubDomains ni preload para un dominio cuyos subdominios/precarga no se evaluaron. HTTPS, cookies Secure y HSTS de un año sí están configurados para producción. El TLS efectivo del servidor requiere comprobación del responsable.
- La consulta de PyPI cubre avisos publicados para las versiones resueltas el día indicado. **pip-audit no completó su consulta y se interrumpió**; no se presenta como una prueba aprobada. No incluye todos los paquetes de cualquier entorno futuro ni sustituye mantenimiento.
- El código y la configuración Docker se entregan revisados; no se realizó construcción/despliegue Docker ni prueba de estrés, pentest externo, envío a Meta o certificación de infraestructura.

## Reproducir

Seguir README, aplicar 01–12 y 22 en una base nueva o solo los incrementos pendientes en una existente; ejecutar migrate, check, test --noinput, npm test y verificar_busqueda_local. Preparar el escenario con cargar_demo_exposicion y simular_whatsapp. La suite exige permisos para crear su base de prueba.

Las capturas documentos-final.png, siniestro-final.png y cortesia-final.png muestran el panel integrado con datos ficticios. Los planes P1–P9 son documentación futura, no módulos implementados.
