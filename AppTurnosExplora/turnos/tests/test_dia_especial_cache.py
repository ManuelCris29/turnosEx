"""
Caché de `DiaEspecial.es_festivo` / `es_mantenimiento_efectivo` / `es_temporada_en`.

Clave versionada (`turnos/models.py::DiaEspecial._version_cache`) + invalidación
por señal (`turnos/signals.py`) ante cualquier escritura del modelo, sin
importar el camino (servicio, admin, o creación directa en tests).
"""
from datetime import date

from django.core.cache import cache
from django.test import TestCase

from turnos.models import DiaEspecial

ANIO = 2031  # año lejano, sin datos de otros tests ni de fixtures reales


class DiaEspecialCacheTest(TestCase):

    def setUp(self):
        cache.clear()

    def test_segunda_llamada_a_es_festivo_no_golpea_la_base_de_datos(self):
        fecha = date(ANIO, 1, 1)
        self.assertFalse(DiaEspecial.es_festivo(fecha))  # cache miss: calcula y guarda

        with self.assertNumQueries(0):
            self.assertFalse(DiaEspecial.es_festivo(fecha))

    def test_crear_festivo_invalida_el_cache(self):
        fecha = date(ANIO, 1, 6)
        self.assertFalse(DiaEspecial.es_festivo(fecha))  # cachea False

        DiaEspecial.objects.create(fecha=fecha, tipo='festivo')

        self.assertTrue(DiaEspecial.es_festivo(fecha))

    def test_borrar_festivo_invalida_el_cache(self):
        fecha = date(ANIO, 1, 6)
        dia = DiaEspecial.objects.create(fecha=fecha, tipo='festivo')
        self.assertTrue(DiaEspecial.es_festivo(fecha))  # cachea True

        dia.delete()

        self.assertFalse(DiaEspecial.es_festivo(fecha))

    def test_temporada_invalida_tambien_el_cache_de_mantenimiento(self):
        """La temporada tiene prioridad sobre mantenimiento; crearla después debe reflejarse."""
        fecha = date(ANIO, 6, 1)
        DiaEspecial.objects.create(fecha=fecha, tipo='mantenimiento')
        self.assertTrue(DiaEspecial.es_mantenimiento_efectivo(fecha))  # cachea True

        DiaEspecial.objects.create(fecha=fecha, tipo='temporada', es_temporada=True)

        self.assertFalse(
            DiaEspecial.es_mantenimiento_efectivo(fecha),
            'la temporada manda sobre mantenimiento; el cache viejo no debe pisar la regla',
        )

    def test_version_del_cache_sube_con_cada_escritura(self):
        version_inicial = DiaEspecial._version_cache()

        DiaEspecial.objects.create(fecha=date(ANIO, 2, 1), tipo='festivo')

        self.assertGreater(DiaEspecial._version_cache(), version_inicial)
