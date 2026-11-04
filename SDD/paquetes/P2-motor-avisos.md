# P2 · Motor de avisos

**Branch:** `paquete-p2-avisos` · **SQL:** `SDD/sql/14_avisos.sql` · **Depende de:** nada. **Lo usan:** P3, P4, P5, P7, P9.
**Por qué (Roberto):** hoy el sistema solo contesta. Para renovar, cobrar y dar seguimiento tiene que poder avisarle al cliente sin que lo hagamos de memoria: sin repetirse, sin bombardear, sin escribirle a quien pidió que no, y dejando todo registrado.

## 1. Restricción de diseño: sin plantillas de Meta
**El sistema no usa plantillas de WhatsApp** (se cobran). Solo manda **texto libre**, y WhatsApp solo lo admite hasta 24 h después del último mensaje del cliente. Como casi siempre un aviso nace *fuera* de esa ventana, un aviso puede salir por **tres caminos**, todos sin plantilla:

| Camino | Cuándo | Quién lo manda |
|---|---|---|
| **Automático** | El contacto escribió hace menos de 24 h y es horario permitido (09:00 a 20:00, Buenos Aires) | El sistema, con `procesar_avisos` |
| **Oportunista** | El contacto escribe por su cuenta (abre la ventana) y la conversación está en modo `bot` | El sistema, a continuación de la respuesta del bot |
| **Manual** | La ventana está cerrada | Una persona. El sistema le deja el texto armado en la lista «Para contactar» y ella lo manda desde su teléfono o su WhatsApp, y lo marca como enviado |

Consecuencias que las demás specs heredan:
- **Nada llama jamás a `type: "template"`.** Un test lo garantiza (AC-T3-63).
- El camino manual saca la charla del sistema: la respuesta del cliente llega al WhatsApp de la persona, no al de la agencia. Por eso el texto manual lleva al final `AVISO_RESPONDER` («Si querés responder o mandar un comprobante, escribinos a nuestro WhatsApp de la agencia: {numero}»), con el número de la variable de entorno `AGENCIA_WHATSAPP` (formato internacional, ej. `+5491139563267`). Excepción a la sección 7 de `00-comun.md`: la etapa A la agrega a `SDD/plantillas/env.example` y a esa sección.
- Los avisos **caducan**: uno que nadie contactó en 7 días ya no sirve (el vencimiento pasó, la cuota se pagó) y pasa a `vencido`.

## 2. Esquema (`14_avisos.sql`)
```
contactos_whatsapp  + acepta_avisos bool NOT NULL default true
tipos_aviso         codigo (PK, texto), nombre, prioridad smallint (1 más urgente … 5), activo bool
avisos              id, tipo → tipos_aviso(codigo), contacto_id → contactos_whatsapp, referencia text,
                    datos jsonb default '{}', asignado_a_id → funcionarios null,
                    programado_para timestamptz, caduca_en timestamptz,
                    estado (pendiente, enviado, enviado_manual, retenido, fallido, cancelado, vencido) default pendiente,
                    mensaje_id → mensajes null, resuelto_por_id → funcionarios null, error text null,
                    creado_en, enviado_en null
                    UNIQUE (tipo, referencia)   -- idempotencia: el mismo hecho no genera dos avisos
```
- `enviado_manual` exige `resuelto_por_id` y `enviado_en`.
- `tipos_aviso` es un **catálogo**: cada paquete inserta los suyos con `INSERT … ON CONFLICT DO UPDATE` (como `12_tipos_de_charla.sql`), así no hay que tocar ningún `CHECK`.
- Este SQL también inserta el tipo de consulta `baja_avisos` (`bot_responde`) en `tipos_consulta`.
- `datos` guarda **ids** (póliza, cuota, interesado…); el texto se arma al enviar o al mostrar, con datos frescos de la base (R12). `asignado_a_id` dice a quién le toca el contacto manual (ej. el responsable de un interesado); `NULL` = cualquiera.

