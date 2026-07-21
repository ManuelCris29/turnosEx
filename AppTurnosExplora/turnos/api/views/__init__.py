"""Vistas de la API de turnos, divididas por dominio.

Este paquete reemplaza el antiguo módulo turnos/api/views.py (1537 líneas). El
__init__ re-exporta todas las vistas para que `from . import views` + `views.X`
(en turnos/api/urls.py) siga funcionando sin cambios.
"""
from .reportes import ReporteDiaView, ReporteDiaExcelView
from .turnos_mes import TurnosPorDiaView, TurnosPorMesView, MisTurnosPorMesView
from .dias_especiales import DiasFestivosView, DiasTemporadaView, DiasEspecialesPorTipoView
from .calculo_automatico import CalcularMantenimientoAutomaticoView, CalcularFestivosAutomaticoView

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
