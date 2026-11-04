# Altas preparadas por el bot y confirmadas por una persona

El bot recopila y guarda una **solicitud**; el registro definitivo se crea al confirmar. Para un cliente, el asesor revisa y confirma. Para una póliza, el asesor ingresa la **prima mensual acordada** y confirma. El bot no fija el precio ni acepta una prima o comisión enviada por el cliente.

## Alta de cliente

1. El contacto escribe «quiero registrarme».
2. El bot pide nombre y apellido completos y DNI. El teléfono sale del chat, no se vuelve a cargar. Si la persona facilita un email, también lo incorpora.
3. Guarda una acción `alta_cliente` con los datos. Si el perfil solo dice «Dani», vuelve a pedir nombre completo al cliente: no deja el apellido para que lo escriba el asesor.
4. En **Acciones**, un aprobador revisa la solicitud y pulsa Aprobar → Confirmar. Se crea el cliente y se vincula el contacto existente sin duplicarlo.
5. Se prepara y despacha el aviso automático: «Tu solicitud de alta como cliente fue aprobada y procesada».

No hay validación manual de identidad ni un mensaje que el asesor tenga que redactar.

## Alta de póliza

El cliente puede decir «quiero asegurar mi camioneta», «quiero contratar un seguro» o «quiero registrar una póliza».

El bot pide patente y, si ese vehículo ya pertenece al cliente, recupera sus datos. Si es nuevo, reúne marca, modelo, año, clase, uso, chasis y valor asegurado solicitado. Pide también compañía, cobertura y fechas de inicio y vencimiento. Chasis y valor se pueden omitir explícitamente cuando no se conocen; no se inventan.

Las compañías se eligen entre las activas de la base. No se muestra su comisión al cliente. Si el número todavía no es cliente, el bot pide también nombre completo y DNI: la confirmación crea cliente, vehículo, póliza y cuotas en una misma transacción. Un error revierte todo; no queda un cliente o vehículo a medio registrar.

Se puede responder una pregunta por vez o enviar varios datos con etiquetas:

```text
Patente: AB123CD
Marca: Toyota
Modelo: Hilux
Año: 2022
Clase: camioneta
Uso: particular
Chasis: omitir
Valor asegurado: 25000000
Compañía: nombre de una compañía activa
Cobertura: total
Inicio: 04/11/2026
Fin: 04/11/2027
```

Las fechas del ejemplo son ficticias; usar las correspondientes a la demostración. El bot valida los datos y pregunta lo que falta. No crea una póliza vigente mientras conversa y avisa que la solicitud todavía no implica cobertura.

Cuando está preparada, **Acciones** muestra vehículo, compañía, cobertura y fechas. El asesor abre Aprobar, ingresa la prima mensual en ARS y pulsa Confirmar. No tiene que volver a cargar los datos del cliente o vehículo. El servidor vuelve a controlar titularidad, compañía activa, importes y pólizas superpuestas antes de crear el plan de cuotas. La comisión se toma de la compañía; el cliente no la decide.

Después de confirmar, llega un aviso con el número de póliza generado. Rechazar también genera un aviso, sin crear una póliza.

## Avisos y tolerancia a fallos

La notificación se guarda en la **misma transacción** que resuelve la acción. El envío comienza después del commit. Si falla la conexión, el alta queda confirmada y el mensaje queda disponible para que el worker lo reintente; la pantalla no presenta el alta como fallida por un problema de mensajería.

Cada acción y estado tiene un único registro de aviso. Repetir una aprobación no crea otro registro ni otra póliza. La aprobación de una gestión externa indica que falta completarla; al registrar su finalización se crea el aviso de cierre. Registrar esa evidencia no ejecuta transferencias ni cambios en una aseguradora externa.

En WhatsApp real se conserva la ventana de envío de 24 horas. Si está cerrada, el aviso queda registrado como fallido por `ventana_24h_cerrada`, sin afirmar que fue entregado. Se rehabilita al reabrirse la ventana de esa conversación y lo despacha el worker. Para iniciar contacto fuera de la ventana o desde una conversación ya cerrada, se necesita un canal manual o una plantilla de Meta aprobada; esta entrega no inventa ni contrata plantillas. En la exposición se usa WhatsApp simulado.

Mantener el procesador de la aplicación activo:

```powershell
python manage.py reprocesar_pendientes --continuo
```

## Actualización

Sobre el `main` del 4/11/2026 que ya tiene SQL 13, 22 y 23, aplicar **24 y 25**, en ese orden, antes de reiniciar web y worker. Sobre una copia que ya tenga nuestra ampliación de vehículos y comisiones (24), aplicar solamente 25.

```powershell
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\24_cartera_vehiculos.sql
psql -h localhost -p 5432 -U seguros_dev -d proyecto -v ON_ERROR_STOP=1 -f .\SDD\sql\25_altas_por_chat.sql
python manage.py migrate
python manage.py check
```

Usar la conexión propia y respaldar antes de actualizar. SQL 25 es aditivo e idempotente: amplía el tipo de acción, agrega el borrador por conversación y la unicidad de los avisos. No modifica pólizas ni clientes existentes. No ejecutar SQL 00 ni recargar el seed sobre una base existente.

Los formularios administrativos anteriores se conservan para carga inicial y correcciones; el recorrido habitual nuevo por WhatsApp queda preparado en Acciones. Los datos de una solicitud se conservan como propuesta hasta la aprobación, y se vuelven a validar al ejecutarla. Los siniestros y las solicitudes de un asesor interrumpen la recopilación y mantienen su prioridad.

## Verificación de esta entrega

- **738 pruebas Django y 51 pruebas JavaScript aprobadas**, con Python 3.12.14, Django 5.2.19, psycopg 3.2.10 y PostgreSQL 17.11.
- Probados: cliente existente y nuevo, vehículo existente y nuevo, rechazo, falta de precio, importe inválido, permisos, datos del cliente que intentan fijar prima/comisión, reversión completa ante error, mensajes repetidos, envío fallido y recuperación de la ventana. Un siniestro durante la recopilación pausa el bot y deriva a una persona.
- Navegador: confirmación de póliza introduciendo solamente la prima, confirmación de cliente sin cargar campos y avisos enviados en los dos chats simulados. Consola sin errores ni advertencias en ese recorrido.
- Se conservaron las pruebas de búsqueda, comisiones, vencimientos, documentación, RAG y hardening. No se enviaron WhatsApp reales ni se usó un proveedor de IA pago en las verificaciones.
- Validación realizada sobre la entrega local antes de su publicación para revisión del equipo.

Capturas con datos ficticios: [confirmación de cliente](capturas/alta-cliente-confirmada.png), [confirmación de póliza](capturas/alta-poliza-confirmada.png).
