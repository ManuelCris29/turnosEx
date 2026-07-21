"""Fachada de compatibilidad para el validador de solicitudes.

La implementación real vive en el paquete `validators/`, dividida por dominio
(BaseValidator, CTValidator, CTPermanenteValidator, DobladaValidator). Aquí se
combinan por herencia múltiple: como todos los métodos son @staticmethod, quedan
expuestos tal cual (incluido el helper _explorador_trabaja).

Los callers existentes que usan `SolicitudValidator.validar_x(...)` siguen
funcionando sin cambios. La migración a imports directos de los módulos nuevos
es un paso posterior.
"""
from .validators.base_validator import BaseValidator
from .validators.ct_validator import CTValidator
from .validators.ct_permanente_validator import CTPermanenteValidator
from .validators.doblada_validator import DobladaValidator


class SolicitudValidator(BaseValidator, CTValidator, CTPermanenteValidator, DobladaValidator):
    """Validador centralizado para solicitudes de cambio de turno (fachada)."""
    pass
