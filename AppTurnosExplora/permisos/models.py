from django.db import models
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from simple_history.models import HistoricalRecords


class PDH(models.Model):
    explorador=models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='permisos_explorador')
    solicitud=models.ForeignKey(SolicitudCambio, on_delete=models.CASCADE, related_name='permisos_solicitud')
    fecha=models.DateField()
    horas=models.DecimalField(max_digits=5, decimal_places=2)
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='supervisor_pdh')
    tipo_registro=models.CharField(max_length=50, default='pdh')
    comentario=models.TextField(null=True, blank=True)
    historial=HistoricalRecords()
    
    def __str__(self):
        return f"explorador: {self.explorador.user.username} - fecha: {self.fecha} - horas: {self.horas}" #type:ignore


class PermisoEspecial(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    TIPO_CHOICES = [
        ('MEDICO', 'Médico'),
        ('PERSONAL', 'Personal'),
        ('FAMILIAR', 'Familiar'),
        ('OTRO', 'Otro'),
    ]
    
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='permisos_especiales')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='permisos_supervisor')
    comentario_supervisor = models.TextField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.tipo} ({self.fecha_inicio} a {self.fecha_fin})"
    
    class Meta:
        verbose_name = "Permiso Especial"
        verbose_name_plural = "Permisos Especiales"





# Create your models here.
