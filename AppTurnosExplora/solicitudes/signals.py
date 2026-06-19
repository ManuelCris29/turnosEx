"""
Señales de la app solicitudes.

Cuando se BORRA una SolicitudCambio, su FK en las deudas (DeudaCorporativa) es
on_delete=SET_NULL, por lo que la deuda quedaría 'activa' pero huérfana (sin solicitud
de origen) y seguiría sumando en el Consolidado de Horas dentro del bucket "Otras".

Para evitar esos huérfanos, al borrar una solicitud cancelamos (no borramos) sus deudas
corporativas: se conserva la traza histórica pero dejan de contar.
"""
import logging
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import SolicitudCambio, DeudaCorporativa

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=SolicitudCambio)
def cancelar_deudas_al_borrar_solicitud(sender, instance, **kwargs):
    """Cancela las deudas corporativas activas de una solicitud antes de borrarla."""
    actualizadas = (
        DeudaCorporativa.objects
        .filter(solicitud_origen=instance, estado='activa')
        .update(estado='cancelada')
    )
    if actualizadas:
        logger.info(
            "Solicitud %s borrada: %s deuda(s) corporativa(s) cancelada(s) para no dejarlas huérfanas.",
            instance.id, actualizadas,
        )
