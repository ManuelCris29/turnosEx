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

# Create your views here.

class CambioTurnoInicioView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/cambio_turno_inicio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from ..services.solicitud_consulta_service import SolicitudConsultaService
        context['tipos_solicitud'] = SolicitudConsultaService.get_tipos_solicitud_activos()
        return context
    
class SolicitarCambioTurnoView(LoginRequiredMixin, View):
    def get(self, request, tipo_id):
        tipo_solicitud = get_object_or_404(TipoSolicitudCambio, id=tipo_id)
        
        # Determinar qué template usar según el tipo de solicitud
        if tipo_solicitud.nombre == "CT PERMANENTE":
            return self._render_ct_permanente(request, tipo_solicitud)
        elif tipo_solicitud.nombre == "DOBLADA":
            return self._render_doblada(request, tipo_solicitud)
        elif tipo_solicitud.nombre == "D FDS":
            return self._render_d_fds(request, tipo_solicitud)
        elif tipo_solicitud.nombre == "DOBLADA PERMANENTE":
            return self._render_doblada_permanente(request, tipo_solicitud)
        elif tipo_solicitud.nombre == "CAMBIO DESCANSO":
            return self._render_cambio_descanso(request, tipo_solicitud)
        else:
            return self._render_cambio_turno_normal(request, tipo_solicitud)

    def _render_cambio_descanso(self, request, tipo_solicitud):
        """Renderizar formulario de Cambio de Día de Descanso (fin de semana)."""
        # Jornada base (AM/PM) del solicitante, para marcar en el calendario qué día
        # trabaja y cuál descansa según la alternancia.
        jornada_base = ''
        try:
            from turnos.models import AsignarJornadaExplorador
            emp = request.user.empleado
            asg = (AsignarJornadaExplorador.objects
                   .filter(explorador=emp, fecha_inicio__lte=timezone.localdate())
                   .select_related('jornada').order_by('-fecha_inicio').first())
            if asg:
                jornada_base = asg.jornada.nombre.upper()
        except Exception:
            logger.warning("Error obteniendo jornada base del empleado", exc_info=True)
        context = {
            'tipo_solicitud': tipo_solicitud,
            # Mañana: el día en curso ya se está trabajando y no hay jornada que intercambiar
            # sin reescribir un turno que la persona está cubriendo (misma regla que el backend).
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            'jornada_base': jornada_base,
            # Para resaltar "tú eres ..." en el distintivo del fin de semana.
            'mi_jornada': jornada_base,
        }
        return render(request, 'solicitudes/solicitar_cambio_descanso.html', context)

    def _render_doblada_permanente(self, request, tipo_solicitud):
        """Renderizar formulario específico para DOBLADA PERMANENTE"""
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate(),
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_doblada_permanente.html', context)
    
    def _render_ct_permanente(self, request, tipo_solicitud):
        """Renderizar formulario especÃ­fico para CT PERMANENTE"""
        # No establecer fecha inicial por defecto - el usuario debe seleccionarla
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_inicio': None,  # Sin fecha inicial - usuario debe seleccionar
            'fecha_fin': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            'comentarios': '',
        }
        return render(request, 'solicitudes/solicitar_ct_permanente.html', context)
    
    def _render_doblada(self, request, tipo_solicitud):
        """Renderizar formulario específico para DOBLADA"""
        # No establecer fecha inicial - el usuario debe seleccionarla
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate(),
            # La cesión admite HOY, pero el pago debe ser posterior a la creación de la solicitud
            # (`validar_acuerdo_previo_obligatorio`). Sin este mínimo propio, el datepicker ofrecía
            # hoy como fecha de pago y la validación la rechazaba después.
            'fecha_minima_pago': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,  # Sin fecha inicial - usuario debe seleccionar
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_doblada.html', context)
    
    def _render_d_fds(self, request, tipo_solicitud):
        """Renderizar formulario específico para D FDS (Doblada de Fin de Semana)"""
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate(),
            'fecha_seleccionada': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
            # Jornada predeterminada del solicitante (AM/PM) para resaltar "tú eres ..." en el distintivo.
            'mi_jornada': self._obtener_mi_jornada(request),
        }
        return render(request, 'solicitudes/solicitar_d_fds.html', context)

    @staticmethod
    def _obtener_mi_jornada(request):
        """Devuelve el nombre de la jornada predeterminada (AM/PM) del usuario actual, o ''."""
        from turnos.models import AsignarJornadaExplorador
        empleado = getattr(request.user, 'empleado', None)
        if not empleado:
            return ''
        asignacion = (
            AsignarJornadaExplorador.objects
            .filter(explorador=empleado)
            .select_related('jornada')
            .order_by('-fecha_inicio')
            .first()
        )
        return (asignacion.jornada.nombre if asignacion and asignacion.jornada else '') or ''

    def _render_cambio_turno_normal(self, request, tipo_solicitud):
        """Renderizar formulario para cambio de turno normal.

        La fecha mínima es MAÑANA: el día en curso ya se está trabajando, así que no hay
        jornada que intercambiar sin reescribir un turno que la persona ya está cubriendo
        (misma regla que valida el backend). Sin fecha preseleccionada: el usuario elige.
        """
        context = {
            'tipo_solicitud': tipo_solicitud,
            'fecha_minima': timezone.localdate() + timezone.timedelta(days=1),
            'fecha_seleccionada': None,
            'empleados_disponibles': [],
            'empleado_seleccionado': None,
        }
        return render(request, 'solicitudes/solicitar_cambio_turno.html', context)


