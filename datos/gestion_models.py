from django.db import models
from django.utils import timezone
from datos.models import Cliente, Funcionario, Interesado, ContactoWhatsapp, Poliza, Cuota, Mensaje

class ConfigGestion(models.Model):
    id=models.SmallIntegerField(primary_key=True)
    automaticos=models.BooleanField(default=False)
    class Meta:
        managed=False
        db_table='gestion_config'

class NotaInterna(models.Model):
    cliente=models.ForeignKey(Cliente,on_delete=models.DO_NOTHING)
    autor=models.ForeignKey(Funcionario,on_delete=models.DO_NOTHING)
    texto=models.TextField()
    creada_en=models.DateTimeField(default=timezone.now)
    class Meta:
        managed=False
        db_table='gestion_notas'

class Tarea(models.Model):
    titulo=models.TextField()
    detalle=models.TextField(default='')
    cliente=models.ForeignKey(Cliente,null=True,on_delete=models.DO_NOTHING)
    interesado=models.ForeignKey(Interesado,null=True,on_delete=models.DO_NOTHING)
    asignada_a=models.ForeignKey(Funcionario,on_delete=models.DO_NOTHING,related_name='+')
    creada_por=models.ForeignKey(Funcionario,on_delete=models.DO_NOTHING,related_name='+')
    vence=models.DateField()
    estado=models.TextField(default='pendiente')
    creada_en=models.DateTimeField(default=timezone.now)
    completada_en=models.DateTimeField(null=True)
    class Meta:
        managed=False
        db_table='gestion_tareas'

class AvisoGestion(models.Model):
    encuesta=models.ForeignKey('Encuesta',null=True,on_delete=models.DO_NOTHING)
    clave=models.TextField(unique=True)
    tipo=models.TextField()
    contacto=models.ForeignKey(ContactoWhatsapp,on_delete=models.DO_NOTHING)
    poliza=models.ForeignKey(Poliza,null=True,on_delete=models.DO_NOTHING)
    cuota=models.ForeignKey(Cuota,null=True,on_delete=models.DO_NOTHING)
    interesado=models.ForeignKey(Interesado,null=True,on_delete=models.DO_NOTHING)
    estado=models.TextField(default='pendiente')
    mensaje=models.OneToOneField(Mensaje,null=True,on_delete=models.DO_NOTHING)
    resuelto_por=models.ForeignKey(Funcionario,null=True,on_delete=models.DO_NOTHING)
    creado_en=models.DateTimeField(default=timezone.now)
    resuelto_en=models.DateTimeField(null=True)
    class Meta:
        managed=False
        db_table='gestion_avisos'

class PerfilCliente(models.Model):
    cliente=models.OneToOneField(Cliente,primary_key=True,on_delete=models.DO_NOTHING)
    nacimiento=models.DateField(null=True)
    comerciales=models.BooleanField(default=False)
    class Meta:
        managed=False
        db_table='gestion_perfiles'

class Renovacion(models.Model):
    origen=models.OneToOneField(Poliza,on_delete=models.DO_NOTHING,related_name='gestion_renovada')
    nueva=models.OneToOneField(Poliza,on_delete=models.DO_NOTHING,related_name='gestion_origen')
    responsable=models.ForeignKey(Funcionario,on_delete=models.DO_NOTHING)
    creada_en=models.DateTimeField(default=timezone.now)
    class Meta:
        managed=False
        db_table='gestion_renovaciones'

class Referido(models.Model):
    referente=models.ForeignKey(Cliente,on_delete=models.DO_NOTHING,related_name='+')
    referido=models.OneToOneField(Cliente,on_delete=models.DO_NOTHING,related_name='+')
    beneficio=models.TextField(default='')
    estado=models.TextField(default='pendiente')
    responsable=models.ForeignKey(Funcionario,on_delete=models.DO_NOTHING)
    creado_en=models.DateTimeField(default=timezone.now)
    class Meta:
        managed=False
        db_table='gestion_referidos'

class Encuesta(models.Model):
    cliente=models.ForeignKey(Cliente,null=True,on_delete=models.DO_NOTHING)
    contacto=models.ForeignKey(ContactoWhatsapp,on_delete=models.DO_NOTHING)
    referencia=models.TextField(unique=True)
    puntaje=models.SmallIntegerField(null=True)
    creada_en=models.DateTimeField(default=timezone.now)
    respondida_en=models.DateTimeField(null=True)
    class Meta:
        managed=False
        db_table='gestion_encuestas'
