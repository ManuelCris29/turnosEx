"""
Tests positivos de re-validación al aprobar para DOBLADA y DOBLADA PERMANENTE.

Garantizan que una solicitud VÁLIDA re-valide True al aprobar (no se bloqueen aprobaciones
válidas por la reconstrucción de datos ni por auto-referencia en chequeos de creación).
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import AsignarJornadaExplorador, Sala
from solicitudes.tests.test_matriz_dobladas import MatrizDobladasTestCase
from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy


class DobladaRevalidacionTest(MatrizDobladasTestCase):
    def test_revalidacion_para_aprobar_ok(self):
        # CASO 1 válido: emisor PM, receptor AM (una jornada cada uno).
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        sol, msg = self.strategy.crear_solicitud(self._datos(tipo_cambio=self.tipo_doblada))
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        ok, m = self.strategy.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)


class DobladaConcurrenciaReceptorTest(MatrizDobladasTestCase):
    def test_caso_b_receptor_ya_comprometido(self):
        from empleados.models import CompetenciaEmpleado
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)

        # A: emisor(PM) -> receptor(AM) doblada, aprobada + aplicada.
        solA, msg = self.strategy.crear_solicitud(self._datos(tipo_cambio=self.tipo_doblada))
        self.assertIsNotNone(solA, msg)
        solA.estado = 'aprobada'
        solA.fecha_resolucion = timezone.now()
        solA.save()
        solA = SolicitudCambio.objects.select_related('doblada').get(id=solA.id)
        ok, m = self.strategy.aplicar_cambios(solA)
        self.assertTrue(ok, m)

        # B: segundo emisor (PM) hacia el MISMO receptor, misma cesión -> debe bloquearse.
        u = User.objects.create_user('emisor2.dob', password='x', email='e2@t.com')
        em2 = Empleado.objects.create(user=u, nombre='Em2', apellido='Test', cedula='3333', email='e2@t.com', activo=True)
        self._asignar_jornada_base(em2, self.jornada_pm)
        CompetenciaEmpleado.objects.get_or_create(empleado=em2, sala=self.sala)
        ok2, m2 = self.strategy.validar_solicitud(self._datos(explorador_solicitante=em2, tipo_cambio=self.tipo_doblada))
        self.assertFalse(ok2, f"B debió bloquearse (receptor ya comprometido por A). msg={m2}")


class DobladaPermRevalidacionTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DP', activo=True)

        u1 = User.objects.create_user(username='sol.dp', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='A', cedula='1', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        u2 = User.objects.create_user(username='rec.dp', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='B', cedula='2', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)

        # Rango futuro (mes siguiente), días: cesión martes (1), devolución jueves (3).
        hoy = timezone.now().date()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        self.ff = self.fi + timedelta(days=27)

    def test_revalidacion_para_aprobar_ok(self):
        strat = DobladaPermanenteStrategy()
        datos = {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',
        }
        # Sanity: debe ser válido al crear.
        ok, msg = strat.validar_solicitud(datos)
        self.assertTrue(ok, msg)
        sol, msg = strat.crear_solicitud(datos)
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        ok, m = strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)

    def test_aplicacion_balanceada(self):
        # Si un lado tiene menos días válidos, la aplicación recorta al mínimo común:
        # se aplican IGUAL número de cesiones y devoluciones (no se paga sin recibir).
        from datetime import timedelta
        from turnos.models import Turno
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',  # martes cubre, jueves devuelve
        })
        self.assertIsNotNone(sol, msg)
        # Comprometer UN jueves (devolución) → ese lado queda con un día válido menos.
        d = self.fi
        while d.weekday() != 3:
            d += timedelta(days=1)
        Turno.objects.create(explorador=self.sol, fecha=d, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.sol, fecha=d, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')

        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        n_ces, n_dev = DPAS.aplicar(sol, sol.doblada_permanente)
        self.assertEqual(n_ces, n_dev, "Cesiones y devoluciones aplicadas deben quedar balanceadas")
        self.assertGreaterEqual(n_ces, 1)

    def test_sabado_rechazado(self):
        # La doblada permanente ya no admite sábados (solo lun-vie).
        strat = DobladaPermanenteStrategy()
        datos = {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '5', 'dias_devolucion': '3',
        }
        ok, msg = strat.validar_solicitud(datos)
        self.assertFalse(ok)
        self.assertIn('lunes a viernes', msg.lower())

    def test_ocurrencias_omite_comprometido_y_sabado(self):
        # Núcleo del comportamiento "omitir": un día comprometido se salta; los demás siguen.
        from datetime import timedelta
        from turnos.models import Turno
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        d = self.fi
        while d.weekday() != 1:  # primer martes
            d += timedelta(days=1)
        primer_martes = d

        occ = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertIn(primer_martes, occ)

        # Comprometer ese martes para el solicitante (doblada previa).
        Turno.objects.create(explorador=self.sol, fecha=primer_martes, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.sol, fecha=primer_martes, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')

        occ2 = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertNotIn(primer_martes, occ2)   # se OMITE
        self.assertGreaterEqual(len(occ2), 1)   # pero los demás martes siguen

        # Sábado: nunca aparece.
        self.assertEqual(list(DPAS._ocurrencias(self.fi, self.ff, {5}, self.sol, self.rec)), [])
