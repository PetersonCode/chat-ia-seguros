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
UMBRAL_AUMENTO_SIGNIFICATIVO = Decimal("15")
def aumento_significativo(actual, nueva, umbral=UMBRAL_AUMENTO_SIGNIFICATIVO) -> bool   # P5 · True si `nueva` supera a `actual` en `umbral` % o más; Decimal sin dividir; actual <= 0 -> False
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

## 8. Vehículos y compañías (P1: `negocio/vehiculos.py`, `negocio/companias.py`, `negocio/polizas.py`)
```python
# negocio/vehiculos.py — todas exigen aprobador activo (PermisoDenegado; funcionario inexistente: NoEncontrado)
def alta_vehiculo(cliente_id: int, patente: str, marca: str, modelo: str, anio: int, uso: str = "particular",
                  chasis: str | None = None, valor_asegurado=None, *, funcionario_id: int) -> Vehiculo
    # patente normalizada; DatosInvalidos: patente repetida o inválida, año fuera de 1950..año actual+1, marca/modelo vacíos,
    # uso desconocido, valor_asegurado <= 0, cliente inactivo. Cliente inexistente: NoEncontrado.
def modificar_vehiculo(vehiculo_id: int, *, funcionario_id: int, patente=None, marca=None, modelo=None, anio=None, uso=None,
                       chasis=SIN_CAMBIO, valor_asegurado=SIN_CAMBIO) -> Vehiculo
    # solo lo recibido; None en patente/marca/modelo/anio/uso = no cambiar; chasis y valor_asegurado: None o "" los borra.
    # La patente propia no cuenta como repetida. El dueño no se cambia.
def dar_de_baja_vehiculo(vehiculo_id: int, *, funcionario_id: int) -> Vehiculo
    # baja lógica (activo=False); EstadoInvalido si ya estaba de baja o si tiene una póliza 'vigente' que no venció.

# negocio/companias.py — todas exigen aprobador activo
def alta_compania(nombre: str, comision_pct, *, funcionario_id: int) -> Compania
    # nombre único sin distinguir mayúsculas ni espacios (se guarda con espacios colapsados); comisión 0..100, 2 decimales.
def modificar_compania(compania_id: int, *, funcionario_id: int, nombre=None, comision_pct=None, activa: bool | None = None) -> Compania
    # solo lo recibido; `activa=True` reactiva. No toca las pólizas ya emitidas.
def desactivar_compania(compania_id: int, *, funcionario_id: int) -> Compania     # = modificar_compania(activa=False)
def porcentaje_validado(valor, campo: str = "La comisión") -> Decimal              # 0..100, 2 decimales, acepta coma; DatosInvalidos

# negocio/polizas.py
def alta_poliza(cliente_id, *, tipo_seguro, cobertura, fecha_inicio, fecha_vencimiento, prima_mensual,
                bien_asegurado=None, numero_poliza=None,
                vehiculo_id: int | None = None, compania_id: int | None = None, comision_pct=None) -> Poliza
    # vehiculo_id: del cliente de la póliza y activo; compania_id: existente y activa (si no, DatosInvalidos).
    # comision_pct de la póliza = el pasado, o el de la compañía en ese momento (queda congelado); sin compañía ni valor, None.
    # bien_asegurado vacío + vehículo -> "<marca> <modelo> <año> (<patente>)". Sin vehículo ni compañía se comporta como antes.
def descripcion_de_vehiculo(vehiculo: Vehiculo) -> str
```
Plantilla del bot `LINEA_VENCIMIENTO` (`negocio/bot/plantillas.py`): ahora termina en `{patente}`, que vale `" · <patente>"` si la póliza tiene vehículo y `""` si no. La patente va en `datos_verificados`.

