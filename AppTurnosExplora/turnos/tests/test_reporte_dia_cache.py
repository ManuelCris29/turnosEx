"""
Caché de `ReporteDiaService.reporte` y `_deuda_del_corte` (turnos/api/views/reportes.py).

TTL corto (5 min) sin invalidación explícita: ver los docstrings de ambas
funciones para la justificación. Estos tests fijan:
1. Que la segunda llamada para la misma fecha no vuelve a tocar la base de datos.
2. Que `_deuda_del_corte` no cachea `proyectada` (depende de "hoy", no de la
   fecha consultada) aunque sí cachee las filas de deuda.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from empleados.models import Empleado
from turnos.api.views.reportes import _deuda_del_corte
from turnos.services.reporte_dia_service import ReporteDiaService

FECHA = date(2029, 5, 9)  # miércoles, año lejano sin datos de otros tests


class ReporteDiaCacheTest(TestCase):

    def setUp(self):
        cache.clear()
        user = User.objects.create_user(username='rep_cache', password='x')
        self.empleado = Empleado.objects.create(
            user=user, nombre='Rep', apellido='Cache', cedula='7001', activo=True,
        )

    def test_segunda_llamada_a_reporte_no_golpea_la_base_de_datos(self):
        ReporteDiaService.reporte(FECHA)  # cache miss: calcula y guarda

        with self.assertNumQueries(0):
            ReporteDiaService.reporte(FECHA)

    def test_el_contenido_cacheado_es_igual_al_calculado_sin_cache(self):
        cacheado = ReporteDiaService.reporte(FECHA)
        sin_cache = ReporteDiaService._reporte_bd(FECHA)
        self.assertEqual(cacheado['dia_info'], sin_cache['dia_info'])


class DeudaDelCorteCacheTest(TestCase):

    def setUp(self):
        cache.clear()

    def test_segunda_llamada_no_golpea_la_base_de_datos(self):
        _deuda_del_corte(FECHA)  # cache miss: calcula y guarda las filas

        with self.assertNumQueries(0):
            _deuda_del_corte(FECHA)

    def test_proyectada_no_queda_pegada_al_primer_valor_cacheado(self):
        """Reproduce el escenario real: la MISMA fecha, "hoy" distinto en cada llamada.

        Antes de separar `proyectada` de la parte cacheada, la segunda llamada
        devolvía el rótulo de la primera (PROYECTADA pegado) porque la clave de
        caché no dependía de "hoy". Este test fija que no vuelva a pasar.
        """
        with patch('django.utils.timezone.localdate', return_value=FECHA - timedelta(5)):
            _, resumen_futuro = _deuda_del_corte(FECHA)
        self.assertTrue(resumen_futuro['proyectada'])

        with patch('django.utils.timezone.localdate', return_value=FECHA + timedelta(5)):
            _, resumen_pasado = _deuda_del_corte(FECHA)
        self.assertFalse(resumen_pasado['proyectada'])
