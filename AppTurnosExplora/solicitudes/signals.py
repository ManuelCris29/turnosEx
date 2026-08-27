"""
Señales de la app solicitudes.

Cuando se BORRA una SolicitudCambio, su FK en las deudas (DeudaCorporativa) es
on_delete=SET_NULL, por lo que la deuda quedaría 'activa' pero huérfana (sin solicitud
de origen) y seguiría sumando en el Consolidado de Horas dentro del bucket "Otras".

Para evitar esos huérfanos, al borrar una solicitud cancelamos (no borramos) sus deudas
corporativas: se conserva la traza histórica pero dejan de contar.
"""
import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from .models import DeudaCorporativa, DeudaExplorador, SolicitudCambio

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=SolicitudCambio)
def cancelar_deudas_al_borrar_solicitud(sender, instance, **kwargs):
    """
    Cancela las deudas de una solicitud antes de borrarla.

    Cubre los DOS modelos de deuda, igual que `cancelar_deudas_al_cancelar_solicitud`. Antes solo
    tocaba las corporativas: al borrar una solicitud que no pasaba por la cancelación —una
    rechazada, por ejemplo— las deudas entre exploradores quedaban vivas apuntando
    a `solicitud_origen=NULL`, imposibles de relacionar con nada.
    """
    corp = (
        DeudaCorporativa.objects
        .filter(solicitud_origen=instance, estado='activa')
        .update(estado='cancelada')
    )
    entre = (
        DeudaExplorador.objects
        .filter(solicitud_origen=instance)
        .exclude(estado='cancelada')
        .update(estado='cancelada')
    )
    if corp or entre:
        logger.info(
            "Solicitud %s borrada: %s deuda(s) corporativa(s) y %s entre exploradores "
            "canceladas para no dejarlas huérfanas.",
            instance.id, corp, entre,
        )


# Estados que dejan a la solicitud SIN efecto vigente: sus deudas no pueden seguir vivas.
# - 'cancelada': se revirtió (ventana de 30 min, admin, comando o script).
# - 'reemplazada': una solicitud posterior pisó sus turnos ("lo último aprobado gana por día").
#   Económicamente es lo mismo: ya no hay doblada real detrás de esos 30 min. Si se deja fuera,
#   vuelve por la puerta de al lado el bug que motivó este patrón — deuda viva sin doblada.
ESTADOS_SIN_EFECTO_VIGENTE = ('cancelada', 'reemplazada')


@receiver(post_save, sender=SolicitudCambio)
def cancelar_deudas_al_cancelar_solicitud(sender, instance, **kwargs):
    """
    Una solicitud CANCELADA o REEMPLAZADA no puede dejar deudas vivas.

    `CancelarSolicitudUseCase` ya las cancela al revertir, pero el estado se puede poner en
    un estado terminal por otras vías que NO pasan por ahí: el admin de Django (el campo es
    editable), un management command (p. ej. `corregir_doblada_cesion_total` al unificar una
    cesión total), un script de mantenimiento, o `_marcar_reemplazadas` al aplicar un cambio
    de descanso posterior. Por esas vías las deudas quedaban activas y el explorador seguía
    debiendo 30 min por una solicitud que ya no tiene efecto.

    Es idempotente: si el use case ya las canceló, este filtro no encuentra filas.
    """
    if instance.estado not in ESTADOS_SIN_EFECTO_VIGENTE:
        return

    corp = (
        DeudaCorporativa.objects
        .filter(solicitud_origen=instance, estado='activa')
        .update(estado='cancelada')
    )
    entre = (
        DeudaExplorador.objects
        .filter(solicitud_origen=instance)
        .exclude(estado='cancelada')
        .update(estado='cancelada')
    )
    if corp or entre:
        logger.info(
            "Solicitud %s %s: %s deuda(s) corporativa(s) y %s entre exploradores canceladas.",
            instance.id, instance.estado, corp, entre,
        )
