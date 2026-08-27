from django.contrib import admin

from .models import (
    CambioPermanenteDetalle,
    CambioPermanenteDia,
    CierreSemanaOverride,
    CierreSolicitudesConfig,
    ConfiguracionSanciones,
    DeudaCorporativa,
    DeudaExplorador,
    DobladaDetalle,
    EmailOutbox,
    Notificacion,
    ReprogramacionDiaDoblada,
    RevisionSancionesDeuda,
    SolicitudCambio,
    TipoSolicitudCambio,
)


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    """
    Ventana a la cola de correos. Su razón de ser es el filtro por estado='fallido':
    esos agotaron los reintentos y nadie los va a recoger ya, así que son los únicos
    que exigen intervención humana. El resto se resuelve solo.
    """
    list_display = ['asunto', 'destinatarios', 'estado', 'intentos', 'creado_en', 'enviado_en']
    list_filter = ['estado', 'creado_en']
    search_fields = ['asunto', 'clave_idempotencia']
    date_hierarchy = 'creado_en'
    # Todo es de solo lectura: editar a mano una fila de la cola solo puede provocar
    # un reenvío indebido o dejarla en un estado que el worker no sepa interpretar.
    readonly_fields = [f.name for f in EmailOutbox._meta.fields]

    def has_add_permission(self, request):
        return False

    @admin.action(description='Reintentar el envío ahora')
    def reintentar(self, request, queryset):
        """Reencola los seleccionados: vuelve a 'pendiente' y disponible de inmediato."""
        from django.utils import timezone

        actualizadas = queryset.exclude(estado=EmailOutbox.ESTADO_ENVIADO).update(
            estado=EmailOutbox.ESTADO_PENDIENTE, intentos=0, disponible_en=timezone.now())
        self.message_user(
            request,
            f'{actualizadas} correo(s) reencolados; el worker los tomará en la próxima pasada. '
            f'Los ya enviados se ignoran para no duplicarlos.')

    actions = ['reintentar']


@admin.register(CierreSolicitudesConfig)
class CierreSolicitudesConfigAdmin(admin.ModelAdmin):
    list_display = ['habilitado', 'dia_cierre', 'hora_cierre', 'actualizado_en']


@admin.register(ConfiguracionSanciones)
class ConfiguracionSancionesAdmin(admin.ModelAdmin):
    list_display = ['dias_ventana_reincidencia', 'actualizado_por', 'actualizado_en']

    def has_add_permission(self, request):
        # Singleton: una segunda fila dejaría ambiguo cuál es la configuración vigente.
        return not ConfiguracionSanciones.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Sin fila no hay política que consultar. Para cambiarla se edita, no se borra.
        return False


@admin.register(CierreSemanaOverride)
class CierreSemanaOverrideAdmin(admin.ModelAdmin):
    list_display = ['semana_lunes', 'habilitado', 'dia_cierre', 'hora_cierre']
    list_filter = ['habilitado', 'dia_cierre']


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'destinatario', 'tipo', 'leida', 'fecha_creacion']
    list_filter = ['tipo', 'leida', 'fecha_creacion']
    search_fields = ['titulo', 'mensaje', 'destinatario__nombre', 'destinatario__apellido']
    date_hierarchy = 'fecha_creacion'
    readonly_fields = ['fecha_creacion', 'fecha_lectura']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('destinatario', 'solicitud')


@admin.register(TipoSolicitudCambio)
class TipoSolicitudCambioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'codigo_estrategia', 'activo', 'genera_deuda']
    list_filter = ['activo', 'genera_deuda']
    search_fields = ['nombre', 'codigo_estrategia']


