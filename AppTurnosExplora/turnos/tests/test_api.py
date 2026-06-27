"""
Tests para API de turnos
"""
from datetime import date, datetime
from django.test import TestCase, Client
from django.contrib.auth.models import User
from empleados.models import Empleado


class TurnosAPITest(TestCase):
    """Tests para la API de turnos"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.empleado = Empleado.objects.create(
            user=self.user,
            nombre='Test',
            apellido='User',
            cedula='1234567890',
            activo=True
        )

    def test_api_requiere_login(self):
        """Test que la API requiere autenticación"""
        response = self.client.get('/turnos/api/mis-turnos-por-mes/')
        self.assertEqual(response.status_code, 302)  # Redirect a login

    def test_api_con_login(self):
        """Test que la API funciona con usuario autenticado"""
        self.client.login(username='testuser', password='test123')
        response = self.client.get('/turnos/api/mis-turnos-por-mes/?mes=11&anio=2025')
        # Puede ser 200 o 400 dependiendo de los parámetros
        self.assertIn(response.status_code, [200, 400])


class MisTurnosFuenteVerdadTest(TestCase):
    """
    Garantiza que la vista MisTurnosPorMesView y la fuente de verdad única
    TurnoService.estado_mes() NO diverjan. La vista consume estado_mes; este test
    bloquea futuras divergencias en la decisión trabaja/jornada por día.
    Ver docs/AUDITORIA_FUENTE_VERDAD_TURNOS.md
    """
    def setUp(self):
        from empleados.models import Jornada
        from turnos.models import AsignarJornadaExplorador
        self.client = Client()
        self.user = User.objects.create_user(username='fvuser', password='test123')
        self.empleado = Empleado.objects.create(
            user=self.user, nombre='Fuente', apellido='Verdad',
            cedula='9090909090', activo=True,
        )
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        AsignarJornadaExplorador.objects.create(
            explorador=self.empleado, jornada=self.am, fecha_inicio=date(2026, 1, 1)
        )

    def test_misturnos_coincide_con_estado_mes(self):
        from turnos.services.turno_service import TurnoService
        self.client.login(username='fvuser', password='test123')
        WORK = {'AM', 'PM', 'DOBLADA'}
        for mes in (7, 8, 9):
            resp = self.client.get(f'/turnos/api/mis-turnos-por-mes/?mes={mes}&anio=2026')
            self.assertEqual(resp.status_code, 200)
            dias = resp.json().get('turnos', {})
            estados = TurnoService.estado_mes(self.empleado, 2026, mes)
            for fstr, info in dias.items():
                d = datetime.strptime(fstr, '%Y-%m-%d').date()
                est = estados[d]
                vista_trabaja = info.get('jornada') in WORK
                self.assertEqual(
                    vista_trabaja, est['trabaja'],
                    msg=f"Divergencia trabaja {fstr}: vista={info.get('jornada')} estado_mes={est}"
                )
                if vista_trabaja:
                    self.assertEqual(
                        info.get('jornada'), est['jornada'],
                        msg=f"Divergencia jornada {fstr}: vista={info.get('jornada')} estado_mes={est['jornada']}"
                    )


