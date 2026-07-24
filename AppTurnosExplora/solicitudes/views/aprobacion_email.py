from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.db.models import Q
from core.mixins import AdminRequiredMixin
from core.services import get_turno_service
from empleados.models import Empleado
from ..models import TipoSolicitudCambio, Notificacion, SolicitudCambio, CambioPermanenteDetalle
from ..services.solicitud_service import SolicitudService
from ..services.solicitud_factory import SolicitudFactory
from ..services.permiso_service import PermisoService
from ..services.notificacion_service import NotificacionService
from django.utils import timezone
import hashlib
import hmac
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error
from .detalle import ObtenerDetalleSolicitudView


def _render_resultado(request, solicitud, tipo, accion, ya=False):
    """
    Renderiza la página de resultado de aprobación/rechazo por email con el
    MISMO detalle rico que el modal 'ver' (fechas, jornadas, compañero, deuda,
    exclusiones, etc.), para los 6 tipos de solicitud.

    `ya=True` indica que la acción NO se volvió a procesar (ya estaba resuelta
    o el rol ya había respondido): la página se muestra pero SIN reenviar
    ninguna notificación.
    """
    try:
        solicitud.refresh_from_db()   # reflejar el estado ya resuelto
    except Exception:
        logger.warning("No se pudo refrescar la solicitud %s tras resolver", solicitud.id, exc_info=True)
    datos = None
    try:
        datos = ObtenerDetalleSolicitudView.construir_datos(solicitud)
    except Exception:
        logger.warning("No se pudo construir el detalle de la solicitud %s", solicitud.id, exc_info=True)
    return render(request, 'solicitudes/aprobacion_exitosa.html', {
        'solicitud': solicitud,
        'tipo': tipo,
        'accion': accion,
        'datos': datos,
        'ya_procesada': ya,
    })


def _ya_resuelto_para(solicitud, tipo):
    """
    True si la acción por email de este rol ya NO debe procesarse ni notificar
    (idempotencia de los enlaces del correo, que pueden clicarse varias veces
    o ser pre-cargados por el cliente de correo):

    - La solicitud ya está resuelta (aprobada / rechazada / cancelada), o
    - El rol que abre el enlace ya había dado su respuesta (aprobado_*).
    """
    if solicitud.estado in ('aprobada', 'rechazada', 'cancelada'):
        return True
    if tipo == 'receptor' and solicitud.aprobado_receptor:
        return True
    if tipo == 'supervisor' and solicitud.aprobado_supervisor:
        return True
    return False


def _accion_actual(solicitud):
    """Acción a mostrar para una solicitud ya resuelta/respondida."""
    return 'rechazada' if solicitud.estado == 'rechazada' else 'aprobada'


# Create your views here.

class AprobarSolicitudEmailView(View):
    """
    Vista para aprobar una solicitud por email (supervisor)
    """
    def get(self, request, solicitud_id, token):
        try:
            # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'explorador_solicitante__supervisor',
                    'tipo_cambio'
                ),
                id=solicitud_id
            )
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'supervisor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Verificar que el usuario actual es el supervisor
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'No se encontrÃ³ supervisor para esta solicitud'
                })
            
            # Idempotencia: si ya está resuelta o el supervisor ya respondió,
            # NO re-procesar ni reenviar notificación (enlaces de correo re-clicados).
            if _ya_resuelto_para(solicitud, 'supervisor'):
                return _render_resultado(request, solicitud, 'supervisor', _accion_actual(solicitud), ya=True)

            # Aprobar la solicitud
            from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.aprobar_solicitud_supervisor(
                solicitud_id,
                supervisor,
                'Aprobado por email'
            )
            
            if success:
                return _render_resultado(request, solicitud, 'supervisor', 'aprobada')
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)

class RechazarSolicitudEmailView(View):
    """
    Vista para rechazar una solicitud por email (supervisor)
    """
    def get(self, request, solicitud_id, token):
        try:
            # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'explorador_solicitante__supervisor',
                    'tipo_cambio'
                ),
                id=solicitud_id
            )
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'supervisor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Verificar que el usuario actual es el supervisor
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'No se encontrÃ³ supervisor para esta solicitud'
                })
            
            # Idempotencia: si ya está resuelta o el supervisor ya respondió,
            # NO re-procesar ni reenviar notificación.
            if _ya_resuelto_para(solicitud, 'supervisor'):
                return _render_resultado(request, solicitud, 'supervisor', _accion_actual(solicitud), ya=True)

            # Rechazar la solicitud
            from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.rechazar_solicitud_supervisor(
                solicitud_id,
                supervisor,
                'Rechazado por email'
            )
            
            if success:
                return _render_resultado(request, solicitud, 'supervisor', 'rechazada')
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)

class AprobarSolicitudReceptorEmailView(View):
    """
    Vista para aprobar una solicitud por email (receptor)
    """
    def get(self, request, solicitud_id, token):
        try:
            # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'explorador_solicitante__supervisor',
                    'tipo_cambio'
                ),
                id=solicitud_id
            )
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'receptor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Idempotencia: si ya está resuelta o el receptor ya respondió,
            # NO re-procesar ni reenviar notificación.
            if _ya_resuelto_para(solicitud, 'receptor'):
                return _render_resultado(request, solicitud, 'receptor', _accion_actual(solicitud), ya=True)

            # Aprobar la solicitud
            from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.aprobar_solicitud_receptor(
                solicitud_id,
                solicitud.explorador_receptor,
                'Aprobado por email'
            )
            
            if success:
                return _render_resultado(request, solicitud, 'receptor', 'aprobada')
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)

class RechazarSolicitudReceptorEmailView(View):
    """
    Vista para rechazar una solicitud por email (receptor)
    """
    def get(self, request, solicitud_id, token):
        try:
            # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'explorador_solicitante__supervisor',
                    'tipo_cambio'
                ),
                id=solicitud_id
            )
            
            # Verificar token
            if not self._verificar_token(solicitud, token, 'receptor'):
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': 'Token invÃ¡lido o expirado'
                })
            
            # Idempotencia: si ya está resuelta o el receptor ya respondió,
            # NO re-procesar ni reenviar notificación.
            if _ya_resuelto_para(solicitud, 'receptor'):
                return _render_resultado(request, solicitud, 'receptor', _accion_actual(solicitud), ya=True)

            # Rechazar la solicitud
            from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.rechazar_solicitud_receptor(
                solicitud_id,
                solicitud.explorador_receptor,
                'Rechazado por email'
            )
            
            if success:
                return _render_resultado(request, solicitud, 'receptor', 'rechazada')
            else:
                return render(request, 'solicitudes/error_token.html', {
                    'mensaje': message
                })
                
        except Exception as e:
            return render(request, 'solicitudes/error_token.html', {
                'mensaje': f'Error al procesar la solicitud: {str(e)}'
            })
    
    def _verificar_token(self, solicitud, token, tipo):
        """Verifica que el token sea vÃ¡lido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producciÃ³n
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)


