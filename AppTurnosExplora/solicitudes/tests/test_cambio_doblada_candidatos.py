"""
CAMBIO DESCANSO / «Cambio de doblada» — el desplegable de dobladas de la semana.

El intercambio es MUTUO: yo tomo la doblada del compañero y él toma mi día completo de
temporada. Por eso no basta con que tenga una doblada esa semana: además debe estar LIBRE mi
día. El envío ya lo validaba (`_validar_semana_cambio_doblada`), pero el desplegable no, así
que ofrecía compañeros que el envío rechazaba con "tu compañero trabaja el ...; debe estar
descansando para tomar tu día completo".

Escenario (el de la pantalla):
- Solicitante grupo AM; su día completo de temporada es el VIERNES (ese día descansa el PM).
- `compa_libre`  (grupo PM): descansa el viernes  -> SÍ puede tomar mi día.
- `compa_ocupado`(grupo AM): trabaja  el viernes  -> NO puede, aunque tenga doblada.
Los dos tienen una doblada real (AM+PM) el miércoles de esa semana.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado, Jornada
from turnos.models import AsignarJornadaExplorador, DescansoSemanaManual, Sala, Turno


class DobladasSemanaCandidatosTest(TestCase):
    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CDob', activo=True)

        self.solicitante = self._empleado('sol.cdob', 'Sol', '9301', self.am)
        self.compa_libre = self._empleado('libre.cdob', 'Libre', '9302', self.pm)
        self.compa_ocupado = self._empleado('ocup.cdob', 'Ocupado', '9303', self.am)

        hoy = timezone.localdate()
        lunes = hoy - timedelta(days=hoy.weekday()) + timedelta(days=7)
        self.miercoles = lunes + timedelta(days=2)   # día de las dobladas
        self.viernes = lunes + timedelta(days=4)     # mi día completo de temporada

        # El viernes descansa el grupo PM -> el solicitante (AM) trabaja el día completo.
        DescansoSemanaManual.objects.create(fecha=self.viernes, jornada=self.pm,
                                            motivo='temporada', descripcion='t', activo=True)

        # Los dos compañeros doblan el miércoles.
        for emp in (self.compa_libre, self.compa_ocupado):
            for jornada in (self.am, self.pm):
                Turno.objects.create(explorador=emp, fecha=self.miercoles,
                                     jornada=jornada, sala=self.sala)

        self.client = Client()
        self.client.force_login(self.solicitante.user)

    def _empleado(self, username, nombre, cedula, jornada):
        u = User.objects.create_user(username, password='x')
        e = Empleado.objects.create(user=u, nombre=nombre, apellido='Test',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _dobladas(self):
        r = self.client.get(reverse('solicitudes:dobladas_semana'),
                            {'fecha': self.viernes.strftime('%Y-%m-%d')},
                            HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json().get('data') or r.json()
        return {d['empleado_id'] for d in data['dobladas']}

    def test_solo_ofrece_a_quien_puede_tomar_mi_dia_completo(self):
        ids = self._dobladas()
        self.assertIn(self.compa_libre.id, ids,
                      'Descansa mi día y tiene doblada: debía ofrecerse.')
        self.assertNotIn(self.compa_ocupado.id, ids,
                         'Trabaja mi día completo: no puede tomarlo, no debía ofrecerse.')

    def test_no_ofrece_a_quien_ya_tiene_mi_dia_comprometido(self):
        """Libre mi día, pero ese día ya está tomado por otra solicitud aprobada."""
        from unittest.mock import patch
        with patch('turnos.services.turno_service.TurnoService.dia_comprometido_por_solicitud',
                   return_value={'motivo': 'DOBLADA'}):
            self.assertEqual(self._dobladas(), set())
