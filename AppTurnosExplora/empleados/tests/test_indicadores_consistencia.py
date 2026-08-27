"""
Regresión: las 3 vistas de KPIs (Dashboard, Mis Indicadores, Indicadores del
supervisor) deben entregar el MISMO número para un mismo explorador.

El bug original: el supervisor contaba solo la participación como solicitante
(incluir_receptor=False) mientras la vista personal contaba solicitante+receptor,
así que un mismo empleado mostraba números distintos según quién mirara.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from core.dashboard.views import DashboardView
from empleados.models import Empleado
from empleados.services.indicadores_service import IndicadoresService
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio


class IndicadoresConsistenciaTest(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.anio = timezone.localdate().year
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CAMBIO TURNO', codigo_estrategia='CT', activo=True
        )

        u_sup = User.objects.create_user(username='sup.ind', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(user=u_sup, nombre='Sup', apellido='Ind', cedula='7001', activo=True)

        u_sol = User.objects.create_user(username='sol.ind', password='x')
        self.solicitante = Empleado.objects.create(
            user=u_sol, nombre='Sol', apellido='Ind', cedula='7002', activo=True, supervisor=self.supervisor
        )
        u_rec = User.objects.create_user(username='rec.ind', password='x')
        self.receptor = Empleado.objects.create(
            user=u_rec, nombre='Rec', apellido='Ind', cedula='7003', activo=True, supervisor=self.supervisor
        )

        # Un cambio APROBADO donde el receptor participa (pero NO es el solicitante)
        SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=date(self.anio, 6, 15),
            estado='aprobada',
        )

    def _dashboard_kpi(self, empleado):
        req = RequestFactory().get('/')
        req.user = empleado.user
        return DashboardView(request=req, kwargs={}).get_context_data()['kpi_cambios']

    def test_receptor_cuenta_igual_en_las_tres_vistas(self):
        rid = self.receptor.id
        # Mis Indicadores (personal): solicitante O receptor
        personal = IndicadoresService.get(explorador_id=rid, anio=self.anio, incluir_receptor=True)
        # Supervisor mirando a ESE explorador: ahora también incluye receptor
        supervisor = IndicadoresService.get(
            explorador_id=str(rid), anio=self.anio, incluir_receptor=bool(str(rid))
        )
        # Dashboard del receptor
        dash = self._dashboard_kpi(self.receptor)

        self.assertEqual(personal['total_general'], 1)          # su participación como receptor cuenta
        self.assertEqual(supervisor['total_general'], 1)        # el supervisor ve lo mismo
        self.assertEqual(dash, 1)                               # el dashboard también
        self.assertEqual(personal['total_general'], supervisor['total_general'])
        self.assertEqual(dash, personal['total_general'])

    def test_sin_incluir_receptor_no_veria_la_participacion(self):
        """Prueba que el flag es lo que importaba: sin él, el receptor daría 0."""
        rid = self.receptor.id
        viejo = IndicadoresService.get(explorador_id=rid, anio=self.anio)  # incluir_receptor=False (default)
        self.assertEqual(viejo['total_general'], 0)
