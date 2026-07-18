from django.db import models
from empleados.models import Empleado, Jornada, Sala, CompetenciaEmpleado, RestriccionEmpleado, SancionEmpleado
from simple_history.models import HistoricalRecords


class AsignarJornadaExplorador(models.Model):
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    jornada = models.ForeignKey(Jornada, on_delete=models.CASCADE)
    fecha_inicio = models.DateField()
    # fecha_fin removido - las jornadas son indefinidas por defecto
    historial = HistoricalRecords()

    class Meta:
        # FASE 1.11: Índice para búsquedas por explorador y fecha_inicio
        # CRÍTICO para rendimiento al obtener jornadas predeterminadas
        indexes = [
            models.Index(fields=['explorador', 'fecha_inicio'], name='jornada_explorador_fecha_idx'),
        ]
        ordering = ['explorador', '-fecha_inicio']

    def __str__(self):
        return f"{self.explorador.user.username} - {self.jornada.nombre}" #type:ignore

class TurnoActivoManager(models.Manager):
    """Manager por defecto de Turno: excluye los ANULADOS (soft-delete).

    Así todas las lecturas activas del sistema (estado_dia/estado_mes, Mis Turnos,
    consolidado, reportes operativos) ignoran los turnos anulados por reprogramación
    SIN tener que filtrar en cada consulta. Para auditoría/reportes históricos que sí
    deben ver los anulados, usar `Turno.all_objects`.
    """
    def get_queryset(self):
        return super().get_queryset().filter(anulado=False)


class Turno(models.Model):
    explorador= models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha= models.DateField()
    jornada= models.ForeignKey(Jornada, on_delete=models.CASCADE)
    sala= models.ForeignKey(Sala, on_delete=models.CASCADE)
    tipo_cambio= models.CharField(max_length=50, null=True, blank=True)
    # Soft-delete auditable: un turno anulado NO se borra físicamente (queda para el
    # historial/estadística), pero no cuenta como turno activo (ni como falta, ni genera deuda).
    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.CharField(max_length=200, null=True, blank=True)
    historial= HistoricalRecords()

    # `objects` excluye anulados (lecturas activas); `all_objects` los incluye (auditoría/admin).
    objects = TurnoActivoManager()
    all_objects = models.Manager()

    class Meta:
        # FASE 1.9: Índice compuesto para búsquedas rápidas por explorador y fecha
        # CRÍTICO para rendimiento con 100+ solicitudes/día
        indexes = [
            models.Index(fields=['explorador', 'fecha'], name='turno_explorador_fecha_idx'),
        ]
        ordering = ['fecha', 'explorador']

    def __str__(self):
        return f"{self.explorador.user.username} - {self.fecha}" #type:ignore
    
class DiaEspecial(models.Model):
    fecha= models.DateField()
    tipo = models.CharField(max_length=50)
    descripcion = models.TextField(null=True, blank=True)
    recurrente = models.BooleanField(default=False) #type:ignore
    activo = models.BooleanField(default=True) #type:ignore
    # Campos para gestión de temporadas
    año_planificacion = models.IntegerField(null=True, blank=True, help_text='Año al que pertenecen las temporadas')
    es_temporada = models.BooleanField(default=False, help_text='Indica si es un día de temporada')
    mes = models.IntegerField(null=True, blank=True, help_text='Mes de la fecha (1-12), calculado automáticamente')
    creado_en=models.DateTimeField(auto_now_add=True)
    actualizado_en=models.DateTimeField(auto_now=True)
    historial= HistoricalRecords()
    
    class Meta:
        indexes = [
            models.Index(fields=['año_planificacion', 'mes', 'es_temporada'], name='dia_esp_anio_mes_temp_idx'),
            models.Index(fields=['fecha', 'tipo', 'activo'], name='dia_esp_fecha_tipo_activo_idx'),
        ]
        ordering = ['fecha']
    
    def save(self, *args, **kwargs):
        # Calcular mes y año de planificación automáticamente desde la fecha
        if self.fecha:
            self.mes = self.fecha.month
            if not self.año_planificacion:
                self.año_planificacion = self.fecha.year
        super().save(*args, **kwargs)
    
    def get_mes(self):
        """Retorna el mes de la fecha"""
        return self.fecha.month if self.fecha else None

    @classmethod
    def es_temporada_en(cls, fecha):
        """True si la fecha cae dentro de un día de temporada activo."""
        try:
            return cls.objects.filter(fecha=fecha, es_temporada=True, activo=True).exists()
        except Exception:
            return False

    @classmethod
    def es_mantenimiento_efectivo(cls, fecha):
        """
        True si la fecha es día de mantenimiento EFECTIVO.

        Regla de negocio: la temporada tiene prioridad sobre el mantenimiento.
        Un lunes (u otro día) marcado como mantenimiento que cae dentro de un
        rango de temporada NO se considera mantenimiento, porque la temporada manda.
        """
        try:
            if cls.es_temporada_en(fecha):
                return False
            return cls.objects.filter(fecha=fecha, tipo='mantenimiento', activo=True).exists()
        except Exception:
            return False

    def __str__(self):
        tipo_str = f" - {self.tipo}"
        if self.es_temporada:
            tipo_str += " (Temporada)"
        return f"{self.fecha}{tipo_str}" #type:ignore


