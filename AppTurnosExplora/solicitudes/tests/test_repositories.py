"""
Tests para SolicitudRepository y TurnoRepository.

Cubren las queries más usadas para detectar regresiones si cambia el ORM.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User

from empleados.models import Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.repositories.solicitud_repository import SolicitudRepository
from solicitudes.repositories.turno_repository import TurnoRepository
from turnos.models import AsignarJornadaExplorador, Sala, Turno


def _emp(username, ced, jornada):
    u = User.objects.create_user(username=username, password='x')
    e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
    AsignarJornadaExplorador.objects.create(
        explorador=e, jornada=jornada, fecha_inicio=date(2025, 1, 1)
    )
    return e


class SolicitudRepositoryTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00', hora_fin='14:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00', hora_fin='22:00')
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CT', codigo_estrategia='CT', activo=True)
        self.a = _emp('repo_a', '601', self.am)
        self.b = _emp('repo_b', '602', self.pm)
        self.fecha = date(2027, 10, 5)

    def _sol(self, estado='pendiente'):
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.a,
            explorador_receptor=self.b,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=self.fecha,
            estado=estado,
        )

    def test_get_by_id_existente(self):
        sol = self._sol()
        resultado = SolicitudRepository.get_by_id(sol.id)
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.id, sol.id)

    def test_get_by_id_inexistente_devuelve_none(self):
        resultado = SolicitudRepository.get_by_id(99999)
        self.assertIsNone(resultado)

    def test_pendientes_de_explorador_solicitante(self):
        self._sol('pendiente')
        qs = SolicitudRepository.pendientes_de_explorador(self.a)
        self.assertEqual(qs.count(), 1)

    def test_pendientes_de_explorador_receptor(self):
        self._sol('pendiente')
        qs = SolicitudRepository.pendientes_de_explorador(self.b)
        self.assertEqual(qs.count(), 1)

    def test_pendientes_no_incluye_aprobadas(self):
        self._sol('aprobada')
        qs = SolicitudRepository.pendientes_de_explorador(self.a)
        self.assertEqual(qs.count(), 0)

    def test_existe_solicitud_activa_entre(self):
        self._sol('pendiente')
        existe = SolicitudRepository.existe_solicitud_activa_entre(
            self.a, self.b, 'CT', self.fecha
        )
        self.assertTrue(existe)

    def test_no_existe_solicitud_activa_cancelada(self):
        self._sol('cancelada')
        existe = SolicitudRepository.existe_solicitud_activa_entre(
            self.a, self.b, 'CT', self.fecha
        )
        self.assertFalse(existe)

    def test_historial_explorador_devuelve_todos_estados(self):
        self._sol('pendiente')
        self._sol('aprobada')
        self._sol('cancelada')
        qs = SolicitudRepository.historial_explorador(self.a)
        self.assertGreaterEqual(qs.count(), 3)


class TurnoRepositoryTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00', hora_fin='14:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00', hora_fin='22:00')
        self.sala = Sala.objects.create(nombre='Sala Repo', activo=True)
        self.emp = _emp('turno_repo', '701', self.am)
        self.fecha = date(2027, 10, 6)

    def test_por_explorador_fecha(self):
        Turno.objects.create(explorador=self.emp, fecha=self.fecha, jornada=self.am, sala=self.sala)
        qs = TurnoRepository.por_explorador_fecha(self.emp, self.fecha)
        self.assertEqual(qs.count(), 1)

    def test_jornadas_en_fecha(self):
        Turno.objects.create(explorador=self.emp, fecha=self.fecha, jornada=self.am, sala=self.sala)
        jornadas = TurnoRepository.jornadas_en_fecha(self.emp.id, self.fecha)
        self.assertIn('AM', jornadas)

    def test_tiene_doblada_true(self):
        Turno.objects.create(explorador=self.emp, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.emp, fecha=self.fecha, jornada=self.pm, sala=self.sala)
        self.assertTrue(TurnoRepository.tiene_doblada(self.emp.id, self.fecha))

    def test_tiene_doblada_false_una_jornada(self):
        Turno.objects.create(explorador=self.emp, fecha=self.fecha, jornada=self.am, sala=self.sala)
        self.assertFalse(TurnoRepository.tiene_doblada(self.emp.id, self.fecha))

    def test_tiene_tipo_cambio(self):
        Turno.objects.create(
            explorador=self.emp, fecha=self.fecha, jornada=self.am,
            sala=self.sala, tipo_cambio='DOBLADA'
        )
        self.assertTrue(TurnoRepository.tiene_tipo_cambio(self.emp, self.fecha, 'DOBLADA'))
        self.assertFalse(TurnoRepository.tiene_tipo_cambio(self.emp, self.fecha, 'CT'))

    def test_por_explorador_rango(self):
        fecha2 = self.fecha + timedelta(days=1)
        Turno.objects.create(explorador=self.emp, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.emp, fecha=fecha2, jornada=self.am, sala=self.sala)
        qs = TurnoRepository.por_explorador_rango(self.emp, self.fecha, fecha2)
        self.assertEqual(qs.count(), 2)
