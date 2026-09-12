"""
`_filtrar_por_descanso_receptor` (api_disponibles_ct_preview.py) usa
`TurnoService.estado_rango_multiple` en vez de `estado_dia` por candidato, para
no pagar ~3-5 consultas por cada uno en un desplegable con varias decenas de
compañeros. Este test fija que el número de consultas no crece con la
cantidad de candidatos.
"""
from datetime import date

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from empleados.models import Empleado
from solicitudes.views.api_disponibles_ct_preview import ObtenerEmpleadosDisponiblesView

MARTES = date(2026, 3, 3)  # martes, sin festivos ni temporada


class FiltroDescansoReceptorCosteConstanteTest(TestCase):

    def setUp(self):
        self.candidatos = [
            Empleado.objects.create(
                user=User.objects.create_user(username=f'cand{i}', password='x'),
                nombre=f'Cand{i}', apellido='Batch', cedula=f'9900{i:03d}', activo=True,
            )
            for i in range(15)
        ]

    def _consultas(self, empleados):
        with CaptureQueriesContext(connection) as ctx:
            ObtenerEmpleadosDisponiblesView._filtrar_por_descanso_receptor(
                empleados, MARTES.isoformat(),
            )
        return len(ctx)

    def test_el_numero_de_consultas_no_crece_con_los_candidatos(self):
        pocos = self._consultas(self.candidatos[:2])
        muchos = self._consultas(self.candidatos)
        self.assertEqual(
            pocos, muchos,
            f'{pocos} consultas con 2 candidatos y {muchos} con {len(self.candidatos)}: '
            f'el filtro debería costar lo mismo sin importar cuántos candidatos evalúa.',
        )

    def test_todos_descansan_sin_turnos_ni_solicitudes(self):
        """Sin ningún dato de por medio, todos deben seguir ofreciéndose (base: sin jornada)."""
        filtrados = ObtenerEmpleadosDisponiblesView._filtrar_por_descanso_receptor(
            self.candidatos, MARTES.isoformat(),
        )
        self.assertEqual(set(e.id for e in filtrados), set(e.id for e in self.candidatos))
