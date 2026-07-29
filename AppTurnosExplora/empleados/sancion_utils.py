"""
Utilidades de sanciones.

Una sanción tiene un rango de fechas durante el cual el explorador NO puede
realizar ninguna solicitud (cambio de turno ni permiso).
"""
from datetime import date as _date

from django.db.models import Q
from django.utils import timezone


def sancion_activa(empleado, fecha=None):
    """
    Devuelve la sanción activa del explorador en la fecha dada (hoy por defecto),
    o None si no está sancionado. fecha_fin nula = sanción indefinida.
    """
    if not empleado:
        return None
    from .models import SancionEmpleado
    f = fecha or timezone.localdate()
    return (
        SancionEmpleado.objects
        .filter(explorador=empleado, fecha_inicio__lte=f)
        .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=f))
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
