"""
Context processors globales.
"""
from core.mixins import es_supervisor


def permisos(request):
    """
    Expone el permiso de administración a todas las plantillas.

    El menú lateral usaba `user.is_staff`, así que un empleado con rol
    Supervisor entraba a las vistas (protegidas por `AdminRequiredMixin`,
    que sí acepta el rol) pero no veía los enlaces. Se usa un nombre propio
    (`puede_administrar`) para no chocar con el `es_supervisor` que varias
    vistas ya inyectan en su contexto.
    """
    return {'puede_administrar': es_supervisor(getattr(request, 'user', None))}
