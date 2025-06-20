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
        return self.nombre

class Empleado(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    cedula = models.CharField(max_length=10, unique=True)
    email = models.EmailField(max_length=254)
    activo = models.BooleanField(default=True) #type:ignore
    historial = HistoricalRecords()

    
    def __str__(self):
        return self.user.username  #type:ignore

class Role(models.Model):
    nombre = models.CharField(max_length=50)
    historial = HistoricalRecords()
    
    def __str__(self):
        return self.nombre

class EmpleadoRole(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.user.username} - {self.role.nombre}" #type:ignore

class Sala(models.Model):
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True) #type:ignore
    historial = HistoricalRecords()
    
    def __str__(self):
        return self.nombre

class CompetenciaEmpleado(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.user.username} - {self.sala.nombre}" #type:ignore

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
        return f"{self.empleado.user.username} - {self.restriccion.nombre}" #type:ignore

class SancionEmpleado(models.Model):
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    motivo = models.TextField()
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_supervisor')
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.user.username} - {self.fecha_inicio}" #type:ignore

