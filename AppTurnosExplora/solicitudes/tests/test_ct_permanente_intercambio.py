# -*- coding: utf-8 -*-
"""Regresión del CT PERMANENTE como INTERCAMBIO real de jornadas.

Cubre los huecos que tenía el flujo `/solicitudes/cambio-turno/solicitar/2/`:

  1. Un día en el que ambos trabajan la MISMA jornada no es aplicable (no hay nada que
     intercambiar) — antes se aplicaba y dejaba a los dos en la jornada contraria, con la
     franja original sin cobertura. La regla vivía solo en el JS.
  2. Si no queda ningún día aplicable, `aplicar_cambios` FALLA — antes devolvía éxito con
     "0 días" y dejaba la solicitud aprobada sin turnos ni snapshot.
  3. Se aplica con delete+create — antes el `create` suelto dejaba dos turnos el mismo día
     y "Mis Turnos" leía el día como DOBLADA.
  4. Cada uno recibe la jornada DEL OTRO (intercambio), no "la contraria de la suya".
  5. Una solicitud cuyo rango ya empezó sigue siendo aprobable por sus días futuros.
  6. La detección de solapamiento cubre el rango nuevo que empieza ANTES del existente.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado
from solicitudes.models import (
    CambioPermanenteDetalle,
    CambioPermanenteDia,
    SolicitudCambio,
    TipoSolicitudCambio,
)
from solicitudes.services.ct_permanente_helper import (
    evaluar_fechas_ct_permanente,
    jornadas_intercambiables_ct,
)
from solicitudes.services.solicitud_validator import SolicitudValidator
from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy
from turnos.models import AsignarJornadaExplorador, Jornada, Sala, Turno


class CTPermanenteIntercambioTest(TestCase):
    def setUp(self):
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CT PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CTP', activo=True)

        u1 = User.objects.create_user(username='ctp.int.sol', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='Int', cedula='41', activo=True)
        u2 = User.objects.create_user(username='ctp.int.rec', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='Int', cedula='42', activo=True)
        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)

        # Dos martes futuros.
        d = timezone.localdate() + timedelta(days=7)
        while d.weekday() != 1:
            d += timedelta(days=1)
        self.d1, self.d2 = d, d + timedelta(days=7)

    def _asignar(self, jornada_sol, jornada_rec, desde=date(2025, 1, 1)):
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=jornada_sol, fecha_inicio=desde)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=jornada_rec, fecha_inicio=desde)

    def _crear(self, fechas=None):
        fechas = fechas or [self.d1, self.d2]
        strat = CTPermanenteStrategy()
        solicitud, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba intercambio',
            'fecha_inicio': self.d1.strftime('%Y-%m-%d'),
            'fecha_fin': self.d2.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'fechas_especificas': [f.strftime('%Y-%m-%d') for f in fechas]},
        })
        self.assertIsNotNone(solicitud, msg)
        return strat, solicitud

    # --- 1. misma jornada = no hay intercambio posible ------------------------
    def test_dia_con_misma_jornada_no_es_aplicable(self):
        self._asignar(self.am, self.am)  # ambos AM
        self.assertIsNone(jornadas_intercambiables_ct(self.sol, self.rec, self.d1))

        aplicables, excluidas = evaluar_fechas_ct_permanente(
            self.d1, self.d2, self.sol, self.rec,
            {'fechas_especificas': [self.d1, self.d2]},
        )
        self.assertEqual(aplicables, [], 'sin jornadas contrarias no hay nada que intercambiar')
        self.assertTrue(any(e['razon'] == 'Sin jornada contraria' for e in excluidas))

    def test_backend_rechaza_fechas_especificas_sin_jornada_contraria(self):
        """El backend ya no confía en el filtrado del frontend: valida él mismo."""
        self._asignar(self.am, self.am)
        strat = CTPermanenteStrategy()
        ok, msg = strat.validar_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Forzado',
            'fecha_inicio': self.d1.strftime('%Y-%m-%d'),
            'fecha_fin': self.d2.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'fechas_especificas': [self.d1.strftime('%Y-%m-%d')]},
        })
        self.assertFalse(ok, 'no debe aceptarse un día sin jornadas contrarias')
        self.assertIn('contrarias', msg)

    # --- 2. sin días aplicables, aplicar FALLA -------------------------------
    def test_aplicar_sin_dias_aplicables_falla(self):
        self._asignar(self.am, self.pm)
        strat, solicitud = self._crear()
        # Después de crearla, ambos pasan a AM: ya no queda ningún día intercambiable.
        AsignarJornadaExplorador.objects.create(
            explorador=self.rec, jornada=self.am, fecha_inicio=self.d1 - timedelta(days=1))
        cache.clear()

        ok, msg = strat.aplicar_cambios(solicitud)
        self.assertFalse(ok, 'aprobar sin materializar nada dejaba solicitudes fantasma')
        self.assertFalse(Turno.objects.filter(fecha__in=[self.d1, self.d2]).exists())

    # --- 3 y 4. intercambio real, un solo turno por día ----------------------
    def test_intercambio_asigna_la_jornada_del_otro(self):
        self._asignar(self.am, self.pm)
        strat, solicitud = self._crear()
        ok, msg = strat.aplicar_cambios(solicitud)
        self.assertTrue(ok, msg)

        for fecha in (self.d1, self.d2):
            t_sol = Turno.objects.get(explorador=self.sol, fecha=fecha)
            t_rec = Turno.objects.get(explorador=self.rec, fecha=fecha)
            self.assertEqual(t_sol.jornada, self.pm, 'el solicitante (AM) recibe la jornada del receptor')
            self.assertEqual(t_rec.jornada, self.am, 'el receptor (PM) recibe la jornada del solicitante')
            self.assertEqual(t_sol.tipo_cambio, 'CT PERMANENTE')

    def test_no_duplica_turnos_cuando_ya_existia_uno(self):
        """Un turno previo del horario importado (tipo_cambio NULL) se reemplaza, no se suma."""
        self._asignar(self.am, self.pm)
        Turno.objects.create(explorador=self.sol, fecha=self.d1, jornada=self.am, sala=self.sala)
        cache.clear()

        strat, solicitud = self._crear()
        ok, msg = strat.aplicar_cambios(solicitud)
        self.assertTrue(ok, msg)

        turnos = Turno.objects.filter(explorador=self.sol, fecha=self.d1)
        self.assertEqual(turnos.count(), 1, 'dos turnos el mismo día se leerían como DOBLADA')
        self.assertEqual(turnos.first().jornada, self.pm)

        # Y al revertir se restaura el turno original que pisamos.
        solicitud.refresh_from_db()
        CTPermanenteStrategy.revertir(solicitud)
        restaurado = Turno.objects.filter(explorador=self.sol, fecha=self.d1)
        self.assertEqual(restaurado.count(), 1)
        self.assertEqual(restaurado.first().jornada, self.am)
        self.assertIsNone(restaurado.first().tipo_cambio)

    # --- 5. rango ya empezado: aprobable por sus días futuros ----------------
    def test_revalidacion_admite_rango_ya_empezado(self):
        self._asignar(self.am, self.pm)
        strat, solicitud = self._crear()
        # Simular que el rango arrancó ayer (aprobación tardía).
        detalle = solicitud.cambio_permanente
        detalle.fecha_inicio = timezone.localdate() - timedelta(days=1)
        detalle.save()
        cache.clear()

        ok, msg = strat.revalidar_para_aprobar(solicitud)
        self.assertTrue(ok, f'debe seguir aprobable por sus días futuros: {msg}')

    def test_aplicar_no_toca_dias_pasados(self):
        self._asignar(self.am, self.pm)
        # Último día laborable ya transcurrido (el detalle solo admite lunes-viernes).
        # OJO: `timezone.localdate()`, no `timezone.localdate()`. El proyecto usa TIME_ZONE
        # 'America/Bogota' (UTC-5) con USE_TZ, así que `timezone.now()` va en UTC y su `.date()`
        # devuelve el día SIGUIENTE a partir de las 19:00 hora local. Con eso, "ayer" resultaba
        # ser HOY y el test fallaba cada noche.
        ayer = timezone.localdate() - timedelta(days=1)
        while ayer.weekday() >= 5:
            ayer -= timedelta(days=1)
        strat = CTPermanenteStrategy()
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, estado='pendiente', comentario='Tardía')
        detalle = CambioPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=ayer, fecha_fin=self.d2)
        for f in (ayer, self.d1):
            CambioPermanenteDia.objects.create(
                cambio_permanente=detalle, tipo='fecha_especifica', fecha_especifica=f)
        cache.clear()

        ok, msg = strat.aplicar_cambios(solicitud)
        self.assertTrue(ok, msg)
        self.assertFalse(Turno.objects.filter(fecha=ayer).exists(),
                         'no se reescriben turnos de días ya transcurridos')
        self.assertTrue(Turno.objects.filter(fecha=self.d1).exists())

    # --- 6. solapamiento por el lado izquierdo -------------------------------
    def test_solapamiento_detecta_rango_que_empieza_antes(self):
        self._asignar(self.am, self.pm)
        existente = SolicitudCambio.objects.create(
            explorador_solicitante=self.sol, explorador_receptor=self.rec,
            tipo_cambio=self.tipo, estado='aprobada', comentario='Existente')
        CambioPermanenteDetalle.objects.create(
            solicitud=existente, fecha_inicio=self.d2, fecha_fin=None)  # indefinido (heredado)

        with self.assertRaises(ValidationError):
            SolicitudValidator.validar_no_cambio_permanente_superpuesto(
                self.sol, self.rec, self.d1, self.d2 + timedelta(days=1))
