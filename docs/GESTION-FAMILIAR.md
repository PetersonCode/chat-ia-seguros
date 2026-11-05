# Lo de hoy y fidelización

La pantalla inicial después del login es **Inicio**. En escritorio la navegación es lateral; en pantallas menores a 1200 px se utiliza el botón **Menú**. Se conserva la paleta azul y la tipografía del panel.

## Operación diaria

- Renovaciones vigentes que vencen en los próximos 30 días, por fecha, excluyendo las ya registradas como renovadas.
- Pólizas automotor con cuotas atrasadas, primero el atraso más antiguo. El importe mostrado es el vencido; no incluye las cuotas futuras.
- Interesados abiertos con próximo contacto vencido, de hoy o sin fecha. Se usa el embudo P5 existente, sin duplicar clientes ni interesados.
- Siniestros no cerrados/rechazados sin movimiento por 7 días. Se cuentan alta, historial y adjuntos.
- Conversaciones abiertas cuyo último mensaje es del cliente y espera más de 2 horas.

Los contadores usan datos reales de la base. Las tarjetas muestran hasta 20 ejemplos por categoría; los primeros cinco se ven directamente y el resto se despliega. La bandeja, Vencimientos e Interesados siguen disponibles para gestionar sus listados.

Se crean tareas con responsable activo, fecha, detalle y cliente opcional. El asignado, el creador o un aprobador pueden completarlas, cancelarlas o reasignarlas; el backend verifica esos permisos. La ficha de cada cliente tiene notas internas con autor y fecha. Estas notas no se envían al cliente ni se incorporan a las fuentes del bot.

## Recordatorios

`python manage.py procesar_gestion` programa avisos idempotentes y prepara envíos. `--dry-run` no escribe ni envía. Docker incluye `gestion-worker` cada hora; fuera de Docker hay que programar ese comando en el servidor. No es una automatización del chat de Codex.

La activación se hace una vez desde Inicio por un aprobador. Inicialmente está apagada: instalar una actualización no dispara una campaña sobre la cartera. Aunque esté apagada, se preparan contactos para gestión manual.

- Vencimientos de póliza: 30, 7, 1 y 0 días antes.
- Cuotas pendientes: 3 días antes, el día del vencimiento y 3, 7 y 14 días después.
- Seguimiento: por fecha de próximo contacto definida en el interesado, una vez por ese hito.
- Envíos automáticos: de 09 a 20 h de Buenos Aires, como máximo uno por contacto y día, con ventana de WhatsApp abierta y conversación en modo bot.
- Antes del envío/reintento se vuelve a consultar la fuente: una cuota pagada o una póliza renovada no generan el recordatorio viejo. Los avisos pendientes caducan a los 7 días.
- «STOP», «No quiero recibir avisos» y expresiones equivalentes desactivan los recordatorios, incluso durante atención humana. No dan de baja el seguro.

