"""
Caché del catálogo TipoSolicitudCambio (solicitudes/views/dashboard_admin.py).
TTL de 1h + invalidación por señal (solicitudes/signals.py).
"""
from django.core.cache import cache
from django.test import TestCase

from solicitudes.models import TipoSolicitudCambio
from solicitudes.views.dashboard_admin import TipoSolicitudCambioListView


class CatalogoTiposSolicitudCacheTest(TestCase):

    def setUp(self):
        cache.clear()

    def test_segunda_llamada_no_golpea_la_base_de_datos(self):
        TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')

        list(TipoSolicitudCambioListView().get_queryset())  # cache miss

        with self.assertNumQueries(0):
            resultado = list(TipoSolicitudCambioListView().get_queryset())
        self.assertEqual(len(resultado), 1)

    def test_crear_tipo_invalida_el_cache(self):
        list(TipoSolicitudCambioListView().get_queryset())  # cachea vacío

        TipoSolicitudCambio.objects.create(nombre='DOBLADA')

        self.assertEqual(len(list(TipoSolicitudCambioListView().get_queryset())), 1)

    def test_borrar_tipo_invalida_el_cache(self):
        tipo = TipoSolicitudCambio.objects.create(nombre='CT PERMANENTE')
        list(TipoSolicitudCambioListView().get_queryset())  # cachea con 1 fila

        tipo.delete()

        self.assertEqual(len(list(TipoSolicitudCambioListView().get_queryset())), 0)
