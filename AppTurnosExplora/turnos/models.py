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

class Turno(models.Model):
    explorador= models.ForeignKey(Empleado, on_delete=models.CASCADE)
    fecha= models.DateField()
    jornada= models.ForeignKey(Jornada, on_delete=models.CASCADE)
    sala= models.ForeignKey(Sala, on_delete=models.CASCADE)
    tipo_cambio= models.CharField(max_length=50, null=True, blank=True)
    historial= HistoricalRecords()

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
    






# Create your models here.
