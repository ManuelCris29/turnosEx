"""
Tests del REVERT de Cambio de Turno sencillo (CT) al cancelar dentro de los 30 min.

CT intercambia las jornadas de solicitante y receptor el mismo día. Al cancelar, debe
restaurar los turnos previos desde el snapshot capturado al aplicar.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy


class CTRevertTest(TestCase):
    def setUp(self):
        # La caché de jornadas (Django cache) puede quedar stale entre tests con IDs ya
        # revertidos; limpiarla evita FK inválidos al restaurar desde snapshot.
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CT', activo=True)

        u1 = User.objects.create_user(username='sol.ct', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='A', cedula='1', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.am, fecha_inicio=date(2025, 1, 1))

        u2 = User.objects.create_user(username='rec.ct', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='B', cedula='2', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.pm, fecha_inicio=date(2025, 1, 1))

        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)

        # Un miércoles futuro (día de semana, no festivo/mantenimiento)
        d = timezone.now().date() + timedelta(days=3)
        while d.weekday() != 2:
            d += timedelta(days=1)
        self.fecha = d

    def _jornadas(self, emp):
        return sorted((t.jornada.nombre.upper(), t.tipo_cambio)
                      for t in Turno.objects.filter(explorador=emp, fecha=self.fecha).select_related('jornada'))

    def test_revalidacion_para_aprobar_ok(self):
        # Un CT válido (pendiente) debe re-validar True al aprobar.
        Turno.objects.create(explorador=self.sol, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.rec, fecha=self.fecha, jornada=self.pm, sala=self.sala)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.fecha,
            estado='pendiente', comentario='Prueba')
        ok, msg = CambioTurnoStrategy().revalidar_para_aprobar(sol)
        self.assertTrue(ok, msg)

    def test_ciclo_aplicar_y_revertir(self):
        # Estado previo real: solicitante AM, receptor PM (sin tipo_cambio).
        Turno.objects.create(explorador=self.sol, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.rec, fecha=self.fecha, jornada=self.pm, sala=self.sala)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.fecha,
            estado='aprobada', comentario='Prueba')

        strat = CambioTurnoStrategy()
        ok, msg = strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)

        sol.refresh_from_db()
        self.assertTrue(sol.snapshot_turnos_previos, "El snapshot debió capturarse al aplicar")
        # Jornadas intercambiadas (con tipo_cambio CT).
        self.assertEqual(self._jornadas(self.sol), [('PM', 'CT')])
        self.assertEqual(self._jornadas(self.rec), [('AM', 'CT')])

        # Revertir → vuelve al estado previo.
        CambioTurnoStrategy.revertir(sol)
        self.assertEqual(self._jornadas(self.sol), [('AM', None)])
        self.assertEqual(self._jornadas(self.rec), [('PM', None)])

    def test_cancelar_por_flujo_completo_no_falla_por_fk_colgante(self):
        """
        REGRESIÓN: cancelar un CT aprobado por el flujo REAL (CancelarSolicitudUseCase) no debe
        fallar. El revert BORRA los turnos materializados y turno_origen/turno_destino apuntaban a
        ellos; al guardar la solicitud se reescribía un id borrado → IntegrityError. El test unitario
        de revert no lo veía porque no llama al save() posterior del use case.
        """
        from django.utils import timezone
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

        Turno.objects.create(explorador=self.sol, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.rec, fecha=self.fecha, jornada=self.pm, sala=self.sala)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.fecha,
            estado='aprobada', fecha_resolucion=timezone.now(), comentario='Prueba')

        ok, msg = CambioTurnoStrategy().aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        sol.refresh_from_db()
        self.assertIsNotNone(sol.turno_origen_id, "El apply debió enlazar turno_origen")

        # Cancelar por el flujo completo: NO debe explotar y debe restaurar los turnos.
        okc, msgc = CancelarSolicitudUseCase().execute(sol.id, self.sol)
        self.assertTrue(okc, f"La cancelación falló: {msgc}")
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'cancelada')
        self.assertIsNone(sol.turno_origen_id, "turno_origen debió quedar en NULL tras el revert")
        self.assertEqual(self._jornadas(self.sol), [('AM', None)])
        self.assertEqual(self._jornadas(self.rec), [('PM', None)])