# FASE 3.6: Modelos de archivo para datos antiguos
class TurnoArchivo(models.Model):
    """Modelo para almacenar turnos antiguos (más de 1 año)
    Mantiene la misma estructura que Turno para facilitar consultas históricas
    """
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha = models.DateField()
    jornada = models.ForeignKey(Jornada, on_delete=models.CASCADE)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE)
    tipo_cambio = models.CharField(max_length=50, null=True, blank=True)
    fecha_archivado = models.DateTimeField(auto_now_add=True)
    # Mantener referencia al ID original para trazabilidad
    turno_original_id = models.IntegerField(null=True, blank=True, help_text='ID del turno original antes de archivar')
    
    class Meta:
        indexes = [
            models.Index(fields=['explorador', 'fecha'], name='turno_arch_exp_fecha_idx'),  # 30 chars
            models.Index(fields=['fecha'], name='turno_arch_fecha_idx'),  # 20 chars
        ]
        ordering = ['fecha', 'explorador']
        verbose_name = 'Turno Archivado'
        verbose_name_plural = 'Turnos Archivados'
    
    def __str__(self):
        return f"{self.explorador.user.username} - {self.fecha} (Archivado)"


class DescansoSemanaManual(models.Model):
    """
    Descanso de ENTRE SEMANA asignado manualmente por el supervisor.

    Normalmente el descanso de semana es el "lunes de mantenimiento" (descansan AM y PM).
    Pero en semanas con TEMPORADA o FESTIVO ese lunes no aplica como descanso, y el descanso
    se mueve a otro día (martes/viernes). Este modelo deja que el supervisor defina, POR
    JORNADA (AM/PM), qué día (lun-vie) descansa ese grupo esa semana. Ej.: AM descansa el
    martes, PM descansa el viernes.
    """
    MOTIVO_CHOICES = [
        ('temporada', 'Temporada'),
        ('festivo', 'Festivo'),
        ('otro', 'Otro'),
    ]
    fecha = models.DateField(help_text='Día (lunes a viernes) en que descansa la jornada indicada')
    jornada = models.ForeignKey(Jornada, on_delete=models.CASCADE, related_name='descansos_semana_manual')
    motivo = models.CharField(max_length=20, choices=MOTIVO_CHOICES, default='temporada',
                              help_text='Por qué esta semana el descanso es manual (temporada/festivo)')
    descripcion = models.CharField(max_length=200, blank=True, default='')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Descanso de semana (manual)'
        verbose_name_plural = 'Descansos de semana (manuales)'
        ordering = ['-fecha', 'jornada']
        constraints = [
            models.UniqueConstraint(fields=['fecha', 'jornada'], name='uniq_descanso_semana_fecha_jornada'),
        ]
        indexes = [
            models.Index(fields=['fecha', 'activo'], name='descsem_fecha_activo_idx'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha and self.fecha.weekday() >= 5:
            raise ValidationError('El descanso de semana debe ser un día de lunes a viernes.')

    def __str__(self):
        return f"{self.jornada.nombre} descansa {self.fecha} ({self.get_motivo_display()})"


class AsignacionEspecialManual(models.Model):
    """
    OVERRIDE manual del grupo que TRABAJA (día completo AM+PM) en un día especial:
    un fin de semana (sábado/domingo) o un festivo entre semana.

    Normalmente esto lo resuelve la alternancia automática:
    - Fin de semana → AlternanciaFinesSemanaService (cálculo por paridad de semanas).
    - Festivo entre semana → FestivosRotacionService (rotación global PM/AM).

    Cuando existe un registro ACTIVO para una fecha, MANDA sobre el cálculo automático:
    `jornada_trabaja` es el grupo que cubre el día completo (dobla), el otro descansa.
    Si no hay registro para la fecha, sigue aplicando la alternancia automática (fallback).
    Un registro por fecha (unique) basta: define quién trabaja; el resto descansa.
    """
    TIPO_CHOICES = [
        ('finde', 'Fin de semana'),
        ('festivo', 'Festivo'),
    ]
    fecha = models.DateField(help_text='Fin de semana (sáb/dom) o festivo entre semana a fijar manualmente')
    jornada_trabaja = models.ForeignKey(
        Jornada, on_delete=models.CASCADE, related_name='asignaciones_especiales_manual',
        help_text='Grupo (AM/PM) que TRABAJA el día completo (dobla). El otro grupo descansa.'
    )
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default='finde')
    descripcion = models.CharField(max_length=200, blank=True, default='')
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Asignación especial (manual)'
        verbose_name_plural = 'Asignaciones especiales (manuales)'
        ordering = ['-fecha']
        constraints = [
            models.UniqueConstraint(fields=['fecha'], name='uniq_asignacion_especial_fecha'),
        ]
        indexes = [
            models.Index(fields=['fecha', 'activo'], name='asigesp_fecha_activo_idx'),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.fecha:
            return
        es_finde = self.fecha.weekday() >= 5
        if self.tipo == 'finde' and not es_finde:
            raise ValidationError('Un override de fin de semana debe caer en sábado o domingo.')
        if self.tipo == 'festivo' and es_finde:
            raise ValidationError('Un override de festivo debe caer de lunes a viernes.')

    def __str__(self):
        return f"{self.jornada_trabaja.nombre} trabaja {self.fecha} ({self.get_tipo_display()})"



# Create your models here.
