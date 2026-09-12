"""
Señales de `turnos`.

Invalidación del caché de `DiaEspecial.es_festivo`/`es_mantenimiento_efectivo`/
`es_temporada_en` ante CUALQUIER escritura del modelo. Igual razón que
`empleados/signals.py` para `PermisoSesion`: `DiaEspecial` se escribe desde
`DiaEspecialService` (patrón "borrar el año y recrear"), pero también desde el
admin de Django y, en tests, por creación directa vía ORM — una señal en el
modelo cubre los tres sin depender de que cada camino se acuerde de invalidar.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.services.cache_service import CACHE_TTL_VERY_LONG, CacheService

from .models import DIA_ESPECIAL_VERSION_KEY, DiaEspecial


@receiver(post_save, sender=DiaEspecial)
@receiver(post_delete, sender=DiaEspecial)
def _bump_version_dia_especial(sender, **kwargs):
    version_actual = CacheService.get(DIA_ESPECIAL_VERSION_KEY, 0)
    CacheService.set(DIA_ESPECIAL_VERSION_KEY, version_actual + 1, ttl=CACHE_TTL_VERY_LONG)
