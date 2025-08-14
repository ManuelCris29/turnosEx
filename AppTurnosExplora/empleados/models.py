from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from simple_history.models import HistoricalRecords



class Jornada(models.Model):
    nombre = models.CharField(max_length=5)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    historial = HistoricalRecords()
    
    def __str__(self):
        return str(self.nombre)

class Empleado(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    cedula = models.CharField(max_length=10, unique=True)
    email = models.EmailField(max_length=254)
    activo = models.BooleanField(default=True) #type:ignore
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados_supervisados')
    historial = HistoricalRecords()

    
    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.user.username})"
    
    def notificaciones_no_leidas_count(self):
        """Retorna el número de notificaciones no leídas"""
        return self.notificaciones.filter(leida=False).count()

class Role(models.Model):
    nombre = models.CharField(max_length=50)
    historial = HistoricalRecords()
    
    def __str__(self):
        return str(self.nombre)

class EmpleadoRole(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.role.nombre}"

class Sala(models.Model):
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True) #type:ignore
    historial = HistoricalRecords()
    
    def __str__(self):
        return str(self.nombre)

class CompetenciaEmpleado(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.sala.nombre}"

class RestriccionEmpleado(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    recomendacion = models.TextField()
    tipo_restriccion = models.CharField(max_length=50)
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.tipo_restriccion}"

class SancionEmpleado(models.Model):
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_explorador')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    motivo = models.TextField()
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_supervisor')
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.explorador.nombre} {self.explorador.apellido} - {self.fecha_inicio} supervisado por {self.supervisor.nombre} {self.supervisor.apellido}"

