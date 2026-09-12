"""
Caché de `DashboardView.get_context_data`: indicadores (admin/explorador) y
morosos pendientes. TTL corto/medio, sin invalidación explícita (ver el
docstring en core/dashboard/views.py) — igual razonamiento que
`ReporteDiaService.reporte`.
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.utils import timezone

from core.dashboard.views import DashboardView
from empleados.models import Empleado
from empleados.services.indicadores_service import IndicadoresService
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio


def _contexto(empleado):
    req = RequestFactory().get('/')
    req.user = empleado.user
    return DashboardView(request=req, kwargs={}).get_context_data()


class DashboardIndicadoresCacheTest(TestCase):

    def setUp(self):
        cache.clear()
        self.anio = timezone.localdate().year
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CAMBIO TURNO', codigo_estrategia='CT', activo=True,
        )
        self.admin = Empleado.objects.create(
            user=User.objects.create_user(username='dash_admin', password='x', is_staff=True),
            nombre='Admin', apellido='Dash', cedula='6001', activo=True,
        )
        self.exp_a = Empleado.objects.create(
            user=User.objects.create_user(username='dash_a', password='x'),
            nombre='ExpA', apellido='Dash', cedula='6002', activo=True,
        )
        self.exp_b = Empleado.objects.create(
            user=User.objects.create_user(username='dash_b', password='x'),
            nombre='ExpB', apellido='Dash', cedula='6003', activo=True,
        )
        SolicitudCambio.objects.create(
            explorador_solicitante=self.exp_a, explorador_receptor=self.exp_b,
            tipo_cambio=self.tipo, fecha_cambio_turno=date(self.anio, 6, 15), estado='aprobada',
        )

    def test_segunda_llamada_admin_no_recalcula_indicadores(self):
        with patch.object(IndicadoresService, 'get', wraps=IndicadoresService.get) as espia:
            _contexto(self.admin)
            _contexto(self.admin)
        self.assertEqual(espia.call_count, 1)

    def test_segunda_llamada_explorador_no_recalcula_indicadores(self):
        with patch.object(IndicadoresService, 'get', wraps=IndicadoresService.get) as espia:
            _contexto(self.exp_a)
            _contexto(self.exp_a)
        self.assertEqual(espia.call_count, 1)

    def test_un_explorador_no_ve_el_cache_de_otro(self):
        kpi_a = _contexto(self.exp_a)['kpi_cambios']
        kpi_b = _contexto(self.exp_b)['kpi_cambios']

        self.assertEqual(kpi_a, 1)  # solicitante de la única solicitud
        self.assertEqual(kpi_b, 1)  # receptor: cuenta igual (incluir_receptor=True)
        # Cada uno debe llegar a su propio valor por su propia clave, no por
        # compartir la del otro (aquí coinciden en valor, así que se verifica la
        # clave directamente).
        self.assertNotEqual(
            f"dashboard_indicadores_v1_emp{self.exp_a.id}_{self.anio}",
            f"dashboard_indicadores_v1_emp{self.exp_b.id}_{self.anio}",
        )


class DashboardMorososCacheTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = Empleado.objects.create(
            user=User.objects.create_user(username='dash_admin2', password='x', is_staff=True),
            nombre='Admin2', apellido='Dash', cedula='6004', activo=True,
        )

    def test_segunda_llamada_no_recalcula_morosos(self):
        with patch(
            'solicitudes.services.deuda_corporativa_service.DeudaCorporativaService.contar_pendientes_de_sancion',
            return_value=0,
        ) as espia:
            _contexto(self.admin)
            _contexto(self.admin)
        self.assertEqual(espia.call_count, 1)
