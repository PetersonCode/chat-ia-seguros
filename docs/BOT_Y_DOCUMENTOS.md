# Bot automotor y documentación

## Atención automática

Un número de WhatsApp vinculado a un cliente activo permite al bot consultar su cuenta sin intervención del asesor. La asociación proviene de la cartera; el nombre o DNI escrito en un mensaje no puede crearla ni sustituirla. En modo real el webhook exige firma de Meta y coincidencia de la línea configurada.

El bot resuelve saldo y vencimientos desde la base, entrega el teléfono de grúa según cobertura y recupera condiciones aprobadas vinculadas a la póliza. Si hay varias pólizas automotor pide al cliente el número o una selección inequívoca; conserva la selección temporalmente y vuelve a comprobar titularidad y vigencia en cada consulta. El vencimiento del contexto se renueva automáticamente, sin pedir una validación humana.

No hay un paso manual de verificación de identidad en este recorrido. El número reconocido es un mecanismo de acceso proporcional al MVP, no una prueba fuerte de identidad; la agencia debe mantener correctas las asociaciones y contemplar números reciclados o perdidos antes de usar datos reales.

## Cuándo deriva

- Si el cliente relata un siniestro ocurrido: siempre. Si es urgente, con prioridad urgente a Roberto; en otros casos, a administración. La consulta queda registrada y la conversación pasa a humano.
- Si pide una persona, falta información suficiente para contestar o se requiere una decisión contractual o administrativa que el bot no puede tomar.
- Si una respuesta dispara un control de seguridad, se retiene y el equipo revisa.

“¿Mi póliza cubre daños por choque?” es informativo. “Me chocaron en la autopista” relata un hecho y deriva. “Se me rompió el parabrisas” también deriva. Una cobertura citada no autoriza una reparación ni una indemnización.

El asesor realiza decisiones críticas finales, como bajas, modificaciones y reembolsos, y atiende los casos derivados. No debe validar rutinariamente cada consulta de saldo, asistencia o cobertura.

Los agradecimientos y despedidas se responden sin derivar ni crear un trámite. Los pedidos claramente ajenos al seguro reciben una aclaración de alcance; existe respaldo por reglas para ejemplos comunes aun sin API generativa. Un pedido real de ayuda o un incidente tiene prioridad sobre el cierre cordial.

## Fuentes y alcance

La agencia trabaja en este MVP únicamente con automotores. Se conservan catálogos/datos históricos anteriores, pero las altas nuevas y el bot se limitan al alcance actual. El PDF aportado contiene motos y reglas de una versión anterior: no se aplican como instrucciones de funcionamiento.

Un aprobador prepara el conocimiento una vez en Documentos: título, versión, referencia y texto autorizado. Para condiciones particulares se indica la póliza. Un borrador no se consulta; hay que aprobarlo. Retirar una fuente la excluye de consultas nuevas; aprobar otra versión del mismo título requiere retirar la anterior para evitar competencia entre versiones.

La asociación documento-póliza es explícita y queda registrada. No se deduce por el nombre del archivo ni por semejanza entre productos. Las fuentes vinculadas a contratos quedan fuera de las búsquedas generales. El panel permite revisar fuentes aprobadas y los aprobadores administrarlas.

Se admite texto pegado, no importación automática de PDF/Word. `cargar_demo_exposicion` incorpora extractos de automotor de las páginas 2 y 4 del PDF ficticio; las personas, DNI y cuotas se guardan como datos operativos, no como pasajes de RAG. Los saldos siempre salen de cuotas reales de la base de prueba.

## Preguntas con otras palabras

Se combinan palabras normalizadas, conceptos del dominio (por ejemplo, cristales/parabrisas) y embeddings locales de `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` mediante FastEmbed/ONNX. El modelo es gratuito y procesa localmente; no se envían las consultas ni documentos a una API de embeddings.

```powershell
python manage.py preparar_busqueda
python manage.py verificar_busqueda_local
```

Configurar `BUSQUEDA_SEMANTICA=true` y reiniciar web y worker. La primera preparación descarga pesos públicos y requiere Internet y disco. Después las consultas no descargan modelos. El cache se conserva en `.modelos/`; en Docker, en el volumen `modelos`. Ajustar workers según RAM disponible.

Si falta el modelo, sigue la búsqueda por conceptos. La similitud mínima es 0,50; fuentes competidoras muy cercanas producen abstención. Es un punto de partida para calibrar con preguntas de la agencia, no una garantía de entender cualquier frase. La respuesta cita un pasaje real, no una condición generada libremente. Se mantienen controles sobre importes, fechas e identificadores.

El modelo puede agregar latencia al cargar por primera vez. No se reentrena al subir documentos: se actualizan las fuentes disponibles. Las consultas de saldo o urgencia no necesitan embeddings.
