from django.db import models
from django.core.exceptions import ValidationError
from empleados.models import Empleado
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.constants import EstadoSolicitud, EstadoCancelacion

class Notificacion(models.Model):
    """Modelo para representar notificaciones del sistema."""
    TIPOS_CHOICES = [
        ('solicitud_cambio', 'Solicitud de Cambio'),
        ('solicitud_doblada', 'Solicitud de Doblada'),
        ('solicitud_permiso', 'Solicitud de Permiso'),
        ('aprobacion', 'Aprobación'),
        ('rechazo', 'Rechazo'),
        ('sancion', 'Sanción'),
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


class EmailOutbox(models.Model):
    """
    Cola persistente de correos pendientes de envío (patrón *outbox*).

    PROBLEMA QUE RESUELVE: hasta ahora el envío se agendaba con `transaction.on_commit`
    + un hilo. Eso protege la operación de negocio (si el correo falla, la aprobación no
    se revierte), pero NO garantiza la entrega: si el proceso muere entre el COMMIT y la
    ejecución del callback —o si el hilo falla por un SMTP caído— el correo se pierde en
    silencio, sin rastro ni reintento. Para el supervisor eso es una solicitud que "nunca
    le llegó" sin forma de saber que existió.

    CÓMO LO RESUELVE: la fila se escribe DENTRO de la misma transacción que el cambio de
    negocio. O commitan las dos cosas o ninguna — nunca hay una aprobación sin su correo
    encolado. El envío real ocurre después, y si falla queda registrado con su error para
    que `procesar_email_outbox` lo reintente.

    IDEMPOTENCIA: `clave_idempotencia` (única) impide encolar dos veces el mismo correo
    lógico, y el reclamo de filas por UPDATE condicional (ver `EmailOutboxService`) impide
    que dos procesos envíen la misma fila a la vez. Un correo enviado no se puede
    "desenviar": aquí la garantía que importa es *como máximo una vez* por clave, además
    de *al menos una vez* por reintento.
    """
    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_ENVIANDO = 'enviando'
    ESTADO_ENVIADO = 'enviado'
    ESTADO_FALLIDO = 'fallido'
    ESTADO_CHOICES = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_ENVIANDO, 'Enviando'),
        (ESTADO_ENVIADO, 'Enviado'),
        (ESTADO_FALLIDO, 'Fallido (agotó reintentos)'),
    ]

    MAX_INTENTOS = 5

    asunto = models.CharField(max_length=500)
    cuerpo_texto = models.TextField()
    cuerpo_html = models.TextField(blank=True, default='')
    remitente = models.EmailField()
    reply_to = models.EmailField(blank=True, default='')
    # Lista de destinatarios ya validada en el momento de encolar.
    destinatarios = models.JSONField(default=list)

    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=ESTADO_PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    ultimo_error = models.TextField(blank=True, default='')

    # Nula cuando no hay una identidad lógica clara: entonces no se deduplica y cada
    # llamada encola su propia fila (comportamiento anterior, sin pérdida).
    clave_idempotencia = models.CharField(max_length=255, null=True, blank=True, unique=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    # Ninguna fila se envía antes de esta marca: es lo que implementa el backoff.
    disponible_en = models.DateTimeField(default=timezone.now)
    enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Correo en cola (outbox)'
        verbose_name_plural = 'Correos en cola (outbox)'
        ordering = ['creado_en']
        indexes = [
            # El índice que usa el worker para barrer: estado + cuándo toca reintentar.
            models.Index(fields=['estado', 'disponible_en'], name='outbox_estado_disp_idx'),
        ]

    def __str__(self):
        return f"[{self.estado}] {self.asunto} → {', '.join(self.destinatarios or [])}"

class TipoSolicitudCambio(models.Model):
    """Modelo para representar los tipos de solicitudes de cambio de turno."""
    nombre = models.CharField(max_length=50, unique=True)
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
        choices=EstadoSolicitud.CHOICES,
        default=EstadoSolicitud.PENDIENTE
    )
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_cambio_turno = models.DateField(null=True, blank=True, help_text='Fecha para la cual se solicita el cambio de turno')
    fecha_resolucion = models.DateTimeField(
        null=True, blank=True,
        help_text='Instante en que la solicitud quedó RESUELTA (aprobada o rechazada). De este '
                  'campo dependen la ventana de cancelación de 30 min y el orden de la guardia '
                  'LIFO, así que NO se sobrescribe al cancelar: para eso está fecha_cancelacion.'
    )
    # Antes la cancelación no dejaba hora en ninguna parte: `fecha_resolucion` conservaba la de la
    # aprobación y el email de cancelación la mostraba rotulada como "Fecha de Cancelación", así que
    # informaba una hora anterior a la real (hasta 30 min antes, el tamaño de la ventana). El único
    # rastro del instante verdadero quedaba de rebote en la notificación generada.
    fecha_cancelacion = models.DateTimeField(
        null=True, blank=True,
        help_text='Instante en que se canceló la solicitud (por el explorador dentro de su ventana '
                  'de 30 min, o por gestión). Null si nunca se canceló.'
    )
    # --- Cancelación consensuada ---------------------------------------------------------
    # Cancelar una solicitud APROBADA deshace un acuerdo de dos: la pide el solicitante y la
    # confirma el receptor. Mientras `cancelacion_estado` es 'pendiente' el `estado` sigue
    # siendo 'aprobada' a propósito — los turnos continúan aplicados y todas las consultas que
    # filtran por 'aprobada' (guardia LIFO, Mis Turnos, reconciliación) siguen viéndola vigente.
    cancelacion_estado = models.CharField(
        max_length=10, choices=EstadoCancelacion.CHOICES, default=EstadoCancelacion.NINGUNA,
        blank=True,
        help_text='Estado de la petición de cancelación. Vacío si nunca se pidió cancelar.'
    )
    cancelacion_solicitada_por = models.ForeignKey(
        Empleado, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cancelaciones_pedidas',
        help_text='Quién pidió cancelar (normalmente el solicitante).'
    )
    cancelacion_solicitada_en = models.DateTimeField(
        null=True, blank=True,
        help_text='Instante de la PETICIÓN de cancelación. Desde aquí corre el plazo de '
                  'respuesta de la contraparte.'
    )
    cancelacion_respondida_por = models.ForeignKey(
        Empleado, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cancelaciones_respondidas',
        help_text='Quién aprobó o rechazó la cancelación.'
    )
    cancelacion_respondida_en = models.DateTimeField(null=True, blank=True)
    cancelacion_motivo = models.TextField(
        null=True, blank=True,
        help_text='Motivo que dio quien pidió cancelar, y/o la respuesta de la contraparte.'
    )

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
    reemplazada_por = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reemplaza_a',
        help_text='Solicitud que reemplazó a esta (cuando el turno fue cedido nuevamente tras los 30 min de gavela).'
    )
    snapshot_turnos_previos = models.JSONField(
        null=True, blank=True,
        help_text=(
            'Turnos de solicitante/receptor en la(s) fecha(s) afectadas ANTES de aplicar el '
            'cambio (usado por CT sencillo). Clave "explorador_id:YYYY-MM-DD", valor lista de '
            '{jornada_nombre, sala_id, tipo_cambio}. Permite revertir al cancelar dentro de los 30 min.'
        )
    )
    snapshot_turnos_resultantes = models.JSONField(
        null=True, blank=True,
        help_text=(
            'Turnos que este cambio DEJÓ en las mismas fechas, mismo formato que '
            'snapshot_turnos_previos. Al cancelar se compara contra los turnos actuales: si no '
            'coinciden, alguien más tocó esos días y revertir pisaría su cambio.'
        )
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
            # "Mis Solicitudes": filtra por solicitante y ordena por fecha_solicitud desc.
            models.Index(
                fields=['explorador_solicitante', '-fecha_solicitud'],
                name='sol_solicitante_fecha_idx'
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
                # `condition=` y no `check=`: el segundo está deprecado y DESAPARECE en
                # Django 6.0 (RemovedInDjango60Warning). El aviso estaba ahí desde hace
                # tiempo pero `--disable-warnings` en pytest.ini lo ocultaba.
                # turnos/models.py:100 ya usaba la forma nueva; esta era la última que
                # quedaba con la vieja.
                condition=(
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

    JORNADA_PAGO_SABADO_CHOICES = [
        ('AM', 'AM'),
        ('PM', 'PM'),
        ('AMBAS', 'Ambas (cubro el día completo; el receptor descansa)'),
    ]

    SUBMODALIDAD_SEMANA_CHOICES = [
        ('intercambio_dia', 'Intercambio de día'),
        ('jornadas_partidas', 'Jornadas partidas (uno AM ambos días, otro PM)'),
        ('cobertura_misma_semana', 'Cobertura con pago en la misma semana'),
        ('cambio_doblada', 'Cambio de doblada de la semana'),
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
    es_intercambio = models.BooleanField(
        default=False,
        help_text='True si es un INTERCAMBIO de dobladas (ambos tienen doblada en días distintos y se '
                  'intercambian): día de cesión el receptor dobla y el solicitante descansa; día de pago el '
                  'solicitante dobla y el receptor descansa. NO genera ni altera deudas (es un swap de días).'
    )
    jornada_pago_sabado = models.CharField(
        max_length=5,
        choices=JORNADA_PAGO_SABADO_CHOICES,
        null=True,
        blank=True,
        help_text='Si la fecha de pago es sábado, jornada que el solicitante cubre ese sábado: '
                  'AM, PM o AMBAS (día completo; en ese caso el receptor descansa y queda debiendo media jornada).'
    )
    fecha_pago_semana = models.DateField(
        null=True,
        blank=True,
        help_text='Solo cuando jornada_pago_sabado=AMBAS: día de semana (lun-vie, mismo mes) en que el '
                  'receptor le devuelve la jornada al solicitante (el receptor dobla y el solicitante descansa).'
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
    submodalidad_semana = models.CharField(
        max_length=30,
        choices=SUBMODALIDAD_SEMANA_CHOICES,
        null=True,
        blank=True,
        help_text='Solo CAMBIO DESCANSO entre semana (temporada): distingue el sub-flujo. '
                  'Las filas antiguas entre-semana sin valor se tratan como intercambio_dia.'
    )
    snapshot_turnos_previos = models.JSONField(
        null=True,
        blank=True,
        help_text='Turnos de solicitante/receptor en fechas de cesión y pago ANTES de aplicar la doblada. '
        'Clave "explorador_id:YYYY-MM-DD", valor lista de {jornada_nombre, sala_id, tipo_cambio}. '
        'Permite revertir la cancelación en 30 min restaurando CT sencillos u otros turnos previos.'
    )
    snapshot_turnos_resultantes = models.JSONField(
        null=True, blank=True,
        help_text='Turnos que la doblada DEJÓ en esas mismas fechas, mismo formato que '
        'snapshot_turnos_previos. Al cancelar se compara contra los turnos actuales: si no '
        'coinciden, alguien más tocó esos días y revertir pisaría su cambio.'
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
    # Fechas ESPECÍFICAS elegidas (CSV de YYYY-MM-DD). Si están pobladas, la aplicación usa estas
    # fechas exactas (permite balancear cuando los weekdays tienen distinto número de ocurrencias).
    # Si están vacías, se expanden los weekdays de dias_cesion/dias_devolucion (retrocompatible).
    fechas_cesion = models.TextField(
        default='', blank=True,
        help_text='Fechas específicas de cesión (YYYY-MM-DD, coma). Prioridad sobre dias_cesion.'
    )
    fechas_devolucion = models.TextField(
        default='', blank=True,
        help_text='Fechas específicas de devolución (YYYY-MM-DD, coma). Prioridad sobre dias_devolucion.'
    )
    minutos_deuda = models.IntegerField(default=30)
    empleado_receptor = models.ForeignKey(
        Empleado, on_delete=models.CASCADE, null=True, blank=True,
        related_name='dobladas_permanentes_recibidas',
    )
    snapshot_turnos_previos = models.JSONField(
        null=True, blank=True,
        help_text='Turnos de solicitante/receptor en las fechas afectadas ANTES de aplicar la doblada '
                  'permanente. Permite revertir al cancelar dentro de los 30 min.'
    )
    snapshot_turnos_resultantes = models.JSONField(
        null=True, blank=True,
        help_text='Turnos que la doblada permanente DEJÓ en esas mismas fechas, mismo formato que '
                  'snapshot_turnos_previos. Al cancelar se compara contra los turnos actuales: si '
                  'no coinciden, alguien más tocó esos días y revertir pisaría su cambio.'
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
        ('pagada', 'Pagada'),
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
        help_text='Estado de la deuda: activa, pagada o cancelada'
    )
    fecha_pago = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha en que se pagó la deuda (cuando estado=pagada)'
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


class ReprogramacionDiaDoblada(models.Model):
    """
    Reprogramación del DÍA DE DOBLADA de UNA persona en una doblada ya aprobada, cuando esa
    persona no pudo cumplirlo (enfermedad, incapacidad, imprevisto).

    Es simétrico: sirve igual para el solicitante o el receptor, sea el primero o el segundo
    en doblar. NO afecta al otro explorador (que ya cumplió o cumplirá su día normal). El día
    original se ANULA (soft-delete del Turno, ver Turno.anulado) y se le resta su deuda de 30
    min; al programar el día nuevo se le vuelve a agregar la doblada + los 30 min en la fecha
    real. Todo queda en registro para auditoría (este modelo + HistoricalRecords + los turnos
    anulados y las deudas canceladas conservan su historial).
    """
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente de programar'),
        ('pagada', 'Pagada (día reprogramado cumplido)'),
        ('cancelada', 'Cancelada'),
    ]
    JORNADA_CHOICES = [('AM', 'AM'), ('PM', 'PM')]

    doblada_origen = models.ForeignKey(
        SolicitudCambio, on_delete=models.CASCADE, related_name='reprogramaciones_dia',
        help_text='Doblada aprobada cuyo día no se cumplió.'
    )
    explorador = models.ForeignKey(
        Empleado, on_delete=models.CASCADE, related_name='reprogramaciones_doblada',
        help_text='Explorador que no cumplió su día y debe reprogramarlo (deudor).'
    )
    fecha_original = models.DateField(help_text='Día de doblada que no se cumplió (se anuló).')
    jornada_debida = models.CharField(
        max_length=2, choices=JORNADA_CHOICES, null=True, blank=True,
        help_text='Jornada que quedó debiendo (la contraria a su jornada ese día).'
    )
    fecha_reprogramada = models.DateField(
        null=True, blank=True, help_text='Día nuevo en que dobla para pagar (lo organiza el supervisor).'
    )
    jornada_pago_previa = models.CharField(
        max_length=2, choices=JORNADA_CHOICES, null=True, blank=True,
        help_text='Jornada única que tenía en el día de pago ANTES de doblar; se restaura al cancelar.'
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    motivo = models.CharField(
        max_length=200, null=True, blank=True, help_text='Motivo de la inasistencia (enfermedad, incapacidad…).'
    )
    registrado_por = models.ForeignKey(
        Empleado, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reprogramaciones_registradas', help_text='Supervisor que registró la inasistencia.'
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Reprogramación de día de doblada'
        verbose_name_plural = 'Reprogramaciones de día de doblada'
        indexes = [
            models.Index(fields=['explorador', 'estado'], name='reprog_explorador_estado_idx'),
            models.Index(fields=['doblada_origen'], name='reprog_doblada_idx'),
        ]
        ordering = ['-creado_en']

    def __str__(self):
        return f"Reprog. {self.explorador} {self.fecha_original} → {self.fecha_reprogramada or 'sin programar'} ({self.estado})"


DIA_CIERRE_CHOICES = [
    ('jueves', 'Jueves'),
    ('viernes', 'Viernes'),
    ('sabado', 'Sábado'),
    ('domingo', 'Domingo'),
    ('primer_habil', 'Primer día hábil de la semana siguiente'),
]


class CierreSolicitudesConfig(models.Model):
    """
    Configuración GLOBAL (por defecto) del cierre semanal de solicitudes.

    Cuando está habilitado, cada semana —a partir del `dia_cierre` a la `hora_cierre`— se cierra
    la programación del fin de semana: no se pueden enviar NUEVAS solicitudes de cambio de turno
    ni permisos cuyo objetivo caiga en la ventana [día de cierre … primer día hábil de la semana
    siguiente]. Es un singleton (una sola fila); las semanas puntuales se ajustan con
    `CierreSemanaOverride`. Si `habilitado=False` no hay ninguna restricción.
    """
    habilitado = models.BooleanField(default=False, help_text='Si está apagado, no hay ninguna restricción.')
    dia_cierre = models.CharField(max_length=15, choices=DIA_CIERRE_CHOICES, default='jueves')
    hora_cierre = models.TimeField(default='14:00', help_text='Hora del día de cierre a partir de la cual se bloquea.')
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Cierre de solicitudes (config)'
        verbose_name_plural = 'Cierre de solicitudes (config)'

    def __str__(self):
        return f"Cierre {'ON' if self.habilitado else 'OFF'} — {self.get_dia_cierre_display()} {self.hora_cierre}"

    @classmethod
    def obtener(cls):
        # `get_or_create(pk=1)` en vez de `first()` + `create()`: dos peticiones concurrentes
        # sobre una base vacía crearían dos filas y `first()` elegiría cualquiera de ellas.
        obj = cls.objects.first()
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CierreSemanaOverride(models.Model):
    """
    Ajuste del cierre para UNA semana específica (identificada por su lunes). Sobre-escribe el
    default global esa semana: otro día/hora, o deshabilitar el cierre solo esa semana.
    """
    semana_lunes = models.DateField(unique=True, help_text='Lunes de la semana a la que aplica el ajuste.')
    habilitado = models.BooleanField(default=True)
    dia_cierre = models.CharField(max_length=15, choices=DIA_CIERRE_CHOICES, default='jueves')
    hora_cierre = models.TimeField(default='14:00')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Cierre por semana (override)'
        verbose_name_plural = 'Cierres por semana (overrides)'
        ordering = ['-semana_lunes']

    def __str__(self):
        return f"Override {self.semana_lunes} — {'ON' if self.habilitado else 'OFF'} {self.get_dia_cierre_display()} {self.hora_cierre}"


# Create your models here.
