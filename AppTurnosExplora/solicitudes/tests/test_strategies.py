"""
Tests para estrategias de solicitudes
"""
from django.test import TestCase
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