Fuera de la ventana se ve **Para contactar**, con texto preparado y un enlace a WhatsApp. Abrir el enlace no envía por sí solo; el asesor envía y registra el contacto realizado. El envío manual depende de la cuenta de WhatsApp usada por el asesor. No se añaden plantillas de Meta ni se garantiza que el tráfico real de WhatsApp sea gratuito. Referencia de la restricción de ventana: [documentación oficial de AWS End User Messaging Social](https://docs.aws.amazon.com/social-messaging/latest/userguide/whatsapp-send-message.html).

El estado «preparado» no equivale a entregado: la interfaz muestra el estado real del mensaje asociado. El worker de WhatsApp existente conserva sus reintentos y comprobaciones de ventana/modo humano. Si se pierde la ventana o se toma el chat, el envío puede fallar o descartarse; queda registrado para revisión.

## Renovación y reporte

**Renovar** abre la revisión del contrato: fecha de inicio al día siguiente del vencimiento, duración propuesta igual a la anterior, nuevo vencimiento editable y prima mensual obligatoria ingresada por el asesor. Solo un aprobador puede confirmar. Se registran la nueva póliza, cuotas y relación con la anterior en una transacción; no puede renovarse dos veces. Si se conserva la cobertura, se crea una copia independiente de las condiciones revisadas. No se realiza una emisión externa ante la aseguradora.

Queda preparado el mensaje de renovación y, cuando se registró a tiempo, el agradecimiento. Se aplican las mismas reglas de entrega de avisos. La fecha de cumpleaños es opcional y el saludo requiere que se haya marcado la aceptación del cliente.

El resumen mensual muestra pólizas registradas nuevas (excluye las renovaciones registradas por este módulo), bajas ejecutadas por acciones, renovaciones, cobros y comisión calculada sobre cobros. La comisión se calcula con la lógica existente y solo se muestra a aprobadores; se informan pólizas sin porcentaje. Las operaciones históricas sin un registro de renovación no se reclasifican automáticamente.

## Credencial, referidos y encuesta

Desde una ficha se descarga una credencial de contacto como imagen PNG de alta resolución para guardar o compartir en el celular. También hay una versión HTML sin conexión con el teléfono pulsable. Incluye póliza, titular, patente, compañía, vigencia y teléfono de asistencia; no incluye DNI ni saldo. «Pasame mi credencial» también devuelve datos de las pólizas vigentes del número reconocido por WhatsApp. No se inventa un teléfono faltante ni se presenta esta tarjeta como certificado emitido por la compañía.

En la ficha se registra quién trajo a otro cliente. Un referido no puede recomendarse a sí mismo ni tener dos recompensas registradas. Un aprobador confirma el beneficio entregado o cancela con una descripción. El importe o regalo se decide por el equipo: no se inventa un descuento ni se modifican cuotas por cargar el referido.

Al detectar consultas resueltas o siniestros cerrados recientes se prepara una encuesta opcional de 1 a 5. Máximo una por contacto en siete días. El cliente responde **Encuesta 4**, por ejemplo; un número suelto no se toma como respuesta, para evitar confundirlo con una selección de póliza. Las respuestas aparecen en Inicio. Se admite una respuesta pendiente no vencida del mismo contacto, sin revelar datos de otros clientes.

## Instalación y demostración

Esta ampliación parte del commit `3eae4fa` del PR #8. Respaldar y aplicar **SQL 27 y luego 28**, después de los scripts anteriores incluido 26. No ejecutar SQL 00 ni seeds sobre una base existente. Reiniciar web y ambos workers con la misma versión. Activar automatismos solo después de verificar contactos, consentimiento y configuración de WhatsApp del entorno.

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\27_gestion_diaria.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\28_fidelizacion.sql
python manage.py check
python manage.py test --noinput
npm test
python manage.py procesar_gestion --dry-run
```

Adaptar las conexiones a la instalación. Para exponer, usar WhatsApp simulado y datos ficticios: entrar a Inicio, asignar una tarea, guardar una nota interna, abrir la revisión de renovación, mostrar la credencial y registrar una respuesta de encuesta. No hace falta completar cumpleaños ni referidos para usar la atención y la cartera.

## Identidad visual compartida

Las 20 páginas utilizan `frontend/static/css/tema.css`: fondo claro, tarjetas blancas, texto oscuro, navegación marina y acciones con colores consistentes. Incluye ingreso, tablas, formularios, estados, alertas, chat y diálogos. `inicio.css` contiene los ajustes particulares del Inicio. Para personalizar la identidad común se modifica `tema.css`, evitando copiar estilos entre pantallas.

## Chat del interesado

El detalle del interesado ofrece **Ver conversación**: abre en la misma pestaña el chat más reciente del contacto vinculado, también si está cerrado. No crea conversaciones. Si no hay contacto o chats, muestra un aviso. La API de detalle incorpora `conversacion_id` nullable, resuelto por contacto y ordenado por fecha de creación e ID descendentes; el listado del embudo conserva su contrato.

## Chat flotante entre módulos

Los enlaces a conversaciones (incluido Ver conversación del interesado) abren una ventana de atención abajo a la derecha. La cabecera permite minimizar, ampliar/reducir y cerrar la ventana; el nombre vuelve a abrirla cuando está minimizada. Se puede seguir usando el módulo y navegar a otro. Ver detalle completo abre la pantalla de supervisión habitual, donde siguen disponibles las acciones sobre mensajes retenidos y expedientes.

En la pantalla completa hay un botón Abrir chat flotante. Se mantiene una conversación flotante por pestaña; abrir otra cambia el chat y conserva el borrador anterior. Minimizar o cerrar la ventana no termina la atención: para devolverla se utiliza Devolver al bot. Un chat cerrado se muestra solo para consulta. El formulario exige atención humana propia y ventana abierta; el backend conserva sus validaciones habituales y CSRF.

La ventana consulta mensajes y estado cada cinco segundos mientras la pestaña está visible. Minimizada indica los mensajes nuevos del cliente que detecta durante esa estancia; ese contador visual se reinicia al abrir la ventana y no es un registro permanente de lectura. Los avisos de error se muestran en la ventana.

La selección, tamaño y borradores se guardan en sessionStorage por usuario, en la pestaña actual; no se almacena allí el historial. Al cerrar sesión desde el panel se eliminan esos datos. Cerrar la pestaña elimina su sesión de almacenamiento. No sincroniza borradores entre dispositivos o pestañas. Si el navegador bloquea almacenamiento, el chat funciona en la página actual pero no puede recuperar el borrador al navegar.

Al abrir **Ver detalle completo** con un clic normal, el flotante queda minimizado. En el detalle, cada mensaje nuevo recibido por el sondeo desplaza el historial al final; una actualización sin mensajes nuevos conserva la posición de lectura.

## Bandeja por contacto

La bandeja utiliza una conversación representativa por contacto: prioriza la abierta y, si no existe, la más reciente cerrada. La selección ocurre en la base antes de paginar, por lo que un contacto no reaparece en otra página. No se borran ni fusionan mensajes o expedientes históricos. La API original sin `agrupada=1` conserva el acceso al historial y sus contratos.

La vista inicial es Necesitan atención: conversaciones abiertas con respuestas retenidas, último mensaje del cliente en atención humana o una derivación pendiente sin respuesta final de un funcionario. El acuse del bot no oculta la derivación. Primero urgencias y después antigüedad del último mensaje. Al responder el funcionario, el cliente pasa a Esperando al cliente, salvo que queden respuestas retenidas para revisión. También se puede consultar Atendiendo el bot, Resueltas y Todos los contactos.

Los cuatro contadores de la bandeja cuentan contactos, no consultas del bot; respetan los filtros de búsqueda. La bandeja se actualiza cada quince segundos con la pestaña visible. Los indicadores de Acciones y Alertas críticas de navegación siguen representando operaciones administrativas y alertas de seguridad: son unidades diferentes de clientes esperando respuesta.

## Datos de cotización compartidos

El bot interpreta datos explícitos del primer mensaje y frases como «Tengo un Toyota Corolla 2020, patente AE432ZZ. Uso particular, en Buenos Aires». Completa faltantes con los datos del interesado abierto del mismo contacto y guarda avances parciales sin esperar al final. No copia el vehículo anterior cuando aparece una patente diferente ni reutiliza automáticamente una cotización ya cerrada. Los datos ambiguos siguen requiriendo una aclaración; no se inventan precios ni coberturas.

El detalle de conversación muestra el enlace al interesado y sus datos para cotizar; al detectar nuevos mensajes vuelve a consultarlos. La ficha de Interesados lee esos mismos datos guardados. No supone un alta de cliente, póliza ni emisión externa. Los mensajes históricos no se reescriben.

## De cotización elegida a póliza

Convertir al interesado conserva también el vehículo completo en el cliente, sin duplicar una patente propia ni apropiarse de una ajena. Una cotización elegida es una propuesta, no un contrato emitido. Desde Documentación, Registrar póliza en el cliente abre la póliza con compañía, cobertura, prima y vehículo de la cotización elegida. El asesor revisa y completa las fechas; no se usa el vencimiento de la oferta como vigencia del seguro. Después de confirmar el registro, puede marcar Emitida.

La ruta preferida desde Documentación es ahora **Registrar póliza con la cotización elegida**: pide únicamente inicio y vencimiento, recupera la opción elegida en el servidor (sin aceptar precios ni compañía del navegador), guarda póliza y cuotas y pasa a Emitida en una transacción. Solo aprobadores; un segundo intento se rechaza. No confirma una oferta vencida ni emite ante la aseguradora. El formulario general de pólizas permanece disponible para carga manual.
