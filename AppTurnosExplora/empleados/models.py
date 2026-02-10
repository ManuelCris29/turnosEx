from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from simple_history.models import HistoricalRecords



class Jornada(models.Model):
    """Modelo para representar las jornadas de trabajo (AM, PM)."""
    nombre = models.CharField(max_length=5)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Jornada'
        verbose_name_plural = 'Jornadas'
        ordering = ['nombre']
    
    def __str__(self):
        return str(self.nombre)

class Empleado(models.Model):
    """Modelo principal para representar empleados/exploradores del sistema."""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=50)
    apellido = models.CharField(max_length=50)
    cedula = models.CharField(max_length=10, unique=True)
    email = models.EmailField(max_length=254)
    activo = models.BooleanField(default=True) #type:ignore
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='empleados_supervisados')
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'
        ordering = ['apellido', 'nombre']
        indexes = [
            models.Index(fields=['activo'], name='empleado_activo_idx'),
            models.Index(fields=['supervisor', 'activo'], name='empleado_super_activo_idx'),
        ]
    
    def __str__(self):
        return f"{self.nombre} {self.apellido} ({self.user.username})"
    
    def notificaciones_no_leidas_count(self):
        """Retorna el número de notificaciones no leídas"""
        return self.notificaciones.filter(leida=False).count()

class Role(models.Model):
    """Modelo para representar roles de empleados (ej: supervisor, explorador)."""
    nombre = models.CharField(max_length=50)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Rol'
        verbose_name_plural = 'Roles'
        ordering = ['nombre']
    
    def __str__(self):
        return str(self.nombre)

class EmpleadoRole(models.Model):
    """Modelo intermedio para la relación muchos a muchos entre Empleado y Role."""
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Rol de Empleado'
        verbose_name_plural = 'Roles de Empleados'
        ordering = ['empleado', 'role']
        unique_together = [['empleado', 'role']]
        indexes = [
            models.Index(fields=['empleado', 'role'], name='empleado_role_comp_idx'),
        ]
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.role.nombre}"

class Sala(models.Model):
    """Modelo para representar las salas del Parque Explora."""
    nombre = models.CharField(max_length=50)
    activo = models.BooleanField(default=True) #type:ignore
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Sala'
        verbose_name_plural = 'Salas'
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['activo'], name='sala_activo_idx'),
        ]
    
    def __str__(self):
        return str(self.nombre)

class CompetenciaEmpleado(models.Model):
    """Modelo para representar las competencias de empleados en salas específicas."""
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Competencia de Empleado'
        verbose_name_plural = 'Competencias de Empleados'
        ordering = ['empleado', 'sala']
        unique_together = [['empleado', 'sala']]
        indexes = [
            models.Index(fields=['empleado', 'sala'], name='comp_emp_sala_idx'),
        ]
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.sala.nombre}"

class AsignacionSalaPeriodo(models.Model):
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    creado_en = models.DateTimeField(auto_now_add=True)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = "Asignación de Sala por Período"
        verbose_name_plural = "Asignaciones de Sala por Períodos"
        ordering = ['fecha_inicio', 'empleado']
    
    def __str__(self):
        return f"{self.empleado.nombre} - {self.sala.nombre} ({self.fecha_inicio} a {self.fecha_fin})"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Validar que el empleado tenga competencia en la sala
        if not CompetenciaEmpleado.objects.filter(
            empleado=self.empleado,
            sala=self.sala
        ).exists():
            raise ValidationError(f"{self.empleado.nombre} no tiene competencia en {self.sala.nombre}")
        
        # Validar que no haya solapamientos
        solapamientos = AsignacionSalaPeriodo.objects.filter(
            empleado=self.empleado,
            activo=True,
            fecha_inicio__lte=self.fecha_fin,
            fecha_fin__gte=self.fecha_inicio
        ).exclude(id=self.id)
        
        if solapamientos.exists():
            raise ValidationError(f"Ya existe una asignación para {self.empleado.nombre} en ese período")

class RestriccionEmpleado(models.Model):
    """Modelo para representar restricciones temporales de empleados."""
    empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    recomendacion = models.TextField()
    tipo_restriccion = models.CharField(max_length=50)
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Restricción de Empleado'
        verbose_name_plural = 'Restricciones de Empleados'
        ordering = ['-fecha_inicio', 'empleado']
        indexes = [
            models.Index(fields=['empleado', 'fecha_inicio'], name='rest_emp_fecha_idx'),
            models.Index(fields=['tipo_restriccion'], name='rest_tipo_idx'),
        ]
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')
    
    def __str__(self):
        return f"{self.empleado.nombre} {self.empleado.apellido} - {self.tipo_restriccion}"

class SancionEmpleado(models.Model):
    """Modelo para representar sanciones aplicadas a empleados."""
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_explorador')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    motivo = models.TextField()
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    supervisor = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='sanciones_supervisor')
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Sanción de Empleado'
        verbose_name_plural = 'Sanciones de Empleados'
        ordering = ['-fecha_inicio', 'explorador']
        indexes = [
            models.Index(fields=['explorador', 'fecha_inicio'], name='sanc_exp_fecha_idx'),
            models.Index(fields=['supervisor'], name='sanc_supervisor_idx'),
        ]
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')
        if self.explorador == self.supervisor:
            raise ValidationError('Un empleado no puede sancionarse a sí mismo.')
    
    def __str__(self):
        return f"{self.explorador.nombre} {self.explorador.apellido} - {self.fecha_inicio} supervisado por {self.supervisor.nombre} {self.supervisor.apellido}"

