from django.db import models
from empleados.models import Empleado, Jornada, Sala, CompetenciaEmpleado, RestriccionEmpleado, SancionEmpleado
from simple_history.models import HistoricalRecords


class AsignarJornadaExplorador(models.Model):
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    jornada = models.ForeignKey(Jornada, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    historial = HistoricalRecords()

    def __str__(self):
        return f"{self.explorador.user.username} - {self.jornada.nombre}" #type:ignore

class AsignarSalaExplorador(models.Model):
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    historial = HistoricalRecords()

    def __str__(self):
        return f"{self.explorador.user.username} - {self.sala.nombre}" #type:ignore

class Turno(models.Model):
    explorador= models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha= models.DateField()
    jornada= models.ForeignKey(Jornada, on_delete=models.CASCADE)
    sala= models.ForeignKey(Sala, on_delete=models.CASCADE)
    tipo_cambio= models.CharField(max_length=50, null=True, blank=True)
    historial= HistoricalRecords()

    def __str__(self):
        return f"{self.explorador.user.username} - {self.fecha}" #type:ignore
    
class DiaEspecial(models.Model):
    fecha= models.DateField()
    tipo = models.CharField(max_length=50)
    descripcion = models.TextField(null=True, blank=True)
    recurrente = models.BooleanField(default=False) #type:ignore
    activo = models.BooleanField(default=True) #type:ignore
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    historial= HistoricalRecords()
    
    def __str__(self):
        return f"{self.fecha}" #type:ignore
    






# Create your models here.
