"""
Tests para la máquina de estados de SolicitudCambio.

Cubren:
- Transiciones válidas (pendiente→aprobada, aprobada→cancelada, etc.)
- Transiciones ilegales lanzan EstadoTransicionError
- Estados terminales no tienen salida
- puede_transicionar() y transiciones_posibles()
"""
from django.test import TestCase
from django.contrib.auth.models import User

from empleados.models import Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.domain.estado_machine import (
    transicionar,
    puede_transicionar,
    transiciones_posibles,
    es_terminal,
    EstadoTransicionError,
)
from turnos.models import AsignarJornadaExplorador
from datetime import date


def _empleado(username, ced, jornada):
    u = User.objects.create_user(username=username, password='x')
    e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
    AsignarJornadaExplorador.objects.create(
        explorador=e, jornada=jornada, fecha_inicio=date(2025, 1, 1)
    )
    return e


class EstadoMachineTransicionesValidasTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00', hora_fin='14:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00', hora_fin='22:00')
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CT', codigo_estrategia='CT', activo=True)
        self.sol = _empleado('sol_fsm', '100', self.am)
        self.rec = _empleado('rec_fsm', '200', self.pm)

    def _solicitud(self, estado='pendiente'):
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.sol,
            explorador_receptor=self.rec,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=date(2027, 8, 1),
            estado=estado,
        )

    def test_pendiente_a_aprobada(self):
        s = self._solicitud('pendiente')
        transicionar(s, 'aprobada')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'aprobada')

    def test_pendiente_a_rechazada(self):
        s = self._solicitud('pendiente')
        transicionar(s, 'rechazada')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'rechazada')

    def test_pendiente_a_cancelada(self):
        s = self._solicitud('pendiente')
        transicionar(s, 'cancelada')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'cancelada')

    def test_aprobada_a_cancelada(self):
        s = self._solicitud('aprobada')
        transicionar(s, 'cancelada')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'cancelada')

    def test_aprobada_a_reemplazada(self):
        s = self._solicitud('aprobada')
        transicionar(s, 'reemplazada')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'reemplazada')

    def test_aprobada_a_pagada(self):
        s = self._solicitud('aprobada')
        transicionar(s, 'pagada')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'pagada')

    def test_save_false_no_persiste(self):
        s = self._solicitud('pendiente')
        transicionar(s, 'aprobada', save=False)
        self.assertEqual(s.estado, 'aprobada')   # en memoria
        s.refresh_from_db()
        self.assertEqual(s.estado, 'pendiente')  # BD sin cambio


class EstadoMachineTransicionesIlegalesTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00', hora_fin='14:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00', hora_fin='22:00')
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CT2', codigo_estrategia='CT', activo=True)
        self.sol = _empleado('sol_ilegal', '300', self.am)
        self.rec = _empleado('rec_ilegal', '400', self.pm)

    def _solicitud(self, estado):
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.sol,
            explorador_receptor=self.rec,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=date(2027, 9, 1),
            estado=estado,
        )

    def test_rechazada_no_puede_transicionar(self):
        s = self._solicitud('rechazada')
        with self.assertRaises(EstadoTransicionError):
            transicionar(s, 'pendiente')

    def test_cancelada_no_puede_transicionar(self):
        s = self._solicitud('cancelada')
        with self.assertRaises(EstadoTransicionError):
            transicionar(s, 'aprobada')

    def test_pagada_no_puede_transicionar(self):
        s = self._solicitud('pagada')
        with self.assertRaises(EstadoTransicionError):
            transicionar(s, 'aprobada')

    def test_reemplazada_no_puede_transicionar(self):
        s = self._solicitud('reemplazada')
        with self.assertRaises(EstadoTransicionError):
            transicionar(s, 'aprobada')

    def test_pendiente_no_puede_ir_a_pagada(self):
        s = self._solicitud('pendiente')
        with self.assertRaises(EstadoTransicionError):
            transicionar(s, 'pagada')

    def test_aprobada_no_puede_volver_a_pendiente(self):
        s = self._solicitud('aprobada')
        with self.assertRaises(EstadoTransicionError):
            transicionar(s, 'pendiente')

    def test_estado_desconocido_lanza_error(self):
        s = self._solicitud('pendiente')
        with self.assertRaises((EstadoTransicionError, ValueError)):
            transicionar(s, 'estado_inventado')


class EstadoMachineHelpersTest(TestCase):

    def test_puede_transicionar_valido(self):
        self.assertTrue(puede_transicionar('pendiente', 'aprobada'))
        self.assertTrue(puede_transicionar('aprobada', 'cancelada'))

    def test_puede_transicionar_invalido(self):
        self.assertFalse(puede_transicionar('rechazada', 'aprobada'))
        self.assertFalse(puede_transicionar('pendiente', 'pagada'))

    def test_transiciones_posibles_pendiente(self):
        t = transiciones_posibles('pendiente')
        self.assertIn('aprobada', t)
        self.assertIn('rechazada', t)
        self.assertIn('cancelada', t)

    def test_transiciones_posibles_terminal(self):
        self.assertEqual(transiciones_posibles('rechazada'), set())
        self.assertEqual(transiciones_posibles('cancelada'), set())

    def test_es_terminal(self):
        for estado in ('rechazada', 'cancelada', 'pagada', 'reemplazada'):
            self.assertTrue(es_terminal(estado), f"{estado} debería ser terminal")

    def test_no_es_terminal(self):
        for estado in ('pendiente', 'aprobada'):
            self.assertFalse(es_terminal(estado), f"{estado} no debería ser terminal")
