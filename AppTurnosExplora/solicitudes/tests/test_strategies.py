"""
Tests para estrategias de solicitudes
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy


class CambioTurnoStrategyTest(TestCase):
    """Tests para CambioTurnoStrategy"""
    
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CT',
            codigo_estrategia='CT',
            activo=True
        )
        # El constructor ya no recibe argumentos: fija internamente el tipo "CT".
        self.strategy = CambioTurnoStrategy()
    
    def test_strategy_instanciacion(self):
        """Test que se puede instanciar la estrategia"""
        self.assertIsNotNone(self.strategy)
        self.assertEqual(self.strategy.tipo_solicitud, 'CT')
    
    def test_strategy_tiene_metodos_requeridos(self):
        """Test que la estrategia tiene los métodos requeridos"""
        self.assertTrue(hasattr(self.strategy, 'validar_solicitud'))
        self.assertTrue(hasattr(self.strategy, 'crear_solicitud'))
        self.assertTrue(hasattr(self.strategy, 'aplicar_cambios'))


class CambioTurnoDescansoSemanaTest(TestCase):
    """
    CT sencillo debe usar la jornada REAL: no se puede intercambiar en un día donde un
    participante tiene DESCANSO DE SEMANA manual (aunque su jornada predeterminada exista).
    """

    def setUp(self):
        from empleados.models import Empleado, Jornada
        from turnos.models import AsignarJornadaExplorador, Sala
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO', codigo_estrategia='CT', activo=True)
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CT', activo=True)
        ue = User.objects.create_user('em_ct', password='x', email='e@e.com')
        self.emisor = Empleado.objects.create(user=ue, nombre='Em', apellido='T', cedula='5551', email='e@e.com', activo=True)
        ur = User.objects.create_user('re_ct', password='x', email='r@r.com')
        self.receptor = Empleado.objects.create(user=ur, nombre='Re', apellido='T', cedula='5552', email='r@r.com', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.emisor, jornada=self.pm, fecha_inicio=date(2026, 1, 1))
        AsignarJornadaExplorador.objects.create(explorador=self.receptor, jornada=self.am, fecha_inicio=date(2026, 1, 1))
        self.strategy = CambioTurnoStrategy()

    @staticmethod
    def _martes_futuro():
        d = timezone.localdate() + timedelta(days=7)
        while d.weekday() != 1:  # martes: día de semana, no sábado/domingo
            d += timedelta(days=1)
        return d

    def _datos(self, fecha):
        return dict(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo, fecha_cambio_turno=str(fecha), comentario='test ct',
        )

    def test_ct_valido_cuando_ambos_trabajan(self):
        f = self._martes_futuro()
        ok, msg = self.strategy.validar_solicitud(self._datos(f))
        self.assertTrue(ok, f'Esperaba VÁLIDO (ambos trabajan, jornadas contrarias): {msg}')

    def test_ct_rechaza_si_receptor_descansa_de_semana(self):
        from turnos.models import DescansoSemanaManual
        f = self._martes_futuro()
        DescansoSemanaManual.objects.create(fecha=f, jornada=self.am, motivo='otro', descripcion='t', activo=True)
        ok, msg = self.strategy.validar_solicitud(self._datos(f))
        self.assertFalse(ok, 'Debe RECHAZAR: el receptor descansa de semana ese día')
        self.assertIn('descansa', str(msg).lower())

    def test_ct_rechaza_si_solicitante_descansa_de_semana(self):
        from turnos.models import DescansoSemanaManual
        f = self._martes_futuro()
        DescansoSemanaManual.objects.create(fecha=f, jornada=self.pm, motivo='otro', descripcion='t', activo=True)
        ok, msg = self.strategy.validar_solicitud(self._datos(f))
        self.assertFalse(ok, 'Debe RECHAZAR: el solicitante descansa de semana ese día')

    def test_ct_permanente_es_dia_descanso_detecta_descanso_semana(self):
        """El helper de CT permanente ahora detecta el descanso de semana manual."""
        from solicitudes.services.cambios_permanentes_helper import _es_dia_descanso
        from turnos.models import DescansoSemanaManual
        f = self._martes_futuro()
        self.assertFalse(_es_dia_descanso(self.receptor, f))
        DescansoSemanaManual.objects.create(fecha=f, jornada=self.am, motivo='otro', descripcion='t', activo=True)
        self.assertTrue(_es_dia_descanso(self.receptor, f))


