from django.urls import path
from . import views

app_name = 'turnos_api'

urlpatterns = [
    path('turnos-por-dia/', views.TurnosPorDiaView.as_view(), name='turnos_por_dia'),
    path('turnos-por-mes/', views.TurnosPorMesView.as_view(), name='turnos_por_mes'),
    path('mis-turnos-por-mes/', views.MisTurnosPorMesView.as_view(), name='mis_turnos_por_mes'),
]
