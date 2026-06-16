from django.db import models
from django.core.exceptions import ValidationError
from empleados.models import Empleado
from turnos.models import Turno
from django.utils import timezone
from simple_history.models import HistoricalRecords

class Notificacion(models.Model):
    """Modelo para representar notificaciones del sistema."""
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
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['destinatario', 'leida'], name='notif_dest_leida_idx'),
            models.Index(fields=['tipo'], name='notif_tipo_idx'),
            models.Index(fields=['fecha_creacion'], name='notif_fecha_creacion_idx'),
        ]
    
    def __str__(self):
        return f"{self.titulo} - {self.destinatario.nombre} {self.destinatario.apellido}"

class TipoSolicitudCambio(models.Model):
    """Modelo para representar los tipos de solicitudes de cambio de turno."""
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

    class Meta:
        verbose_name = 'Tipo de Solicitud de Cambio'
        verbose_name_plural = 'Tipos de Solicitudes de Cambio'
        ordering = ['nombre']
        indexes = [
            models.Index(fields=['activo'], name='tipo_sol_activo_idx'),
        ]
    
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
    """Modelo para almacenar detalles de cambios permanentes de turno."""
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='cambio_permanente')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Detalle de Cambio Permanente'
        verbose_name_plural = 'Detalles de Cambios Permanentes'
        ordering = ['-fecha_inicio', 'solicitud']
        indexes = [
            models.Index(fields=['solicitud'], name='camb_perm_solicitud_idx'),
            models.Index(fields=['fecha_inicio'], name='camb_perm_fecha_inicio_idx'),
        ]
    
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')

    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud}" #type:ignore


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
    
    def save(self, *args, **kwargs):
        """
        Validar que los días seleccionados sean solo lunes-viernes.
        CT PERMANENTE no permite sábados ni domingos.
        """
        # Validar día de semana seleccionado
        if self.tipo == 'dia_semana' and self.dia_semana is not None:
            if self.dia_semana == 5:  # Sábado
                raise ValidationError('Los cambios permanentes solo se pueden realizar de lunes a viernes. No se permiten sábados.')
            if self.dia_semana == 6:  # Domingo
                raise ValidationError('Los cambios permanentes solo se pueden realizar de lunes a viernes. No se permiten domingos.')
        
        # Validar fecha específica
        if self.tipo == 'fecha_especifica' and self.fecha_especifica:
            if self.fecha_especifica.weekday() == 5:  # Sábado
                raise ValidationError(f'La fecha {self.fecha_especifica} es sábado. Los cambios permanentes solo se permiten de lunes a viernes.')
            if self.fecha_especifica.weekday() == 6:  # Domingo
                raise ValidationError(f'La fecha {self.fecha_especifica} es domingo. Los cambios permanentes solo se permiten de lunes a viernes.')
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.tipo == 'fecha_especifica' and self.fecha_especifica:
            return f"Fecha específica: {self.fecha_especifica}"
        elif self.tipo == 'dia_semana' and self.dia_semana is not None:
            dias_semana_nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            return f"Día de semana: {dias_semana_nombres[self.dia_semana]}"
        return f"Día de cambio permanente (ID: {self.id})"

