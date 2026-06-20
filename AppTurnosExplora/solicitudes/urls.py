from django.urls import path
from .views import (
    SolicitudesView, TipoSolicitudCambioListView, TipoSolicitudCambioCreateView,
    TipoSolicitudCambioUpdateView, TipoSolicitudCambioDeleteView,
    # PermisoDetalleListView, PermisoDetalleCreateView, PermisoDetalleUpdateView, PermisoDetalleDeleteView,  # COMENTADO TEMPORALMENTE
    CambioTurnoInicioView, SolicitarCambioTurnoView, ObtenerEmpleadosDisponiblesView, ObtenerTurnoExploradorView,
    ObtenerJornadasRangoView, ObtenerCambioAprobadoView, ProcesarSolicitudView, NotificacionesListView, MarcarNotificacionLeidaView,
    MisSolicitudesListView, SolicitudesPendientesListView, AprobarSolicitudView, RechazarSolicitudView,
    AprobarSolicitudReceptorView, RechazarSolicitudReceptorView, CancelarSolicitudView, AprobarSolicitudAmbosView,
    AprobarSolicitudEmailView, RechazarSolicitudEmailView, AprobarSolicitudReceptorEmailView, RechazarSolicitudReceptorEmailView,
    ObtenerDetalleSolicitudView, PrevisualizarCTPermanenteView,
    ObtenerExploradoresDobladaView, VerificarDobladaExistenteView, ObtenerFechasDescansoView,
    VerificarCoincidenciaJornadasView,
    GestionSolicitudesView, ReenviarNotificacionSolicitudView,
    GestionCancelarSolicitudView, GestionEliminarSolicitudView,
    AlternanciaFindeView, DescansosSemanaUsuarioView,
)

app_name = 'solicitudes'

