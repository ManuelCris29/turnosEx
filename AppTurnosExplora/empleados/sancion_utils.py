"""
Utilidades de sanciones.

Una sanción tiene un rango de fechas durante el cual el explorador NO puede
realizar ninguna solicitud (cambio de turno ni permiso).
"""

import logging

from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def invalidar_cache_turnos(sancion):
    """Refresca Mis Turnos del explorador en todos los meses que la sanción puede afectar.

    IMPLEMENTACIÓN ÚNICA a propósito. Había dos, y ya habían divergido: la de la vista de
    sanciones llegaba hasta `fecha_fin`, y la del servicio de deuda extendía SIEMPRE un año
    hacia adelante. Cuál se ejecutaba dependía de por dónde entrara el usuario (levantar la
    sanción a mano o la revisión automática), así que el mismo hecho dejaba la caché en dos
    estados distintos.

    Se conserva la versión que cubre más: invalidar de MÁS solo cuesta un recálculo, mientras
    que invalidar de MENOS deja a alguien viendo unos turnos que ya no son los suyos. El año
    extra es el que necesitan las sanciones indefinidas —se muestran en todos los meses
    futuros— y las que acaban de levantarse, cuyos meses cacheados hay que refrescar.

    Nunca lanza: que falle un borrado de caché no puede tumbar el guardado de la sanción.
    """
    try:
        from datetime import date, timedelta

        from core.services.cache_service import CacheService

        hoy = timezone.localdate()
        desde = sancion.fecha_inicio
        hasta = max(sancion.fecha_fin or hoy, hoy + timedelta(days=365))
        meses = set()
        d = date(desde.year, desde.month, 1)
        while d <= hasta:
            meses.add((d.month, d.year))
            d = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
        for m, y in meses:
            CacheService.invalidar_cache_turnos_empleado(sancion.explorador_id, m, y)
    except Exception:
        logger.warning('Error invalidando caché de turnos por sanción (explorador=%s)',
                       getattr(sancion, 'explorador_id', '?'), exc_info=True)


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


def refrescar_y_sancion(empleado, fecha=None):
    """
    Punto de entrada ÚNICO para "¿puede este explorador hacer solicitudes?".

    Primero refresca la auto-sanción por deuda de doblada vencida y solo después consulta.
    El orden importa: la sanción por deuda NO existe hasta que algo la crea, así que
    llamar a `sancion_activa()` a secas responde "no sancionado" sobre una deuda vencida
    que todavía nadie evaluó. Eso es justo lo que dejaba las pantallas abiertas a un
    explorador moroso: los formularios se abrían y se llenaban enteros, y el bloqueo solo
    aparecía al enviar (que era, además, el momento en que la sanción nacía).

    Usa esta función en TODA pantalla o endpoint que decida si alguien puede solicitar.
    `sancion_activa()` queda para lecturas que ya vienen detrás de un refresco, o para
    consultar la sanción de OTRA persona en una fecha dada (informes, aprobación).

    Nunca lanza: si el refresco falla, se registra y se responde con lo que haya en BD.
    Un fallo aquí no puede tumbar la pantalla de un explorador que no debe nada.
    """
    if not empleado:
        return None
    try:
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
        DeudaCorporativaService.gestionar_sancion_por_deuda(empleado)
    except Exception:
        logger.exception('Error gestionando la sanción automática por deuda (empleado=%s)',
                         getattr(empleado, 'id', '?'))
    return sancion_activa(empleado, fecha)
