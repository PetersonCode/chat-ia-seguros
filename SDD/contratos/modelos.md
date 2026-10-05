# Contrato · Modelos, consultas y limpieza (`datos/`)

**Lo implementa:** T4 · **Lo usan:** T3 (y T2 para leer).
Cambiar algo de acá requiere acuerdo de las 4 personas.

## 1. Modelos (`datos/models.py`)
Todos con `class Meta: managed = False` y `db_table` explícito. **Django no crea ni migra estas tablas.**
PK: `models.BigAutoField(primary_key=True)` (los catálogos: `SmallAutoField`). FK con `on_delete=models.DO_NOTHING`; el nombre del campo es el de la columna sin `_id` (`cliente_id` → `cliente`).
Los campos que en la base tienen `DEFAULT` llevan el mismo default en Django (`timezone.now`, `True`, `"pendiente"`, `dict`…), porque Django envía todas las columnas en el `INSERT`.
**Todas** las FK a `Funcionario` usan `related_name="+"`, salvo `Derivacion.derivado_a` (`related_name="derivaciones"`).

| Modelo | Tabla | Campos (FK → modelo) | `related_name` |
|---|---|---|---|
| `Funcionario` | `funcionarios` | nombre, email, rol, puede_aprobar, activo, creado_en | |
| `TipoSeguro` | `tipos_seguro` | codigo, nombre | |
| `TipoConsulta` | `tipos_consulta` | codigo, nombre, politica | |
| `Cliente` | `clientes` | dni, nombre, apellido, email, activo, creado_en | |
| `ContactoWhatsapp` | `contactos_whatsapp` | numero, cliente→Cliente (null), nombre_perfil, creado_en | `cliente.contactos` |
| `Poliza` | `polizas` | numero_poliza, cliente→Cliente, tipo_seguro→TipoSeguro, cobertura, estado, fecha_inicio, fecha_vencimiento, prima_mensual, bien_asegurado, creado_en | `cliente.polizas` |
| `ConductorPoliza` | `conductores_poliza` | poliza→Poliza, nombre, dni, relacion, activo | `poliza.conductores` |
| `Cuota` | `cuotas` | poliza→Poliza, periodo, importe, vencimiento, estado, fecha_pago, importe_pagado | `poliza.cuotas` |
| `Siniestro` | `siniestros` | numero_siniestro, poliza→Poliza, consulta→ConsultaBot (null), fecha_ocurrencia, descripcion, estado, creado_en | `poliza.siniestros` |
| `Conversacion` | `conversaciones` | contacto→ContactoWhatsapp, estado, modo, funcionario→Funcionario (null), ultimo_mensaje_cliente_en, creada_en, cerrada_en | `contacto.conversaciones` |
| `Mensaje` | `mensajes` | conversacion→Conversacion, consulta→ConsultaBot (null), direccion, emisor, funcionario→Funcionario (null), texto, estado_envio, wa_message_id, error, payload (JSON), fecha_hora, enviado_en | `conversacion.mensajes`, `consulta.mensajes` |
| `ConsultaBot` | `consultas_bot` | codigo_caso, fecha_hora, contacto→ContactoWhatsapp (null), conversacion→Conversacion (null), mensaje_usuario, respuesta_bot, tipo_consulta→TipoConsulta, estado, funcionario_asignado→Funcionario (null), fecha_resolucion, revisado_por→Funcionario (null), revisado_en, respuesta_corregida, nota_revision, notas_importacion, datos_origen (JSON), creado_en | `conversacion.consultas` |
| `Alerta` | `alertas` | consulta→ConsultaBot, mensaje→Mensaje (null), tipo, severidad, descripcion, origen, estado, creada_en, resuelta_por→Funcionario (null), resuelta_en, resolucion | `consulta.alertas`, `mensaje.alertas` |
| `Derivacion` | `derivaciones` | consulta→ConsultaBot, derivado_a→Funcionario, prioridad, motivo, creada_en, atendida_en | `consulta.derivaciones` |
| `AccionPendiente` | `acciones_pendientes` | consulta→ConsultaBot, poliza→Poliza (null), tipo_accion, parametros (JSON), estado, solicitada_en, resuelta_por→Funcionario (null), resuelta_en, motivo | `consulta.acciones` |

