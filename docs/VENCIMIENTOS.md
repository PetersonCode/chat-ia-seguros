# Pantalla de vencimientos y recordatorios

Implementación del pedido del equipo del 4/11/2026. Se usan el menú, colores, tipografía, tablas, botones, etiquetas y diálogo existentes; no se cambió la hoja de estilos global.

## Qué muestra

En **Vencimientos**, las pólizas automotor de clientes activos priorizan los pagos atrasados: primero las que tienen cuotas impagas con vencimiento anterior a hoy, desde el atraso más antiguo. Luego se ordena el resto por fecha de fin de la póliza ascendente, con ID como desempate. Se muestra cliente, vehículo, número, fecha, días restantes, saldo pendiente y fecha del último aviso. El saldo es el de esa póliza, calculado por la vista existente a partir de sus cuotas, no la suma de otras pólizas del cliente.

El filtro inicial muestra las próximas fechas sin límite. Se puede elegir 7, 30, 60 o 90 días, buscar cliente/póliza/vehículo e incluir las vencidas de los últimos 30 días. No se muestran pólizas dadas de baja ni clientes inactivos. La lista está paginada y no hace consultas adicionales por cada fila.

La prioridad de atraso se calcula con la **fecha de vencimiento de las cuotas impagas**, sin confundir un saldo aún a tiempo con deuda vencida. Una cuota que vence hoy no se considera atrasada. La pantalla muestra el importe vencido dentro del saldo total y desde qué fecha; el recordatorio también lo distingue. Al pagar esas cuotas deja de tener prioridad de atraso. Los filtros de plazo siguen referidos al **fin del contrato**: la prioridad se aplica dentro de los resultados elegidos, no incorpora pólizas fuera del filtro. Este incremento no incorpora cobranza, renovación ni el motor automático completo P2/P3. P7 trata sobre siniestros y no es la especificación de esta pantalla.

## Enviar un recordatorio

1. Pulsar Enviar recordatorio en una fila.
2. Revisar el mensaje preparado y su número. Si el cliente tiene varios números, elegir uno de su cartera; nunca se puede indicar un número de otro cliente.
3. Enviar. El sistema calcula nuevamente fecha y saldo desde la base y registra quién lo hizo. No admite texto arbitrario ni datos financieros suministrados por el navegador.

Ejemplo:

> Hola Ana, te recordamos que tu póliza POL-90202 vence en 7 días (11/11/2026).
> Saldo pendiente de esta póliza: $25.000.
> Si ya realizaste el pago o querés consultar la renovación, escribinos. Seguros Castaño.

El texto distingue vence hoy, vence mañana y venció hace N días. El envío queda en la conversación como mensaje del funcionario, sin tomar el control al bot ni cambiar el estado de la póliza o sus cuotas. Cualquier funcionario activo puede gestionar este aviso informativo; las aprobaciones contractuales siguen como antes.

## WhatsApp y estados reales

El envío directo usa el canal de texto de la agencia existente, cuando hay conversación abierta y una ventana de 24 horas desde el último mensaje del cliente. En simulación se registra un envío ficticio; en modo real se usa Meta. Fuera de la ventana no se intenta el envío directo ni se declara enviado.

En ese caso se ofrece Copiar texto o Abrir WhatsApp con el mensaje preparado. El asesor lo envía por su WhatsApp y después pulsa Ya lo envié por WhatsApp; queda un registro **manual** por su declaración, sin inventar un mensaje ni una confirmación de Meta en el chat de la agencia. La agencia debe usar contactos autorizados y respetar las solicitudes de no recibir comunicaciones; este incremento no implementa la gestión completa de consentimiento del futuro P2.

Esta alternativa manual permite operar sin incorporar plantillas a la API. Las plantillas aprobadas necesarias para iniciar mensajes fuera de ventana constituyen otra integración, pendiente. Referencia: [Política oficial de WhatsApp Business](https://business.whatsapp.com/policy/preview?lang=es_LA), consultada el 4/11/2026.

El historial diferencia Enviado, En cola, Falló el envío y Envío manual registrado. Enviado significa que el transporte lo aceptó (o fue simulado), no que el destinatario lo leyó. Los fallos usan los reintentos existentes del worker; el texto conservado corresponde al momento del aviso. No se agregó una garantía de entrega única del proveedor ante errores de red ambiguos.

Una restricción de base evita dos avisos para la misma póliza/número/día, incluso con doble clic o solicitudes simultáneas. No se mandan avisos solos ni se programa una campaña. Si hay varias pólizas del mismo cliente, el asesor decide cuál contactar. El registro conserva texto, saldo, fecha, destinatario y funcionario; si se borra un chat, el registro se conserva sin el vínculo al mensaje.

## Instalar sobre la versión anterior

Respaldar y aplicar solamente el nuevo incremento si ya están aplicados 01–12 y 22:

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\23_recordatorios_polizas.sql
python manage.py migrate
python manage.py check
```

SQL 23 es aditivo e idempotente; no cambia datos de pólizas/cuotas ni envía mensajes. Reiniciar web/worker y publicar los estáticos de esta versión. Para una base nueva, aplicar 01–12, 22 y 23 en orden según README. No ejecutar 00 ni repetir el seed sobre información que se quiera conservar.

## Demostración ficticia

```powershell
python manage.py cargar_demo_vencimientos
```

Requiere desarrollo, WhatsApp simulado, LLM generativo desactivado y catálogos preparados. Crea a Ana Demostración con tres pólizas que, al ejecutar el comando por primera vez, vencen a 1, 7 y 21 días y tienen $25.000 pendientes cada una. Habilita una conversación simulada reciente. No restablece fechas, saldos, pagos ni contraseñas al repetirlo; no se ejecuta al iniciar el sistema.

Para mostrar un envío usar POL-90202 y luego volver a abrir el diálogo: aparece el historial y no se puede duplicar el aviso ese día. Los teléfonos son ficticios: no llamar ni enviar desde un WhatsApp real durante la exposición.

## API

- `GET /api/vencimientos/?dias=30&incluir_vencidas=true&q=&pagina=1`: funcionario autenticado; `dias` opcional de 1 a 3650, página de 25 filas.
- `GET /api/polizas/{id}/recordatorio/?contacto_id=…`: vista previa actual, números del cliente, disponibilidad del canal y últimos cinco avisos; no escribe ni envía.
- `POST /api/polizas/{id}/recordatorio/`: `{contacto_id, canal: "api"|"manual"}`. Devuelve 201 para un aviso nuevo y 200 para el ya registrado ese día. Devuelve 409 si el envío directo no tiene ventana y 400 si el número no es del cliente. Usa sesión y CSRF existentes.

La lectura del listado y la preparación/envío quedan cubiertos por la auditoría HTTP, sin guardar búsquedas ni cuerpos. El historial operativo sí conserva el mensaje informativo que el asesor eligió enviar.
