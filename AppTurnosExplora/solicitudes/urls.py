from django.urls import path
from .views import (
    SolicitudesView, TipoSolicitudCambioListView, TipoSolicitudCambioCreateView,
    TipoSolicitudCambioUpdateView, TipoSolicitudCambioDeleteView,
    PermisoDetalleListView, PermisoDetalleCreateView, PermisoDetalleUpdateView, PermisoDetalleDeleteView,
    CambioTurnoInicioView, SolicitarCambioTurnoView, ObtenerEmpleadosDisponiblesView, ObtenerTurnoExploradorView,
    ProcesarSolicitudView, NotificacionesListView, MarcarNotificacionLeidaView,
    MisSolicitudesListView, SolicitudesPendientesListView, AprobarSolicitudView, RechazarSolicitudView
)

# A medida que vayas creando las vistas para la app de solicitudes,
# deberás agregarlas aquí.
urlpatterns = [
    path('cambio-turno/', CambioTurnoInicioView.as_view(), name='cambio_turno_inicio'),
    path('cambio-turno/solicitar/<int:tipo_id>/', SolicitarCambioTurnoView.as_view(), name='solicitar_cambio_turno'),
    path('obtener-empleados-disponibles/', ObtenerEmpleadosDisponiblesView.as_view(), name='obtener_empleados_disponibles'),
    path('obtener-turno-explorador/', ObtenerTurnoExploradorView.as_view(), name='obtener_turno_explorador'),
    path('procesar-solicitud/', ProcesarSolicitudView.as_view(), name='procesar_solicitud'),
    path('notificaciones/', NotificacionesListView.as_view(), name='notificaciones_list'),
    path('notificaciones/<int:notificacion_id>/marcar-leida/', MarcarNotificacionLeidaView.as_view(), name='marcar_notificacion_leida'),
    path('mis-solicitudes/', MisSolicitudesListView.as_view(), name='mis_solicitudes_list'),
    path('solicitudes-pendientes/', SolicitudesPendientesListView.as_view(), name='solicitudes_pendientes_list'),
    path('aprobar-solicitud/<int:solicitud_id>/', AprobarSolicitudView.as_view(), name='aprobar_solicitud'),
    path('rechazar-solicitud/<int:solicitud_id>/', RechazarSolicitudView.as_view(), name='rechazar_solicitud'),
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