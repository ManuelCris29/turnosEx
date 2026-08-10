"""
Gestión de Solicitudes (panel de supervisión).

A diferencia de "Solicitudes Pendientes" (bandeja de lo que TÚ debes aprobar), esta vista
muestra TODAS las solicitudes para que un supervisor/admin las supervise y gestione:
- Detecta las ATASCADAS (pendientes con muchos días sin resolverse) → evita cuellos de botella.
- Muestra exactamente dónde está trabada (falta receptor / falta supervisor).
- Acciones: Reenviar notificación (idempotente), Cancelar (soft), Eliminar (para re-montar).

Acceso: staff o rol Supervisor (AdminRequiredMixin).
"""
import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from core.mixins import AdminRequiredMixin
from ..models import SolicitudCambio
from django.utils import timezone
from solicitudes.views.reprogramacion_views import TIPOS_REPROGRAMABLES

logger = logging.getLogger(__name__)

# Días pendiente a partir de los cuales una solicitud se considera "atascada".
UMBRAL_ATASCO_DIAS = 3

# Se valida contra los choices del modelo: un `?estado=` inventado devolvía una lista vacía
# sin explicar por qué, y parecía que no había solicitudes.
ESTADOS_VALIDOS = {c[0] for c in SolicitudCambio._meta.get_field('estado').choices} | {'todos'}


