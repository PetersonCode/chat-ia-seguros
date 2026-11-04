# Referencias primarias y alcance

Consultadas el 4/11/2026. Este documento enlaza referencias públicas; no reproduce el texto completo de normas sujetas a licencia ni sustituye una evaluación profesional de conformidad.

- [ISO/IEC 27001:2022](https://www.iso.org/standard/27001): sistema de gestión de seguridad de la información.
- [ISO/IEC 27701:2025](https://www.iso.org/standard/27701): sistema de gestión de privacidad de información personal.
- [AICPA — Trust Services Criteria](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022): referencia temática de controles para SOC 2.
- [Django — checklist de despliegue](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/): diferencias entre desarrollo y producción, secretos, cookies y HTTPS.
- [Django — publicación de seguridad 5.2.19](https://www.djangoproject.com/weblog/2026/nov/03/security-releases/): versión de la rama 5.2 usada en las pruebas.
- [OWASP — autenticación](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): cuotas, sesiones y mensajes de error.
- [OWASP — prevención de SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): validación de destinos y redirecciones.
- [OWASP — ASVS](https://asvs.owasp.org/): referencia práctica para revisión de aplicaciones; no se afirma haber verificado todos sus requisitos.
- [FastEmbed](https://qdrant.github.io/fastembed/): inferencia local de embeddings mediante ONNX.
- [Modelo multilingüe original](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) y [conversión ONNX utilizada por FastEmbed](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q): procedencia de los pesos públicos.
- [DRF 3.18.2](https://pypi.org/project/djangorestframework/3.18.2/), [Pillow 13.0.0](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html), [python-dotenv 1.2.2](https://pypi.org/project/python-dotenv/1.2.2/): versiones actualizadas tras revisar avisos de seguridad.
- [PyPI JSON API](https://docs.pypi.org/api/json/): consulta de los avisos publicados para cada nombre/versión. La evidencia incluye 39 paquetes directos y transitivos del entorno verificado, más Gunicorn incluido en ese total; no es un SBOM universal para todos los sistemas operativos.

Herramientas de validación: unittest/Django, Node test runner, PostgreSQL, Bandit y consulta automatizada de avisos de PyPI. La ejecución de pip-audit no completó su consulta en este entorno y se interrumpió; sus resultados no se presentan como aprobados. Se verificó la API de PyPI directamente para las versiones resueltas. Ninguna de estas herramientas garantiza detectar todas las vulnerabilidades.

Datos de exposición: `datos_demo/base_conocimiento_ficticia.pdf`, aportado por el equipo. Se usan las condiciones automotor de la página 2, asistencia de la 4 y registros ficticios seleccionados de las páginas 6–7. El archivo original se conserva sin alteraciones; sus instrucciones y limitaciones históricas no reemplazan el comportamiento implementado ni el alcance automotor pedido por el usuario. No se cargan datos personales en la biblioteca documental.

La implementación y documentación recibieron asistencia de IA. El equipo debe revisar, comprender y declarar esa asistencia conforme a la consigna de la facultad; usar herramientas gratuitas en el sistema no acredita que todas las herramientas empleadas en su desarrollo hayan sido gratuitas.
