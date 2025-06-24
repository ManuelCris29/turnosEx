from django.urls import path
from .views import (
    MisTurnosView, CambiosTurnoView, ConsolidadoHorasView, DiasEspecialesView,
    TurnoListView, TurnoCreateView, TurnoUpdateView, TurnoDeleteView,
    DiaEspecialListView, DiaEspecialCreateView, DiaEspecialUpdateView, DiaEspecialDeleteView
)

# A medida que vayas creando las vistas para la app de turnos,
# deberás agregarlas aquí.
urlpatterns = [
    path('mis-turnos/', MisTurnosView.as_view(), name='mis_turnos'),
    path('cambios-turno/', CambiosTurnoView.as_view(), name='cambios_turno'),
    path('consolidado-horas/', ConsolidadoHorasView.as_view(), name='consolidado_horas'),
    path('dias-especiales/', DiasEspecialesView.as_view(), name='dias_especiales'),
    path('dias-especiales-admin/', DiaEspecialListView.as_view(), name='dias_especiales_list'),
    path('dias-especiales-admin/create/', DiaEspecialCreateView.as_view(), name='dias_especiales_create'),
    path('dias-especiales-admin/edit/<int:pk>/', DiaEspecialUpdateView.as_view(), name='dias_especiales_edit'),
    path('dias-especiales-admin/delete/<int:pk>/', DiaEspecialDeleteView.as_view(), name='dias_especiales_delete'),
    path('lista/', TurnoListView.as_view(), name='turnos_list'),
    path('crear/', TurnoCreateView.as_view(), name='turnos_create'),
    path('editar/<int:pk>/', TurnoUpdateView.as_view(), name='turnos_edit'),
    path('eliminar/<int:pk>/', TurnoDeleteView.as_view(), name='turnos_delete'),
] 