# A medida que vayas creando las vistas para la app de solicitudes,
# deberás agregarlas aquí.
urlpatterns = [
    # PÁGINA PRINCIPAL - Dashboard de solicitudes (tu vista preferida)
    path('', SolicitudesView.as_view(), name='solicitudes'),
    
    # NOTIFICACIONES
    path('notificaciones/', NotificacionesListView.as_view(), name='notificaciones_list'),
    path('notificaciones/<int:notificacion_id>/marcar-leida/', MarcarNotificacionLeidaView.as_view(), name='marcar_notificacion_leida'),
    
    # MIS SOLICITUDES
    path('mis-solicitudes/', MisSolicitudesListView.as_view(), name='mis_solicitudes_list'),
    
    # SOLICITUDES PENDIENTES (con funcionalidad completa)
    path('solicitudes-pendientes/', SolicitudesPendientesListView.as_view(), name='solicitudes_pendientes_list'),

    # Gestión / supervisión de TODAS las solicitudes (detectar atascadas, reenviar, cancelar, eliminar)
    path('gestion-solicitudes/', GestionSolicitudesView.as_view(), name='gestion_solicitudes'),
    path('gestion-solicitudes/<int:solicitud_id>/reenviar/', ReenviarNotificacionSolicitudView.as_view(), name='gestion_reenviar_solicitud'),
    path('gestion-solicitudes/<int:solicitud_id>/cancelar/', GestionCancelarSolicitudView.as_view(), name='gestion_cancelar_solicitud'),
    path('gestion-solicitudes/<int:solicitud_id>/eliminar/', GestionEliminarSolicitudView.as_view(), name='gestion_eliminar_solicitud'),
    
    # ACCIONES DE SOLICITUDES (funcionales)
    path('aprobar-solicitud/<int:solicitud_id>/', AprobarSolicitudView.as_view(), name='aprobar_solicitud'),
    path('rechazar-solicitud/<int:solicitud_id>/', RechazarSolicitudView.as_view(), name='rechazar_solicitud'),
    path('aprobar-solicitud-receptor/<int:solicitud_id>/', AprobarSolicitudReceptorView.as_view(), name='aprobar_solicitud_receptor'),
    path('rechazar-solicitud-receptor/<int:solicitud_id>/', RechazarSolicitudReceptorView.as_view(), name='rechazar_solicitud_receptor'),
    path('aprobar-solicitud-ambos/<int:solicitud_id>/', AprobarSolicitudAmbosView.as_view(), name='aprobar_solicitud_ambos'),
    path('cancelar-solicitud/<int:solicitud_id>/', CancelarSolicitudView.as_view(), name='cancelar_solicitud'),
    
    # CAMBIO DE TURNO
    path('cambio-turno/', CambioTurnoInicioView.as_view(), name='cambio_turno_inicio'),
    path('cambio-turno/solicitar/<int:tipo_id>/', SolicitarCambioTurnoView.as_view(), name='solicitar_cambio_turno'),
    path('obtener-empleados-disponibles/', ObtenerEmpleadosDisponiblesView.as_view(), name='obtener_empleados_disponibles'),
    path('obtener-turno-explorador/', ObtenerTurnoExploradorView.as_view(), name='obtener_turno_explorador'),
    path('obtener-jornadas-rango/', ObtenerJornadasRangoView.as_view(), name='obtener_jornadas_rango'),
    path('obtener-cambio-aprobado/', ObtenerCambioAprobadoView.as_view(), name='obtener_cambio_aprobado'),
    path('alternancia-finde/', AlternanciaFindeView.as_view(), name='alternancia_finde'),
    path('descansos-semana-usuario/', DescansosSemanaUsuarioView.as_view(), name='descansos_semana_usuario'),
    path('obtener-detalle-solicitud/<int:solicitud_id>/', ObtenerDetalleSolicitudView.as_view(), name='obtener_detalle_solicitud'),
    path('previsualizar-ct-permanente/', PrevisualizarCTPermanenteView.as_view(), name='previsualizar_ct_permanente'),
    path('procesar-solicitud/', ProcesarSolicitudView.as_view(), name='procesar_solicitud'),
    
    # DOBLADA - Endpoints específicos
    path('obtener-exploradores-doblada/', ObtenerExploradoresDobladaView.as_view(), name='obtener_exploradores_doblada'),
    path('verificar-doblada-existente/', VerificarDobladaExistenteView.as_view(), name='verificar_doblada_existente'),
    path('obtener-fechas-descanso/', ObtenerFechasDescansoView.as_view(), name='obtener_fechas_descanso'),
    path('verificar-coincidencia-jornadas/', VerificarCoincidenciaJornadasView.as_view(), name='verificar_coincidencia_jornadas'),
    
    # APROBACIÓN POR EMAIL
    path('aprobar-email/<int:solicitud_id>/<str:token>/', AprobarSolicitudEmailView.as_view(), name='aprobar_solicitud_email'),
    path('rechazar-email/<int:solicitud_id>/<str:token>/', RechazarSolicitudEmailView.as_view(), name='rechazar_solicitud_email'),
    path('aprobar-receptor-email/<int:solicitud_id>/<str:token>/', AprobarSolicitudReceptorEmailView.as_view(), name='aprobar_solicitud_receptor_email'),
    path('rechazar-receptor-email/<int:solicitud_id>/<str:token>/', RechazarSolicitudReceptorEmailView.as_view(), name='rechazar_solicitud_receptor_email'),
    
    # ADMINISTRACIÓN
    path('tipos-solicitud/', TipoSolicitudCambioListView.as_view(), name='tiposolicitudcambio_list'),
    path('tipos-solicitud/create/', TipoSolicitudCambioCreateView.as_view(), name='tiposolicitudcambio_create'),
    path('tipos-solicitud/edit/<int:pk>/', TipoSolicitudCambioUpdateView.as_view(), name='tiposolicitudcambio_edit'),
    path('tipos-solicitud/delete/<int:pk>/', TipoSolicitudCambioDeleteView.as_view(), name='tiposolicitudcambio_delete'),
    # path('permisos-detalle/', PermisoDetalleListView.as_view(), name='permisodetalle_list'),  # COMENTADO TEMPORALMENTE
    # path('permisos-detalle/create/', PermisoDetalleCreateView.as_view(), name='permisodetalle_create'),  # COMENTADO TEMPORALMENTE
    # path('permisos-detalle/edit/<int:pk>/', PermisoDetalleUpdateView.as_view(), name='permisodetalle_edit'),  # COMENTADO TEMPORALMENTE
    # path('permisos-detalle/delete/<int:pk>/', PermisoDetalleUpdateView.as_view(), name='permisodetalle_delete'),  # COMENTADO TEMPORALMENTE
    
    # URL LEGACY (redirigir a la vista principal)
    path('notificaciones-solicitudes/', SolicitudesView.as_view(), name='notificaciones_solicitudes'),
    path('dashboard/', SolicitudesView.as_view(), name='dashboard_solicitudes'),
] 