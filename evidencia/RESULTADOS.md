# Verificación de la entrega corregida

Fecha: 26/10/2026. Entorno Windows, Python 3.12.14 y PostgreSQL 17.11 aislado.

| Verificación | Resultado |
|---|---|
| SQL 01–11 y migraciones en una base nueva | Correctos |
| `python manage.py check` | Sin errores |
| `python manage.py test --noinput --verbosity 2` | **536 pruebas aprobadas**, 0 fallos y 0 errores; 32.440 s |
| `npm test` | **48 pruebas aprobadas**, 0 fallos |
| Compilación Python y `git diff --check` | Correctos |
| Login en navegador con PBKDF2 | Aprobador y operador ingresaron |
| Biblioteca desde interfaz | Borrador → lectura → aprobación → búsqueda → retiro |
| Gestión externa desde interfaz | Importe → aprobación → referencia/motivo → finalización → historial |
| Permisos visibles de operador | Sin formulario de carga ni botones de aprobar o retirar |
| Dos conexiones concurrentes | Una sola aprobación y una sola finalización; worker probado con commits reales |

Los logs completos están en `django-tests.txt` y `javascript-tests.txt`.
Algunos tests provocan excepciones deliberadamente para verificar errores y reintentos;
el resultado de la suite es el resumen final **OK**.

El runner usa un hasher rápido solo para los usuarios ficticios de los tests.
La aplicación normal conserva PBKDF2; también hay una prueba explícita de ese login.

Las capturas `documentos.png`, `finalizacion.png` y `operador.png` muestran datos
ficticios de una base de revisión y no incluyen contraseñas ni clientes reales.

No se enviaron mensajes reales de WhatsApp ni se certificó un proveedor LLM real.
El equipo debe completar su propia demostración y configuración de credenciales.
