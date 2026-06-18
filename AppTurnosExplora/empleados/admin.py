from django.contrib import admin
from .models import Empleado, Role, Sala, EmpleadoRole, CompetenciaEmpleado, Jornada, RestriccionEmpleado, SancionEmpleado

@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'apellido', 'email', 'supervisor', 'activo']
    list_filter = ['activo', 'supervisor']
    search_fields = ['nombre', 'apellido', 'email', 'cedula']
    autocomplete_fields = ['supervisor']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('supervisor', 'user')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "supervisor":
            kwargs["queryset"] = Empleado.objects.filter(
                activo=True, 
                empleadorole__role__nombre__icontains='supervisor'
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['nombre']

@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo']
    list_filter = ['activo']

@admin.register(EmpleadoRole)
class EmpleadoRoleAdmin(admin.ModelAdmin):
    list_display = ['empleado', 'role']
    list_filter = ['role']

@admin.register(CompetenciaEmpleado)
class CompetenciaEmpleadoAdmin(admin.ModelAdmin):
    list_display = ['empleado', 'sala']

@admin.register(Jornada)
class JornadaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'hora_inicio', 'hora_fin']

@admin.register(RestriccionEmpleado)
class RestriccionEmpleadoAdmin(admin.ModelAdmin):
    list_display = ['empleado', 'tipo_restriccion', 'fecha_inicio', 'fecha_fin']
    list_filter = ['tipo_restriccion']

@admin.register(SancionEmpleado)
class SancionEmpleadoAdmin(admin.ModelAdmin):
    list_display = ['explorador', 'supervisor', 'fecha_inicio', 'fecha_fin']
    list_filter = ['fecha_inicio']
