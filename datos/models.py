from django.db import models
from django.utils import timezone


class Rol(models.TextChoices):
    PROPIETARIO = "propietario", "Propietario"
    ADMINISTRACION = "administracion", "Administración"
    OPERADOR = "operador", "Operador"


class Politica(models.TextChoices):
    BOT_RESPONDE = "bot_responde", "Bot responde"
    REQUIERE_APROBACION = "requiere_aprobacion", "Requiere aprobación"
    DERIVAR_HUMANO = "derivar_humano", "Derivar a humano"
    SEGURIDAD = "seguridad", "Seguridad"


class Cobertura(models.TextChoices):
    BASICA = "basica", "Básica"
    INTERMEDIA = "intermedia", "Intermedia"
    TOTAL = "total", "Total"


class EstadoPoliza(models.TextChoices):
    VIGENTE = "vigente", "Vigente"
    VENCIDA = "vencida", "Vencida"
    DADA_DE_BAJA = "dada_de_baja", "Dada de baja"


class Relacion(models.TextChoices):
    TITULAR = "titular", "Titular"
    CONYUGE = "conyuge", "Cónyuge"
    HIJO = "hijo", "Hijo"
    OTRO = "otro", "Otro"


class EstadoCuota(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    PAGADA = "pagada", "Pagada"
    VENCIDA = "vencida", "Vencida"


class EstadoSiniestro(models.TextChoices):
    DENUNCIADO = "denunciado", "Denunciado"
    EN_EVALUACION = "en_evaluacion", "En evaluación"
    APROBADO = "aprobado", "Aprobado"
    RECHAZADO = "rechazado", "Rechazado"
    CERRADO = "cerrado", "Cerrado"


class EstadoConversacion(models.TextChoices):
    ABIERTA = "abierta", "Abierta"
    CERRADA = "cerrada", "Cerrada"


class ModoConversacion(models.TextChoices):
    BOT = "bot", "Bot"
    HUMANO = "humano", "Humano"


class Direccion(models.TextChoices):
    ENTRANTE = "entrante", "Entrante"
    SALIENTE = "saliente", "Saliente"


class Emisor(models.TextChoices):
    CLIENTE = "cliente", "Cliente"
    BOT = "bot", "Bot"
    FUNCIONARIO = "funcionario", "Funcionario"


class EstadoEnvio(models.TextChoices):
    RECIBIDO = "recibido", "Recibido"
    PENDIENTE_ENVIO = "pendiente_envio", "Pendiente de envío"
    RETENIDO = "retenido", "Retenido"
    DESCARTADO = "descartado", "Descartado"
    ENVIADO = "enviado", "Enviado"
    ENTREGADO = "entregado", "Entregado"
    LEIDO = "leido", "Leído"
    FALLIDO = "fallido", "Fallido"


class EstadoConsulta(models.TextChoices):
    ABIERTO = "abierto", "Abierto"
    PENDIENTE_REVISION = "pendiente_revision", "Pendiente de revisión"
    DERIVADO = "derivado", "Derivado"
    CERRADO = "cerrado", "Cerrado"


class TipoAlerta(models.TextChoices):
    PROMPT_INJECTION = "prompt_injection", "Prompt injection"
    FUGA_DATOS = "fuga_datos", "Fuga de datos"
    ACCION_SIN_APROBACION = "accion_sin_aprobacion", "Acción sin aprobación"
    DATO_INVENTADO = "dato_inventado", "Dato inventado"
    DATO_INCONSISTENTE = "dato_inconsistente", "Dato inconsistente"
    DATO_NO_VERIFICADO = "dato_no_verificado", "Dato no verificado"


class Severidad(models.TextChoices):
    BAJA = "baja", "Baja"
    MEDIA = "media", "Media"
    ALTA = "alta", "Alta"
    CRITICA = "critica", "Crítica"


class OrigenAlerta(models.TextChoices):
    AUTOMATICA = "automatica", "Automática"
    MANUAL = "manual", "Manual"


class EstadoAlerta(models.TextChoices):
    ABIERTA = "abierta", "Abierta"
    EN_REVISION = "en_revision", "En revisión"
    RESUELTA = "resuelta", "Resuelta"
    DESCARTADA = "descartada", "Descartada"


class Prioridad(models.TextChoices):
    NORMAL = "normal", "Normal"
    URGENTE = "urgente", "Urgente"


class TipoAccion(models.TextChoices):
    BAJA_POLIZA = "baja_poliza", "Baja de póliza"
    AGREGAR_CONDUCTOR = "agregar_conductor", "Agregar conductor"
    MODIFICAR_POLIZA = "modificar_poliza", "Modificar póliza"
    REEMBOLSO = "reembolso", "Reembolso"
    APERTURA_SINIESTRO = "apertura_siniestro", "Apertura de siniestro"


class EstadoAccion(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    APROBADA = "aprobada", "Aprobada"
    RECHAZADA = "rechazada", "Rechazada"
    EJECUTADA = "ejecutada", "Ejecutada"


class Funcionario(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.TextField()
    email = models.TextField()
    rol = models.TextField(choices=Rol.choices)
    puede_aprobar = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "funcionarios"


class TipoSeguro(models.Model):
    id = models.SmallAutoField(primary_key=True)
    codigo = models.TextField()
    nombre = models.TextField()

    class Meta:
        managed = False
        db_table = "tipos_seguro"


class TipoConsulta(models.Model):
    id = models.SmallAutoField(primary_key=True)
    codigo = models.TextField()
    nombre = models.TextField()
    politica = models.TextField(choices=Politica.choices)

    class Meta:
        managed = False
        db_table = "tipos_consulta"


class Cliente(models.Model):
    id = models.BigAutoField(primary_key=True)
    dni = models.TextField()
    nombre = models.TextField()
    apellido = models.TextField()
    email = models.TextField(null=True)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "clientes"


class ContactoWhatsapp(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero = models.TextField()
    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="contactos",
    )
    nombre_perfil = models.TextField(null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "contactos_whatsapp"


class Poliza(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_poliza = models.TextField()
    cliente = models.ForeignKey(
        Cliente, on_delete=models.DO_NOTHING, related_name="polizas"
    )
    tipo_seguro = models.ForeignKey(TipoSeguro, on_delete=models.DO_NOTHING)
    cobertura = models.TextField(choices=Cobertura.choices)
    estado = models.TextField(
        choices=EstadoPoliza.choices, default=EstadoPoliza.VIGENTE
    )
    fecha_inicio = models.DateField()
    fecha_vencimiento = models.DateField()
    prima_mensual = models.DecimalField(max_digits=12, decimal_places=2)
    bien_asegurado = models.TextField(null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "polizas"


class ConductorPoliza(models.Model):
    id = models.BigAutoField(primary_key=True)
    poliza = models.ForeignKey(
        Poliza, on_delete=models.DO_NOTHING, related_name="conductores"
    )
    nombre = models.TextField()
    dni = models.TextField()
    relacion = models.TextField(choices=Relacion.choices)
    activo = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "conductores_poliza"


class Cuota(models.Model):
    id = models.BigAutoField(primary_key=True)
    poliza = models.ForeignKey(
        Poliza, on_delete=models.DO_NOTHING, related_name="cuotas"
    )
    periodo = models.DateField()
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    vencimiento = models.DateField()
    estado = models.TextField(
        choices=EstadoCuota.choices, default=EstadoCuota.PENDIENTE
    )
    fecha_pago = models.DateField(null=True)
    importe_pagado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True
    )

    class Meta:
        managed = False
        db_table = "cuotas"


class Siniestro(models.Model):
    id = models.BigAutoField(primary_key=True)
    numero_siniestro = models.TextField()
    poliza = models.ForeignKey(
        Poliza, on_delete=models.DO_NOTHING, related_name="siniestros"
    )
    consulta = models.ForeignKey(
        "ConsultaBot", on_delete=models.DO_NOTHING, null=True
    )
    fecha_ocurrencia = models.DateField()
    descripcion = models.TextField()
    estado = models.TextField(
        choices=EstadoSiniestro.choices, default=EstadoSiniestro.DENUNCIADO
    )
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "siniestros"


class Conversacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    contacto = models.ForeignKey(
        ContactoWhatsapp, on_delete=models.DO_NOTHING, related_name="conversaciones"
    )
    estado = models.TextField(
        choices=EstadoConversacion.choices, default=EstadoConversacion.ABIERTA
    )
    modo = models.TextField(
        choices=ModoConversacion.choices, default=ModoConversacion.BOT
    )
    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.DO_NOTHING, null=True, related_name="+"
    )
    ultimo_mensaje_cliente_en = models.DateTimeField(null=True)
    creada_en = models.DateTimeField(default=timezone.now)
    cerrada_en = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "conversaciones"


class Mensaje(models.Model):
    id = models.BigAutoField(primary_key=True)
    conversacion = models.ForeignKey(
        Conversacion, on_delete=models.DO_NOTHING, related_name="mensajes"
    )
    consulta = models.ForeignKey(
        "ConsultaBot",
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="mensajes",
    )
    direccion = models.TextField(choices=Direccion.choices)
    emisor = models.TextField(choices=Emisor.choices)
    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.DO_NOTHING, null=True, related_name="+"
    )
    texto = models.TextField()
    estado_envio = models.TextField(choices=EstadoEnvio.choices)
    wa_message_id = models.TextField(null=True)
    error = models.TextField(null=True)
    payload = models.JSONField(null=True)
    fecha_hora = models.DateTimeField(default=timezone.now)
    enviado_en = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "mensajes"


class ConsultaBot(models.Model):
    id = models.BigAutoField(primary_key=True)
    codigo_caso = models.TextField()
    fecha_hora = models.DateTimeField()
    contacto = models.ForeignKey(
        ContactoWhatsapp, on_delete=models.DO_NOTHING, null=True
    )
    conversacion = models.ForeignKey(
        Conversacion,
        on_delete=models.DO_NOTHING,
        null=True,
        related_name="consultas",
    )
    mensaje_usuario = models.TextField(null=True)
    respuesta_bot = models.TextField(null=True)
    tipo_consulta = models.ForeignKey(TipoConsulta, on_delete=models.DO_NOTHING)
    estado = models.TextField(
        choices=EstadoConsulta.choices,
        default=EstadoConsulta.PENDIENTE_REVISION,
    )
    funcionario_asignado = models.ForeignKey(
        Funcionario, on_delete=models.DO_NOTHING, null=True, related_name="+"
    )
    fecha_resolucion = models.DateField(null=True)
    revisado_por = models.ForeignKey(
        Funcionario, on_delete=models.DO_NOTHING, null=True, related_name="+"
    )
    revisado_en = models.DateTimeField(null=True)
    respuesta_corregida = models.TextField(null=True)
    nota_revision = models.TextField(null=True)
    notas_importacion = models.TextField(null=True)
    datos_origen = models.JSONField(null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "consultas_bot"


class Alerta(models.Model):
    id = models.BigAutoField(primary_key=True)
    consulta = models.ForeignKey(
        ConsultaBot, on_delete=models.DO_NOTHING, related_name="alertas"
    )
    mensaje = models.ForeignKey(
        Mensaje, on_delete=models.DO_NOTHING, null=True, related_name="alertas"
    )
    tipo = models.TextField(choices=TipoAlerta.choices)
    severidad = models.TextField(choices=Severidad.choices)
    descripcion = models.TextField()
    origen = models.TextField(
        choices=OrigenAlerta.choices, default=OrigenAlerta.AUTOMATICA
    )
    estado = models.TextField(
        choices=EstadoAlerta.choices, default=EstadoAlerta.ABIERTA
    )
    creada_en = models.DateTimeField(default=timezone.now)
    resuelta_por = models.ForeignKey(
        Funcionario, on_delete=models.DO_NOTHING, null=True, related_name="+"
    )
    resuelta_en = models.DateTimeField(null=True)
    resolucion = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "alertas"


class Derivacion(models.Model):
    id = models.BigAutoField(primary_key=True)
    consulta = models.ForeignKey(
        ConsultaBot, on_delete=models.DO_NOTHING, related_name="derivaciones"
    )
    derivado_a = models.ForeignKey(
        Funcionario,
        on_delete=models.DO_NOTHING,
        related_name="derivaciones",
    )
    prioridad = models.TextField(
        choices=Prioridad.choices, default=Prioridad.NORMAL
    )
    motivo = models.TextField()
    creada_en = models.DateTimeField(default=timezone.now)
    atendida_en = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "derivaciones"


class AccionPendiente(models.Model):
    id = models.BigAutoField(primary_key=True)
    consulta = models.ForeignKey(
        ConsultaBot, on_delete=models.DO_NOTHING, related_name="acciones"
    )
    poliza = models.ForeignKey(Poliza, on_delete=models.DO_NOTHING, null=True)
    tipo_accion = models.TextField(choices=TipoAccion.choices)
    parametros = models.JSONField(default=dict)
    estado = models.TextField(
        choices=EstadoAccion.choices, default=EstadoAccion.PENDIENTE
    )
    solicitada_en = models.DateTimeField(default=timezone.now)
    resuelta_por = models.ForeignKey(
        Funcionario, on_delete=models.DO_NOTHING, null=True, related_name="+"
    )
    resuelta_en = models.DateTimeField(null=True)
    motivo = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "acciones_pendientes"


class VPolizaResumen(models.Model):
    poliza = models.OneToOneField(
        Poliza,
        on_delete=models.DO_NOTHING,
        db_column="poliza_id",
        primary_key=True,
    )
    numero_poliza = models.TextField()
    cliente = models.TextField()
    dni = models.TextField()
    tipo_seguro = models.TextField()
    cobertura = models.TextField()
    estado = models.TextField()
    fecha_vencimiento = models.DateField()
    saldo_pendiente = models.DecimalField(max_digits=12, decimal_places=2)
    proximo_vencimiento_pago = models.DateField(null=True)

    class Meta:
        managed = False
        db_table = "v_polizas_resumen"

    def save(self, *args, **kwargs):
        raise TypeError("Es una vista de solo lectura")

    def delete(self, *args, **kwargs):
        raise TypeError("Es una vista de solo lectura")


class VConsultaSupervision(models.Model):
    id = models.BigIntegerField(primary_key=True)
    codigo_caso = models.TextField()
    fecha_hora = models.DateTimeField()
    whatsapp = models.TextField(null=True)
    cliente = models.TextField(null=True)
    tipo_consulta = models.TextField()
    politica = models.TextField()
    mensaje_usuario = models.TextField(null=True)
    respuesta_bot = models.TextField(null=True)
    estado = models.TextField()
    funcionario_asignado = models.TextField(null=True)
    alertas_abiertas = models.BigIntegerField()
    severidad_maxima = models.TextField(null=True)
    color = models.TextField()
    cerrado_con_alerta = models.BooleanField()
    revisada = models.BooleanField()

    class Meta:
        managed = False
        db_table = "v_consultas_supervision"

    def save(self, *args, **kwargs):
        raise TypeError("Es una vista de solo lectura")

    def delete(self, *args, **kwargs):
        raise TypeError("Es una vista de solo lectura")


class VBandejaConversacion(models.Model):
    conversacion_id = models.BigIntegerField(primary_key=True)
    whatsapp = models.TextField()
    cliente = models.TextField(null=True)
    estado = models.TextField()
    modo = models.TextField()
    atendida_por = models.TextField(null=True)
    ultimo_mensaje = models.TextField(null=True)
    ultimo_emisor = models.TextField(null=True)
    ultimo_mensaje_en = models.DateTimeField(null=True)
    alertas_abiertas = models.BigIntegerField()
    respuestas_retenidas = models.BigIntegerField()
    ventana_24h_abierta = models.BooleanField(null=True)

    class Meta:
        managed = False
        db_table = "v_bandeja_conversaciones"

    def save(self, *args, **kwargs):
        raise TypeError("Es una vista de solo lectura")

    def delete(self, *args, **kwargs):
        raise TypeError("Es una vista de solo lectura")
