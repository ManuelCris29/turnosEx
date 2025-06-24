from django.db import models
from empleados.models import Empleado
from turnos.models import Turno
from django.utils import timezone
from simple_history.models import HistoricalRecords

class TipoSolicitudCambio(models.Model):
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True) #type:ignore
    historial = HistoricalRecords()

    def __str__(self):
        return self.nombre

class SolicitudCambio(models.Model):
    explorador_solicitante= models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='solicitudes_explorador_solicitante')
    explorador_receptor= models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='solicitudes_explorador_destino')
    tipo_cambio= models.ForeignKey(TipoSolicitudCambio, on_delete=models.CASCADE)
    estado= models.CharField(max_length=50, default='pendiente')
    fecha_solicitud= models.DateTimeField(default=timezone.now)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    turno_origen= models.ForeignKey(Turno, on_delete=models.CASCADE, related_name='solicitudes_turno_origen')
    turno_destino= models.ForeignKey(Turno, on_delete=models.CASCADE, related_name='solicitudes_turno_destino')
    comentario=models.TextField(null=True, blank=True)
    historial= HistoricalRecords()

    def __str__(self):
        return f" solicitante: {self.explorador_solicitante.user.username} - solicitado: {self.explorador_receptor.user.username} - {self.tipo_cambio.nombre}" #type:ignore

class CambioPermanenteDetalle(models.Model):
    solicitud=models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='cambio_permanente')
    fecha_inicio=models.DateField()
    fecha_fin=models.DateField(null=True, blank=True)
    historial=HistoricalRecords()

class PermisoDetalle(models.Model):
    solicitud=models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='permiso')
    horas_solicitadas=models.DecimalField(max_digits=5, decimal_places=2, default=0)
    historial=HistoricalRecords()

    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud} - horas: {self.horas_solicitadas}" #type:ignore

class DobladaDetalle(models.Model):
    solicitud=models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='doblada')
    minutos_deuda=models.IntegerField(default=30) #type:ignore
    historial=HistoricalRecords()
    
    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud}" #type:ignore


# Create your models here.
