from django.contrib import admin

from .models import PDH, PermisoEspecial


@admin.register(PDH)
class PDHAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'fecha', 'horas', 'supervisor', 'tipo_registro']
    list_filter = ['tipo_registro', 'fecha']
    search_fields = ['explorador__nombre', 'explorador__apellido', 'explorador__cedula']
    date_hierarchy = 'fecha'
    ordering = ['-fecha', 'explorador']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('explorador', 'supervisor', 'solicitud')


@admin.register(PermisoEspecial)
class PermisoEspecialAdmin(admin.ModelAdmin):
    list_display = ['empleado', 'tipo', 'fecha_inicio', 'fecha_fin', 'estado', 'supervisor']
    list_filter = ['tipo', 'estado', 'fecha_inicio']
    search_fields = ['empleado__nombre', 'empleado__apellido', 'empleado__cedula', 'motivo']
    date_hierarchy = 'fecha_inicio'
    ordering = ['-fecha_inicio', 'empleado']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('empleado', 'supervisor')