## 8 bis. Embudo de interesados y cotizaciones (P5: `negocio/interesados.py`, `negocio/cotizaciones.py`, `negocio/bot/cotizacion.py`)
Cualquier funcionario **activo** puede todo, salvo `convertir_en_cliente` (aprobador). Un funcionario inactivo o inexistente es `PermisoDenegado`; un interesado, cotización o póliza inexistente, `NoEncontrado`.
```python
# negocio/interesados.py
TRANSICIONES   # consulta→cotizando→documentacion→emitida (de a una) y una etapa atrás (cotizando→consulta, documentacion→cotizando); cualquiera abierta→perdida; perdida→consulta. emitida es final.
def crear_interesado(funcionario_id, nombre, origen, telefono=None, apellido=None, datos=None) -> Interesado
    # en `consulta`, el que lo crea es el responsable, primer historial con estado_anterior nulo. El teléfono pasa por normalizar_telefono y
    # reutiliza el contacto (o lo crea sin cliente). Si el número ya tiene un interesado abierto devuelve ese. Si es de un cliente activo, nace con cliente_id.
def mover_interesado(interesado_id, estado_nuevo, funcionario_id, nota=None, motivo_perdida=None) -> Interesado
    # transición inválida / salir de emitida: EstadoInvalido. perdida sin motivo de 3+ caracteres: DatosInvalidos. emitida exige cliente y una póliza
    # creada DESPUÉS del interesado (EstadoInvalido). Reabrir una perdida cuando el número ya tiene otro interesado abierto: EstadoInvalido.
def convertir_en_cliente(interesado_id, funcionario_id, dni, nombre, apellido, email=None, telefono=None) -> Interesado
    # aprobador; solo en `documentacion`. alta_cliente (adopta el contacto) o reutiliza al cliente de ese DNI. No cambia la etapa.
    # `telefono` solo se usa si el interesado no tiene contacto de WhatsApp (alta_cliente lo exige).
def asignar_interesado(interesado_id, responsable_id, funcionario_id) -> Interesado     # responsable inactivo o inexistente: DatosInvalidos
def programar_contacto(interesado_id, fecha, funcionario_id) -> Interesado              # hoy o futura (date o "aaaa-mm-dd"); vacía/None la borra
def actualizar_datos_interesado(interesado_id, datos: dict, funcionario_id) -> Interesado
    # mezcla con lo existente; normaliza patente y dni, valida anio y uso; valor vacío/None borra la clave; solo escalares
def datos_normalizados(datos: dict | None) -> dict
def registrar_cotizacion_del_bot(contacto, datos: dict, *, responsable_id=None) -> Interesado
    # lo usa el bot: suma los datos al interesado abierto de ese número o crea uno (origen whatsapp, historial sin autor).
    # Si no tenía proximo_contacto, queda para hoy; si tenía, lo conserva.
# Cada gestión (asignar, programar, datos, convertir) deja una línea de historial en la etapa actual (estado_anterior == estado_nuevo) con la nota de qué se hizo.

# Seguimiento (se engancha al motor de avisos de P2; ver "Pendiente de P2" en SDD/entregas/P5.md)
def seguimiento_interesados(hoy: date) -> list[dict]
    # generador: por cada interesado en `cotizando` con WhatsApp, que lleva 2..4 días (tipo seguimiento_cotizacion_2d) o 5..11 días (…_5d)
    # y cuyo contacto NO escribió desde que entró a esa etapa. Cada dict: {tipo, contacto_id, referencia: "interesado:<id>:<2d|5d>:<fecha de entrada>",
    # datos: {"interesado_id"}, asignado_a_id: responsable}
def texto_seguimiento_cotizacion(datos: dict) -> tuple[str, frozenset[str]]    # el texto de TEXTOS_AVISO para ambos tipos (datos = {"interesado_id"})

# negocio/cotizaciones.py
def cargar_cotizacion(funcionario_id, compania_id, cobertura, prima_mensual, interesado_id=None, poliza_id=None, vigencia_hasta=None, notas=None) -> Cotizacion
    # exactamente uno de interesado_id / poliza_id; compañía activa (inexistente NoEncontrado, desactivada DatosInvalidos); prima > 0, 2 decimales, acepta coma
def elegir_cotizacion(cotizacion_id, funcionario_id) -> Cotizacion      # desmarca la anterior del mismo destino en la misma transacción
def quitar_cotizacion(cotizacion_id, funcionario_id) -> None            # borra una no elegida; la elegida: EstadoInvalido
def variacion_renovacion(poliza_id) -> Decimal | None                   # % de la prima de la póliza a la cotización elegida (2 decimales); None sin elegida
```
**Bot (`negocio/bot/cotizacion.py`, `plantillas.py`, `orquestador.py`).** Una consulta `cotizacion` ya no deriva en seco: pide en orden patente, marca y modelo, año, uso y localidad (`PEDIDO_COTIZACION`; con un solo dato pendiente, `PEDIDO_COTIZACION_UNO`), hasta `registro.MAX_PEDIDOS` veces; lee las respuestas con expresiones regulares y **deja vacío lo que no puede leer con certeza**; guarda en `Interesado.datos`, responde `COTIZACION_REGISTRADA` y deriva a Graciela con `Interesado #<id>` en el motivo. Sin estado propio: el rastro es `MARCA_PEDIDO_COTIZACION` en el log (igual que el alta). `COTIZACION_REGISTRADA` está en la lista de mensajes permitidos durante la atención humana (`whatsapp.mensaje_permitido_durante_atencion`) y en el payload `aviso_derivacion`; sin eso se descartaba al derivar.

## 9. Qué excepción lanza cada caso (para que T2 la traduzca)
| Situación | Excepción |
|---|---|
| Funcionario sin `puede_aprobar` en una operación de aprobador, o que no es el asignado | `PermisoDenegado` |
| Id inexistente | `NoEncontrado` |
| Mensaje que ya no está `retenido`; acción ya resuelta; derivación ya atendida; ventana de 24 h cerrada (`codigo="ventana_24h_cerrada"`) | `EstadoInvalido` |
| Motivo vacío o corto, tipo de acción inválido, texto vacío | `DatosInvalidos` |
| P5: transición de etapa inválida, interesado emitido, emitir sin cliente/póliza nueva, quitar la cotización elegida, convertir fuera de `documentacion` | `EstadoInvalido` |
| P5: origen, nombre, teléfono, prima, cobertura, dato (patente, DNI, año, uso), fecha pasada o responsable inválidos; ambos o ninguno de interesado/póliza | `DatosInvalidos` |
| Faltan parámetros para ejecutar una acción | `ParametrosIncompletos` |
