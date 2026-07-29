"""
Tests de la FUENTE ÚNICA `DescansoPorSolicitudService.en_rango`, de la que dependen
`estado_dia`/`estado_mes` (TurnoService) y el endpoint de Mis Turnos.

Garantiza que la atribución de descanso/compañero se calcula por FECHA específica y con
el compañero correcto, para que las 3 capas nunca vuelvan a divergir.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from turnos.models import Sala, AsignarJornadaExplorador
from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy
from solicitudes.services.doblada_permanente_aplicacion_service import (
    DobladaPermanenteAplicacionService as DPAS,
)
from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService as DS


class DescansoPorSolicitudServiceTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo_perm = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DS', activo=True)
        u1 = User.objects.create_user(username='sol.ds', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='DS', cedula='51', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        u2 = User.objects.create_user(username='c1.ds', password='x')
        self.c1 = Empleado.objects.create(user=u2, nombre='Uno', apellido='C', cedula='52', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.c1, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        u3 = User.objects.create_user(username='c2.ds', password='x')
        self.c2 = Empleado.objects.create(user=u3, nombre='Dos', apellido='C', cedula='53', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.c2, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        for e in (self.sol, self.c1, self.c2):
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        hoy = timezone.localdate()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        import calendar
        self.ff = date(anio, mes, calendar.monthrange(anio, mes)[1])
        self.lunes = [d for d in self._dias() if d.weekday() == 0]
        self.martes = [d for d in self._dias() if d.weekday() == 1]

    def _dias(self):
        d, out = self.fi, []
        while d <= self.ff:
            out.append(d)
            d += timedelta(days=1)
        return out

    def _perm(self, receptor, fecha_ces, fecha_dev):
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': receptor,
            'tipo_cambio': self.tipo_perm, 'comentario': 'ds',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'), 'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['0'], 'dias_devolucion': ['1'],
            'fechas_cesion': fecha_ces.strftime('%Y-%m-%d'),
            'fechas_devolucion': fecha_dev.strftime('%Y-%m-%d'),
        })
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'; sol.fecha_resolucion = timezone.now(); sol.save()
        from solicitudes.models import SolicitudCambio
        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        DPAS.aplicar(sol, sol.doblada_permanente)
        return sol

    def test_perm_multicompanero_por_fecha(self):
        """El mismo weekday (lunes) repartido entre dos compañeros por fechas distintas: cada
        fecha de cesión se atribuye a SU compañero; un lunes no cedido no aparece."""
        if len(self.lunes) < 3 or len(self.martes) < 2:
            self.skipTest('mes sin suficientes lunes/martes')
        self._perm(self.c1, self.lunes[0], self.martes[0])
        self._perm(self.c2, self.lunes[1], self.martes[1])
        from django.core.cache import cache
        cache.clear()
        r = DS.en_rango(self.sol, self.fi, self.ff)
        self.assertEqual((r.get(self.lunes[0]) or {}).get('companero', {}).get('nombre'), 'Uno C')
        self.assertEqual((r.get(self.lunes[1]) or {}).get('companero', {}).get('nombre'), 'Dos C')
        self.assertNotIn(self.lunes[2], r, 'un lunes sin fecha cedida no debe aparecer como descanso')

    def test_en_fecha_coincide_con_en_rango(self):
        self._perm(self.c1, self.lunes[0], self.martes[0])
        from django.core.cache import cache
        cache.clear()
        uno = DS.en_fecha(self.sol, self.lunes[0])
        self.assertIsNotNone(uno)
        self.assertEqual(uno['companero']['nombre'], 'Uno C')
        self.assertEqual(uno['motivo'], 'doblada permanente')
        # Un día sin descanso devuelve None.
        self.assertIsNone(DS.en_fecha(self.sol, self.lunes[2] if len(self.lunes) > 2 else self.ff))