@admin.register(SolicitudCambio)
class SolicitudCambioAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'tipo_cambio', 'explorador_solicitante', 'explorador_receptor',
        'fecha_cambio_turno', 'estado', 'fecha_solicitud'
    ]
    list_filter = ['estado', 'tipo_cambio', 'fecha_solicitud', 'fecha_cambio_turno']
    search_fields = [
        'explorador_solicitante__nombre', 'explorador_solicitante__apellido',
        'explorador_receptor__nombre', 'explorador_receptor__apellido',
        'comentario'
    ]
    date_hierarchy = 'fecha_solicitud'
    # Las tres marcas de tiempo son un registro de auditoría: se muestran, no se editan.
    readonly_fields = ['fecha_solicitud', 'fecha_resolucion', 'fecha_cancelacion']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'explorador_solicitante', 'explorador_receptor', 'tipo_cambio',
            'turno_origen', 'turno_destino'
        )


@admin.register(CambioPermanenteDetalle)
class CambioPermanenteDetalleAdmin(admin.ModelAdmin):
    list_display = ['solicitud', 'fecha_inicio', 'fecha_fin']
    list_filter = ['fecha_inicio']
    search_fields = ['solicitud__id']
    date_hierarchy = 'fecha_inicio'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('solicitud')


@admin.register(CambioPermanenteDia)
class CambioPermanenteDiaAdmin(admin.ModelAdmin):
    list_display = ['cambio_permanente', 'tipo', 'fecha_especifica', 'dia_semana']
    list_filter = ['tipo', 'dia_semana']
    search_fields = ['cambio_permanente__solicitud__id']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('cambio_permanente')


@admin.register(DobladaDetalle)
class DobladaDetalleAdmin(admin.ModelAdmin):
    list_display = [
        'solicitud', 'fecha_pago', 'tipo_cesion', 'jornada_cedida',
        'jornada_cubre_en_pago', 'jornada_pago_sabado', 'minutos_deuda',
    ]
    list_filter = ['tipo_cesion', 'fecha_pago']
    search_fields = ['solicitud__id', 'empleado_receptor__nombre', 'empleado_receptor__apellido']
    date_hierarchy = 'fecha_pago'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('solicitud', 'empleado_receptor')


@admin.register(DeudaExplorador)
class DeudaExploradorAdmin(admin.ModelAdmin):
    list_display = ['deudor', 'acreedor', 'fecha_pago_pactada', 'estado', 'jornada_cedida', 'media_jornada']
    list_filter = ['estado', 'jornada_cedida', 'media_jornada', 'fecha_pago_pactada']
    search_fields = [
        'deudor__nombre', 'deudor__apellido',
        'acreedor__nombre', 'acreedor__apellido'
    ]
    date_hierarchy = 'fecha_generacion'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('deudor', 'acreedor', 'solicitud_origen')


@admin.register(DeudaCorporativa)
class DeudaCorporativaAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'minutos', 'fecha_doblada', 'estado', 'fecha_generacion']
    list_filter = ['estado', 'fecha_generacion', 'fecha_doblada']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'comentario']
    date_hierarchy = 'fecha_generacion'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'solicitud_origen')


@admin.register(ReprogramacionDiaDoblada)
class ReprogramacionDiaDobladaAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'doblada_origen', 'fecha_original', 'fecha_reprogramada', 'estado', 'registrado_por', 'creado_en']
    list_filter = ['estado', 'creado_en']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'motivo']
    date_hierarchy = 'creado_en'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'doblada_origen', 'registrado_por')


@admin.register(RevisionSancionesDeuda)
class RevisionSancionesDeudaAdmin(admin.ModelAdmin):
    """
    Bitácora de la revisión diaria de sanciones por deuda.

    Sirve para responder "¿corrió ayer?" cuando el cron falla en silencio: debe haber una
    fila por día. Un hueco en las fechas es la señal de que la tarea programada no se
    ejecutó — ver MANUAL_SANCIONES_DEUDA.md, sección 8.
    """
    list_display = ('fecha', 'ejecutado_en', 'sanciones_creadas', 'sanciones_levantadas')
    list_filter = ('fecha',)
    ordering = ('-fecha',)
    readonly_fields = ('fecha', 'ejecutado_en', 'sanciones_creadas',
                       'sanciones_levantadas', 'detalle')

    def has_add_permission(self, request):
        # Crear una fila a mano equivaldría a decirle al proceso que ese día ya se hizo,
        # y el trabajo real quedaría sin ejecutar.
        return False
