from django.db import models
from empleados.models import Empleado
from turnos.models import Turno
from django.utils import timezone
from simple_history.models import HistoricalRecords

class TipoSolicitudCambio(models.Model):
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True) #type:ignore
    genera_deuda = models.BooleanField(default=False, help_text='¿Este tipo de solicitud genera deuda de horas?')
    historial = HistoricalRecords()

    def __str__(self):
        return self.nombre

class SolicitudCambio(models.Model):
    explorador_solicitante = models.ForeignKey(
        Empleado, related_name='solicitudes_enviadas', on_delete=models.CASCADE
    )
    explorador_receptor = models.ForeignKey(
        Empleado, related_name='solicitudes_recibidas', on_delete=models.CASCADE
    )
    tipo_cambio = models.ForeignKey('TipoSolicitudCambio', on_delete=models.CASCADE)
    estado = models.CharField(
        max_length=20,
        choices=[
            ('pendiente', 'Pendiente'),
            ('aprobada', 'Aprobada'),
            ('rechazada', 'Rechazada'),
            ('pagada', 'Pagada'),
        ],
        default='pendiente'
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)
    comentario = models.TextField(null=True, blank=True)
    aprobado_receptor = models.BooleanField(default=False)
    fecha_aprobacion_receptor = models.DateTimeField(null=True, blank=True)
    aprobado_supervisor = models.BooleanField(default=False)
    fecha_aprobacion_supervisor = models.DateTimeField(null=True, blank=True)
    turno_origen = models.ForeignKey(
        'turnos.Turno', related_name='solicitud_origen', null=True, blank=True, on_delete=models.SET_NULL
    )
    turno_destino = models.ForeignKey(
        'turnos.Turno', related_name='solicitud_destino', null=True, blank=True, on_delete=models.SET_NULL
    )
    solicitud_origen = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='transferencias'
    )
    historial = HistoricalRecords()

    def __str__(self):
        return f"{self.tipo_cambio.descripcion} - {self.explorador_solicitante} a {self.explorador_receptor} ({self.fecha_solicitud.date()})"

class CambioPermanenteDetalle(models.Model):
    solicitud=models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='cambio_permanente')
    fecha_inicio=models.DateField()
    fecha_fin=models.DateField(null=True, blank=True)
    historial=HistoricalRecords()

class PermisoDetalle(models.Model):
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='permiso')
    horas_solicitadas = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    fecha_pago = models.DateField(null=True, blank=True)  # <-- NUEVO
    historial = HistoricalRecords()

    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud} - horas: {self.horas_solicitadas}" #type:ignore

class DobladaDetalle(models.Model):
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='doblada')
    minutos_deuda = models.IntegerField(default=30)
    fecha_pago = models.DateField(null=True, blank=True)  # <-- NUEVO
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud}" #type:ignore


# Create your models here.
