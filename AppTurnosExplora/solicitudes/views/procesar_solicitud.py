import logging

from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from ..models import TipoSolicitudCambio
from ..services.solicitud_request_parser import SolicitudRequestParser
from ..services.solicitud_orchestrator import SolicitudOrchestrator
from core.utils.json_responses import json_error

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class ProcesarSolicitudView(LoginRequiredMixin, View):

    def post(self, request):
        try:
            tipo_solicitud_id = request.POST.get('tipo_solicitud_id')
            if not tipo_solicitud_id:
                return json_error('El tipo de solicitud es requerido', status=400, code='missing_fields')

            try:
                tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)
            except TipoSolicitudCambio.DoesNotExist:
                return json_error('Tipo de solicitud no válido', status=400, code='invalid_type')

            # Falla rápida: campos requeridos según tipo, antes de tocar más la BD
            ok, error_msg = SolicitudRequestParser.validate_required(tipo_solicitud.nombre, request.POST)
            if not ok:
                return json_error(error_msg, status=400, code='missing_fields')

            solicitante = request.user.empleado
            return SolicitudOrchestrator.procesar(request.POST, tipo_solicitud, solicitante)

        except Exception:
            logger.exception("Error inesperado en ProcesarSolicitudView")
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')
