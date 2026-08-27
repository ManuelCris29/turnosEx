from django.contrib import admin

from .models import (
    CompetenciaEmpleado,
    Empleado,
    EmpleadoRole,
    Jornada,
    RestriccionEmpleado,
    Role,
    Sala,
    SancionEmpleado,
)


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    # `email` ya no es una columna de Empleado: vive en la cuenta (ver
    # `Empleado.email`). Como list_display admite propiedades pero no sabe
    # ordenar por ellas, se expone via metodo con su ruta ORM real; la busqueda
    # necesita esa misma ruta o el admin revienta al escribir en el buscador.
    list_display = ['nombre', 'apellido', 'email_cuenta', 'supervisor', 'activo']
    list_filter = ['activo', 'supervisor']
    search_fields = ['nombre', 'apellido', 'user__email', 'cedula']

    @admin.display(description='Email', ordering='user__email')
    def email_cuenta(self, obj):
        return obj.email
    autocomplete_fields = ['supervisor']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('supervisor', 'user')
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "supervisor":
            kwargs["queryset"] = Empleado.objects.filter(
                activo=True,
                empleadorole__role__nombre__iexact=Role.SUPERVISOR
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'es_protegido']

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
    list_display = ['explorador', 'supervisor', 'fecha_inicio', 'fecha_fin', 'levantada_en']
    list_filter = ['fecha_inicio', 'levantada_en']
    readonly_fields = ['levantada_en', 'levantada_por', 'levantada_motivo']

    def has_delete_permission(self, request, obj=None):
        """
        Una sanción no se borra: es un hecho disciplinario y su registro debe
        sobrevivir, también cuando se puso por error (ahí se levanta indicándolo
        como motivo). Bloqueado también aquí porque si no el admin sería la puerta
        de atrás que deja sin efecto la regla en el resto de la aplicación.
        """
        return False

    def get_actions(self, request):
        # La acción masiva de borrado no pasa por has_delete_permission de cada objeto.
        actions = super().get_actions(request)
        actions.pop('delete_selected', None)
        return actions
