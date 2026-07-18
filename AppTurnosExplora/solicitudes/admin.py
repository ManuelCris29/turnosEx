from django.contrib import admin
from .models import (
    Notificacion, TipoSolicitudCambio, SolicitudCambio,
    CambioPermanenteDetalle, CambioPermanenteDia,
    DobladaDetalle, DeudaExplorador, DeudaCorporativa,
    ReprogramacionDiaDoblada,
)


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
    readonly_fields = ['fecha_solicitud', 'fecha_resolucion']
    
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
