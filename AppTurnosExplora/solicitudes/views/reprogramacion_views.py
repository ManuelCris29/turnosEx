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
import calendar
import logging
from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from core.mixins import AdminRequiredMixin

from ..models import ReprogramacionDiaDoblada, SolicitudCambio
from ..services.reprogramacion_doblada_service import ReprogramacionDobladaService as RS

logger = logging.getLogger(__name__)

# Destino unico de todos los redirect del panel: cambiar el nombre de la ruta en
# urls.py obliga a tocar un solo sitio.
_URL_LISTA = 'solicitudes:reprog_list'


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

    ESTADOS_VALIDOS = ('pendiente', 'pagada', 'cancelada', 'todos')
    POR_PAGINA = 25

    def get(self, request):
        estado = request.GET.get('estado', 'pendiente')
        if estado not in self.ESTADOS_VALIDOS:
            estado = 'pendiente'
        qs = (ReprogramacionDiaDoblada.objects
              .select_related('explorador', 'doblada_origen', 'registrado_por')
              .order_by('-creado_en'))
        if estado != 'todos':
            qs = qs.filter(estado=estado)
        base = ReprogramacionDiaDoblada.objects.all()
        conteos = {
            'pendiente': base.filter(estado='pendiente').count(),
            'pagada': base.filter(estado='pagada').count(),
            'cancelada': base.filter(estado='cancelada').count(),
            'todos': base.count(),
        }
        # El histórico crece sin límite (sobre todo en "todas"): paginar para no traerlo entero.
        pagina = Paginator(qs, self.POR_PAGINA).get_page(request.GET.get('page'))
        return render(request, self.template_name, {
            'reprogs': pagina, 'pagina': pagina, 'estado_sel': estado, 'conteos': conteos,
        })


# D FDS entra aquí igual que DOBLADA: comparte el mismo detalle y la misma estructura (el receptor
# dobla en la cesión, el solicitante en el pago). Lo único propio del fin de semana son las reglas
# del día con el que se compensa, que viven en el servicio (`_validar_dia_compensacion_finde`).
TIPOS_REPROGRAMABLES = ('DOBLADA', 'D FDS', 'DOBLADA PERMANENTE')


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
        if not motivo:
            messages.error(request, 'Escribe el motivo de la inasistencia.')
            return redirect('solicitudes:reprog_registrar', solicitud_id=solicitud_id)
        cand = next((c for c in self._candidatos(solicitud) if c['rol'] == rol), None)
        if not cand or fecha_original not in cand['fechas']:
            messages.error(request, 'La selección no es válida.')
            return redirect('solicitudes:reprog_registrar', solicitud_id=solicitud_id)
        try:
            supervisor = getattr(request.user, 'empleado', None)
            reprog = RS.registrar_inasistencia(
                solicitud, cand['explorador'], supervisor=supervisor,
                motivo=motivo, fecha_original=fecha_original)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('solicitudes:reprog_registrar', solicitud_id=solicitud_id)
        _notificar(
            cand['explorador'],
            'Tienes un día de doblada pendiente por reprogramar',
            f"No se cumplió tu día de doblada del {fecha_original.strftime('%d/%m/%Y')}"
            f" ({motivo}). Debes pagarlo doblando otro día; tu supervisor "
            f"lo organizará contigo. La deuda de 30 min de ese día quedó anulada y se recalculará en el día que dobles.",
        )
        messages.success(request, f'Inasistencia registrada. Ahora programa el día en que {cand["explorador"].nombre} pagará doblando.')
        return redirect('solicitudes:reprog_programar', reprog_id=reprog.id)


class ProgramarReprogramacionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Programa el día en que la persona paga doblándose, mostrando su calendario real (estado_mes)."""
    template_name = 'solicitudes/reprogramacion_programar.html'

    # Rango de años aceptado en la navegación del calendario (evita ?anio=99999 y meses inválidos).
    ANIO_MIN, ANIO_MAX = 2020, 2100

    def _mes_pedido(self, request, reprog):
        """(anio, mes) validados desde la query string, con el mes del día no cumplido de fallback."""
        hoy = timezone.localdate()
        base_anio = reprog.fecha_original.year if reprog.fecha_original else hoy.year
        base_mes = reprog.fecha_original.month if reprog.fecha_original else hoy.month
        try:
            anio = int(request.GET.get('anio'))
            if not (self.ANIO_MIN <= anio <= self.ANIO_MAX):
                anio = base_anio
        except (TypeError, ValueError):
            anio = base_anio
        try:
            mes = int(request.GET.get('mes'))
            if not (1 <= mes <= 12):
                mes = base_mes
        except (TypeError, ValueError):
            mes = base_mes
        return anio, mes

    def _contexto_calendario(self, reprog, anio, mes):
        from core.services.cache_service import CacheService
        from solicitudes.services.acuerdo_por_dia_service import AcuerdoPorDiaService
        from turnos.services.turno_service import TurnoService

        # Refrescar solo el caché de ESTE explorador y mes: el calendario debe reflejar su estado
        # real de Mis Turnos. (No vaciar el caché global: afectaría a toda la aplicación.)
        CacheService.invalidar_cache_turnos_empleado(reprog.explorador_id, mes, anio)
        estados = TurnoService.estado_mes(reprog.explorador, anio, mes)
        ndias = calendar.monthrange(anio, mes)[1]
        # Los acuerdos del MES en una sola consulta (la misma fuente que enriquece Mis Turnos):
        # sirven para que el motivo de un día bloqueado pueda nombrar la solicitud y el compañero
        # en vez de quedarse en "no tiene una jornada única". Fuera del bucle a propósito, para no
        # pagar una consulta por día.
        acuerdos = AcuerdoPorDiaService.en_rango(
            reprog.explorador, date(anio, mes, 1), date(anio, mes, ndias))
        hoy = timezone.localdate()
        es_finde = RS.es_dfds(reprog)
        dias = []
        for d in (date(anio, mes, i) for i in range(1, ndias + 1)):
            est = estados.get(d) or {}
            # Misma validación que aplica `programar`: lo que se pinta elegible es exactamente lo
            # que el servicio acepta (en D FDS son días de fin de semana libres, no jornadas únicas).
            try:
                j = RS.validar_dia_pago(reprog, d, hoy=hoy, acuerdo=acuerdos.get(d))
                valido, motivo = True, None
            except ValueError as e:
                j, valido, motivo = None, False, str(e)
            if valido:
                cubre = 'AM + PM (día completo)' if es_finde else ('PM' if j == 'AM' else 'AM')
            else:
                cubre = None
            dias.append({
                'fecha': d, 'dow': d.weekday(),
                'jornada': (est.get('jornada') or ('DESCANSO' if not est.get('trabaja') else '')),
                'valido': valido, 'contraria': cubre, 'motivo': motivo,
            })
        return {'dias': dias, 'anio': anio, 'mes': mes, 'es_finde': es_finde,
                'mes_nombre': ['', 'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                               'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][mes]}

    def get(self, request, reprog_id):
        reprog = get_object_or_404(
            ReprogramacionDiaDoblada.objects.select_related(
                'explorador', 'doblada_origen', 'doblada_origen__tipo_cambio'), id=reprog_id)
        # Mes/año de la URL: si vienen ausentes o corruptos (?mes=abc, ?mes=13) se cae al mes del
        # día no cumplido en vez de reventar con un 500.
        anio, mes = self._mes_pedido(request, reprog)
        ctx = {'reprog': reprog}
        ctx.update(self._contexto_calendario(reprog, anio, mes))
        # navegación de mes
        ctx['mes_prev'] = (12, anio - 1) if mes == 1 else (mes - 1, anio)
        ctx['mes_next'] = (1, anio + 1) if mes == 12 else (mes + 1, anio)
        return render(request, self.template_name, ctx)

    def post(self, request, reprog_id):
        reprog = get_object_or_404(
            ReprogramacionDiaDoblada.objects.select_related(
                'explorador', 'doblada_origen', 'doblada_origen__tipo_cambio'), id=reprog_id)
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
        return redirect(_URL_LISTA)


class CancelarReprogramacionView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Dos acciones distintas sobre una reprogramación, según el estado en que esté:

    - 'pagada'   → `deshacer_pago`: se quita el día de pago y VUELVE A PENDIENTE (la deuda sigue
      viva y el supervisor puede volver a programarle el día). Antes esto la cerraba y la persona
      quedaba sin pagar y sin poder ser reprogramada.
    - 'pendiente' → `cerrar_sin_pago`: se perdona la deuda (queda 'cancelada').

    El POST trae `accion` y el servicio valida el estado, así que un doble submit —o un botón
    viejo en pantalla— no puede encadenar "deshacer pago" con "cerrar sin pago" y borrar en
    silencio una deuda real: la segunda petición falla o es no-op (patrón #21).
    """

    def post(self, request, reprog_id):
        reprog = get_object_or_404(ReprogramacionDiaDoblada, id=reprog_id)
        accion = request.POST.get('accion') or ('deshacer_pago' if reprog.estado == 'pagada' else 'cerrar_sin_pago')

        if accion == 'deshacer_pago':
            fecha_pago = reprog.fecha_reprogramada  # capturar antes de deshacer
            try:
                RS.deshacer_pago(reprog)
            except ValueError as e:
                messages.error(request, str(e))
                return redirect(_URL_LISTA)
            if fecha_pago:
                _notificar(
                    reprog.explorador,
                    'Pago de doblada cancelado (sigues debiendo el día)',
                    f"Tu supervisor canceló el pago de doblada que tenías el {fecha_pago.strftime('%d/%m/%Y')}: "
                    f"ese día vuelve a tu jornada normal en Mis Turnos. Tu día de doblada del "
                    f"{reprog.fecha_original.strftime('%d/%m/%Y')} sigue pendiente de pago y tu supervisor "
                    f"te programará otro día.",
                )
                messages.success(
                    request,
                    f'Día de pago deshecho: volvió a su jornada normal y la reprogramación de '
                    f'{reprog.explorador.nombre} quedó PENDIENTE de programar otra vez.')
            else:
                messages.info(request, 'Esta reprogramación ya estaba pendiente de programar.')
            return redirect(_URL_LISTA)

        # cerrar_sin_pago: el día no cumplido queda anulado y nadie lo repone.
        if reprog.estado == 'cancelada':
            messages.info(request, 'Esta reprogramación ya estaba cancelada.')
            return redirect(_URL_LISTA)
        try:
            RS.cerrar_sin_pago(reprog)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(_URL_LISTA)
        _notificar(
            reprog.explorador,
            'Reprogramación de doblada cerrada sin pago',
            f"Tu supervisor cerró la reprogramación de tu día de doblada del "
            f"{reprog.fecha_original.strftime('%d/%m/%Y')} sin programar un día de pago. "
            f"Ese día queda anulado y no tienes que doblarlo.",
        )
        messages.warning(
            request,
            f'Reprogramación cerrada sin pago: el día {reprog.fecha_original.strftime("%d/%m/%Y")} '
            f'queda anulado y {reprog.explorador.nombre} no lo repondrá.')
        return redirect(_URL_LISTA)
