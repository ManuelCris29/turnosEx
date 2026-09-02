from django.db import models
from simple_history.models import HistoricalRecords

from core.constants import TipoCambioTurno

# Los tres últimos NO se usan en este archivo: se RE-EXPORTAN. Hay código y tests
# que hacen `from turnos.models import CompetenciaEmpleado`, así que quitarlos de
# aquí los rompe aunque nada falle en este módulo. El `noqa` evita que un
# `ruff --fix` vuelva a borrarlos.
# Deuda: re-exportar modelos entre apps confunde sobre dónde vive cada cosa; lo
# correcto sería que cada consumidor importe de `empleados.models` directamente.
from empleados.models import (  # noqa: F401
    CompetenciaEmpleado,
    Empleado,
    Jornada,
    RestriccionEmpleado,
    Sala,
    SancionEmpleado,
)


class AsignarJornadaExplorador(models.Model):
    explorador = models.ForeignKey(Empleado, on_delete=models.CASCADE)
    # PROTECT: borrar una jornada no debe arrastrar el historial de asignaciones.
    jornada = models.ForeignKey(Jornada, on_delete=models.PROTECT)
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
    jornada= models.ForeignKey(Jornada, on_delete=models.PROTECT)
    # La sala es INFORMATIVA: dice en qué espacio tiene competencia el explorador, no
    # condiciona el turno. Por eso admite NULL: un explorador sin competencia cargada
    # (p. ej. alguien que acaba de pasar de supervisor a explorador) debe poder recibir
    # turnos igual, y la UI muestra 'Por asignar'. Antes era NOT NULL y
    # `obtener_sala_explorador_fecha` lanzaba ValidationError, lo que hacía fallar la
    # aprobación de solicitudes por un dato que no cambia la operación.
    sala= models.ForeignKey(Sala, on_delete=models.CASCADE, null=True, blank=True)
    # De dónde viene este turno. NULL = turno normal, sin cambio de por medio.
    # Los `choices` documentan y validan en formularios/admin, pero Django solo los
    # comprueba en `full_clean()`: la garantía real de que no entre un valor inventado
    # es la CheckConstraint de más abajo. Ver `core.constants` para por qué este
    # vocabulario NO es el mismo que el de `TipoSolicitudCambio.nombre`.
    tipo_cambio= models.CharField(max_length=50, null=True, blank=True,
                                  choices=TipoCambioTurno.CHOICES)
    # Soft-delete auditable: un turno anulado NO se borra físicamente (queda para el
    # historial/estadística), pero no cuenta como turno activo (ni como falta, ni genera deuda).
    anulado = models.BooleanField(default=False)
    motivo_anulacion = models.CharField(max_length=200, null=True, blank=True)
    # Discriminante de unicidad: 1 si el turno está activo, NULL si está anulado. Existe para
    # poder declarar "un solo turno ACTIVO por (explorador, fecha, jornada)" en MySQL, que no
    # soporta índices únicos parciales (`UniqueConstraint(condition=...)`). En un índice único
    # los NULL no colisionan entre sí, así que varios anulados conviven y solo el activo es
    # único. Se mantiene sola en `save()`: no asignarla a mano.
    activo_key = models.PositiveSmallIntegerField(null=True, blank=True, default=1, editable=False)
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
        constraints = [
            # El invariante "un día = un conjunto de jornadas sin repetir" se sostenía solo por
            # la disciplina de delete-then-create repetida en ~15 sitios (strategies, servicios
            # de aplicación, restauración de snapshot). Cualquier ruta nueva que creara sin
            # borrar duplicaba el turno en silencio y ninguna de las tres capas de defensa lo
            # notaba: la persona aparecía dos veces en la misma jornada y el consolidado de
            # horas contaba doble. Ahora lo garantiza la base de datos.
            models.UniqueConstraint(
                fields=['explorador', 'fecha', 'jornada', 'activo_key'],
                name='turno_unico_activo_por_jornada',
            ),
            # `tipo_cambio` fue un CharField(50) libre durante toda la vida del proyecto: en esa
            # única columna llegaron a convivir el `nombre` de la maestra ('DOBLADA'), su
            # `codigo_estrategia` ('CT'), una abreviatura propia ('DOBLADA PERM') y valores sin
            # tipo de solicitud ('PAGO REPROGRAMADO', 'PERMISO'). Nada validaba lo que se
            # escribía, así que un typo entraba en silencio y solo se notaba cuando el turno
            # dejaba de contarse en los filtros que buscan el texto exacto.
            models.CheckConstraint(
                condition=models.Q(tipo_cambio__isnull=True)
                | models.Q(tipo_cambio__in=TipoCambioTurno.TODOS),
                name='turno_tipo_cambio_valido',
            ),
        ]
        ordering = ['fecha', 'explorador']

    def save(self, *args, **kwargs):
        # `activo_key` es derivada de `anulado`: se mantiene aquí para que la restricción de
        # unicidad no dependa de que cada llamador se acuerde de actualizarla.
        self.activo_key = None if self.anulado else 1
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            kwargs['update_fields'] = list(set(kwargs['update_fields']) | {'activo_key'})
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.explorador.user.username} - {self.fecha}" #type:ignore
    
