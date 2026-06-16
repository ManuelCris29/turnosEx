"""
Test de integración: verifica que al APROBAR/aplicar cada tipo de solicitud,
el cambio se refleja en la API de "Mis Turnos" (/turnos/api/mis-turnos-por-mes/).

Cubre los 5 tipos: CT sencillo, Doblada, D FDS, CT Permanente y Doblada Permanente.
Las fechas se calculan dinámicamente (siempre futuras) para no caducar.
"""
from datetime import date, timedelta

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from turnos.models import Sala, AsignarSalaExplorador, AsignarJornadaExplorador
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService


class ReflejoMisTurnosTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)

        # Supervisor
        u_sup = User.objects.create_user(username='sup.test', password='x')
        self.supervisor = Empleado.objects.create(user=u_sup, nombre='Sup', apellido='Test', cedula='900', activo=True,
                                                  email='sup@test.com')
        # Solicitante AM, Receptor PM (jornadas contrarias)
        u_sol = User.objects.create_user(username='sol.test', password='x')
        self.sol = Empleado.objects.create(user=u_sol, nombre='Sol', apellido='AM', cedula='901', activo=True,
                                           email='sol@test.com', supervisor=self.supervisor)
        u_rec = User.objects.create_user(username='rec.test', password='x')
        self.rec = Empleado.objects.create(user=u_rec, nombre='Rec', apellido='PM', cedula='902', activo=True,
                                           email='rec@test.com', supervisor=self.supervisor)

        for emp, jor in ((self.sol, self.am), (self.rec, self.pm)):
            AsignarJornadaExplorador.objects.create(explorador=emp, jornada=jor, fecha_inicio=date(2025, 1, 1))
            AsignarSalaExplorador.objects.create(explorador=emp, sala=self.sala, fecha_inicio=date(2025, 1, 1))
            # CT sencillo busca salas vía competencias del empleado
            CompetenciaEmpleado.objects.create(empleado=emp, sala=self.sala)

        self.tipos = {n: TipoSolicitudCambio.objects.create(nombre=n) for n in
                      ['CAMBIO TURNO', 'DOBLADA', 'D FDS', 'CT PERMANENTE', 'DOBLADA PERMANENTE']}

    # ----------------------------------------------------------------- helpers
    def _dia_semana(self, weekday, desde=None):
        d = desde or (timezone.now().date() + timedelta(days=30))
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return d

    def _findes_fds(self):
        """(cesion, pago) en un mismo mes futuro: cesion día que trabaja AM, pago día que trabaja PM."""
        base = timezone.now().date() + timedelta(days=30)
        for _ in range(6):
            anio, mes = base.year, base.month
            ces = pago = None
            d = date(anio, mes, 1)
            while d.month == mes:
                if d > timezone.now().date() and d.weekday() in (5, 6):
                    g = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(d)
                    if g == 'AM' and not ces:
                        ces = d
                    if g == 'PM' and not pago:
                        pago = d
                d += timedelta(days=1)
            if ces and pago:
                return ces, pago
            base = (date(anio, mes, 28) + timedelta(days=7))
        self.fail("No se hallaron fechas de finde para D FDS")

    def _crear_y_aplicar(self, tipo, datos):
        ok, msg = SolicitudFactory.validar_solicitud(tipo, datos)
        self.assertTrue(ok, f"validar falló: {msg}")
        sol, msg = SolicitudFactory.crear_solicitud(tipo, datos)
        self.assertIsNotNone(sol, f"crear falló: {msg}")
        sol = SolicitudCambio.objects.select_related(
            'doblada', 'doblada_permanente', 'cambio_permanente',
            'explorador_solicitante', 'explorador_receptor', 'tipo_cambio'
        ).get(id=sol.id)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        ok, msg = SolicitudFactory.aplicar_cambios(sol)
        self.assertTrue(ok, f"aplicar falló: {msg}")
        return sol

    def _cell(self, empleado, fecha):
        cache.clear()
        self.client.force_login(empleado.user)
        resp = self.client.get('/turnos/api/mis-turnos-por-mes/', {'mes': fecha.month, 'anio': fecha.year})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json().get(fecha.strftime('%Y-%m-%d'), {})

    # ------------------------------------------------------------------- tests
    def test_ct_sencillo_refleja(self):
        f = self._dia_semana(0)  # lunes
        sol = self._crear_y_aplicar(self.tipos['CAMBIO TURNO'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['CAMBIO TURNO'], 'comentario': 'test',
            'fecha_cambio_turno': f.strftime('%Y-%m-%d'),
        })
        self.assertEqual(self._cell(self.sol, f).get('jornada'), 'PM')   # AM -> PM
        self.assertEqual(self._cell(self.rec, f).get('jornada'), 'AM')   # PM -> AM

    def test_doblada_refleja(self):
        fc = self._dia_semana(0)
        fp = self._dia_semana(2, desde=fc + timedelta(days=1))  # otro día, mismo mes habitualmente
        if fp.month != fc.month:
            fp = self._dia_semana(2, desde=fc.replace(day=1))
        sol = self._crear_y_aplicar(self.tipos['DOBLADA'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['DOBLADA'], 'comentario': 'test',
            'fecha_cambio_turno': fc.strftime('%Y-%m-%d'), 'fecha_pago': fp.strftime('%Y-%m-%d'),
            'jornada_cedida': 'AM', 'tipo_cesion': 'cesion_completa',
            'fecha_creacion_solicitud': timezone.now().date(),
        })
        self.assertTrue(self._cell(self.sol, fc).get('es_descanso'))   # solicitante descansa en cesión
        self.assertEqual(self._cell(self.rec, fc).get('jornada'), 'DOBLADA')  # receptor dobla en cesión
        self.assertEqual(self._cell(self.sol, fp).get('jornada'), 'DOBLADA')  # solicitante dobla en pago
        self.assertTrue(self._cell(self.rec, fp).get('es_descanso'))   # receptor descansa en pago

    def test_d_fds_refleja(self):
        ces, pago = self._findes_fds()
        sol = self._crear_y_aplicar(self.tipos['D FDS'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['D FDS'], 'comentario': 'test',
            'fecha_cambio_turno': ces.strftime('%Y-%m-%d'), 'fecha_pago': pago.strftime('%Y-%m-%d'),
            'fecha_creacion_solicitud': timezone.now().date(),
        })
        self.assertTrue(self._cell(self.sol, ces).get('es_descanso'))
        self.assertEqual(self._cell(self.rec, ces).get('jornada'), 'DOBLADA')
        self.assertEqual(self._cell(self.sol, pago).get('jornada'), 'DOBLADA')
        self.assertTrue(self._cell(self.rec, pago).get('es_descanso'))

    def test_ct_permanente_refleja(self):
        fi = self._dia_semana(0)             # lunes
        ff = fi + timedelta(days=10)
        sol = self._crear_y_aplicar(self.tipos['CT PERMANENTE'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['CT PERMANENTE'], 'comentario': 'test',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'dias_semana': [0]},
        })
        self.assertEqual(self._cell(self.sol, fi).get('jornada'), 'PM')  # AM -> PM en el lunes
        self.assertEqual(self._cell(self.rec, fi).get('jornada'), 'AM')

    def test_doblada_permanente_refleja(self):
        fi = self._dia_semana(0)             # lunes (cesión)
        martes = self._dia_semana(1, desde=fi)  # martes (devolución)
        ff = fi + timedelta(days=13)
        sol = self._crear_y_aplicar(self.tipos['DOBLADA PERMANENTE'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['DOBLADA PERMANENTE'], 'comentario': 'test',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['0'], 'dias_devolucion': ['1'],
        })
        # Lunes (cesión): solicitante descansa, receptor dobla
        self.assertTrue(self._cell(self.sol, fi).get('es_descanso'))
        self.assertEqual(self._cell(self.rec, fi).get('jornada'), 'DOBLADA')
        # Martes (devolución): solicitante dobla, receptor descansa
        self.assertEqual(self._cell(self.sol, martes).get('jornada'), 'DOBLADA')
        self.assertTrue(self._cell(self.rec, martes).get('es_descanso'))
