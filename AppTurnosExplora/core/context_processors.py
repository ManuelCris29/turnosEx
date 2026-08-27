"""
Context processors globales.
"""
from core.mixins import es_supervisor
from core.utils import comentarios


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


def mensajes_comentario(request):
    """
    Expone a TODAS las plantillas los textos del comentario obligatorio.

    Sin esto cada plantilla repetía el literal a mano y el navegador acababa avisando con
    unas palabras distintas de las que devolvía el servidor para el mismo fallo. Es un
    context processor y no algo que inyecte cada vista para que nadie tenga que acordarse
    al añadir una pantalla nueva.
    """
    return {
        'MSG_COMENTARIO': comentarios.MSG_COMENTARIO,
        'MSG_MOTIVO': comentarios.MSG_MOTIVO,
    }


def sesiones_permitidas(request):
    """
    Expone a todas las plantillas qué sesiones del menú ve este usuario.

    Se llama `sesiones` en la plantilla y es un dict {codigo: bool}, así que el
    menú pregunta `{% if sesiones.pdh %}`. Es un dict COMPLETO (incluye las
    apagadas con valor False) a propósito: en Django una clave que no existe y
    una que vale False se pintan igual, y con el dict completo un código mal
    escrito en la plantilla se detecta comparándolo con el catálogo en vez de
    esconder la entrada en silencio.
    """
    from core.permisos_sesion import sesiones_habilitadas
    return {'sesiones': sesiones_habilitadas(getattr(request, 'user', None))}