class GestionSolicitudesView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Lista todas las solicitudes con filtro por estado/antigüedad y acciones de gestión."""
    template_name = 'solicitudes/gestion_solicitudes_list.html'

    def get(self, request):
        estado = request.GET.get('estado', 'pendiente')
        if estado not in ESTADOS_VALIDOS:
            estado = 'pendiente'
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
            filtro = (
                Q(explorador_solicitante__nombre__icontains=q) |
                Q(explorador_solicitante__apellido__icontains=q) |
                Q(explorador_receptor__nombre__icontains=q) |
                Q(explorador_receptor__apellido__icontains=q)
            )
            # Todo el panel identifica las solicitudes por "#123" (mensajes, comentarios), así que
            # buscar por ese número tiene que funcionar.
            numero = q.lstrip('#')
            if numero.isdigit():
                filtro |= Q(id=int(numero))
            qs = qs.filter(filtro)

        hoy = timezone.localdate()
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

            # ¿Se le puede reprogramar un día por inasistencia? La lista de tipos vive en la vista
            # de reprogramación (fuente única); antes la plantilla los comparaba a mano y al añadir
            # D FDS habría quedado desincronizada.
            s.reprogramable = (
                s.estado == 'aprobada'
                and s.tipo_cambio is not None
                and s.tipo_cambio.nombre in TIPOS_REPROGRAMABLES
            )

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
        # `next` viene del formulario, o sea del cliente: sin validar, un POST con
        # next=https://otro-sitio redirigía fuera de la aplicación después de ejecutar la acción.
        destino = request.POST.get('next')
        if destino and url_has_allowed_host_and_scheme(
            destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(destino)
        return redirect('solicitudes:gestion_solicitudes')

    def _empleado(self, request):
        """
        El Empleado del usuario, o None. `AdminRequiredMixin` deja pasar a cualquier `is_staff`,
        y un superusuario creado por consola no tiene Empleado: sin esta guarda, pulsar Cancelar
        reventaba con AttributeError.
        """
        return getattr(request.user, 'empleado', None)

    def _invalidar_contadores(self, solicitud):
        """Los badges de solicitudes viven en caché; tras cancelar quedaban contando de más."""
        from core.services.cache_service import CacheService

        claves = [
            f"solicitudes_count_mis_{solicitud.explorador_solicitante_id}",
            f"solicitudes_count_pend_{solicitud.explorador_solicitante_id}",
        ]
        if solicitud.explorador_receptor_id:
            claves.append(f"solicitudes_count_pend_{solicitud.explorador_receptor_id}")
        supervisor = solicitud.explorador_solicitante.supervisor
        if supervisor:
            claves.append(f"solicitudes_count_pend_{supervisor.id}")
        CacheService.delete_many(claves)


class ReenviarNotificacionSolicitudView(_AccionGestionBase):
    def post(self, request, solicitud_id):
        solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
        if solicitud.estado != 'pendiente':
            messages.warning(request, f'La solicitud #{solicitud.id} no está pendiente; no se reenvía notificación.')
            return self._volver(request)

        from core.services.cache_service import CacheService
        if not CacheService.acquire_lock(f"reenvio_notif_lock_{solicitud.id}", ttl=30):
            messages.warning(request, f'Notificación de la solicitud #{solicitud.id} ya reenviada hace un momento; espera antes de reintentar.')
            return self._volver(request)
        try:
            from ..services.notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_solicitud(solicitud)
            messages.success(request, f'Notificación reenviada para la solicitud #{solicitud.id}.')
        except Exception:
            # El detalle va al log, no a la pantalla: str(e) aqui puede ser el
            # error crudo del driver de correo o de la base.
            logger.exception('Fallo al reenviar la notificación de la solicitud %s', solicitud.id)
            referencia = getattr(request, 'request_id', None)
            messages.error(request, 'No se pudo reenviar la notificación.' + (
                f' Código de referencia: {referencia}' if referencia else ''))
        return self._volver(request)


class GestionCancelarSolicitudView(_AccionGestionBase):
    """
    Cancela una solicitud desde gestión, REVIRTIENDO sus efectos.

    Antes solo ponía `estado='cancelada'`: los turnos seguían aplicados, así que el horario
    mostraba un intercambio que ya no existía. Toda la casuística (pendiente, aprobada sin
    cumplir, ya cumplida, cumplida a medias) vive en el caso de uso.
    """
    def post(self, request, solicitud_id):
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
        from ..services.notificacion_service import NotificacionService

        empleado = self._empleado(request)
        if empleado is None:
            messages.error(request, 'Tu usuario no tiene un empleado asociado; no puedes gestionar solicitudes.')
            return self._volver(request)

        solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
        ok, msg = CancelarSolicitudUseCase().execute_supervisor(solicitud.id, empleado)
        if not ok:
            messages.warning(request, f'Solicitud #{solicitud.id}: {msg}')
            return self._volver(request)

        logger.info("Solicitud %s cancelada desde gestión por %s %s (usuario %s).",
                    solicitud.id, empleado.nombre, empleado.apellido, request.user.username)
        self._invalidar_contadores(solicitud)
        # El aviso no puede tumbar una cancelación que en BD ya está hecha.
        try:
            NotificacionService.crear_notificacion_gestion(solicitud, empleado, 'cancelada')
        except Exception:
            logger.exception("No se pudo notificar la cancelación de la solicitud %s", solicitud.id)
        messages.success(request, f'Solicitud #{solicitud.id}: {msg}')
        return self._volver(request)


class GestionEliminarSolicitudView(_AccionGestionBase):
    """
    Borra la solicitud para poder volver a montarla desde cero.

    Antes borraba la fila sin más: si la solicitud estaba aplicada, sus turnos se quedaban
    puestos y encima desaparecía el registro que explicaba de dónde salían — imposible de
    rastrear, y la nueva solicitud chocaba con ellos. Ahora primero se REVIERTE con las mismas
    guardas que la cancelación (incluida la que impide reescribir días ya trabajados) y solo
    entonces se borra.

    Con una diferencia respecto a cancelar: si los días YA SE TRABAJARON, cancelar los conserva
    y deja el registro explicándolos, pero borrar los dejaría huérfanos. Por eso se pide el
    cierre administrativo desactivado y esas solicitudes no se pueden eliminar, solo cancelar.
    """
    def post(self, request, solicitud_id):
        from django.db import transaction
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
        from ..services.notificacion_service import NotificacionService

        empleado = self._empleado(request)
        if empleado is None:
            messages.error(request, 'Tu usuario no tiene un empleado asociado; no puedes gestionar solicitudes.')
            return self._volver(request)

        solicitud = get_object_or_404(SolicitudCambio, id=solicitud_id)
        sid = solicitud.id

        try:
            # Revertir y borrar en una sola transacción: si el borrado falla, la reversión no
            # debe quedar aplicada a medias con la solicitud todavía viva.
            with transaction.atomic():
                if solicitud.estado in ('pendiente', 'aprobada'):
                    ok, msg = CancelarSolicitudUseCase().execute_supervisor(
                        sid, empleado, permitir_cierre_administrativo=False)
                    if not ok:
                        messages.warning(request, f'No se eliminó la solicitud #{sid}: {msg}')
                        return self._volver(request)

                # El signal pre_delete cancela las deudas asociadas para no dejarlas huérfanas.
                solicitud.refresh_from_db()
                logger.info("Solicitud %s eliminada desde gestión por %s %s (usuario %s).",
                            sid, empleado.nombre, empleado.apellido, request.user.username)
                solicitud.delete()
        except Exception:
            logger.exception("Error al eliminar la solicitud %s desde gestión", sid)
            messages.error(request, f'No se pudo eliminar la solicitud #{sid}. No se cambió nada.')
            return self._volver(request)

        # Se avisa una vez confirmado el borrado, no antes: un aviso de "eliminada" sobre una
        # solicitud que sigue viva confundiría al explorador.
        self._invalidar_contadores(solicitud)
        try:
            # `delete()` deja el objeto en memoria con pk=None; el aviso cita el número, así que
            # se restituye para el texto. La notificación va sin FK (`vincular=False`) porque la
            # fila ya no existe y el FK es CASCADE: se borraría con ella.
            solicitud.pk = sid
            NotificacionService.crear_notificacion_gestion(
                solicitud, empleado, 'eliminada', vincular=False)
        except Exception:
            logger.exception("No se pudo notificar la eliminación de la solicitud %s", sid)

        messages.success(request, f'Solicitud #{sid} eliminada. Puede volver a montarse desde cero.')
        return self._volver(request)
