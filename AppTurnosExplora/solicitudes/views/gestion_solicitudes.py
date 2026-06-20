"""
Gestión de Solicitudes (panel de supervisión).

A diferencia de "Solicitudes Pendientes" (bandeja de lo que TÚ debes aprobar), esta vista
muestra TODAS las solicitudes para que un supervisor/admin las supervise y gestione:
- Detecta las ATASCADAS (pendientes con muchos días sin resolverse) → evita cuellos de botella.
- Muestra exactamente dónde está trabada (falta receptor / falta supervisor).
- Acciones: Reenviar notificación (idempotente), Cancelar (soft), Eliminar (para re-montar).

Acceso: staff o rol Supervisor (AdminRequiredMixin).
"""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View

from core.mixins import AdminRequiredMixin
from ..models import SolicitudCambio

# Días pendiente a partir de los cuales una solicitud se considera "atascada".
UMBRAL_ATASCO_DIAS = 3


class GestionSolicitudesView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Lista todas las solicitudes con filtro por estado/antigüedad y acciones de gestión."""
    template_name = 'solicitudes/gestion_solicitudes_list.html'

    def get(self, request):
        estado = request.GET.get('estado', 'pendiente')
        solo_atascadas = request.GET.get('atascadas') == '1'
        q = (request.GET.get('q') or '').strip()

        qs = (
            SolicitudCambio.objects
            .select_related('explorador_solicitante', 'explorador_receptor',
                            'explorador_solicitante__supervisor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )
        if estado and estado != 'todos':
            qs = qs.filter(estado=estado)
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(explorador_solicitante__nombre__icontains=q) |
                Q(explorador_solicitante__apellido__icontains=q) |
                Q(explorador_receptor__nombre__icontains=q) |
                Q(explorador_receptor__apellido__icontains=q)
            )

        hoy = date.today()
        umbral_fecha = hoy - timedelta(days=UMBRAL_ATASCO_DIAS)
        if solo_atascadas:
            qs = qs.filter(estado='pendiente', fecha_solicitud__date__lte=umbral_fecha)

        paginator = Paginator(qs, 30)
        page = paginator.get_page(request.GET.get('page'))

        # Enriquecer cada solicitud con antigüedad y dónde está trabada
        for s in page.object_list:
            if s.estado == 'pendiente' and s.fecha_solicitud:
                dias = (hoy - s.fecha_solicitud.date()).days
                s.dias_pendiente = dias
                s.nivel = 'danger' if dias > UMBRAL_ATASCO_DIAS else 'warning' if dias >= 2 else 'ok'
                faltan = []
                if not s.aprobado_receptor:
                    faltan.append('receptor')
                if not s.aprobado_supervisor:
                    faltan.append('supervisor')
                s.bloqueo = ', '.join(faltan) if faltan else '—'
            else:
                s.dias_pendiente = None
                s.nivel = None
                s.bloqueo = None

        # Conteos para los chips de filtro
        base = SolicitudCambio.objects.all()
        conteos = {
            'pendiente': base.filter(estado='pendiente').count(),
            'atascadas': base.filter(estado='pendiente', fecha_solicitud__date__lte=umbral_fecha).count(),
            'aprobada': base.filter(estado='aprobada').count(),
            'rechazada': base.filter(estado='rechazada').count(),
            'cancelada': base.filter(estado='cancelada').count(),
            'todos': base.count(),
        }

        return render(request, self.template_name, {
            'page': page,
            'estado_sel': estado,
            'solo_atascadas': solo_atascadas,
            'q': q,
            'conteos': conteos,
            'umbral': UMBRAL_ATASCO_DIAS,
        })


class _AccionGestionBase(LoginRequiredMixin, AdminRequiredMixin, View):
    """Base para las acciones POST de gestión. Redirige de vuelta conservando los filtros."""
    def _volver(self, request):
        destino = request.POST.get('next') or 'solicitudes:gestion_solicitudes'
        return redirect(destino)


class ReenviarNotificacionSolicitudView(_AccionGestionBase):
    def post(self, request, solicitud_id):
        solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
        if solicitud.estado != 'pendiente':
            messages.warning(request, f'La solicitud #{solicitud.id} no está pendiente; no se reenvía notificación.')
            return self._volver(request)
        try:
            from ..services.notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_solicitud(solicitud)
            messages.success(request, f'Notificación reenviada para la solicitud #{solicitud.id}.')
        except Exception as e:
            messages.error(request, f'No se pudo reenviar la notificación: {e}')
        return self._volver(request)


class GestionCancelarSolicitudView(_AccionGestionBase):
    def post(self, request, solicitud_id):
        from django.utils import timezone
        solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
        if solicitud.estado not in ('pendiente', 'aprobada'):
            messages.warning(request, f'La solicitud #{solicitud.id} ya está {solicitud.get_estado_display().lower()}.')
            return self._volver(request)
        solicitud.estado = 'cancelada'
        solicitud.fecha_resolucion = timezone.now()
        solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada desde gestión por {request.user.empleado.nombre} {request.user.empleado.apellido}."
        solicitud.save()
        messages.success(request, f'Solicitud #{solicitud.id} cancelada.')
        return self._volver(request)


class GestionEliminarSolicitudView(_AccionGestionBase):
    def post(self, request, solicitud_id):
        solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
        sid = solicitud.id
        # El signal pre_delete cancela las deudas asociadas para no dejarlas huérfanas.
        solicitud.delete()
        messages.success(request, f'Solicitud #{sid} eliminada. Puede volver a montarse desde cero.')
        return self._volver(request)
