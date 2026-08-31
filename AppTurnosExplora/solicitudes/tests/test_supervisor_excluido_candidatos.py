"""
El supervisor no aparece como "companero que cubre" en NINGUN formulario.

El supervisor aprueba las solicitudes; no cambia turnos ni cubre huecos. Antes
cada camino armaba su propio queryset y solo el servicio base filtraba algo
(`is_staff`), asi que un supervisor por ROL —sin cuenta de staff— salia como
candidato en todos los desplegables.

Cada caso monta un supervisor y un explorador GEMELO (misma jornada base, mismos
turnos): se comprueba que el gemelo SI sale, para que el test no pase por un
montaje incompleto que deje la lista vacia, y que el supervisor NO.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado, EmpleadoRole, Jornada, Role
from permisos.forms import PermisoEspecialForm
from solicitudes.services.doblada_filtro_service import DobladaFiltroService
from solicitudes.services.empleado_disponibilidad_service import EmpleadoDisponibilidadService
from solicitudes.services.strategies.cambio_descanso_strategy import CambioDescansoStrategy
from solicitudes.services.strategies.d_fds_strategy import DFDSStrategy
from turnos.models import AsignarJornadaExplorador


class SupervisorExcluidoCandidatosTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.am = Jornada.objects.create(nombre=Jornada.AM, hora_inicio='06:00:00', hora_fin='14:00:00')
        cls.pm = Jornada.objects.create(nombre=Jornada.PM, hora_inicio='14:00:00', hora_fin='22:00:00')
        cls.rol_sup = Role.objects.create(nombre=Role.SUPERVISOR)
        cls.rol_exp = Role.objects.create(nombre=Role.EXPLORADOR)

    def _empleado(self, username, cedula, rol):
        user = User.objects.create_user(username=username, password='x')
        emp = Empleado.objects.create(
            user=user, nombre=username, apellido='Prueba', cedula=cedula, activo=True
        )
        EmpleadoRole.objects.create(empleado=emp, role=rol)
        return emp

    def setUp(self):
        # Fecha futura: un sabado, para que sirva tambien a D FDS.
        hoy = timezone.localdate()
        d = hoy + timedelta(days=14)
        while d.weekday() != 5:
            d += timedelta(days=1)
        self.sabado = d
        self.inicio = hoy - timedelta(days=30)

        self.solicitante = self._empleado('solicitante', '100', self.rol_exp)
        self.gemelo = self._empleado('gemelo', '101', self.rol_exp)
        # Supervisor SIN is_staff: el caso que el filtro viejo dejaba pasar.
        self.supervisor = self._empleado('supervisor', '102', self.rol_sup)

        AsignarJornadaExplorador.objects.create(
            explorador=self.solicitante, jornada=self.am, fecha_inicio=self.inicio
        )
        for emp in (self.gemelo, self.supervisor):
            AsignarJornadaExplorador.objects.create(
                explorador=emp, jornada=self.pm, fecha_inicio=self.inicio
            )

    def _assert_pool(self, empleados):
        ids = {getattr(e, 'id', None) or e.get('id') for e in empleados}
        self.assertIn(self.gemelo.id, ids, 'montaje incompleto: el gemelo deberia ser candidato')
        self.assertNotIn(self.supervisor.id, ids)

    def test_servicio_base(self):
        self._assert_pool(
            EmpleadoDisponibilidadService.get_empleados_disponibles(None, self.solicitante)
        )

    def test_d_fds(self):
        self._assert_pool(
            DFDSStrategy().get_empleados_disponibles(self.sabado.isoformat(), self.solicitante)
        )

    def test_cambio_descanso(self):
        self._assert_pool(
            CambioDescansoStrategy().get_empleados_disponibles(
                self.sabado.isoformat(), self.solicitante
            )
        )

    def test_doblada_empleados_en_descanso(self):
        self._assert_pool(
            DobladaFiltroService.obtener_empleados_en_descanso(
                self.sabado.isoformat(), self.solicitante.id
            )
        )

    def test_cobertura_candidatos_view(self):
        self.client.force_login(self.solicitante.user)
        resp = self.client.get(
            reverse('solicitudes:cobertura_candidatos'),
            {'fecha_trabajo': self.sabado.isoformat(), 'opcion': 'AM'},
        )
        self.assertEqual(resp.status_code, 200)
        self._assert_pool(resp.json()['candidatos'])

    def test_campo_cubre_de_permiso_especial(self):
        form = PermisoEspecialForm(empleado=self.solicitante)
        self._assert_pool(form.fields['cubre'].queryset)
