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
from core.utils.date_utils import DateUtils
import hashlib
import hmac
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error

# Create your views here.

class AlternanciaMesView(LoginRequiredMixin, View):
    """
    Fines de semana de un mes para la Doblada de Fin de Semana (tarjetas).

    Sin parámetros o con ?anio=&mes=: devuelve TODOS los fines de semana cuyo sábado cae en
    el mes, cada uno con la jornada (AM/PM) del sábado y del domingo, y QUÉ DÍA trabaja el
    usuario (fuente de verdad estado_dia). Así el formulario muestra de un vistazo, sin tener
    que seleccionar, cuál día es el suyo. También devuelve la lista de meses disponibles.

    Cada finde:
      {sabado:{fecha,dia,jornada,mio}, domingo:{...}, mi_dia:'sabado'|'domingo'|null,
       trabaja_ambos:bool, seleccionable:bool}
    """
    def get(self, request):
        from datetime import date as _date, timedelta as _td
        from calendar import monthrange
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        from turnos.services.turno_service import TurnoService

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'findes': [], 'meses': []})

        hoy = _date.today()
        meses_es = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
                    'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        try:
            anio = int(request.GET.get('anio'))
            mes = int(request.GET.get('mes'))
        except (TypeError, ValueError):
            anio, mes = hoy.year, hoy.month

        # Meses disponibles: mes actual + 6 siguientes
        meses = []
        y, m = hoy.year, hoy.month
        for _ in range(7):
            meses.append({'anio': y, 'mes': m, 'label': f'{meses_es[m]} {y}'})
            m += 1
            if m > 12:
                m = 1
                y += 1

        estados = TurnoService.estado_mes(emp, anio, mes)

        def _info(d, e_estados, e_emp):
            e = e_estados.get(d) or TurnoService.estado_dia(e_emp, d)
            return bool(e['trabaja'])

        # Receptor opcional: para validar el otro lado del D FDS en cada finde.
        receptor = None
        rec_estados = {}
        try:
            rid = int(request.GET.get('receptor_id'))
            from empleados.models import Empleado as _Emp
            receptor = _Emp.objects.filter(id=rid).first()
            if receptor:
                rec_estados = TurnoService.estado_mes(receptor, anio, mes)
        except (TypeError, ValueError):
            pass

        findes = []
        _, ultimo = monthrange(anio, mes)
        d = _date(anio, mes, 1)
        while d <= _date(anio, mes, ultimo):
            if d.weekday() == 5:  # sábado ancla del finde
                sab = d
                dom = sab + _td(days=1)
                mio_sab = _info(sab, estados, emp)
                mio_dom = _info(dom, estados, emp)
                trabaja_ambos = mio_sab and mio_dom
                if trabaja_ambos:
                    mi_dia = None
                elif mio_sab:
                    mi_dia = 'sabado'
                elif mio_dom:
                    mi_dia = 'domingo'
                else:
                    mi_dia = None
                dia_trabajo = sab if mi_dia == 'sabado' else (dom if mi_dia == 'domingo' else None)
                seleccionable = bool(dia_trabajo and dia_trabajo >= hoy)
                item = {
                    'sabado': {'fecha': sab.isoformat(), 'dia': sab.strftime('%d/%m'),
                               'jornada': AlternanciaFinesSemanaService.jornada_trabaja_sabado(sab),
                               'mio': mio_sab},
                    'domingo': {'fecha': dom.isoformat(), 'dia': dom.strftime('%d/%m'),
                                'jornada': AlternanciaFinesSemanaService.jornada_trabaja_domingo(sab),
                                'mio': mio_dom},
                    'mi_dia': mi_dia,
                    'trabaja_ambos': trabaja_ambos,
                    'seleccionable': seleccionable,
                }
                if receptor:
                    r_sab = _info(sab, rec_estados, receptor)
                    r_dom = _info(dom, rec_estados, receptor)
                    item['receptor'] = {
                        'sabado_mio': r_sab, 'domingo_mio': r_dom,
                        'trabaja_ambos': r_sab and r_dom,
                    }
                findes.append(item)
            d += _td(days=1)
        return json_ok({'findes': findes, 'meses': meses, 'anio': anio, 'mes': mes})


class AlternanciaFindeView(LoginRequiredMixin, View):
    """
    Devuelve, para el fin de semana de una fecha dada (sábado o domingo), qué jornada
    (AM/PM) trabaja el sábado y cuál el domingo según la alternancia. Sirve de "distintivo"
    en la Doblada de Fin de Semana para ver de un vistazo la configuración del finde.
    """
    def get(self, request):
        from datetime import datetime, timedelta
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        from turnos.services.turno_service import TurnoService
        fecha_str = request.GET.get('fecha')
        if not fecha_str:
            return json_error('Falta el parámetro fecha', status=400, code='missing_params')
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return json_error('Formato de fecha inválido (use YYYY-MM-DD)', status=400, code='invalid_date')
        if fecha.weekday() not in (5, 6):
            return json_error('La fecha debe ser sábado o domingo', status=400, code='no_finde')

        sabado = fecha if fecha.weekday() == 5 else fecha - timedelta(days=1)
        domingo = sabado + timedelta(days=1)

        # "mio": ¿el USUARIO trabaja ese día REALMENTE? Usa la fuente de verdad única
        # (estado_dia, las mismas capas de "Mis Turnos"), NO la alternancia pura. Así el
        # distintivo refleja cambios aprobados (p. ej. un cambio de descanso que movió su
        # día de trabajo del domingo al sábado). La jornada AM/PM sigue siendo la del finde.
        emp = getattr(request.user, 'empleado', None)

        def _mio(d):
            return bool(emp and TurnoService.estado_dia(emp, d)['trabaja'])

        return json_ok({
            'sabado': {
                'fecha': sabado.strftime('%Y-%m-%d'),
                'dia': sabado.strftime('%d/%m'),
                'jornada': AlternanciaFinesSemanaService.jornada_trabaja_sabado(sabado),
                'mio': _mio(sabado),
            },
            'domingo': {
                'fecha': domingo.strftime('%Y-%m-%d'),
                'dia': domingo.strftime('%d/%m'),
                'jornada': AlternanciaFinesSemanaService.jornada_trabaja_domingo(sabado),
                'mio': _mio(domingo),
            },
        })