**Vistas (solo lectura; `save()` y `delete()` lanzan `TypeError`):**
| Modelo | Vista | Campos |
|---|---|---|
| `VPolizaResumen` | `v_polizas_resumen` | poliza (PK, `OneToOneField` a Poliza, columna `poliza_id`), numero_poliza, cliente, dni, tipo_seguro, cobertura, estado, fecha_vencimiento, saldo_pendiente, proximo_vencimiento_pago |
| `VConsultaSupervision` | `v_consultas_supervision` | id (PK), codigo_caso, fecha_hora, whatsapp, cliente, tipo_consulta, politica, mensaje_usuario, respuesta_bot, estado, funcionario_asignado, alertas_abiertas, severidad_maxima, color, cerrado_con_alerta, revisada |
| `VBandejaConversacion` | `v_bandeja_conversaciones` | conversacion_id (PK), whatsapp, cliente, estado, modo, atendida_por, ultimo_mensaje, ultimo_emisor, ultimo_mensaje_en, alertas_abiertas, respuestas_retenidas, ventana_24h_abierta |

## 2. Opciones (`TextChoices` en `datos/models.py`)
Mismos valores que las restricciones `CHECK` de la base (T4 lo verifica con un test).
| Clase | Valores |
|---|---|
| `Rol` | propietario, administracion, operador |
| `Politica` | bot_responde, requiere_aprobacion, derivar_humano, seguridad |
| `Cobertura` | basica, intermedia, total |
| `EstadoPoliza` | vigente, vencida, dada_de_baja |
| `Relacion` | titular, conyuge, hijo, otro |
| `EstadoCuota` | pendiente, pagada, vencida |
| `EstadoSiniestro` | denunciado, en_evaluacion, aprobado, rechazado, cerrado |
| `EstadoConversacion` | abierta, cerrada |
| `ModoConversacion` | bot, humano |
| `Direccion` | entrante, saliente |
| `Emisor` | cliente, bot, funcionario |
| `EstadoEnvio` | recibido, pendiente_envio, retenido, descartado, enviado, entregado, leido, fallido |
| `EstadoConsulta` | abierto, pendiente_revision, derivado, cerrado |
| `TipoAlerta` | prompt_injection, fuga_datos, accion_sin_aprobacion, dato_inventado, dato_inconsistente, dato_no_verificado |
| `Severidad` | baja, media, alta, critica |
| `OrigenAlerta` | automatica, manual |
| `EstadoAlerta` | abierta, en_revision, resuelta, descartada |
| `Prioridad` | normal, urgente |
| `TipoAccion` | baja_poliza, agregar_conductor, modificar_poliza, reembolso, apertura_siniestro |
| `EstadoAccion` | pendiente, aprobada, rechazada, ejecutada |

Reglas que la **base** ya hace cumplir (no hace falta reimplementarlas, pero sí conocerlas): `dni` solo 7-8 dígitos; `numero` = `+549` + 10 dígitos; `numero_poliza` = `POL-#####`; `numero_siniestro` = `SIN-AAAA-#####`; `codigo_caso` = `CASO-###`; una sola conversación `abierta` por contacto; `wa_message_id` único; entrante ⇔ emisor cliente ⇔ estado `recibido`; un **trigger** impide resolver una acción sin `puede_aprobar` y ejecutarla sin aprobarla antes.