class DobladaDetalle(models.Model):
    """Modelo para almacenar detalles de solicitudes de doblada."""
    TIPO_CESION_CHOICES = [
        ('cesion_completa', 'Cesión Completa'),
        ('cesion_parcial_am', 'Cesión Parcial AM'),
        ('cesion_parcial_pm', 'Cesión Parcial PM'),
    ]
    
    JORNADA_CHOICES = [
        ('AM', 'AM'),
        ('PM', 'PM'),
    ]
    
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='doblada')
    minutos_deuda = models.IntegerField(default=30)
    fecha_pago = models.DateField(
        help_text='Fecha en que el solicitante devolverá la doblada. Obligatorio: No existen dobladas abiertas.'
    )
    tipo_cesion = models.CharField(
        max_length=50,
        choices=TIPO_CESION_CHOICES,
        default='cesion_completa',
        help_text='Tipo de cesión: completa o parcial (AM/PM)'
    )
    jornada_cedida = models.CharField(
        max_length=2,
        choices=JORNADA_CHOICES,
        null=True,
        blank=True,
        help_text='Jornada específica que se cede (si es cesión parcial)'
    )
    jornada_pago_sabado = models.CharField(
        max_length=2,
        choices=JORNADA_CHOICES,
        null=True,
        blank=True,
        help_text='Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
    )
    JORNADA_CUBRE_PAGO_CHOICES = [
        ('AM', 'AM'),
        ('PM', 'PM'),
        ('AMBAS', 'Ambas (receptor descansa el día completo)'),
    ]
    jornada_cubre_en_pago = models.CharField(
        max_length=5,
        choices=JORNADA_CUBRE_PAGO_CHOICES,
        null=True,
        blank=True,
        help_text='Si el receptor tiene doblada (AM+PM) en fecha de pago: qué parte cubre el deudor, o ambas.'
    )
    snapshot_turnos_previos = models.JSONField(
        null=True,
        blank=True,
        help_text='Turnos de solicitante/receptor en fechas de cesión y pago ANTES de aplicar la doblada. '
        'Clave "explorador_id:YYYY-MM-DD", valor lista de {jornada_nombre, sala_id, tipo_cambio}. '
        'Permite revertir la cancelación en 30 min restaurando CT sencillos u otros turnos previos.'
    )
    empleado_receptor = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='dobladas_recibidas',
        help_text='Explorador que cubre la doblada (redundante con SolicitudCambio.explorador_receptor, pero útil para consultas directas)'
    )
    historial = HistoricalRecords(excluded_fields=['jornada_pago_sabado'])
    
    class Meta:
        verbose_name = 'Detalle de Doblada'
        verbose_name_plural = 'Detalles de Dobladas'
        ordering = ['-fecha_pago', 'solicitud']
        indexes = [
            models.Index(fields=['solicitud'], name='doblada_solicitud_idx'),
            models.Index(fields=['fecha_pago'], name='doblada_fecha_pago_idx'),
            models.Index(fields=['empleado_receptor', 'fecha_pago'], name='doblada_receptor_fecha_idx'),
        ]
    
    def __str__(self):
        return f"solicitud: {self.solicitud.id} - fecha: {self.solicitud.fecha_solicitud}" #type:ignore


class DobladaPermanenteDetalle(models.Model):
    """
    Detalle de una Doblada Permanente: doblada recurrente en días fijos de la
    semana dentro de un rango (mutuo acuerdo entre dos exploradores).

    - dias_cesion: días de la semana en que el SOLICITANTE no asiste y el RECEPTOR
      cubre (el receptor se dobla AM+PM esos días; el solicitante descansa).
    - dias_devolucion: días de la semana en que el SOLICITANTE devuelve el favor
      doblándose (el solicitante se dobla AM+PM; el receptor descansa).

    Días: 0=lunes .. 6=domingo, separados por coma. No se permiten domingos.
    Cada doblada efectiva acumula 30 min de deuda corporativa para quien se dobla.
    """
    solicitud = models.OneToOneField(SolicitudCambio, on_delete=models.CASCADE, related_name='doblada_permanente')
    fecha_inicio = models.DateField(help_text='Inicio del rango de vigencia.')
    fecha_fin = models.DateField(help_text='Fin del rango de vigencia.')
    dias_cesion = models.CharField(
        max_length=20, default='',
        help_text='Días de la semana que cede el solicitante (los cubre el receptor). 0=lun..6=dom, coma.'
    )
    dias_devolucion = models.CharField(
        max_length=20, default='',
        help_text='Días de la semana en que el solicitante devuelve (se dobla). 0=lun..6=dom, coma.'
    )
    minutos_deuda = models.IntegerField(default=30)
    empleado_receptor = models.ForeignKey(
        Empleado, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dobladas_permanentes_recibidas',
    )
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Detalle de Doblada Permanente'
        verbose_name_plural = 'Detalles de Doblada Permanente'
        ordering = ['-fecha_inicio', 'solicitud']
        indexes = [
            models.Index(fields=['solicitud'], name='dob_perm_solicitud_idx'),
            models.Index(fields=['fecha_inicio'], name='dob_perm_fecha_idx'),
        ]

    @staticmethod
    def _dias_legibles(dias_str):
        nombres = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        dias = [int(d) for d in dias_str.split(',') if d.strip().isdigit()]
        return ', '.join(nombres[d] for d in sorted(dias) if 0 <= d <= 6)

    def dias_cesion_legible(self):
        return DobladaPermanenteDetalle._dias_legibles(self.dias_cesion)

    def dias_devolucion_legible(self):
        return DobladaPermanenteDetalle._dias_legibles(self.dias_devolucion)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fecha_inicio and self.fecha_fin and self.fecha_fin < self.fecha_inicio:
            raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio.')

    def __str__(self):
        return f"Doblada permanente sol {self.solicitud_id} ({self.fecha_inicio} a {self.fecha_fin})"


