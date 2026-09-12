"""
Señales de `empleados`.

Invalidación del caché de `sesiones_habilitadas` (core/permisos_sesion.py) ante
CUALQUIER escritura de `PermisoSesion`. Se usa una señal de modelo y no una
llamada explícita en la vista porque `PermisoSesion` tiene más de un camino de
escritura real: `PermisosSesionUpdateView`, el admin de Django
(`PermisoSesionAdmin`, empleados/admin.py) y, en tests, la creación directa por
ORM. Un solo punto de invalidación en el modelo cubre los tres sin tener que
acordarse de llamarlo en cada uno.

Misma razón para los catálogos de Sala y Jornada (empleados/views/salas.py,
jornadas.py): también se editan desde el admin y se crean por ORM en decenas
de tests.
"""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from core.permisos_sesion import invalidar_cache_sesiones
from core.services.cache_service import CacheService

from .models import Empleado, Jornada, PermisoSesion, Sala


@receiver(post_save, sender=PermisoSesion)
@receiver(post_delete, sender=PermisoSesion)
def _invalidar_cache_sesiones_al_escribir(sender, instance, **kwargs):
    try:
        invalidar_cache_sesiones(instance.empleado.user_id)
    except Empleado.DoesNotExist:
        # El empleado ya se borró en cascada (post_delete durante la baja de un
        # Empleado): su caché de permisos ya no le importa a nadie.
        pass


@receiver(post_save, sender=Sala)
@receiver(post_delete, sender=Sala)
def _invalidar_catalogo_salas(sender, **kwargs):
    CacheService.delete('catalogo_salas_v1')


@receiver(post_save, sender=Jornada)
@receiver(post_delete, sender=Jornada)
def _invalidar_catalogo_jornadas(sender, **kwargs):
    CacheService.delete('catalogo_jornadas_v1')
