"""Vistas de la API de turnos, divididas por dominio.

Este paquete reemplaza el antiguo módulo turnos/api/views.py (1537 líneas). El
__init__ re-exporta todas las vistas para que `from . import views` + `views.X`
(en turnos/api/urls.py) siga funcionando sin cambios.
"""
from .calculo_automatico import CalcularFestivosAutomaticoView, CalcularMantenimientoAutomaticoView
from .dias_especiales import DiasEspecialesPorTipoView, DiasFestivosView, DiasTemporadaView
from .reportes import ReporteDiaExcelView, ReporteDiaView
from .turnos_mes import MisTurnosPorMesView, TurnosPorDiaView, TurnosPorMesView

__all__ = [
    'ReporteDiaView',
    'ReporteDiaExcelView',
    'TurnosPorDiaView',
    'TurnosPorMesView',
    'MisTurnosPorMesView',
    'DiasFestivosView',
    'DiasTemporadaView',
    'DiasEspecialesPorTipoView',
    'CalcularMantenimientoAutomaticoView',
    'CalcularFestivosAutomaticoView',
]