## 3. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-32 | Dados `Aviso`, `TipoAviso` y `ContactoWhatsapp.acepta_avisos`, entonces son `managed = False` con los campos y FK del esquema, `EstadoAviso` (7 valores) coincide con el `CHECK` (como AC-T4-07), el SQL 14 está en `test_runner.py` y se puede aplicar dos veces; un aviso `enviado_manual` sin `resuelto_por_id` es rechazado por la base (SQL directo); `crear_catalogos()` agrega el tipo de consulta `baja_avisos`; fábricas `crear_tipo_aviso` y `crear_aviso`. |
| AC-T4-33 | Dadas las consultas nuevas, entonces `avisos_pendientes(ahora)` devuelve los `pendiente` con `programado_para <= ahora` y `caduca_en > ahora`, por `prioridad` del tipo y luego por antigüedad; `avisos_para_contactar(ahora, asignado_a_id=None)` devuelve, de esos, los de contactos con `acepta_avisos` y **sin ventana de 24 h abierta** (sin mensaje del cliente en las últimas 24 h), con el filtro opcional por asignado (incluye los sin asignar); `listar_avisos(estado=None, tipo=None, contacto_id=None)` (más nuevos primero, con contacto y cliente incluidos); `aviso_enviado_hoy(contacto_id, hoy)` indica si ya se le mandó uno ese día (zona Buenos Aires). Número fijo de consultas. |

## 4. Etapa B · Lógica (T3)
Archivos: `negocio/avisos.py` (nuevo), `negocio/bot/orquestador.py` y `negocio/bot/` (clasificador y plantillas fijas), `negocio/management/commands/procesar_avisos.py`. **No se toca el envío real de `negocio/whatsapp.py`**: los avisos usan el mismo camino de texto libre de siempre.

Piezas: un **registro de generadores** (`GENERADORES`: cada paquete registra `generar(hoy) -> list[AvisoNuevo]` con `tipo`, `contacto_id`, `referencia`, `datos` y `asignado_a_id` opcional) y un **registro de textos de aviso** (`TEXTOS_AVISO[tipo] -> función(datos) -> (texto, datos_verificados)`).
| ID | Criterio |
|---|---|
| AC-T3-62 | Dado `programar_aviso(tipo, contacto_id, referencia, datos, para=None, caduca_en=None, asignado_a_id=None)`, entonces crea el aviso `pendiente` (`caduca_en` por defecto 7 días después de `programado_para`) y, si se llama otra vez con el mismo `(tipo, referencia)`, devuelve el existente sin duplicar; un tipo desconocido o inactivo es `DatosInvalidos`; si el contacto tiene `acepta_avisos = False` el aviso se crea directamente `cancelado` con `error='baja_avisos'`; un contacto inexistente es `NoEncontrado`. |
| AC-T3-63 | Dados `texto_de_aviso(aviso_id, para_manual=False) -> (texto, datos_verificados)` y `enviar_avisos(ahora)`, entonces el primero arma el texto con `TEXTOS_AVISO` y datos frescos (con `para_manual=True` agrega `AVISO_RESPONDER`); el segundo recorre `avisos_pendientes(ahora)` **solo de contactos con ventana de 24 h abierta**, dentro de 09:00 a 20:00, pasa el texto por `evaluar_salida`, crea el mensaje saliente de la conversación abierta como texto libre y deja el aviso `enviado` con `mensaje_id` (si la salida genera alertas, el mensaje queda `retenido` según R13 y el aviso `retenido`); **máximo un aviso por contacto por día**, sale primero el de menor `prioridad`; los de ventana cerrada quedan `pendiente` y no se envían; los que pasaron `caduca_en` pasan a `vencido`. **Ningún camino crea ni manda un mensaje `type: "template"`**: un test recorre el cuerpo de todo lo que sale por la API simulada y falla si aparece. |
| AC-T3-64 | Dado `entregar_avisos_pendientes(contacto_id)`, que el orquestador llama al terminar de procesar un mensaje entrante, entonces entrega hasta **2** avisos `pendiente` no caducados del contacto, por `prioridad`, como mensajes del bot a continuación de la respuesta (con `evaluar_salida`, R13), y los deja `enviado`; no entrega nada si la conversación está en `modo='humano'`, si el contacto no acepta avisos, si la consulta fue `siniestro_urgente`, `prompt_injection` o `baja_avisos`, si la respuesta del bot quedó `retenida`, o si ya se le entregó un aviso ese día. |
| AC-T3-65 | Dada una consulta de tipo `baja_avisos` («no me escriban más», “dejen de mandarme mensajes”, «STOP», «no quiero recibir avisos», «darme de baja de los avisos»), entonces el clasificador por reglas la reconoce **antes** de `baja` (y «quiero dar de baja el seguro» sigue siendo `baja`), el bot pone `acepta_avisos = False` en el contacto, cancela sus avisos `pendiente` y responde `BAJA_AVISOS` («Listo, no te vamos a mandar más avisos. Si necesitás algo, escribinos cuando quieras.»). `cambiar_avisos(contacto_id, acepta, funcionario_id)` (aprobador) lo vuelve a activar. |
| AC-T3-66 | Dado `python manage.py procesar_avisos [--dry-run]`, entonces ejecuta en orden todos los generadores registrados para la fecha de hoy (Buenos Aires), programa los avisos, marca los caducados y llama a `enviar_avisos(ahora)`; imprime `programados / enviados / retenidos / cancelados / vencidos / para_contactar_a_mano`; con `--dry-run` no escribe nada; correrlo dos veces el mismo día no duplica avisos. Pensado para correr cada hora (servicio aparte en `docker-compose.yml`, como el de `reprocesar_pendientes`). |
| AC-T3-67 | Dados `cancelar_aviso(aviso_id, funcionario_id)` y `marcar_aviso_manual(aviso_id, funcionario_id)`, entonces el primero pasa un aviso `pendiente` a `cancelado` y el segundo a `enviado_manual` con `resuelto_por` y `enviado_en`; en cualquier otro estado, `EstadoInvalido`; inexistente, `NoEncontrado`. Cualquier funcionario activo puede usarlos. |

