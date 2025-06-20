from django.urls import path
from .views import (
    MisTurnosView, CambiosTurnoView, ConsolidadoHorasView, DiasEspecialesView
)

# A medida que vayas creando las vistas para la app de turnos,
# deberás agregarlas aquí.
urlpatterns = [
    path('mis-turnos/', MisTurnosView.as_view(), name='mis_turnos'),
    path('cambios-turno/', CambiosTurnoView.as_view(), name='cambios_turno'),
    path('consolidado-horas/', ConsolidadoHorasView.as_view(), name='consolidado_horas'),
    path('dias-especiales/', DiasEspecialesView.as_view(), name='dias_especiales'),
] 