# -*- coding: utf-8 -*-
"""Regresión: el CT PERMANENTE respeta "Mis Turnos" (TurnoService.estado_dia) y, al expandir el
rango de días, OMITE los días que el usuario no trabaja realmente: dobladas, mantenimientos,
festivos, temporada, descansos y días libres por otra solicitud.

Cada test crea UN tipo de día sobre un martes candidato y verifica que:
  - NO aparece en las fechas aplicables, y
  - aparece en las excluidas con la razón esperada.
El primer test (control) fija que un martes normal SÍ es aplicable, para que las exclusiones
prueben algo real (no un rango vacío).
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, CompetenciaEmpleado
from turnos.models import (
    Jornada, Sala, Turno, DiaEspecial, DescansoSemanaManual, AsignarJornadaExplorador,
)
from solicitudes.models import (
    SolicitudCambio, TipoSolicitudCambio, CambioPermanenteDetalle, CambioPermanenteDia,
)
from solicitudes.services.ct_permanente_helper import (
    calcular_fechas_aplicables_ct_permanente as calc,
    calcular_fechas_aplicables_y_excluidas_ct_permanente as calc_full,
)


class CTPermanenteOmiteDiasTest(TestCase):
    def setUp(self):
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CT PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CTP', activo=True)
        # Solicitante y receptor: base AM (ambos trabajan) → un martes normal es aplicable.
        u1 = User.objects.create_user(username='ctp.sol', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='CTP', cedula='31', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        u2 = User.objects.create_user(username='ctp.rec', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='CTP', cedula='32', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)

        hoy = timezone.localdate()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        self.ff = self.fi + timedelta(days=27)
        # Solicitud + detalle sobre TODOS los martes del rango.
        self.solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, estado='pendiente', comentario='CTP test')
        self.detalle = CambioPermanenteDetalle.objects.create(
            solicitud=self.solicitud, fecha_inicio=self.fi, fecha_fin=self.ff)
        CambioPermanenteDia.objects.create(cambio_permanente=self.detalle, tipo='dia_semana', dia_semana=1)

    def _martes(self):
        out, d = [], self.fi
        while d <= self.ff:
            if d.weekday() == 1:
                out.append(d)
            d += timedelta(days=1)
        return out

    def _aplicables(self):
        cache.clear()
        return calc(self.detalle, self.sol, self.rec)

    def _razon(self, fecha):
        cache.clear()
        _, exc = calc_full(self.detalle, self.sol, self.rec)
        for e in exc:
            if e['fecha'] == fecha:
                return e['razon']
        return None

    # --- control: sin nada, todos los martes son aplicables ------------------
    def test_control_martes_normal_es_aplicable(self):
        martes = self._martes()
        self.assertEqual(self._aplicables(), martes,
                         'sin excepciones, todos los martes (base AM/PM, ambos trabajan) son aplicables')

    # --- doblada: 2 turnos reales AM+PM ese día ------------------------------
    def test_doblada_del_solicitante_se_omite(self):
        m = self._martes()[0]
        Turno.objects.create(explorador=self.sol, fecha=m, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.sol, fecha=m, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        self.assertNotIn(m, self._aplicables(), 'un día con doblada real no está en jornada predeterminada')
        self.assertEqual(self._razon(m), 'Doblada Solicitante')

    # --- mantenimiento -------------------------------------------------------
    def test_mantenimiento_se_omite(self):
        m = self._martes()[0]
        DiaEspecial.objects.create(fecha=m, tipo='mantenimiento', activo=True)
        self.assertNotIn(m, self._aplicables())
        self.assertEqual(self._razon(m), 'Mantenimiento')

    # --- festivo -------------------------------------------------------------
    def test_festivo_se_omite(self):
        m = self._martes()[0]
        DiaEspecial.objects.create(fecha=m, tipo='festivo', activo=True)
        self.assertNotIn(m, self._aplicables())
        self.assertEqual(self._razon(m), 'Festivo')

    # --- temporada -----------------------------------------------------------
    def test_temporada_se_omite(self):
        m = self._martes()[0]
        DiaEspecial.objects.create(fecha=m, tipo='temporada', es_temporada=True, activo=True)
        self.assertNotIn(m, self._aplicables())
        self.assertEqual(self._razon(m), 'Temporada')

    # --- descanso de temporada (DescansoSemanaManual) por jornada ------------
    def test_descanso_semana_manual_se_omite(self):
        m = self._martes()[0]
        # El grupo AM (solicitante) descansa ese martes por temporada → estado_dia: no trabaja.
        DescansoSemanaManual.objects.create(fecha=m, jornada=self.am, activo=True)
        self.assertNotIn(m, self._aplicables(), 'si el solicitante descansa (Mis Turnos), el día se omite')
        self.assertEqual(self._razon(m), 'Descanso Solicitante')

    # --- doblada VIRTUAL por temporada, SIN compañero elegido ----------------
    def test_doblada_virtual_se_omite_sin_receptor(self):
        """Cuando el grupo contrario descansa por temporada, el otro grupo DOBLA ese día. Esa
        doblada es VIRTUAL: la calcula `estado_dia` y no deja ninguna fila `Turno`, así que
        `_tipo_cambio_previo` no la ve.

        Regresión: la vista previa sin compañero (receptor=None) daba ese día por APLICABLE —
        `_es_dia_descanso` no excluye una doblada (`trabaja=True`) y la única comprobación de
        media jornada estaba condicionada a que hubiera receptor—. Se ofrecía cambiar el turno
        de un día en el que el solicitante ya cubre AM y PM.
        """
        from solicitudes.services.ct_permanente_helper import (
            evaluar_fechas_ct_permanente, _razones_exclusion_ct_permanente,
        )
        from turnos.services.turno_service import TurnoService

        m = self._martes()[0]
        # Descansa el grupo PM → el solicitante (AM) queda DOBLADA ese martes.
        DescansoSemanaManual.objects.create(fecha=m, jornada=self.pm, activo=True)
        cache.clear()

        self.assertEqual(TurnoService.estado_dia(self.sol, m).get('jornada'), 'DOBLADA',
                         'precondición: el solicitante dobla ese día según Mis Turnos')
        self.assertFalse(Turno.objects.filter(explorador=self.sol, fecha=m).exists(),
                         'precondición: la doblada es virtual, sin filas Turno que delaten el cambio')

        aplicables, _ = evaluar_fechas_ct_permanente(
            self.fi, self.ff, self.sol, None, {'dias_semana': [1]})
        self.assertNotIn(m, aplicables, 'sin compañero elegido, un día ya doblado NO es aplicable')
        self.assertEqual(_razones_exclusion_ct_permanente(m, self.sol, None), ['Doblada Solicitante'])

    # --- turno real que cambia la jornada (CT sencillo) → cambio previo ------
    def test_cambio_previo_se_omite(self):
        m = self._martes()[0]
        Turno.objects.create(explorador=self.rec, fecha=m, jornada=self.am, sala=self.sala, tipo_cambio='CAMBIO TURNO')
        self.assertNotIn(m, self._aplicables(), 'un día ya cambiado no está en jornada predeterminada')
        self.assertEqual(self._razon(m), 'Cambio Previo Receptor')

    # --- coherencia global: toda aplicable trabaja de verdad en Mis Turnos ---
    def test_toda_aplicable_ambos_trabajan_segun_estado_dia(self):
        from turnos.services.turno_service import TurnoService
        # Mezcla varias excepciones en martes distintos.
        ms = self._martes()
        DiaEspecial.objects.create(fecha=ms[0], tipo='mantenimiento', activo=True)
        DescansoSemanaManual.objects.create(fecha=ms[1], jornada=self.pm, activo=True)
        Turno.objects.create(explorador=self.sol, fecha=ms[2], jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.sol, fecha=ms[2], jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        for f in self._aplicables():
            es = TurnoService.estado_dia(self.sol, f)
            er = TurnoService.estado_dia(self.rec, f)
            self.assertTrue(es.get('trabaja') and es.get('jornada') in ('AM', 'PM'),
                            f'{f}: solicitante debe trabajar jornada única en Mis Turnos, got {es}')
            self.assertTrue(er.get('trabaja') and er.get('jornada') in ('AM', 'PM'),
                            f'{f}: receptor debe trabajar jornada única en Mis Turnos, got {er}')
