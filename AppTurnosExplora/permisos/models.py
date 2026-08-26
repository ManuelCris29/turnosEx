from django.db import models
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from simple_history.models import HistoricalRecords
from core.constants import EstadoCancelacion


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
    # Deuda MENSUAL de permisos que salda este pago. Va por una tabla intermedia y no por
    # un M2M plano porque un mes se puede pagar A TROZOS: hay que guardar cuántos minutos
    # cubre este PDH de cada mes, o al borrarlo no se sabría cuánto devolver.
    deudas_permiso_mes = models.ManyToManyField('permisos.DeudaPermisoMes', blank=True,
                                                through='permisos.PagoDeudaPermisoMes',
                                                related_name='pdhs',
                                                help_text='Meses de permiso que paga este registro.')
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
    # De este campo cuelga el plazo para pedir la cancelación. NO sirve `actualizado_en`: es
    # `auto_now`, así que cualquier guardado posterior (un comentario del supervisor, la propia
    # petición de cancelación) reiniciaba el reloj de 24 h. Es el equivalente de
    # `SolicitudCambio.fecha_resolucion`, que este modelo no tenía.
    fecha_aprobacion = models.DateTimeField(
        null=True, blank=True,
        help_text='Instante en que el permiso quedó APROBADO. Null si nunca se aprobó.'
    )
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
    # --- Cancelación consensuada ----------------------------------------------------------
    # Un permiso aprobado ya movió turnos (y, si hay quien cubra, los de otra persona), así que
    # el dueño no lo cancela solo: lo PIDE y su supervisor lo confirma. Aquí la contraparte es
    # el supervisor, porque el permiso no tiene receptor. Mientras está pendiente el permiso
    # sigue en estado APROBADO y los turnos no se tocan.
    cancelacion_estado = models.CharField(
        max_length=10, choices=EstadoCancelacion.CHOICES, default=EstadoCancelacion.NINGUNA,
        blank=True,
        help_text='Estado de la petición de cancelación. Vacío si nunca se pidió cancelar.'
    )
    cancelacion_solicitada_por = models.ForeignKey(
        Empleado, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='permisos_cancelacion_pedida'
    )
    cancelacion_solicitada_en = models.DateTimeField(null=True, blank=True)
    cancelacion_respondida_por = models.ForeignKey(
        Empleado, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='permisos_cancelacion_respondida'
    )
    cancelacion_respondida_en = models.DateTimeField(null=True, blank=True)
    cancelacion_motivo = models.TextField(null=True, blank=True)

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

    def ocurrencias_por_mes(self, hasta=None):
        """
        Las obligaciones de este permiso repartidas por mes: [(anio, mes, ocurrencias)].

        Un permiso permanente de agosto a noviembre no es UNA deuda de 8 h 30: son cuatro
        deudas mensuales independientes, porque cada una vence al cerrar SU mes y se
        sanciona por separado. Tratarlas como un bloque obligaba a esperar a noviembre para
        reclamar lo de agosto.

        Un permiso puntual es el caso degenerado: un único mes con una ocurrencia.

        Con `hasta` se cuentan solo las ocurrencias que YA han ocurrido a esa fecha. Sirve
        para la consulta "a 25 de agosto, ¿cuánto lleva debido este mes?": lo que aún no ha
        pasado todavía no se debe. Sin `hasta` (el uso normal: `horas_totales`,
        `desglose_mensual`) cuenta el rango entero y el resultado no cambia.
        """
        if hasta is not None and self.fecha_inicio > hasta:
            return []
        if not self.es_permanente:
            return [(self.fecha_inicio.year, self.fecha_inicio.month, 1)]

        from datetime import timedelta
        dias = {int(d) for d in self.dias_semana.split(',') if d.strip().isdigit()}
        if not dias:
            return []

        fin = self.fecha_fin if hasta is None else min(self.fecha_fin, hasta)
        conteo = {}
        d = self.fecha_inicio
        while d <= fin:
            if d.weekday() in dias:
                clave = (d.year, d.month)
                conteo[clave] = conteo.get(clave, 0) + 1
            d += timedelta(days=1)
        return [(anio, mes, n) for (anio, mes), n in sorted(conteo.items())]

    def horas_totales(self):
        """
        Horas que este permiso acumula a la deuda del explorador.
        - Normal: el tiempo solicitado.
        - Permanente: tiempo × número de ocurrencias (días de la semana en el rango).

        Se calcula sumando el desglose mensual en vez de recorrer el rango otra vez: dos
        recorridos paralelos pueden divergir, y entonces el total mostrado en pantalla no
        cuadraría con la suma de las deudas que de verdad se cobran.
        """
        ocurrencias = sum(n for _, _, n in self.ocurrencias_por_mes())
        return round(float(self.tiempo or 0) * ocurrencias, 2)

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



