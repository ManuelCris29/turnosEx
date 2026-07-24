"""
Reprogramación del día de doblada por inasistencia (panel del supervisor).

Flujo:
1. Registrar inasistencia (sobre una doblada aprobada): elige quién no cumplió su día → anula ese
   día (soft-delete auditable) y resta sus 30 min; crea la reprogramación en 'pendiente'.
2. Programar el día de pago: muestra el calendario/jornada real de esa persona (fuente única
   estado_mes) y el supervisor elige el día en que dobla → aplica la doblada + regenera los 30 min.

Acceso: staff o rol Supervisor (AdminRequiredMixin). La persona afectada (deudor) recibe una
notificación; el otro explorador no se ve afectado.
"""
import logging
from datetime import date, timedelta
import calendar

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View

from core.mixins import AdminRequiredMixin
from ..models import SolicitudCambio, ReprogramacionDiaDoblada
from ..services.reprogramacion_doblada_service import ReprogramacionDobladaService as RS

logger = logging.getLogger(__name__)


def _notificar(explorador, titulo, mensaje):
    try:
        from ..models import Notificacion
        Notificacion.objects.create(
            destinatario=explorador, tipo='solicitud_doblada', titulo=titulo, mensaje=mensaje, solicitud=None,
        )
    except Exception:
        logger.warning("Error creando notificación de reprogramación", exc_info=True)


class ReprogramacionListView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Lista de reprogramaciones (pendientes/pagadas/canceladas)."""
    template_name = 'solicitudes/reprogramacion_list.html'

    def get(self, request):
        estado = request.GET.get('estado', 'pendiente')
        qs = (ReprogramacionDiaDoblada.objects
              .select_related('explorador', 'doblada_origen', 'registrado_por')
              .order_by('-creado_en'))
        if estado and estado != 'todos':
            qs = qs.filter(estado=estado)
        base = ReprogramacionDiaDoblada.objects.all()
        conteos = {
            'pendiente': base.filter(estado='pendiente').count(),
            'pagada': base.filter(estado='pagada').count(),
            'cancelada': base.filter(estado='cancelada').count(),
            'todos': base.count(),
        }
        return render(request, self.template_name, {'reprogs': qs, 'estado_sel': estado, 'conteos': conteos})


TIPOS_REPROGRAMABLES = ('DOBLADA', 'DOBLADA PERMANENTE')


class RegistrarInasistenciaView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Registra que UNA persona no cumplió UN día de doblada (sencilla o permanente)."""
    template_name = 'solicitudes/reprogramacion_registrar.html'

    def _get_solicitud(self, solicitud_id):
        return get_object_or_404(
            SolicitudCambio.objects.select_related(
                'doblada', 'doblada_permanente', 'tipo_cambio',
                'explorador_solicitante', 'explorador_receptor'),
            id=solicitud_id, tipo_cambio__nombre__in=TIPOS_REPROGRAMABLES, estado='aprobada')

    def _candidatos(self, solicitud):
        """[{rol, explorador, fechas:[...]}] — en sencilla 1 fecha, en permanente varias."""
        return [
            {'rol': rol, 'explorador': emp, 'fechas': fechas}
            for (rol, emp, fechas) in RS.participantes_y_dias(solicitud)
        ]

    def get(self, request, solicitud_id):
        solicitud = self._get_solicitud(solicitud_id)
        es_permanente = solicitud.tipo_cambio.nombre == 'DOBLADA PERMANENTE'
        return render(request, self.template_name, {
            'solicitud': solicitud,
            'candidatos': self._candidatos(solicitud),
            'es_permanente': es_permanente,
            'puede_cancelar': (not es_permanente) and RS.puede_cancelar(solicitud),
        })

    def post(self, request, solicitud_id):
        from datetime import date as _date
        solicitud = self._get_solicitud(solicitud_id)
        # Valor "rol|YYYY-MM-DD": identifica persona + día específico que no se cumplió.
        seleccion = request.POST.get('seleccion') or ''
        motivo = (request.POST.get('motivo') or '').strip()
        try:
            rol, fecha_iso = seleccion.split('|', 1)
            fecha_original = _date.fromisoformat(fecha_iso)
        except ValueError:
            messages.error(request, 'Selecciona quién no cumplió y qué día.')
            return redirect('solicitudes:reprog_registrar', solicitud_id=solicitud_id)
        cand = next((c for c in self._candidatos(solicitud) if c['rol'] == rol), None)
        if not cand or fecha_original not in cand['fechas']:
            messages.error(request, 'La selección no es válida.')
            return redirect('solicitudes:reprog_registrar', solicitud_id=solicitud_id)
        try:
            supervisor = getattr(request.user, 'empleado', None)
            reprog = RS.registrar_inasistencia(
                solicitud, cand['explorador'], supervisor=supervisor,
                motivo=motivo or None, fecha_original=fecha_original)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('solicitudes:reprog_registrar', solicitud_id=solicitud_id)
        _notificar(
            cand['explorador'],
            'Tienes un día de doblada pendiente por reprogramar',
            f"No se cumplió tu día de doblada del {fecha_original.strftime('%d/%m/%Y')}"
            f"{' (' + motivo + ')' if motivo else ''}. Debes pagarlo doblando otro día; tu supervisor "
            f"lo organizará contigo. La deuda de 30 min de ese día quedó anulada y se recalculará en el día que dobles.",
        )
        messages.success(request, f'Inasistencia registrada. Ahora programa el día en que {cand["explorador"].nombre} pagará doblando.')
        return redirect('solicitudes:reprog_programar', reprog_id=reprog.id)


class ProgramarReprogramacionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Programa el día en que la persona paga doblándose, mostrando su calendario real (estado_mes)."""
    template_name = 'solicitudes/reprogramacion_programar.html'

    def _contexto_calendario(self, reprog, anio, mes):
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.ct_permanente_helper import _jornada_doblada_perm
        from django.core.cache import cache
        cache.clear()
        estados = TurnoService.estado_mes(reprog.explorador, anio, mes)
        ndias = calendar.monthrange(anio, mes)[1]
        hoy = date.today()
        dias = []
        for d in (date(anio, mes, i) for i in range(1, ndias + 1)):
            est = estados.get(d) or {}
            j = _jornada_doblada_perm(reprog.explorador, d)  # None si no puede doblar
            valido = bool(j) and d >= hoy and d != reprog.fecha_original
            dias.append({
                'fecha': d, 'dow': d.weekday(),
                'jornada': (est.get('jornada') or ('DESCANSO' if not est.get('trabaja') else '')),
                'valido': valido, 'contraria': ('PM' if j == 'AM' else 'AM') if j else None,
            })
        return {'dias': dias, 'anio': anio, 'mes': mes,
                'mes_nombre': ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                               'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][mes]}

    def get(self, request, reprog_id):
        reprog = get_object_or_404(
            ReprogramacionDiaDoblada.objects.select_related('explorador', 'doblada_origen'), id=reprog_id)
        hoy = date.today()
        anio = int(request.GET.get('anio') or reprog.fecha_original.year or hoy.year)
        mes = int(request.GET.get('mes') or reprog.fecha_original.month or hoy.month)
        ctx = {'reprog': reprog}
        ctx.update(self._contexto_calendario(reprog, anio, mes))
        # navegación de mes
        ctx['mes_prev'] = (12, anio - 1) if mes == 1 else (mes - 1, anio)
        ctx['mes_next'] = (1, anio + 1) if mes == 12 else (mes + 1, anio)
        return render(request, self.template_name, ctx)

    def post(self, request, reprog_id):
        reprog = get_object_or_404(ReprogramacionDiaDoblada.objects.select_related('explorador'), id=reprog_id)
        fecha_str = request.POST.get('fecha_nueva')
        try:
            fecha_nueva = date.fromisoformat(fecha_str)
        except (TypeError, ValueError):
            messages.error(request, 'Elige un día válido del calendario.')
            return redirect('solicitudes:reprog_programar', reprog_id=reprog_id)
        try:
            RS.programar(reprog, fecha_nueva)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('solicitudes:reprog_programar', reprog_id=reprog_id)
        _notificar(
            reprog.explorador,
            'Día de doblada reprogramado',
            f"Tu supervisor programó tu pago de doblada para el {fecha_nueva.strftime('%d/%m/%Y')}: "
            f"ese día te doblas (AM + PM). Aparece en tu calendario de Mis Turnos.",
        )
        messages.success(request, f'Pago reprogramado: {reprog.explorador.nombre} dobla el {fecha_nueva.strftime("%d/%m/%Y")}.')
        return redirect('solicitudes:reprog_list')


class CancelarReprogramacionView(LoginRequiredMixin, AdminRequiredMixin, View):
    def post(self, request, reprog_id):
        reprog = get_object_or_404(ReprogramacionDiaDoblada, id=reprog_id)
        RS.cancelar(reprog)
        messages.success(request, 'Reprogramación cancelada.')
        return redirect('solicitudes:reprog_list')
