import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View

from core.utils.json_responses import json_error

from ..models import TipoSolicitudCambio
from ..use_cases.crear_solicitud import CrearSolicitudUseCase

logger = logging.getLogger(__name__)


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

            return CrearSolicitudUseCase().execute(request.POST, tipo_solicitud, request.user.empleado)

        except Exception:
            logger.exception("Error inesperado en ProcesarSolicitudView")
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')
