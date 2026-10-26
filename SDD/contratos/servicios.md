# Contrato · Lógica de negocio (`negocio/`)

**Lo implementa:** T3 · **Lo usa:** T2.
Reglas generales: las funciones que escriben usan `transaction.atomic`; reciben **IDs y datos simples** (nunca `request`); los errores de negocio son excepciones de `negocio/errores.py`. Cambiar algo de acá requiere acuerdo de las 4 personas.

## 1. Errores (`negocio/errores.py`)
```python
class ErrorNegocio(Exception):
    codigo: str = "error_negocio"
    def __init__(self, mensaje: str): ...        # mensaje en español, apto para mostrar al usuario
class DatosInvalidos(ErrorNegocio):      codigo = "datos_invalidos"         # -> HTTP 400
class ParametrosIncompletos(ErrorNegocio): codigo = "parametros_incompletos"  # -> HTTP 400
class PermisoDenegado(ErrorNegocio):     codigo = "permiso_denegado"        # -> HTTP 403
class NoEncontrado(ErrorNegocio):        codigo = "no_encontrado"           # -> HTTP 404
class EstadoInvalido(ErrorNegocio):      codigo = "estado_invalido"         # -> HTTP 409
```
Un `EstadoInvalido` puede llevar un código más específico, p. ej. `EstadoInvalido("…", codigo="ventana_24h_cerrada")` (el constructor acepta `codigo` opcional).

## 2. Sesión (`negocio/sesion.py`)
```python
def funcionario_de(user) -> Funcionario    # por email del User de Django; PermisoDenegado si no hay funcionario activo
```

## 3. Reglas puras (`negocio/reglas.py`, sin base de datos)
```python
RANGO_SEVERIDAD = {"baja": 1, "media": 2, "alta": 3, "critica": 4}
def severidad_por_rango(rango: int) -> str | None          # 0 -> None, 1 -> 'baja' … 4 -> 'critica'
def color_por_severidad(severidad: str | None) -> str      # critica 'rojo' · alta 'naranja' · media/baja 'amarillo' · None 'verde'
def sin_respuesta(*, estado: str, modo: str, ultimo_emisor: str | None,
                  ultimo_fecha_hora: datetime | None, ahora: datetime) -> bool
    # True si estado 'abierta', modo 'bot', el último mensaje es del cliente y tiene más de 10 minutos
def ventana_24h_abierta(ultimo_mensaje_cliente_en: datetime | None, ahora: datetime) -> bool
```

## 4. WhatsApp (`negocio/whatsapp.py`)
```python
def verificar_suscripcion(mode: str | None, token: str | None, challenge: str | None) -> str | None
    # devuelve challenge si mode == 'subscribe' y token == WHATSAPP_VERIFY_TOKEN; si no, None
def verificar_firma(cuerpo: bytes, firma: str | None) -> bool
    # firma = header X-Hub-Signature-256 ("sha256=<hex>"); HMAC-SHA256 de cuerpo con WHATSAPP_APP_SECRET; compare_digest
def procesar_webhook(payload: dict) -> None
    # Persiste entry[].changes[].value: messages[] -> mensaje + trabajo durable;
    # statuses[] -> actualizar_estado_entrega. Error de persistencia se propaga.
def registrar_entrante(wa_message_id: str, numero_raw: str, texto: str,
                       payload: dict | None = None, nombre_perfil: str | None = None) -> Mensaje | None
    # None si el wa_message_id ya existía
def enviar_pendientes(conversacion_id: int) -> int            # cuántos envió
def actualizar_estado_entrega(wa_message_id: str, estado: str) -> None   # 'sent'|'delivered'|'read'|'failed'
```

## 5. Bot (`negocio/bot/`)
```python
@dataclass
class AlertaDetectada:
    tipo: str            # valores de TipoAlerta
    severidad: str       # valores de Severidad
    descripcion: str

@dataclass
class ResultadoBot:
    ignorado: bool                    # True si la conversación estaba en modo humano o ya se procesó
    tipo_consulta: str | None
    mensaje_respuesta_id: int | None  # mensaje del bot creado (retenido o no)
    retenido: bool
    alertas: list[str]                # tipos de alerta creados

# negocio/bot/orquestador.py
def procesar_mensaje(mensaje_id: int) -> ResultadoBot
# negocio/bot/guardrails.py
def evaluar_entrada(texto: str) -> list[AlertaDetectada]
def evaluar_salida(texto: str, *, cliente_id: int | None,
                   datos_verificados: frozenset[str] = frozenset()) -> list[AlertaDetectada]
```

## 6. Supervisión (`negocio/supervision.py`)
```python
def liberar_respuesta(mensaje_id: int, funcionario_id: int, texto_corregido: str | None = None) -> Mensaje
    # Devuelve el mensaje que sale al cliente (el mismo, o el nuevo del funcionario si se corrigió).
def descartar_respuesta(mensaje_id: int, funcionario_id: int, motivo: str) -> Mensaje
def tomar_conversacion(conversacion_id: int, funcionario_id: int) -> Conversacion
    # Cualquier funcionario activo puede tomar o reasignar; cancela las respuestas bot comunes en cola.
def devolver_al_bot(conversacion_id: int, funcionario_id: int) -> Conversacion
    # Solo el funcionario actualmente asignado puede devolver.
def responder_como_humano(conversacion_id: int, funcionario_id: int, texto: str) -> Mensaje
    # Requiere modo humano y que funcionario_id sea el responsable actual.
def reabrir_consulta(consulta_id: int, funcionario_id: int) -> ConsultaBot
```
Aprobador requerido en: `liberar_respuesta`, `descartar_respuesta`, `reabrir_consulta`.

