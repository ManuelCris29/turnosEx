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





# Create your models here.
