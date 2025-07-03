from django.urls import path
from .views import (
    SolicitudesView, TipoSolicitudCambioListView, TipoSolicitudCambioCreateView,
    TipoSolicitudCambioUpdateView, TipoSolicitudCambioDeleteView,
    PermisoDetalleListView, PermisoDetalleCreateView, PermisoDetalleUpdateView, PermisoDetalleDeleteView,
    CambioTurnoInicioView, SolicitarCambioTurnoView, ObtenerEmpleadosDisponiblesView
)

# A medida que vayas creando las vistas para la app de solicitudes,
# deberás agregarlas aquí.
urlpatterns = [
    path('cambio-turno/', CambioTurnoInicioView.as_view(), name='cambio_turno_inicio'),
    path('cambio-turno/solicitar/<int:tipo_id>/', SolicitarCambioTurnoView.as_view(), name='solicitar_cambio_turno'),
    path('obtener-empleados-disponibles/', ObtenerEmpleadosDisponiblesView.as_view(), name='obtener_empleados_disponibles'),
    path('', SolicitudesView.as_view(), name='solicitudes'),
    path('tipos-solicitud/', TipoSolicitudCambioListView.as_view(), name='tiposolicitudcambio_list'),
    path('tipos-solicitud/create/', TipoSolicitudCambioCreateView.as_view(), name='tiposolicitudcambio_create'),
    path('tipos-solicitud/edit/<int:pk>/', TipoSolicitudCambioUpdateView.as_view(), name='tiposolicitudcambio_edit'),
    path('tipos-solicitud/delete/<int:pk>/', TipoSolicitudCambioDeleteView.as_view(), name='tiposolicitudcambio_delete'),
    path('permisos-detalle/', PermisoDetalleListView.as_view(), name='permisodetalle_list'),
    path('permisos-detalle/create/', PermisoDetalleCreateView.as_view(), name='permisodetalle_create'),
    path('permisos-detalle/edit/<int:pk>/', PermisoDetalleUpdateView.as_view(), name='permisodetalle_edit'),
    path('permisos-detalle/delete/<int:pk>/', PermisoDetalleDeleteView.as_view(), name='permisodetalle_delete'),
] 