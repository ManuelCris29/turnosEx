"""Vistas de la app solicitudes (divididas por ámbito)."""

from .dashboard_admin import *  # noqa: F401,F403
from .cambio_turno_pages import *  # noqa: F401,F403
from .api_disponibles_ct_preview import *  # noqa: F401,F403
from .api_turno_jornada import *  # noqa: F401,F403
from .procesar_solicitud import *  # noqa: F401,F403
from .notificaciones_listas import *  # noqa: F401,F403
from .aprobacion_views import *  # noqa: F401,F403
from .aprobacion_email import *  # noqa: F401,F403
from .doblada_api import *  # noqa: F401,F403
from .detalle import *  # noqa: F401,F403
from .gestion_solicitudes import *  # noqa: F401,F403
from .reprogramacion_views import *  # noqa: F401,F403
from .cierre_config_views import *  # noqa: F401,F403

__all__ = [
    "SolicitudesView",
    "TipoSolicitudCambioListView",
    "TipoSolicitudCambioCreateView",
    "TipoSolicitudCambioUpdateView",
    "TipoSolicitudCambioDeleteView",
    "CambioTurnoInicioView",
    "SolicitarCambioTurnoView",
    "ObtenerEmpleadosDisponiblesView",
    "PrevisualizarCTPermanenteView",
    "PrevisualizarDobladaPermanenteView",
    "DiasDisponiblesDobladaPermanenteView",
    "ObtenerTurnoExploradorView",
    "VerificarCoincidenciaJornadasView",
    "ObtenerJornadasRangoView",
    "ObtenerCambioAprobadoView",
    "ProcesarSolicitudView",
    "NotificacionesListView",
    "MarcarNotificacionLeidaView",
    "MisSolicitudesListView",
    "SolicitudesPendientesListView",
    "AprobarSolicitudView",
    "AprobarSolicitudReceptorView",
    "RechazarSolicitudView",
    "RechazarSolicitudReceptorView",
    "CancelarSolicitudView",
    "AprobarSolicitudAmbosView",
    "AprobarSolicitudEmailView",
    "RechazarSolicitudEmailView",
    "AprobarSolicitudReceptorEmailView",
    "RechazarSolicitudReceptorEmailView",
    "ObtenerExploradoresDobladaView",
    "VerificarDobladaExistenteView",
    "ObtenerFechasDescansoView",
    "ObtenerDetalleSolicitudView",
]