## 3. Consultas de lectura (`datos/selectors.py`)
Solo leen. Devuelven modelos o `QuerySet` (sin diccionarios armados para la API).
```python
def funcionario_por_email(email: str) -> Funcionario | None          # activo; sin distinguir mayúsculas
def funcionario_por_nombre(nombre: str) -> Funcionario | None        # activo; sin distinguir mayúsculas ni espacios
def cliente_por_dni(dni: str) -> Cliente | None                      # dni ya normalizado
def contacto_por_numero(numero: str) -> ContactoWhatsapp | None      # número ya normalizado
def conversacion_abierta(contacto_id: int) -> Conversacion | None
def mensajes_de(conversacion_id: int, despues_de: int | None = None) -> QuerySet[Mensaje]
    # orden (fecha_hora, id); con despues_de, solo id > despues_de; prefetch de alertas
def historial_reciente(conversacion_id: int, limite: int = 6) -> list[Mensaje]   # los últimos N, en orden cronológico
def tipo_consulta(codigo: str) -> TipoConsulta                       # TipoConsulta.DoesNotExist si no existe
def poliza_por_numero(numero: str) -> Poliza | None
def siniestro_por_numero(numero: str) -> Siniestro | None
def polizas_vigentes(cliente_id: int) -> QuerySet[Poliza]
def resumen_polizas(cliente_id: int) -> QuerySet[VPolizaResumen]     # orden por fecha_vencimiento
def alertas_abiertas(*, consulta_id: int | None = None, conversacion_id: int | None = None,
                     mensaje_id: int | None = None) -> QuerySet[Alerta]   # estado abierta o en_revision
def bandeja(*, estado: str | None = None, con_alertas: bool = False, esperando_humano: bool = False,
            q: str | None = None) -> QuerySet[Conversacion]
    # anota: alertas_abiertas (int), severidad_rango (0 sin alertas, 1 baja … 4 critica), retenidas (int),
    #        ultimo_texto, ultimo_emisor, ultimo_fecha_hora (del último mensaje).
    # esperando_humano = modo 'humano'. q busca en nombre/apellido del cliente y en el número.
    # Orden: primero las que tienen retenidas > 0 o severidad_rango = 4; después ultimo_fecha_hora descendente.
    # select_related de contacto__cliente y funcionario.
def detalle_conversacion(conversacion_id: int) -> Conversacion       # select_related; DoesNotExist si no existe
def listar_alertas(*, tipo: str | None = None, severidad: str | None = None,
                   estado: str | None = "abierta") -> QuerySet[Alerta]   # select_related consulta; más nuevas primero
def consultas_cerradas_con_alertas() -> QuerySet[ConsultaBot]        # estado 'cerrado' con alertas abiertas
def listar_acciones(*, estado: str | None = "pendiente") -> QuerySet[AccionPendiente]
    # más antiguas primero; select_related poliza, consulta__conversacion__contacto__cliente, resuelta_por
def derivaciones_de(funcionario_id: int, *, incluir_atendidas: bool = False) -> QuerySet[Derivacion]
    # urgentes primero, luego más antiguas
def buscar_clientes(q: str | None = None) -> QuerySet[Cliente]
    # anota polizas_vigentes (int). q: si normalizar_dni(q) funciona, busca por dni exacto;
    # si no, nombre o apellido que contengan q (sin distinguir mayúsculas). Orden apellido, nombre.
def detalle_cliente(cliente_id: int) -> Cliente                      # prefetch contactos, polizas, siniestros de sus pólizas
def detalle_poliza(poliza_id: int) -> Poliza                         # prefetch cuotas (más reciente primero), conductores, siniestros
def contar_pendientes(funcionario_id: int) -> dict[str, int]
    # {"acciones": pendientes, "derivaciones": sin atender de ese funcionario, "alertas_criticas": abiertas y críticas}
```

## 4. Fábricas para tests (`datos/fabricas.py`)
Crean objetos válidos con valores por defecto únicos (contadores). Todas aceptan `**campos` para sobrescribir.
```python
def crear_catalogos() -> None          # 5 tipos de seguro y 12 tipos de consulta iguales a SDD/sql/02_seed.sql; idempotente
def crear_funcionario(nombre="Graciela", puede_aprobar=True, **campos) -> Funcionario
def crear_cliente(**campos) -> Cliente
def crear_contacto(cliente: Cliente | None = None, **campos) -> ContactoWhatsapp
def crear_poliza(cliente: Cliente | None = None, **campos) -> Poliza                 # tipo automotor, vigente
def crear_cuota(poliza: Poliza, **campos) -> Cuota                                    # pendiente
def crear_conversacion(contacto: ContactoWhatsapp | None = None, **campos) -> Conversacion   # abierta, modo bot
def crear_mensaje(conversacion: Conversacion, **campos) -> Mensaje                    # entrante del cliente, 'recibido'
def crear_consulta(conversacion: Conversacion | None = None, tipo: str = "saludo", **campos) -> ConsultaBot
def crear_alerta(consulta: ConsultaBot, **campos) -> Alerta                           # dato_inventado, alta, abierta
def crear_accion(consulta: ConsultaBot, **campos) -> AccionPendiente                  # baja_poliza, pendiente
def crear_derivacion(consulta: ConsultaBot, derivado_a: Funcionario, **campos) -> Derivacion
```
`crear_funcionario` también crea un `User` de Django con el mismo email y clave `"clave-de-prueba"` (solo tests).

## 5. Limpieza de datos (`datos/limpieza.py`, funciones puras)
```python
def normalizar_dni(raw: str) -> str            # '28.111.222' -> '28111222'; ValueError si no quedan 7-8 dígitos
def normalizar_telefono(raw: str) -> str       # -> '+549' + 10 dígitos; ValueError si no se puede
def parsear_fecha_hora(raw: str) -> FechaParseada   # dataclass (fecha: date, hora: time | None); ValueError si inválida
def normalizar_tipo_seguro(raw: str) -> str    # 'AUTO' -> 'automotor'; ValueError si desconocido
```
Ejemplos exactos en la spec T4.