La toma y la reasignación se serializan bloqueando la fila de la conversación.
Solo salen durante la atención humana mensajes del funcionario, avisos de
derivación y respuestas del bot liberadas expresamente por un aprobador. Las
respuestas automáticas comunes que estaban pendientes se descartan; no se
reactivan al devolver el chat al bot. El envío retiene el mismo bloqueo mientras
registra el intento, con un timeout de red de 10 segundos para WhatsApp real.

## 7. Acciones y derivaciones (`negocio/acciones.py`)
```python
def solicitar_accion(consulta_id: int, tipo: str, poliza_id: int | None = None,
                     parametros: dict | None = None) -> AccionPendiente
def completar_parametros(accion_id: int, funcionario_id: int, parametros: dict) -> AccionPendiente
def aprobar_accion(accion_id: int, funcionario_id: int, motivo: str | None = None) -> AccionPendiente
    # aprueba y ejecuta el efecto en una transacción; devuelve la acción 'ejecutada'
def rechazar_accion(accion_id: int, funcionario_id: int, motivo: str) -> AccionPendiente
def derivar(consulta_id: int, derivado_a_id: int, prioridad: str = "normal", motivo: str = "") -> Derivacion
def atender_derivacion(derivacion_id: int, funcionario_id: int) -> Derivacion
```
Aprobador requerido en: `completar_parametros`, `aprobar_accion`, `rechazar_accion`.

## 8. Expediente operativo (`negocio/siniestros.py`)
```python
def registrar_denuncia(*, cliente_id: int, poliza_id: int, fecha_ocurrencia,
                       descripcion: str, funcionario_id: int) -> Siniestro
def transicionar_siniestro(siniestro_id: int, *, estado: str, motivo: str,
                           funcionario_id: int) -> Siniestro
```
La denuncia requiere un funcionario activo, póliza del cliente indicado,
descripción y fecha no futura dentro de la cobertura de la póliza. Su número se
asigna secuencialmente por año bajo `pg_advisory_xact_lock(4243)`. La denuncia
inicial y cada cambio guardan responsable, motivo y fecha en el historial.
Solo un aprobador activo puede cambiar el estado; se permiten únicamente
`denunciado → en_evaluacion → aprobado|rechazado → cerrado`. El motivo de cada
cambio requiere al menos tres caracteres. El historial es inmutable en SQL.
`aprobado` es una decisión operativa interna: no significa ni genera una
indemnización de la aseguradora. La apertura desde una acción del bot usa el
mismo servicio y conserva la consulta de origen.

## 9. Pólizas (`negocio/polizas.py`)
```python
def registrar_pago(poliza_id: int, *, referencia: str, importe,
                   funcionario_id: int) -> Pago
```
Registra una sola cuota completa, con referencia única, importe, fecha local,
responsable y relación uno-a-uno con la cuota. Repetir referencia con la misma
póliza e importe devuelve el movimiento existente sin volver a bajar el saldo;
reutilizarla con otros datos da `EstadoInvalido`. Solo un aprobador activo
registra el pago. Un importe distinto al total de la cuota da `DatosInvalidos`.
`06_pagos_con_referencia.sql` asegura la unicidad y actualiza la cuota dentro de
la misma transacción.

El selector de cobertura actual exige estado `vigente` y fecha local dentro del
intervalo inclusivo `[fecha_inicio, fecha_vencimiento]`. Para el MVP académico,
las cuotas se generan en ciclos mensuales desde `fecha_inicio`: el último ciclo
parcial se cobra completo, una fecha exacta de aniversario no agrega otro ciclo,
y los días 29, 30 o 31 se acotan al último día de un mes corto y recuperan el
día original en los ciclos siguientes. Cada cuota vence al inicio de su ciclo;
`periodo` conserva el primer día de ese mes por la restricción SQL existente.
No se aplican automáticamente prorrateos, descuentos, devoluciones ni recargos.
Esta simplificación queda pendiente de validación con la agencia.

El alta no comprueba duplicados por bien asegurado y período:
`bien_asegurado` es texto libre y no hay una regla acordada de identidad o
solapamiento.

## 10. Consulta documental (`negocio/documentos.py`)
`buscar_fragmentos(consulta)` solo devuelve pasajes de documentos en estado
`aprobado`. La recuperación es lexical, local y no llama al LLM. El bot de
`consulta_cobertura` cita el pasaje y su referencia como información general;
si no hay respaldo suficiente, mantiene la derivación normal. La cita no
confirma que una condición aplique a una póliza particular. Los documentos
retirados dejan de ser candidatos a búsquedas nuevas.

## 11. Qué excepción lanza cada caso (para que T2 la traduzca)
| Situación | Excepción |
|---|---|
| Funcionario sin `puede_aprobar` en una operación de aprobador, o que no es el asignado | `PermisoDenegado` |
| Id inexistente | `NoEncontrado` |
| Mensaje que ya no está `retenido`; acción ya resuelta; derivación ya atendida; ventana de 24 h cerrada (`codigo="ventana_24h_cerrada"`) | `EstadoInvalido` |
| Motivo vacío o corto, tipo de acción inválido, texto vacío, fecha de siniestro futura o fuera de cobertura, póliza que no pertenece al cliente | `DatosInvalidos` |
| Faltan parámetros para ejecutar una acción | `ParametrosIncompletos` |
