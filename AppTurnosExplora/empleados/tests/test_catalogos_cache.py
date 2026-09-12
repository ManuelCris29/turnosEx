"""
Caché de los catálogos casi-estáticos Sala y Jornada (empleados/views/salas.py,
jornadas.py). TTL de 24h + invalidación por señal (empleados/signals.py) ante
cualquier escritura del modelo, sin importar el camino (vista, admin o
creación directa en tests).
"""
from django.core.cache import cache
from django.test import TestCase

from empleados.models import Jornada, Sala
from empleados.views.jornadas import JornadaListView
from empleados.views.salas import SalaListView


class CatalogoSalasCacheTest(TestCase):

    def setUp(self):
        cache.clear()

    def test_segunda_llamada_no_golpea_la_base_de_datos(self):
        Sala.objects.create(nombre='Sala 1', activo=True)

        list(SalaListView().get_queryset())  # cache miss: calcula y guarda

        with self.assertNumQueries(0):
            resultado = list(SalaListView().get_queryset())
        self.assertEqual(len(resultado), 1)

    def test_crear_sala_invalida_el_cache(self):
        list(SalaListView().get_queryset())  # cachea la lista vacía

        Sala.objects.create(nombre='Sala nueva', activo=True)

        self.assertEqual(len(list(SalaListView().get_queryset())), 1)

    def test_borrar_sala_invalida_el_cache(self):
        sala = Sala.objects.create(nombre='Sala X', activo=True)
        list(SalaListView().get_queryset())  # cachea con 1 fila

        sala.delete()

        self.assertEqual(len(list(SalaListView().get_queryset())), 0)


class CatalogoJornadasCacheTest(TestCase):

    def setUp(self):
        cache.clear()

    def test_segunda_llamada_no_golpea_la_base_de_datos(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')

        list(JornadaListView().get_queryset())  # cache miss

        with self.assertNumQueries(0):
            resultado = list(JornadaListView().get_queryset())
        self.assertEqual(len(resultado), 1)

    def test_crear_jornada_invalida_el_cache(self):
        list(JornadaListView().get_queryset())  # cachea vacío

        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')

        self.assertEqual(len(list(JornadaListView().get_queryset())), 1)
