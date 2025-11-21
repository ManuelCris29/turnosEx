from django.db import models
from empleados.models import Empleado
from turnos.models import Turno
from django.utils import timezone
from simple_history.models import HistoricalRecords

class Notificacion(models.Model):
    TIPOS_CHOICES = [
        ('solicitud_cambio', 'Solicitud de Cambio'),
        ('solicitud_doblada', 'Solicitud de Doblada'),
        ('solicitud_permiso', 'Solicitud de Permiso'),
        ('aprobacion', 'Aprobación'),
        ('rechazo', 'Rechazo'),
    ]
    
    destinatario = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='notificaciones')
    tipo = models.CharField(max_length=20, choices=TIPOS_CHOICES)
    titulo = models.CharField(max_length=200)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_lectura = models.DateTimeField(null=True, blank=True)
    solicitud = models.ForeignKey('SolicitudCambio', on_delete=models.CASCADE, null=True, blank=True)
    
    class Meta:
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"{self.titulo} - {self.destinatario.nombre} {self.destinatario.apellido}"

class TipoSolicitudCambio(models.Model):
    nombre = models.CharField(max_length=50)
    codigo_estrategia = models.CharField(
        max_length=50, 
        null=True, 
        blank=True,
        help_text='Código para mapear a la estrategia. Si está vacío, se usa el nombre normalizado. Ejemplos: "CT", "DOBLADA", "CT PERMANENTE"'
    )
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
            ('cancelada', 'Cancelada'),
            ('pagada', 'Pagada'),
        ],
        default='pendiente'
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_cambio_turno = models.DateField(null=True, blank=True, help_text='Fecha para la cual se solicita el cambio de turno')
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

    class Meta:
        # FASE 1.10: Índices críticos para rendimiento con 100+ solicitudes/día
        # FASE 3.1: Agregar índices adicionales para optimizar consultas de turnos
        indexes = [
            # Búsqueda por receptor y fecha (más común - para First-Come, First-Served)
            models.Index(
                fields=['explorador_receptor', 'fecha_cambio_turno', 'estado'],
                name='sol_receptor_fecha_estado_idx'  # Máximo 30 caracteres
            ),
            # FASE 3.1: Índice para búsqueda por turno_origen (usado en MisTurnosPorMesView)
            models.Index(
                fields=['turno_origen', 'estado'],
                name='sol_turno_origen_estado_idx'
            ),
            # FASE 3.1: Índice para búsqueda por turno_destino (usado en MisTurnosPorMesView)
            models.Index(
                fields=['turno_destino', 'estado'],
                name='sol_turno_destino_estado_idx'
            ),
            # FASE 3.1: Índice para búsqueda por fecha_resolucion (para ordenar por más reciente)
            models.Index(
                fields=['-fecha_resolucion', 'estado'],
                name='sol_fecha_resol_estado_idx'
            ),
        ]
        ordering = ['-fecha_solicitud']

    def __str__(self):
        return f"{self.tipo_cambio.nombre} - {self.explorador_solicitante} a {self.explorador_receptor} ({self.fecha_cambio_turno})"

class CambioPermanenteDetalle(models.Model):
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='cambio_permanente')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    historial = HistoricalRecords()

    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud} - horas: {self.horas_solicitadas}" #type:ignore


class CambioPermanenteDia(models.Model):
    """
    Modelo para almacenar los días específicos o días de la semana seleccionados
    para un cambio permanente.
    
    Permite dos tipos de selección:
    - fecha_especifica: Días específicos (ej: 23 nov, 27 nov, 3 dic)
    - dia_semana: Días de la semana (ej: todos los martes, todos los jueves)
    
    Si no hay registros en esta tabla, se usa el rango completo (comportamiento retrocompatible).
    """
    TIPO_CHOICES = [
        ('fecha_especifica', 'Fecha Específica'),
        ('dia_semana', 'Día de Semana'),
    ]
    
    cambio_permanente = models.ForeignKey(
        CambioPermanenteDetalle, 
        on_delete=models.CASCADE, 
        related_name='dias'
    )
    fecha_especifica = models.DateField(
        null=True, 
        blank=True,
        help_text='Fecha específica seleccionada (ej: 23 de noviembre)'
    )
    dia_semana = models.IntegerField(
        null=True, 
        blank=True,
        choices=[
            (0, 'Lunes'),
            (1, 'Martes'),
            (2, 'Miércoles'),
            (3, 'Jueves'),
            (4, 'Viernes'),
            (5, 'Sábado'),
            (6, 'Domingo'),
        ],
        help_text='Día de la semana (0=Lunes, 6=Domingo)'
    )
    tipo = models.CharField(
        max_length=20, 
        choices=TIPO_CHOICES,
        help_text='Tipo de selección: fecha específica o día de semana'
    )
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Día de Cambio Permanente'
        verbose_name_plural = 'Días de Cambio Permanente'
        indexes = [
            models.Index(fields=['cambio_permanente', 'tipo'], name='camb_perm_dia_camb_tipo_idx'),
            models.Index(fields=['fecha_especifica'], name='camb_perm_dia_fecha_idx'),
            models.Index(fields=['dia_semana'], name='camb_perm_dia_dia_sem_idx'),
        ]
        # Asegurar que cada tipo tenga solo un valor no nulo
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(tipo='fecha_especifica', fecha_especifica__isnull=False, dia_semana__isnull=True) |
                    models.Q(tipo='dia_semana', dia_semana__isnull=False, fecha_especifica__isnull=True)
                ),
                name='camb_perman_dia_tipo_valido'
            ),
        ]
    
    def __str__(self):
        if self.tipo == 'fecha_especifica' and self.fecha_especifica:
            return f"Fecha específica: {self.fecha_especifica}"
        elif self.tipo == 'dia_semana' and self.dia_semana is not None:
            dias_semana_nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            return f"Día de semana: {dias_semana_nombres[self.dia_semana]}"
        return f"Día de cambio permanente (ID: {self.id})"

class DobladaDetalle(models.Model):
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='doblada')
    minutos_deuda = models.IntegerField(default=30)
    fecha_pago = models.DateField(null=True, blank=True)  # <-- NUEVO
    historial = HistoricalRecords()
    
    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud}" #type:ignore


# Create your models here.