## 5. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-29 | Dados `GET /api/avisos/?estado=&tipo=&pagina=` (paginado), `POST /api/avisos/{id}/cancelar/` y `POST /api/avisos/{id}/marcar-manual/` (cualquier funcionario), entonces devuelven `aviso` `{id, tipo, tipo_nombre, estado, programado_para, caduca_en, enviado_en, resuelto_por, asignado_a, error, contacto: {id, whatsapp, cliente}}` y los errores siguen AC-T2-03; la ruta `/panel/avisos/` está en la lista blanca. |
| AC-T2-30 | Dados `GET /api/avisos/para-contactar/?asignado_a=me` (paginado; usa `avisos_para_contactar`; cada ítem suma `texto`, el de `texto_de_aviso(id, para_manual=True)`, y `numero` del contacto) y `PATCH /api/contactos/{id}/avisos/` con `{acepta_avisos}` (aprobador), entonces la lista incluye también los sin asignar, y `cliente_detalle` muestra `acepta_avisos` por contacto. |

## 6. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-27 | Dado `lib/avisos.js`, entonces `enlaceWhatsapp("+5491126914442", "Hola Ana")` → `https://wa.me/5491126914442?text=Hola%20Ana` (sin `+`, texto con `encodeURIComponent`), un número inválido devuelve `null`, `etiquetaEstadoAviso` → «Pendiente», «Enviado», «Enviado a mano», «Retenido», «Falló», «Cancelado», «Vencido» (desconocido → «—») y `agruparAvisosPorDia(avisos)` agrupa por fecha de `programado_para` sin modificar la lista original. |
| AC-T1-28 | **(QA)** Dada `/panel/avisos/`, entonces tiene dos pestañas: «Para contactar» (por cliente: tipo de aviso, texto ya armado, y los botones «Abrir WhatsApp» —enlace en pestaña nueva con `rel="noopener"`—, «Copiar texto», «Marcar como enviado» y «Cancelar»; filtro «Solo los míos») e «Historial» (todos los estados, filtros por estado y tipo, paginación, enlace a la conversación); marcar o cancelar saca la fila sin recargar y los errores de la API se muestran. |
| AC-T1-29 | **(QA)** Dada la ficha de cliente, entonces cada contacto muestra «Recibe avisos: sí/no» con un botón para cambiarlo (solo aprobadores) y la lista de sus últimos avisos. |

## 7. Terminado cuando
Los 13 AC con prueba; un `procesar_avisos --dry-run` contra la base real que no escribe nada; contratos actualizados (incluida la **forma de registrar un generador y un texto de aviso**, que es lo que usan los demás paquetes); SQL 14 aplicado; `AGENCIA_WHATSAPP` en `env.example` y en `00-comun.md`; a mano, con tu propio número: un aviso con ventana abierta sale solo, uno con ventana cerrada aparece en «Para contactar» con su botón «Abrir WhatsApp», y al escribir «hola» desde el celular el bot responde y entrega el aviso pendiente. `SDD/entregas/P2.md`.
