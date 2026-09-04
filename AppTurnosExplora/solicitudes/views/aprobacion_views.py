import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from ..models import SolicitudCambio
from ..use_cases.aprobar_solicitud import (
    AprobarAmbosRolesUseCase,
    AprobarComoReceptorUseCase,
    AprobarComoSupervisorUseCase,
    RechazarComoReceptorUseCase,
    RechazarComoSupervisorUseCase,
)
from ..use_cases.cancelar_solicitud import CancelarSolicitudUseCase

logger = logging.getLogger(__name__)

# Regla transversal: el comentario es obligatorio en toda acción que resuelve algo.
# Los textos y el contrato viven en core para que permisos y solicitudes digan lo mismo.
from core.utils.comentarios import MSG_COMENTARIO, MSG_MOTIVO, exigir_texto_json
from core.utils.json_responses import json_error, json_ok

# Create your views here.


class AprobarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        comentario, error = exigir_texto_json(request, 'comentario_respuesta', MSG_COMENTARIO)
        if error:
            return error
        success, message = AprobarComoSupervisorUseCase().execute(solicitud_id, request.user.empleado, comentario)
        return json_ok({'success': success, 'message': message})

class AprobarSolicitudReceptorView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        comentario, error = exigir_texto_json(request, 'comentario_respuesta', MSG_COMENTARIO)
        if error:
            return error
        success, message = AprobarComoReceptorUseCase().execute(solicitud_id, request.user.empleado, comentario)
        return json_ok({'success': success, 'message': message})

class RechazarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        comentario, error = exigir_texto_json(request, 'comentario_respuesta', MSG_COMENTARIO)
        if error:
            return error
        success, message = RechazarComoSupervisorUseCase().execute(solicitud_id, request.user.empleado, comentario)
        return json_ok({'success': success, 'message': message})

class RechazarSolicitudReceptorView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            comentario, error = exigir_texto_json(request, 'comentario_respuesta', MSG_COMENTARIO)
            if error:
                return error
            success, message = RechazarComoReceptorUseCase().execute(solicitud_id, request.user.empleado, comentario)
            return json_ok({'success': success, 'message': message})
        except Exception:
            logger.exception('Error en RechazarSolicitudReceptorView')
            return json_error('Error al rechazar la solicitud', status=500, code='internal_error')

class CancelarSolicitudView(LoginRequiredMixin, View):
    """
    Acción de cancelar del SOLICITANTE.

    Si la solicitud está pendiente se retira en el acto. Si ya está aprobada esto NO cancela
    nada: registra la petición y avisa al receptor, que es quien decide. El use case devuelve
    el mensaje que corresponde a cada caso y aquí se distingue por el estado resultante para
    no mandar la notificación equivocada.
    """

    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
            motivo, error = exigir_texto_json(request, 'motivo', MSG_MOTIVO)
            if error:
                return error
            ok, msg = CancelarSolicitudUseCase().execute(
                solicitud_id, request.user.empleado, motivo
            )
            if not ok:
                if 'propias' in msg:
                    return json_error(msg, status=403, code='forbidden')
                if 'más reciente' in msg:
                    return json_error(msg, status=400, code='cambio_mas_reciente')
                if 'conflicto de jornadas' in msg:
                    return json_error(msg, status=400, code='conflicto_integridad')
                if 'horas posteriores a su aprobación' in msg:
                    return json_error(msg, status=400, code='ventana_expirada')
                if 'Ya pediste cancelar' in msg:
                    return json_error(msg, status=400, code='cancelacion_ya_pedida')
                if 'quedó firme' in msg:
                    return json_error(msg, status=400, code='cancelacion_cerrada')
                return json_error(msg, status=400, code='invalid_state')

            solicitud = SolicitudCambio.objects.con_relaciones().filter(id=solicitud_id).first()
            _invalidar_contadores(solicitud)

            from ..services.notificacion_service import NotificacionService
            if solicitud.estado == 'cancelada':
                # Camino de la PENDIENTE retirada: no hubo acuerdo que deshacer.
                NotificacionService.crear_notificacion_cancelacion(solicitud)
                return json_ok({'message': msg, 'cancelada': True})

            # Camino de la APROBADA: sólo se pidió; el cambio sigue vigente.
            NotificacionService.crear_notificacion_peticion_cancelacion(solicitud)
            return json_ok({'message': msg, 'cancelada': False, 'cancelacion_pendiente': True})
        except Exception:
            logger.exception('Error en CancelarSolicitudView')
            return json_error('Error al cancelar la solicitud', status=500, code='internal_error')


class ResponderCancelacionView(LoginRequiredMixin, View):
    """
    Respuesta del RECEPTOR a una petición de cancelación: `accion=aprobar` o `accion=rechazar`.

    Aprobar es lo único que revierte los turnos. Rechazar deja el cambio firme y cierra el
    asunto, así que el solicitante recibe aviso en ambos casos: para él la diferencia es si
    mañana trabaja su turno original o el cambiado.
    """

    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')

            accion = (request.POST.get('accion') or '').strip().lower()
            if accion not in ('aprobar', 'rechazar'):
                return json_error('Acción no válida: usa "aprobar" o "rechazar".',
                                  status=400, code='accion_invalida')

            comentario, error = exigir_texto_json(request, 'comentario_respuesta', MSG_COMENTARIO)
            if error:
                return error

            aprueba = accion == 'aprobar'
            ok, msg = CancelarSolicitudUseCase().responder_cancelacion(
                solicitud_id, request.user.empleado, aprueba, comentario,
            )
            if not ok:
                if 'No eres el receptor' in msg:
                    return json_error(msg, status=403, code='forbidden')
                if 'más reciente' in msg:
                    return json_error(msg, status=400, code='cambio_mas_reciente')
                if 'conflicto de jornadas' in msg:
                    return json_error(msg, status=400, code='conflicto_integridad')
                if 'plazo' in msg:
                    return json_error(msg, status=400, code='plazo_vencido')
                return json_error(msg, status=400, code='invalid_state')

            solicitud = SolicitudCambio.objects.con_relaciones().filter(id=solicitud_id).first()
            _invalidar_contadores(solicitud)

            from ..services.notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_respuesta_cancelacion(
                solicitud, request.user.empleado, aprueba
            )
            return json_ok({'message': msg, 'aprobada': aprueba})
        except Exception:
            logger.exception('Error en ResponderCancelacionView')
            return json_error('Error al responder la cancelación', status=500, code='internal_error')


def _invalidar_contadores(solicitud):
    """Contadores de las bandejas de las tres personas que pueden ver esta solicitud."""
    from core.services.cache_service import CacheService

    cache_keys = [
        f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
        f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
    ]
    if solicitud.explorador_receptor_id:
        cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_receptor_id}")
    if solicitud.explorador_solicitante.supervisor:
        cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
    CacheService.delete_many(cache_keys)


class AprobarSolicitudAmbosView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
            comentario, error = exigir_texto_json(request, 'comentario_respuesta', MSG_COMENTARIO)
            if error:
                return error
            ok, msg = AprobarAmbosRolesUseCase().execute(
                solicitud_id, request.user.empleado, comentario
            )
            if not ok:
                status = 403 if 'permisos' in msg else 400
                return json_error(msg, status=status, code='approval_error')
            return json_ok({'message': msg})
        except Exception:
            logger.exception('Error en AprobarSolicitudAmbosView')
            return json_error('Error al aprobar en ambos roles', status=500, code='internal_error')


# Vistas para aprobación por email (sin login requerido)
