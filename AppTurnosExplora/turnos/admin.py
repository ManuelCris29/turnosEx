from django.contrib import admin
from .models import (
    AsignarJornadaExplorador, AsignarSalaExplorador,
    Turno, DiaEspecial, TurnoArchivo
)


@admin.register(AsignarJornadaExplorador)
class AsignarJornadaExploradorAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'jornada', 'fecha_inicio']
    list_filter = ['jornada', 'fecha_inicio']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'explorador__cedula']
    date_hierarchy = 'fecha_inicio'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'jornada')


@admin.register(AsignarSalaExplorador)
class AsignarSalaExploradorAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'sala', 'fecha_inicio', 'fecha_fin']
    list_filter = ['sala', 'fecha_inicio']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'explorador__cedula']
    date_hierarchy = 'fecha_inicio'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'sala')


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'fecha', 'jornada', 'sala', 'tipo_cambio']
    list_filter = ['jornada', 'sala', 'tipo_cambio', 'fecha']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'explorador__cedula']
    date_hierarchy = 'fecha'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'jornada', 'sala')


@admin.register(DiaEspecial)
class DiaEspecialAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'tipo', 'recurrente', 'activo', 'es_temporada', 'año_planificacion']
    list_filter = ['tipo', 'recurrente', 'activo', 'es_temporada', 'año_planificacion']
    search_fields = ['tipo', 'descripcion']
    date_hierarchy = 'fecha'


@admin.register(TurnoArchivo)
class TurnoArchivoAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'fecha', 'jornada', 'sala', 'fecha_archivado']
    list_filter = ['jornada', 'sala', 'fecha_archivado']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'explorador__cedula']
    date_hierarchy = 'fecha_archivado'
    readonly_fields = ['fecha_archivado', 'turno_original_id']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'jornada', 'sala')
