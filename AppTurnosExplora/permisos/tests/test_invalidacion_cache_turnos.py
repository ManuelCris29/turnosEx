"""
La caché de Mis Turnos guarda el mes entero por empleado con TTL largo. Si al aprobar o
revertir un permiso no cae la clave del mes AFECTADO, el explorador sigue viendo el horario
anterior hasta que expire (con Redis en producción no hay reinicio que lo tape).

Aquí se fija QUÉ meses hay que invalidar. El caso que se escapaba: la compensación de
MEDIA_JORNADA_TEMPORADA es un día de la misma semana, y una semana cruza el cambio de mes.
"""
from datetime import date

from django.test import TestCase

from permisos.views import _meses_afectados_por_permiso


class _PermisoFalso:
    """Doble mínimo: la función solo lee fechas, así que no hace falta tocar la BD."""

    def __init__(self, inicio, fin, compensacion=None):
        self.fecha_inicio = inicio
        self.fecha_fin = fin
        self.fecha_compensacion = compensacion


class MesesAfectadosPorPermisoTest(TestCase):

    def test_permiso_de_un_dia(self):
        p = _PermisoFalso(date(2026, 3, 10), date(2026, 3, 10))
        self.assertEqual(_meses_afectados_por_permiso(p), {(3, 2026)})

    def test_rango_que_cruza_varios_meses(self):
        p = _PermisoFalso(date(2026, 1, 15), date(2026, 4, 2))
        self.assertEqual(_meses_afectados_por_permiso(p),
                         {(1, 2026), (2, 2026), (3, 2026), (4, 2026)})

    def test_rango_corto_sobre_febrero_no_se_salta_el_mes_final(self):
        """El recorrido avanza de 28 en 28 días: febrero es justo el que se salta."""
        p = _PermisoFalso(date(2026, 2, 1), date(2026, 3, 1))
        self.assertEqual(_meses_afectados_por_permiso(p), {(2, 2026), (3, 2026)})

    def test_rango_que_cruza_el_cambio_de_anio(self):
        p = _PermisoFalso(date(2026, 12, 28), date(2027, 1, 4))
        self.assertEqual(_meses_afectados_por_permiso(p), {(12, 2026), (1, 2027)})

    def test_compensacion_en_el_mismo_mes_no_agrega_nada(self):
        p = _PermisoFalso(date(2026, 3, 10), date(2026, 3, 10), compensacion=date(2026, 3, 12))
        self.assertEqual(_meses_afectados_por_permiso(p), {(3, 2026)})

    def test_compensacion_en_otro_mes_agrega_ese_mes(self):
        """Media jornada de temporada el 31 de marzo, compensada el 2 de abril: abril también."""
        p = _PermisoFalso(date(2026, 3, 31), date(2026, 3, 31), compensacion=date(2026, 4, 2))
        self.assertEqual(_meses_afectados_por_permiso(p), {(3, 2026), (4, 2026)})

    def test_sin_compensacion_no_falla(self):
        p = _PermisoFalso(date(2026, 3, 10), date(2026, 3, 10), compensacion=None)
        self.assertEqual(_meses_afectados_por_permiso(p), {(3, 2026)})
