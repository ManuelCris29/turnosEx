"""
Pruebas de la comprobación de despliegue de la caché (core/checks.py).

Esta comprobación es la red que impide repetir un fallo concreto: salir a
producción con LocMemCache y varios workers de Gunicorn, lo que hace que
invalidar Mis Turnos limpie un solo proceso y los demás sirvan datos viejos.
"""
from django.test import override_settings

from core.checks import LOCMEM, cache_compartida_en_produccion

REDIS = {'default': {'BACKEND': 'django.core.cache.backends.redis.RedisCache',
                     'LOCATION': 'redis://localhost:6379/1'}}
LOCAL = {'default': {'BACKEND': LOCMEM, 'LOCATION': 'appturnos'}}


class TestCacheCompartidaEnProduccion:

    @override_settings(IS_PRODUCTION=True, CACHES=LOCAL)
    def test_error_si_produccion_usa_cache_local(self):
        errores = cache_compartida_en_produccion(None)

        assert len(errores) == 1
        assert errores[0].id == 'core.E001'
        assert 'CACHE_URL' in errores[0].hint

    @override_settings(IS_PRODUCTION=True, CACHES=REDIS)
    def test_sin_error_si_produccion_usa_cache_compartida(self):
        assert cache_compartida_en_produccion(None) == []

    @override_settings(IS_PRODUCTION=False, CACHES=LOCAL)
    def test_sin_error_en_desarrollo(self):
        """En desarrollo (un solo proceso) LocMemCache es correcta."""
        assert cache_compartida_en_produccion(None) == []
