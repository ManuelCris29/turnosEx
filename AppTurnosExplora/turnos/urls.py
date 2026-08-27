from django.urls import include, path

from .views import (
    AperturaAnioView,
    AsignacionEspecialAnualView,
    AsignacionEspecialSiembraView,
    CambiosTurnoView,
    ConsolidadoHorasView,
    DescansoSemanaAnualView,
    DescansoSemanaCreateView,
    DescansoSemanaDeleteView,
    DescansoSemanaListView,
    DescansoSemanaUpdateView,
    DiaEspecialFestivosMantenimientoAnualView,
    DiaEspecialListView,
    DiaEspecialTemporadasAnualView,
    DiaEspecialUpdateView,
    DiaEspecialVisualizarListView,
    DiasEspecialesView,
    MisTurnosView,
    TurnosCalendarioView,
)

urlpatterns = [
    path('mis-turnos/', MisTurnosView.as_view(), name='mis_turnos'),
    path('cambios-turno/', CambiosTurnoView.as_view(), name='cambios_turno'),
    path('consolidado-horas/', ConsolidadoHorasView.as_view(), name='consolidado_horas'),
    path('dias-especiales/', DiasEspecialesView.as_view(), name='dias_especiales'),
    path('dias-especiales/visualizar/', DiaEspecialVisualizarListView.as_view(), name='dias_especiales_visualizar'),
    path('dias-especiales/temporadas-anual/', DiaEspecialTemporadasAnualView.as_view(), name='dias_especiales_temporadas_anual'),
    path('dias-especiales/festivos-mantenimiento-anual/', DiaEspecialFestivosMantenimientoAnualView.as_view(), name='dias_especiales_festivos_mantenimiento_anual'),
    path('dias-especiales-admin/', DiaEspecialListView.as_view(), name='dias_especiales_list'),
    path('dias-especiales-admin/edit/<int:pk>/', DiaEspecialUpdateView.as_view(), name='dias_especiales_edit'),
    # No hay ruta de baja: las altas y bajas se hacen desde las páginas anuales, que ven
    # el año completo y protegen contra ediciones concurrentes.

    # Descanso de semana (manual) para semanas con temporada/festivo
    path('descanso-semana/', DescansoSemanaListView.as_view(), name='descanso_semana_list'),
    path('descanso-semana/anual/', DescansoSemanaAnualView.as_view(), name='descanso_semana_anual'),
    path('asignacion-especial/anual/', AsignacionEspecialAnualView.as_view(), name='asignacion_especial_anual'),
    path('asignacion-especial/anual/siembra/', AsignacionEspecialSiembraView.as_view(), name='asignacion_especial_siembra'),
    # Sin año: el siguiente al actual. Es la que usa el menú, que no conoce el año.
    path('apertura-anio/', AperturaAnioView.as_view(), name='apertura_anio_actual'),
    path('apertura-anio/<int:anio>/', AperturaAnioView.as_view(), name='apertura_anio'),
    path('descanso-semana/create/', DescansoSemanaCreateView.as_view(), name='descanso_semana_create'),
    path('descanso-semana/edit/<int:pk>/', DescansoSemanaUpdateView.as_view(), name='descanso_semana_edit'),
    path('descanso-semana/delete/<int:pk>/', DescansoSemanaDeleteView.as_view(), name='descanso_semana_delete'),
    path('lista/', TurnosCalendarioView.as_view(), name='turnos_list'),
    path('api/', include('turnos.api.urls')),
] 