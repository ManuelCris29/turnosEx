"""
Utilidades de sanciones.

Una sanción tiene un rango de fechas durante el cual el explorador NO puede
realizar ninguna solicitud (cambio de turno ni permiso).
"""

from django.db.models import Q
from django.utils import timezone


def vigentes_en(fecha=None):
    """
    Filtro ÚNICO de "sanción que bloquea en `fecha`". Toda comprobación de sanción
    debe partir de aquí: si cada sitio rearma las condiciones a mano, basta con que
    uno olvide una para que un sancionado pase o un levantado siga bloqueado.

    Vigente = la fecha cae en el rango Y la sanción no se ha levantado antes de ella.
    `fecha_fin` nula = indefinida.
    """
    f = fecha or timezone.localdate()
    return (
        Q(fecha_inicio__lte=f)
        & (Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=f))
        & (Q(levantada_en__isnull=True) | Q(levantada_en__gt=f))
    )


def sancion_activa(empleado, fecha=None):
    """
    Devuelve la sanción vigente del explorador en la fecha dada (hoy por defecto),
    o None si no está sancionado.
    """
    if not empleado:
        return None
    from .models import SancionEmpleado
    return (
        SancionEmpleado.objects
        .filter(vigentes_en(fecha), explorador=empleado)
        .select_related('supervisor')
        .order_by('-fecha_inicio')
        .first()
    )


def mensaje_sancion(sancion):
    """Mensaje claro para mostrar al explorador bloqueado."""
    if not sancion:
        return ''
    fin = sancion.fecha_fin.strftime('%d/%m/%Y') if sancion.fecha_fin else 'indefinida'
    return (
        f'Estás sancionado del {sancion.fecha_inicio.strftime("%d/%m/%Y")} al {fin}. '
        'Durante la sanción no puedes realizar solicitudes de cambio de turno ni de permisos.'
    )
