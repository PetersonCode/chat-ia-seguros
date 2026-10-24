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
    # Recorre entry[].changes[].value: messages[] -> registrar_entrante (+ bot en segundo plano);
    # statuses[] -> actualizar_estado_entrega. Nunca lanza por datos raros: los registra en el log.
def registrar_entrante(wa_message_id: str, numero_raw: str, texto: str,
                       payload: dict | None = None, nombre_perfil: str | None = None) -> Mensaje | None
    # None si el wa_message_id ya existía
def enviar_pendientes(conversacion_id: int) -> int            # cuántos envió
def actualizar_estado_entrega(wa_message_id: str, estado: str) -> None   # 'sent'|'delivered'|'read'|'failed'
def en_segundo_plano(funcion, *args) -> None                  # hilo; los tests lo reemplazan con mock
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
def devolver_al_bot(conversacion_id: int, funcionario_id: int) -> Conversacion
def responder_como_humano(conversacion_id: int, funcionario_id: int, texto: str) -> Mensaje
def reabrir_consulta(consulta_id: int, funcionario_id: int) -> ConsultaBot
```
Aprobador requerido en: `liberar_respuesta`, `descartar_respuesta`, `reabrir_consulta`.

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

## 8. Qué excepción lanza cada caso (para que T2 la traduzca)
| Situación | Excepción |
|---|---|
| Funcionario sin `puede_aprobar` en una operación de aprobador, o que no es el asignado | `PermisoDenegado` |
| Id inexistente | `NoEncontrado` |
| Mensaje que ya no está `retenido`; acción ya resuelta; derivación ya atendida; ventana de 24 h cerrada (`codigo="ventana_24h_cerrada"`) | `EstadoInvalido` |
| Motivo vacío o corto, tipo de acción inválido, texto vacío | `DatosInvalidos` |
| Faltan parámetros para ejecutar una acción | `ParametrosIncompletos` |
