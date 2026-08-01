from django.db import models
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from simple_history.models import HistoricalRecords


class PDH(models.Model):
    """Pago de Horas (PDH): descuento de horas del consolidado autorizado por un supervisor."""
    explorador=models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='permisos_explorador')
    # Opcional: un Pago de Horas no necesariamente se ata a una solicitud puntual.
    solicitud=models.ForeignKey(SolicitudCambio, on_delete=models.CASCADE, related_name='permisos_solicitud', null=True, blank=True)
    fecha=models.DateField(help_text='Fecha en que se paga la hora')
    horas=models.DecimalField(max_digits=5, decimal_places=2, help_text='Horas pagadas (se descuentan del consolidado)')
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='supervisor_pdh', help_text='Supervisor/líder que autoriza el pago')
    # 'pago_horas' = descuento de horas autorizado por un supervisor (ledger de pagos).
    tipo_registro=models.CharField(max_length=50, default='pago_horas')
    comentario=models.TextField(null=True, blank=True)
    # Deudas concretas que este pago salda (las horas del PDH = suma de estas deudas).
    deudas_pagadas = models.ManyToManyField('solicitudes.DeudaCorporativa', blank=True,
                                            related_name='pdhs_pago',
                                            help_text='Dobladas (0.5 h c/u) que paga este registro.')
    permisos_pagados = models.ManyToManyField('permisos.PermisoEspecial', blank=True,
                                              related_name='pdhs_pago',
                                              help_text='Permisos aprobados que paga este registro.')
    historial=HistoricalRecords()
    
    class Meta:
        verbose_name = 'PDH'
        verbose_name_plural = 'PDHs'
        ordering = ['-fecha', 'explorador']
        indexes = [
            models.Index(fields=['explorador', 'fecha'], name='pdh_exp_fecha_idx'),
            models.Index(fields=['solicitud'], name='pdh_solicitud_idx'),
            models.Index(fields=['fecha'], name='pdh_fecha_idx'),
        ]
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.horas <= 0:
            raise ValidationError('Las horas deben ser mayores a cero.')
        if self.horas > 24:
            raise ValidationError('Las horas no pueden ser mayores a 24.')
    
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
        ('MEDIA_JORNADA_TEMPORADA', 'Media jornada temporada (compensada)'),
        ('OTRO', 'Otro'),
    ]
    
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='permisos_especiales')
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default='PERSONAL')
    # Permanente: se repite en días fijos de la semana dentro de un rango.
    es_permanente = models.BooleanField(default=False, help_text='True si es un permiso permanente (días fijos de la semana).')
    fecha_inicio = models.DateField(help_text='Permiso normal: el día. Permanente: inicio del rango.')
    fecha_fin = models.DateField(help_text='Permiso normal: igual que inicio. Permanente: fin del rango.')
    # Días de la semana para permanente (0=lunes .. 6=domingo), separados por coma. Ej: "1,2"
    dias_semana = models.CharField(max_length=20, blank=True, default='',
                                   help_text='Permanente: días de la semana (0=lun..6=dom) separados por coma.')
    tiempo = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                 help_text='Horas solicitadas por ocurrencia (se acumulan a la deuda del explorador).')
    especificacion = models.CharField(max_length=120, blank=True, default='',
                                      help_text='Ej: "Entrada 1:30 pm" / "Salida 5:00 pm".')
    cubre = models.ForeignKey(Empleado, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name='permisos_que_cubre',
                              help_text='Compañero que cubre el hueco (opcional).')
    motivo = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='PENDIENTE')
    # Pago de la deuda generada por este permiso (se salda vía PDH, igual que las dobladas).
    pagado = models.BooleanField(default=False, help_text='True si la deuda de este permiso ya fue pagada (PDH).')
    fecha_pago = models.DateField(null=True, blank=True, help_text='Fecha en que se pagó la deuda de este permiso.')
    supervisor = models.ForeignKey(Empleado, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='permisos_supervisor',
                                   help_text='Supervisor que aprueba/rechaza.')
    comentario_supervisor = models.TextField(null=True, blank=True)
    # --- Solo tipo MEDIA_JORNADA_TEMPORADA (día completo de temporada partido en dos) ---
    jornada_trabaja = models.CharField(
        max_length=2, choices=[('AM', 'AM'), ('PM', 'PM')], null=True, blank=True,
        help_text='Media jornada temporada: jornada que trabajará en su día completo (fecha_inicio). '
                  'La otra media se trabaja en fecha_compensacion. Sin deuda (tiempo=0).'
    )
    fecha_compensacion = models.DateField(
        null=True, blank=True,
        help_text='Media jornada temporada: día de descanso de la MISMA semana donde trabaja '
                  'la media jornada restante.'
    )
    snapshot_turnos_previos = models.JSONField(
        null=True, blank=True,
        help_text='Turnos previos del empleado en fecha_inicio y fecha_compensacion antes de aplicar '
                  'el permiso aprobado (mismo formato que DobladaDetalle). Permite revertir.'
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.tipo} ({self.fecha_inicio} a {self.fecha_fin})"

    def dias_semana_legible(self):
        """Nombres de los días de la semana del permiso permanente."""
        nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        dias = [int(d) for d in self.dias_semana.split(',') if d.strip().isdigit()]
        return ', '.join(nombres[d] for d in sorted(dias) if 0 <= d <= 6)

    def horas_totales(self):
        """
        Horas que este permiso acumula a la deuda del explorador.
        - Normal: el tiempo solicitado.
        - Permanente: tiempo × número de ocurrencias (días de la semana en el rango).
        """
        if not self.es_permanente:
            return float(self.tiempo or 0)
        from datetime import timedelta
        dias = {int(d) for d in self.dias_semana.split(',') if d.strip().isdigit()}
        if not dias:
            return 0.0
        n, d = 0, self.fecha_inicio
        while d <= self.fecha_fin:
            if d.weekday() in dias:
                n += 1
            d += timedelta(days=1)
        return round(float(self.tiempo or 0) * n, 2)

    class Meta:
        verbose_name = "Permiso Especial"
        verbose_name_plural = "Permisos Especiales"
        ordering = ['-fecha_inicio', 'empleado']
        indexes = [
            models.Index(fields=['empleado', 'estado'], name='perm_esp_emp_estado_idx'),
            models.Index(fields=['estado'], name='perm_esp_estado_idx'),
            models.Index(fields=['fecha_inicio'], name='perm_esp_fecha_idx'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        # En el form puntual, fecha_inicio/fecha_fin se asignan en la vista (no son campos),
        # por lo que pueden estar vacíos al validar el ModelForm.
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')





# Create your models here.