class DiaEspecial(models.Model):
    # Año mínimo/máximo aceptado en toda la gestión de días especiales.
    # Fuente única: formularios, servicios y endpoints API validan contra estos límites.
    ANIO_MIN = 2000
    ANIO_MAX = 2100

    TIPO_FESTIVO = 'festivo'
    TIPO_MANTENIMIENTO = 'mantenimiento'
    TIPO_TEMPORADA = 'temporada'
    # `tipo` se compara por igualdad exacta en `es_festivo`/`es_mantenimiento_efectivo`,
    # así que un valor escrito a mano ("Festivo") dejaría el día sin efecto en silencio.
    TIPO_CHOICES = [
        (TIPO_FESTIVO, 'Festivo'),
        (TIPO_MANTENIMIENTO, 'Mantenimiento'),
        (TIPO_TEMPORADA, 'Temporada'),
    ]

    fecha= models.DateField()
    tipo = models.CharField(max_length=50, choices=TIPO_CHOICES)
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
        constraints = [
            # Un mismo día no puede estar registrado dos veces con el mismo tipo.
            # Sin esto, el borrado por `año_planificacion` puede dejar restos que
            # luego se duplican al volver a guardar el año.
            models.UniqueConstraint(fields=['fecha', 'tipo'], name='dia_esp_fecha_tipo_uniq'),
        ]
        ordering = ['fecha']

    def save(self, *args, **kwargs):
        # `mes` y `año_planificacion` son siempre derivados de `fecha`: se recalculan
        # en cada save. Si solo se rellenaran cuando están vacíos, editar la fecha a
        # otro año dejaría el registro apuntando al año viejo — invisible en el listado
        # de su año real y borrable al regenerar el año anterior.
        if self.fecha:
            self.mes = self.fecha.month
            self.año_planificacion = self.fecha.year
        # `es_temporada` es redundante con `tipo`; se deriva para que no puedan
        # contradecirse (p. ej. un día creado desde el CRUD con tipo "temporada"
        # pero la bandera en False sería invisible para TemporadaService).
        self.es_temporada = (self.tipo == self.TIPO_TEMPORADA)
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
    def es_festivo(cls, fecha):
        """True si la fecha es un festivo activo. Fuente única para "¿es festivo?"."""
        try:
            return cls.objects.filter(fecha=fecha, tipo='festivo', activo=True).exists()
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
    jornada = models.ForeignKey(Jornada, on_delete=models.PROTECT)
    # Informativa y opcional, igual que en `Turno` (ver comentario allí).
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, null=True, blank=True)
    # Espejo del campo en `Turno` (ver allí). Sin CheckConstraint a propósito: esta tabla es
    # historial y solo recibe copias de filas que ya pasaron la validación del original.
    tipo_cambio = models.CharField(max_length=50, null=True, blank=True,
                                   choices=TipoCambioTurno.CHOICES)
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
    jornada = models.ForeignKey(Jornada, on_delete=models.PROTECT, related_name='descansos_semana_manual')
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
    FUENTE DE VERDAD del grupo que TRABAJA (día completo AM+PM) en un día especial:
    un fin de semana (sábado/domingo) o un festivo entre semana.

    `jornada_trabaja` es el grupo que cubre el día completo (dobla); el otro descansa.
    Un registro por fecha (unique) basta: define quién trabaja, el resto descansa.

    El supervisor publica estas filas una vez al año desde `/turnos/asignacion-especial/anual/`
    (sembrar + ajustes). NO hay cálculo automático detrás: una fecha SIN fila significa
    "sin planificar", y así se reporta en `TurnoService.estado_dia` — nunca se inventa un
    grupo. Antes esto era un override sobre una fórmula, lo que hacía que el pasado se
    recalculara solo; ver docs/02-refactorizacion/PLAN_ALTERNANCIA_SEMILLA_ANUAL.md.
    """
    TIPO_CHOICES = [
        ('finde', 'Fin de semana'),
        ('festivo', 'Festivo'),
    ]
    fecha = models.DateField(help_text='Fin de semana (sáb/dom) o festivo entre semana a fijar manualmente')
    jornada_trabaja = models.ForeignKey(
        Jornada, on_delete=models.PROTECT, related_name='asignaciones_especiales_manual',
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


class AperturaAnioConfig(models.Model):
    """
    Configuración GLOBAL de la APERTURA DE AÑO: cuándo se le recuerda al supervisor que
    debe dejar planificado el año siguiente, y cuándo se le bloquea la navegación hasta
    que lo complete.

    Es un singleton (una sola fila), igual que `CierreSolicitudesConfig`.

    Aquí SOLO se configuran las FECHAS. Qué procesos son obligatorios no se configura: son
    siempre los mismos cinco y su completitud se DERIVA de los datos reales
    (`AperturaAnioService.estado`). Si fuera una casilla que alguien marca a mano, se podría
    declarar listo un año a medio planificar y el checklist dejaría de significar nada.
    """
    inicio_recordatorio_dia = models.PositiveSmallIntegerField(
        default=1, help_text='Día del mes en que empieza el aviso en el dashboard.')
    inicio_recordatorio_mes = models.PositiveSmallIntegerField(
        default=11, help_text='Mes en que empieza el aviso (1-12). Por defecto noviembre.')
    inicio_bloqueo_dia = models.PositiveSmallIntegerField(
        default=1, help_text='Día del mes en que empieza el bloqueo.')
    inicio_bloqueo_mes = models.PositiveSmallIntegerField(
        default=12, help_text='Mes en que empieza el bloqueo (1-12). Por defecto diciembre.')
    bloqueo_duro = models.BooleanField(
        default=True,
        help_text='Si está apagado, solo se avisa: nunca se redirige al supervisor.')
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Apertura de año (config)'
        verbose_name_plural = 'Apertura de año (config)'

    def __str__(self):
        return (f"Aviso {self.inicio_recordatorio_dia}/{self.inicio_recordatorio_mes} — "
                f"Bloqueo {self.inicio_bloqueo_dia}/{self.inicio_bloqueo_mes} "
                f"({'duro' if self.bloqueo_duro else 'solo aviso'})")

    @classmethod
    def obtener(cls):
        # `get_or_create(pk=1)` en vez de `first()` + `create()`: dos peticiones concurrentes
        # sobre una base vacía crearían dos filas y `first()` elegiría cualquiera de ellas.
        obj = cls.objects.first()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def _fecha(self, dia, mes, anio):
        import calendar
        from datetime import date
        # Se recorta al último día del mes: evita que un 31 configurado reviente en meses cortos.
        return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))

    def fecha_recordatorio(self, anio):
        return self._fecha(self.inicio_recordatorio_dia, self.inicio_recordatorio_mes, anio)

    def fecha_bloqueo(self, anio):
        return self._fecha(self.inicio_bloqueo_dia, self.inicio_bloqueo_mes, anio)


# Create your models here.
