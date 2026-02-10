from django.urls import path
from . import views

app_name = 'turnos_api'

urlpatterns = [
    path('turnos-por-dia/', views.TurnosPorDiaView.as_view(), name='turnos_por_dia'),
    path('turnos-por-mes/', views.TurnosPorMesView.as_view(), name='turnos_por_mes'),
    path('mis-turnos-por-mes/', views.MisTurnosPorMesView.as_view(), name='mis_turnos_por_mes'),
    path('dias-festivos/', views.DiasFestivosView.as_view(), name='dias_festivos'),
    path('dias-temporada/', views.DiasTemporadaView.as_view(), name='dias_temporada'),
    path('dias-especiales-por-tipo/', views.DiasEspecialesPorTipoView.as_view(), name='dias_especiales_por_tipo'),
    path('calcular-mantenimiento-automatico/', views.CalcularMantenimientoAutomaticoView.as_view(), name='calcular_mantenimiento_automatico'),
    path('calcular-festivos-automatico/', views.CalcularFestivosAutomaticoView.as_view(), name='calcular_festivos_automatico'),
]
