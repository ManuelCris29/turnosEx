"""
Tests del REVERT de CT permanente al cancelar dentro de los 30 min.

CT permanente crea turnos `CT PERMANENTE` en un rango recurrente. Al cancelar, debe hacer
un BORRADO DIRIGIDO: borra solo sus turnos CT PERMANENTE, respetando un CT sencillo que
hubiera modificado uno de esos días después (turno que ya no es 'CT PERMANENTE').
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import TipoSolicitudCambio
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy


class CTPermRevertTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CT PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CTP', activo=True)

        u1 = User.objects.create_user(username='sol.ctp', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='A', cedula='1', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.am, fecha_inicio=date(2025, 1, 1))

        u2 = User.objects.create_user(username='rec.ctp', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='B', cedula='2', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.pm, fecha_inicio=date(2025, 1, 1))

        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)

        # Dos martes futuros
        d = timezone.localdate() + timedelta(days=5)
        while d.weekday() != 1:
            d += timedelta(days=1)
        self.d1 = d
        self.d2 = d + timedelta(days=7)

    def test_revalidacion_para_aprobar_ok(self):
        # Un CT permanente válido (pendiente) debe re-validar True al aprobar.
        strat = CTPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.d1.strftime('%Y-%m-%d'),
            'fecha_fin': self.d2.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'fechas_especificas': [
                self.d1.strftime('%Y-%m-%d'), self.d2.strftime('%Y-%m-%d')]},
        })
        self.assertIsNotNone(sol, msg)
        ok, m = strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)

    def test_revert_dirigido_respeta_ct_sencillo(self):
        strat = CTPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.d1.strftime('%Y-%m-%d'),
            'fecha_fin': self.d2.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'fechas_especificas': [
                self.d1.strftime('%Y-%m-%d'), self.d2.strftime('%Y-%m-%d')]},
        })
        self.assertIsNotNone(sol, msg)
        ok, msg = strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        sol.refresh_from_db()

        # Creó turnos CT PERMANENTE en d1 y d2.
        self.assertTrue(Turno.objects.filter(explorador=self.sol, fecha=self.d1, tipo_cambio='CT PERMANENTE').exists())
        self.assertTrue(Turno.objects.filter(explorador=self.sol, fecha=self.d2, tipo_cambio='CT PERMANENTE').exists())
        self.assertTrue(sol.snapshot_turnos_previos, "Debió guardar las fechas creadas")

        # Simular un CT sencillo encima el d1: ese turno pasa a 'CT'.
        t = Turno.objects.get(explorador=self.sol, fecha=self.d1)
        t.tipo_cambio = 'CT'
        t.save()

        # Revertir (borrado dirigido).
        CTPermanenteStrategy.revertir(sol)

        # d2: turnos CT PERMANENTE borrados (vuelve a virtual).
        self.assertFalse(Turno.objects.filter(explorador=self.sol, fecha=self.d2).exists())
        self.assertFalse(Turno.objects.filter(explorador=self.rec, fecha=self.d2).exists())
        # d1: el CT sencillo posterior se RESPETA (no se borra).
        self.assertTrue(Turno.objects.filter(explorador=self.sol, fecha=self.d1, tipo_cambio='CT').exists())
