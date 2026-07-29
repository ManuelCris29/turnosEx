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
        d = timezone.localdate() + timedelta(days=3)
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

    def test_cada_uno_conserva_su_sala(self):
        """La sala es informativa (dice en qué es experto el explorador): el CT intercambia la
        JORNADA, no la sala. Antes se le ponía a cada uno la primera sala de competencia del OTRO.
        """
        otra = Sala.objects.create(nombre='Sala Rec', activo=True)
        CompetenciaEmpleado.objects.filter(empleado=self.rec).delete()
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=otra)
        Turno.objects.create(explorador=self.sol, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.rec, fecha=self.fecha, jornada=self.pm, sala=otra)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.fecha,
            estado='aprobada', comentario='Prueba')
        ok, msg = CambioTurnoStrategy().aplicar_cambios(sol)
        self.assertTrue(ok, msg)

        t_sol = Turno.objects.get(explorador=self.sol, fecha=self.fecha)
        t_rec = Turno.objects.get(explorador=self.rec, fecha=self.fecha)
        # Jornadas intercambiadas…
        self.assertEqual((t_sol.jornada.nombre.upper(), t_rec.jornada.nombre.upper()), ('PM', 'AM'))
        # …pero cada uno con SU sala.
        self.assertEqual(t_sol.sala_id, self.sala.id)
        self.assertEqual(t_rec.sala_id, otra.id)

    def test_sin_tope_de_cambios_por_fecha(self):
        """No hay límite de cambios por explorador/fecha: con varios ya aprobados, uno nuevo
        sigue siendo válido y aplicable. El tope anterior (3) además se contaba a sí mismo al
        aprobar, así que el tercero nunca llegaba a aplicarse."""
        u3 = User.objects.create_user(username='ter.ct', password='x')
        tercero = Empleado.objects.create(user=u3, nombre='Ter', apellido='C', cedula='3', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=tercero, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=tercero, sala=self.sala)

        # Tres cambios ya aprobados del solicitante en esa misma fecha.
        for _ in range(3):
            SolicitudCambio.objects.create(
                explorador_solicitante=self.sol, explorador_receptor=tercero,
                tipo_cambio=self.tipo, fecha_cambio_turno=self.fecha,
                estado='aprobada', comentario='Previo')

        Turno.objects.create(explorador=self.sol, fecha=self.fecha, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.rec, fecha=self.fecha, jornada=self.pm, sala=self.sala)
        nueva = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.fecha,
            estado='aprobada', comentario='Prueba')

        strat = CambioTurnoStrategy()
        ok, msg = strat.revalidar_para_aprobar(nueva)
        self.assertTrue(ok, msg)
        ok, msg = strat.aplicar_cambios(nueva)
        self.assertTrue(ok, msg)
        self.assertEqual(self._jornadas(self.sol), [('PM', 'CT')])

    def test_hoy_se_rechaza_al_crear_pero_no_al_aprobar(self):
        """El día en curso ya se está trabajando: no se puede PEDIR un CT para hoy. Pero una
        solicitud enviada ayer para hoy sigue siendo aprobable — decide el supervisor."""
        strat = CambioTurnoStrategy()
        datos = {
            'explorador_solicitante': self.sol,
            'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo,
            'comentario': 'Prueba',
            'fecha_cambio_turno': timezone.localdate().strftime('%Y-%m-%d'),
        }
        ok, msg = strat.validar_solicitud(dict(datos))
        self.assertFalse(ok)
        self.assertIn('hoy', msg.lower())

        # Al re-validar para aprobar, la regla de "hoy" no aplica: debe pasar de ella
        # (puede fallar más adelante por otras reglas del día, que este test no configura).
        ok, msg = strat.validar_solicitud({**datos, 'es_revalidacion': True})
        self.assertNotIn('el día ya está en curso', msg)

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
