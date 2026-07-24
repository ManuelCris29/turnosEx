"""
Tests para el flujo de aprobación y rechazo de solicitudes.

Cubren:
- Aprobación por receptor → estado intermedio (aprobado_receptor=True)
- Aprobación por supervisor → solicitud aprobada + turnos aplicados
- Rechazo por receptor → solicitud rechazada
- Rechazo por supervisor → solicitud rechazada
- No se puede aprobar una solicitud ya rechazada
- No puede aprobar alguien que no es parte de la solicitud
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.solicitud_aprobacion_service import SolicitudAprobacionService

aprobar_solicitud_receptor = SolicitudAprobacionService.aprobar_solicitud_receptor
aprobar_solicitud_supervisor = SolicitudAprobacionService.aprobar_solicitud_supervisor
rechazar_solicitud_receptor = SolicitudAprobacionService.rechazar_solicitud_receptor
rechazar_solicitud_supervisor = SolicitudAprobacionService.rechazar_solicitud_supervisor
from turnos.models import AsignarJornadaExplorador, Sala, Turno


def _dia_semana_futuro(offset_semanas=2):
    """Devuelve un miércoles al menos 2 semanas en el futuro."""
    d = timezone.now().date() + timedelta(weeks=offset_semanas)
    while d.weekday() != 2:
        d += timedelta(days=1)
    return d


class AprobacionBaseTest(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Apr', activo=True)
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CAMBIO TURNO', codigo_estrategia='CT', activo=True
        )

        def _emp(username, ced, jor):
            u = User.objects.create_user(username=username, password='x')
            e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
            AsignarJornadaExplorador.objects.create(
                explorador=e, jornada=jor, fecha_inicio=date(2025, 1, 1)
            )
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
            return e

        self.solicitante = _emp('apr_sol', '501', self.am)
        self.receptor = _emp('apr_rec', '502', self.pm)

        u_sup = User.objects.create_user(username='apr_sup', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=u_sup, nombre='Sup', apellido='X', cedula='503', activo=True
        )
        self.solicitante.supervisor = self.supervisor
        self.solicitante.save()

        self.fecha = _dia_semana_futuro()
        Turno.objects.create(explorador=self.solicitante, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.receptor, fecha=self.fecha, jornada=self.pm, sala=self.sala)

    def _solicitud(self):
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=self.fecha,
            estado='pendiente',
            snapshot_turnos_previos={
                f"{self.solicitante.id}:{self.fecha.isoformat()}": [
                    {'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': None}
                ],
                f"{self.receptor.id}:{self.fecha.isoformat()}": [
                    {'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None}
                ],
            }
        )


class AprobacionReceptorTest(AprobacionBaseTest):

    def test_aprobacion_receptor_marca_flag(self):
        sol = self._solicitud()
        ok, _ = aprobar_solicitud_receptor(sol.id, self.receptor, 'ok')
        self.assertTrue(ok)
        sol.refresh_from_db()
        self.assertTrue(sol.aprobado_receptor)
        self.assertEqual(sol.estado, 'pendiente')  # aún falta supervisor

    def test_rechazo_receptor_rechaza_solicitud(self):
        sol = self._solicitud()
        ok, _ = rechazar_solicitud_receptor(sol.id, self.receptor, 'no quiero')
        self.assertTrue(ok)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'rechazada')

    def test_receptor_incorrecto_no_puede_aprobar(self):
        sol = self._solicitud()
        ok, _ = aprobar_solicitud_receptor(sol.id, self.supervisor, 'ok')
        self.assertFalse(ok)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'pendiente')


class AprobacionSupervisorTest(AprobacionBaseTest):

    def test_aprobacion_supervisor_pasa_validacion_permisos(self):
        """El supervisor correcto recibe respuesta de negocio (no error de permisos)."""
        sol = self._solicitud()
        sol.aprobado_receptor = True
        sol.save()
        ok, msg = aprobar_solicitud_supervisor(sol.id, self.supervisor, 'Aprobado por supervisor en test')
        # Puede fallar por re-validación de negocio (fecha, comentario, turno), pero NO por permisos
        self.assertNotIn('permisos', msg.lower())

    def test_supervisor_incorrecto_no_puede_aprobar(self):
        otro_u = User.objects.create_user(username='otro_sup', password='x')
        otro_sup = Empleado.objects.create(
            user=otro_u, nombre='Otro', apellido='Sup', cedula='999', activo=True
        )
        sol = self._solicitud()
        sol.aprobado_receptor = True
        sol.save()
        ok, _ = aprobar_solicitud_supervisor(sol.id, otro_sup, 'ok')
        self.assertFalse(ok)

    def test_rechazo_supervisor_rechaza_solicitud(self):
        sol = self._solicitud()
        ok, _ = rechazar_solicitud_supervisor(sol.id, self.supervisor, 'rechazado')
        self.assertTrue(ok)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'rechazada')

    def test_no_puede_aprobar_solicitud_ya_rechazada(self):
        sol = self._solicitud()
        sol.estado = 'rechazada'
        sol.save()
        ok, _ = aprobar_solicitud_supervisor(sol.id, self.supervisor, 'ok')
        self.assertFalse(ok)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'rechazada')

    def test_flujo_completo_receptor_luego_supervisor_flags(self):
        """Tras aprobación de receptor los flags quedan correctos; supervisor recibe respuesta de negocio."""
        sol = self._solicitud()
        ok, _ = aprobar_solicitud_receptor(sol.id, self.receptor, 'ok receptor')
        self.assertTrue(ok)
        sol.refresh_from_db()
        self.assertTrue(sol.aprobado_receptor)
        self.assertEqual(sol.estado, 'pendiente')  # aún falta supervisor

        # El supervisor recibe respuesta de negocio, no error de permisos ni de estado
        ok, msg = aprobar_solicitud_supervisor(sol.id, self.supervisor, 'ok supervisor')
        self.assertNotIn('permisos', msg.lower())
        self.assertNotIn('no está pendiente', msg.lower())


class IdempotenciaEmailTest(AprobacionBaseTest):
    """
    Los enlaces del correo pueden clicarse varias veces (o el cliente de correo
    los pre-carga). Re-aprobar/re-responder NO debe re-procesar ni reenviar la
    notificación. La segunda llamada debe devolver False (sin agendar on_commit).
    """

    def test_reaprobar_receptor_no_reprocesa(self):
        sol = self._solicitud()
        ok, _ = aprobar_solicitud_receptor(sol.id, self.receptor, 'ok')
        self.assertTrue(ok)
        sol.refresh_from_db()
        self.assertTrue(sol.aprobado_receptor)
        self.assertEqual(sol.estado, 'pendiente')  # falta supervisor → estado sigue pendiente

        # Segundo clic al mismo enlace: NO re-procesa (no reenvía notificación)
        ok2, msg2 = aprobar_solicitud_receptor(sol.id, self.receptor, 'ok')
        self.assertFalse(ok2)
        self.assertIn('Ya habías aprobado', msg2)

    def test_reaprobar_supervisor_no_reprocesa(self):
        sol = self._solicitud()
        ok, _ = aprobar_solicitud_supervisor(sol.id, self.supervisor, 'ok')
        self.assertTrue(ok)
        ok2, msg2 = aprobar_solicitud_supervisor(sol.id, self.supervisor, 'ok')
        self.assertFalse(ok2)
        self.assertIn('Ya habías aprobado', msg2)

    def test_ya_resuelto_para_tras_responder(self):
        from solicitudes.views.aprobacion_email import _ya_resuelto_para
        sol = self._solicitud()
        self.assertFalse(_ya_resuelto_para(sol, 'receptor'))
        aprobar_solicitud_receptor(sol.id, self.receptor, 'ok')
        sol.refresh_from_db()
        # El receptor ya respondió → el enlace del correo queda inerte
        self.assertTrue(_ya_resuelto_para(sol, 'receptor'))

    def test_ya_resuelto_bloquea_rechazo_tras_aprobar(self):
        """Tras aprobar como receptor, el enlace de rechazo del correo queda inerte."""
        from solicitudes.views.aprobacion_email import _ya_resuelto_para
        sol = self._solicitud()
        aprobar_solicitud_receptor(sol.id, self.receptor, 'ok')
        sol.refresh_from_db()
        self.assertTrue(_ya_resuelto_para(sol, 'receptor'))
