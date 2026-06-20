# Strategies package for different solicitud types

from .base_strategy import SolicitudStrategy
from .cambio_turno_strategy import CambioTurnoStrategy
from .doblada_strategy import DobladaStrategy
from .ct_permanente_strategy import CTPermanenteStrategy
from .d_fds_strategy import DFDSStrategy
from .doblada_permanente_strategy import DobladaPermanenteStrategy
from .cambio_descanso_strategy import CambioDescansoStrategy

__all__ = [
    'SolicitudStrategy',
    'CambioTurnoStrategy',
    'DobladaStrategy',
    'CTPermanenteStrategy',
    'DFDSStrategy',
    'DobladaPermanenteStrategy',
    'CambioDescansoStrategy',
]