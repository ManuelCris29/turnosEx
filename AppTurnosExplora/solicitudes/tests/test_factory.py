"""
Tests para SolicitudFactory
"""
from django.test import TestCase
from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from solicitudes.services.strategies import (
    CambioTurnoStrategy,
    CTPermanenteStrategy
)


class SolicitudFactoryTest(TestCase):
    """Tests para SolicitudFactory"""
    
    def setUp(self):
        # Crear tipos de solicitud
        self.tipo_ct = TipoSolicitudCambio.objects.create(
            nombre='CT',
            codigo_estrategia='CT',
            activo=True
        )
        self.tipo_ct_permanente = TipoSolicitudCambio.objects.create(
            nombre='CT PERMANENTE',
            codigo_estrategia='CT_PERMANENTE',
            activo=True
        )
    
    def test_get_strategy_ct(self):
        """Test que se obtiene la estrategia correcta para CT"""
        strategy = SolicitudFactory.get_strategy(self.tipo_ct)
        self.assertIsNotNone(strategy)
        self.assertIsInstance(strategy, CambioTurnoStrategy)
    
    def test_get_strategy_ct_permanente(self):
        """Test que se obtiene la estrategia correcta para CT PERMANENTE"""
        strategy = SolicitudFactory.get_strategy(self.tipo_ct_permanente)
        self.assertIsNotNone(strategy)
        self.assertIsInstance(strategy, CTPermanenteStrategy)
    
    def test_get_strategy_por_codigo(self):
        """Test que se puede obtener estrategia por código"""
        tipo_con_codigo = TipoSolicitudCambio.objects.create(
            nombre='Test Tipo',
            codigo_estrategia='CT',
            activo=True
        )
        strategy = SolicitudFactory.get_strategy(tipo_con_codigo)
        self.assertIsNotNone(strategy)
        self.assertIsInstance(strategy, CambioTurnoStrategy)