class DeudaPermisoMes(models.Model):
    """
    Lo que un explorador debe por UN permiso en UN mes concreto.

    Existe porque `PermisoEspecial` no puede representarlo: tiene un único `pagado`
    booleano para todo su rango, así que un permanente de agosto a noviembre era una deuda
    global de todo-o-nada. Eso impedía tres cosas a la vez: reclamar agosto al cerrar
    agosto, aceptar un pago parcial, y —efecto colateral— pagar siquiera un permiso largo,
    porque el total superaba el tope de horas de un solo PDH.

    La deuda de cada mes vence al terminar ese mes y se evalúa sola. Varios permisos que
    caen en el mismo mes generan VARIAS filas, no una fusionada: la deuda se suma para
    decidir la sanción, pero cada obligación conserva de qué permiso viene.

    No se borra nunca: se paga, se cancela, o la consume una sanción cumplida.
    """
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('pagada', 'Pagada'),
        ('consumida_por_sancion', 'Consumida por sanción'),
        ('cancelada', 'Cancelada'),
    ]

    permiso = models.ForeignKey(
        PermisoEspecial, on_delete=models.CASCADE, related_name='deudas_mes',
        help_text='Permiso que generó esta obligación mensual.')
    # Desnormalizado a propósito: casi todas las consultas son "qué debe esta persona",
    # y sin él cada una tendría que pasar por el permiso para llegar al empleado.
    explorador = models.ForeignKey(
        Empleado, on_delete=models.CASCADE, related_name='deudas_permiso_mes')
    anio = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField(help_text='1..12')
    minutos_generados = models.PositiveIntegerField(
        help_text='Tiempo del permiso × ocurrencias en ESE mes.')
    minutos_pagados = models.PositiveIntegerField(
        default=0, help_text='Lo abonado hasta ahora. Permite el pago parcial.')
    ocurrencias = models.PositiveSmallIntegerField(
        help_text='Cuántos días del permiso caen en ese mes (trazabilidad del cálculo).')
    estado = models.CharField(max_length=25, choices=ESTADO_CHOICES, default='activa')
    fecha_pago = models.DateField(
        null=True, blank=True,
        help_text='Fecha del pago que la SALDÓ (no la del primer abono parcial).')
    # Si una sanción cumplida extinguió esta deuda, aquí queda de cuál se trata. Es la
    # trazabilidad que exige la regla: la deuda deja de cobrarse, pero no de explicarse.
    sancion_consumidora = models.ForeignKey(
        'empleados.SancionEmpleado', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deudas_permiso_consumidas')
    fecha_consumo = models.DateField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    historial = HistoricalRecords()

    class Meta:
        verbose_name = 'Deuda mensual de permiso'
        verbose_name_plural = 'Deudas mensuales de permisos'
        ordering = ['anio', 'mes', 'permiso']
        constraints = [
            models.UniqueConstraint(fields=['permiso', 'anio', 'mes'],
                                    name='deuda_permiso_mes_unica'),
        ]
        indexes = [
            models.Index(fields=['explorador', 'estado'], name='dpm_exp_estado_idx'),
            models.Index(fields=['explorador', 'anio', 'mes'], name='dpm_exp_periodo_idx'),
        ]

    @property
    def minutos_pendientes(self) -> int:
        """Lo que falta por pagar. Nunca negativo: un exceso no genera crédito."""
        return max(0, self.minutos_generados - self.minutos_pagados)

    @property
    def horas_generadas(self) -> float:
        return round(self.minutos_generados / 60, 2)

    @property
    def horas_pagadas(self) -> float:
        return round(self.minutos_pagados / 60, 2)

    @property
    def horas_pendientes(self) -> float:
        return round(self.minutos_pendientes / 60, 2)

    @property
    def periodo(self):
        """El mes al que pertenece, en el vocabulario de la capa de cálculo de sanciones."""
        from solicitudes.services.sancion_deuda_calculo import Periodo
        return Periodo(self.anio, self.mes)

    def __str__(self):
        return (f'{self.explorador} — permiso {self.permiso_id} '
                f'{self.anio}-{self.mes:02d}: {self.horas_pendientes} h pendientes')


class PagoDeudaPermisoMes(models.Model):
    """
    Cuántos minutos de una deuda mensual cubre un PDH concreto.

    Es la tabla intermedia del M2M y guarda el importe porque el pago puede ser PARCIAL:
    sin este dato, borrar un PDH no sabría cuánto devolver a la deuda y la dejaría o
    saldada de más o resucitada entera.
    """
    pdh = models.ForeignKey(PDH, on_delete=models.CASCADE, related_name='detalles_permiso_mes')
    # PROTECT: una deuda con pagos encima no puede desaparecer y dejar el PDH cuadrando
    # con la nada. Primero se revierte el pago, después se toca la deuda.
    deuda = models.ForeignKey(DeudaPermisoMes, on_delete=models.PROTECT, related_name='pagos')
    minutos = models.PositiveIntegerField(help_text='Minutos de esa deuda que cubre este pago.')

    class Meta:
        verbose_name = 'Detalle de pago de deuda mensual'
        verbose_name_plural = 'Detalles de pago de deudas mensuales'
        constraints = [
            models.UniqueConstraint(fields=['pdh', 'deuda'], name='pago_deuda_permiso_mes_unico'),
        ]

    def __str__(self):
        return f'PDH {self.pdh_id} → deuda {self.deuda_id}: {self.minutos} min'