class DeudaExplorador(models.Model):
    """
    Modelo para registrar deudas entre exploradores.
    Se genera cuando un explorador cede su jornada a otro (doblada).
    """
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('pagada', 'Pagada'),
        ('cancelada', 'Cancelada'),
    ]
    
    JORNADA_CHOICES = [
        ('AM', 'AM'),
        ('PM', 'PM'),
    ]
    
    deudor = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='deudas_como_deudor',
        help_text='Explorador que debe la jornada'
    )
    acreedor = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='deudas_como_acreedor',
        help_text='Explorador al que se le debe la jornada'
    )
    solicitud_origen = models.ForeignKey(
        SolicitudCambio,
        on_delete=models.CASCADE,
        related_name='deuda_generada',
        help_text='Solicitud de doblada que generó esta deuda'
    )
    fecha_generacion = models.DateField(
        auto_now_add=True,
        help_text='Fecha en que se generó la deuda'
    )
    fecha_pago_pactada = models.DateField(help_text='Fecha acordada para pagar la deuda')
    fecha_pago_real = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha en que se pagó realmente la deuda'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='pendiente',
        help_text='Estado de la deuda'
    )
    media_jornada = models.BooleanField(
        default=True,
        help_text='True si es media jornada, False si es completa'
    )
    jornada_cedida = models.CharField(
        max_length=2,
        choices=JORNADA_CHOICES,
        help_text='Jornada que se cedió (AM o PM)'
    )
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Deuda entre Exploradores'
        verbose_name_plural = 'Deudas entre Exploradores'
        indexes = [
            models.Index(fields=['deudor', 'estado'], name='deuda_deudor_estado_idx'),
            models.Index(fields=['acreedor', 'estado'], name='deuda_acreedor_estado_idx'),
            models.Index(fields=['fecha_pago_pactada', 'estado'], name='deuda_fecha_pago_estado_idx'),
        ]
        ordering = ['-fecha_generacion']
    
    def __str__(self):
        return f"{self.deudor.nombre} debe a {self.acreedor.nombre} - {self.jornada_cedida} ({self.estado})"


class DeudaCorporativa(models.Model):
    """
    Modelo para registrar deudas corporativas acumuladas.
    Cada doblada genera +30 minutos de deuda corporativa que se acumula permanentemente.
    """
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('cancelada', 'Cancelada'),
    ]
    
    explorador = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='deudas_corporativas',
        help_text='Explorador que acumula la deuda corporativa'
    )
    solicitud_origen = models.ForeignKey(
        SolicitudCambio,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deudas_corporativas_generadas',
        help_text='Solicitud que generó esta deuda (opcional)'
    )
    minutos = models.IntegerField(
        default=30,
        help_text='Minutos de deuda corporativa (típicamente 30 por doblada)'
    )
    fecha_generacion = models.DateField(
        auto_now_add=True,
        help_text='Fecha en que se generó la deuda'
    )
    fecha_doblada = models.DateField(
        help_text='Fecha en que se realizó la doblada que generó esta deuda'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='activa',
        help_text='Estado de la deuda: activa o cancelada'
    )
    comentario = models.TextField(
        null=True,
        blank=True,
        help_text='Comentario opcional sobre la deuda'
    )
    historial = HistoricalRecords()
    
    class Meta:
        verbose_name = 'Deuda Corporativa'
        verbose_name_plural = 'Deudas Corporativas'
        indexes = [
            models.Index(fields=['explorador', 'estado'], name='deuda_corp_exp_estado_idx'),
            models.Index(fields=['fecha_generacion', 'estado'], name='deuda_corp_fecha_estado_idx'),
            models.Index(fields=['fecha_doblada'], name='deuda_corp_fecha_dob_idx'),
        ]
        ordering = ['-fecha_generacion']
    
    def __str__(self):
        return f"{self.explorador.nombre} - {self.minutos} min ({self.estado}) - {self.fecha_doblada}"
    
    @staticmethod
    def obtener_deuda_total(explorador):
        """
        Calcula la deuda corporativa total acumulada de un explorador.
        Suma todas las deudas con estado 'activa'.
        """
        from django.db.models import Sum
        total = DeudaCorporativa.objects.filter(
            explorador=explorador,
            estado='activa'
        ).aggregate(total=Sum('minutos'))['total']
        return total or 0


# Create your models here.
