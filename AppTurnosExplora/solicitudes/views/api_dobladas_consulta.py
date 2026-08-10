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

class DobladasSemanaView(LoginRequiredMixin, View):
    """
    Dobladas reales (Turno AM+PM, lun-vie) de la semana de la fecha dada, de OTROS
    empleados. Alimenta el sub-flujo "cambio de doblada" del Cambio de Día de
    Descanso entre semana: el solicitante elige cuál doblada de la semana tomar.

    `fecha` es MI día completo de temporada (el que cedo). Solo se listan compañeros que
    además estén LIBRES ese día: el intercambio es mutuo (él toma mi día completo), así que
    quien trabaja ese día no puede tomarlo. Es la misma condición que valida el envío
    (`_validar_semana_cambio_doblada`); sin ella el desplegable ofrecía gente que el envío
    tumbaba con "tu compañero trabaja el ...; debe estar descansando".
    """
    def get(self, request):
        from datetime import datetime as _dt, timedelta as _td
        from collections import defaultdict
        from turnos.models import Turno
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.cambio_descanso_aplicacion_service import (
            CambioDescansoAplicacionService as _App)

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'dobladas': []})
        try:
            fecha = _dt.strptime(request.GET.get('fecha', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return json_error('Parámetro fecha inválido (YYYY-MM-DD)', status=400, code='bad_request')

        lunes = fecha - _td(days=fecha.weekday())
        viernes = lunes + _td(days=4)

        # Jornadas por (empleado, fecha) en la semana laboral
        pares = defaultdict(set)
        nombres = {}
        for t in (Turno.objects
                  .filter(fecha__range=(lunes, viernes), explorador__activo=True)
                  .exclude(explorador=emp)
                  .select_related('jornada', 'explorador')):
            pares[(t.explorador_id, t.fecha)].add(t.jornada.nombre.upper())
            nombres[t.explorador_id] = f"{t.explorador.nombre} {t.explorador.apellido}"

        # ¿Puede este compañero tomar MI día completo? Se calcula una vez por empleado
        # (no por doblada), que es como lo valida el envío.
        candidatos = {emp_id for (emp_id, _f) in pares}
        libre_mi_dia = {
            e.id: (not _App._jornadas_actuales(e, fecha)
                   and not TurnoService.dia_comprometido_por_solicitud(e, fecha))
            for e in Empleado.objects.filter(id__in=candidatos)
        }

        dobladas = [
            {'empleado_id': emp_id, 'nombre': nombres[emp_id], 'fecha': f.isoformat()}
            for (emp_id, f), js in sorted(pares.items(), key=lambda kv: (kv[0][1], nombres[kv[0][0]]))
            if {'AM', 'PM'} <= js and f != fecha and libre_mi_dia.get(emp_id)
        ]
        return json_ok({'dobladas': dobladas})


class ExploradoresConDobladaView(LoginRequiredMixin, View):
    """
    Candidatos para el modo "Intercambiar doblada" del formulario de doblada. Devuelve
    exploradores ACTIVOS que tienen una DOBLADA (AM+PM) en el día B (`fecha`) y que, además,
    están LIBRES el día A (`fecha_cesion`) para poder asumir la doblada del solicitante ese día
    (una doblada es día completo: quien la cubre debe estar descansando). Excluye al usuario
    actual y el caso A==B.
    """
    def get(self, request):
        from datetime import datetime as _dt
        from turnos.services.turno_service import TurnoService as _TS
        fecha = request.GET.get('fecha')
        try:
            fecha_obj = DateUtils.parse_date(fecha)
        except (TypeError, ValueError):
            return json_error('Fecha inválida', status=400, code='fecha_invalida')
        # Día A (fecha de cesión): opcional, pero si viene se filtra por "libre ese día".
        fecha_cesion = request.GET.get('fecha_cesion')
        fecha_cesion_obj = None
        if fecha_cesion:
            try:
                fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)
            except (TypeError, ValueError):
                fecha_cesion_obj = None
        if fecha_cesion_obj == fecha_obj:
            return json_ok({'exploradores': [], 'motivo': 'mismo_dia'})
        yo = getattr(request.user, 'empleado', None)
        # El SOLICITANTE debe estar LIBRE el día B para poder asumir la doblada del compañero;
        # si ese día ya trabaja, ni siquiera tiene sentido buscar candidatos.
        if yo and _TS.estado_dia(yo, fecha_obj).get('trabaja'):
            return json_ok({'exploradores': [], 'motivo': 'solicitante_ocupado'})
        con_doblada_b = 0   # cuántos tienen doblada el día B (antes del filtro "libre el día A")
        out = []
        for emp in Empleado.objects.filter(activo=True).exclude(id=getattr(yo, 'id', None)):
            if _TS.estado_dia(emp, fecha_obj).get('jornada') != 'DOBLADA':
                continue
            con_doblada_b += 1
            # Debe estar LIBRE el día A para poder cubrir tu doblada ese día.
            if fecha_cesion_obj and _TS.estado_dia(emp, fecha_cesion_obj).get('trabaja'):
                continue
            out.append({'id': emp.id, 'nombre': f'{emp.nombre} {emp.apellido}'})
        out.sort(key=lambda x: x['nombre'])
        motivo = None
        if not out:
            motivo = 'ninguno_libre_dia_a' if con_doblada_b else 'sin_dobladas'
        return json_ok({'exploradores': out, 'motivo': motivo})


class SabadoPagoComprometidoView(LoginRequiredMixin, View):
    """
    ¿El sábado dado ya está COMPROMETIDO como fecha de pago por otra doblada aprobada del
    usuario actual? Un sábado solo admite UN pago de doblada (se reparte en dos mitades), así
    que si ya hay una que paga ese sábado, el formulario debe avisar de una vez (en lugar de
    mostrar el selector AM/PM y dejar que el guard del backend lo rechace al enviar).

    Espejo en la UI del guard de DobladaStrategy.validar_solicitud (misma consulta).
    """
    def get(self, request):
        from datetime import datetime as _dt
        fecha = request.GET.get('fecha')
        try:
            fecha_obj = DateUtils.parse_date(fecha)
        except (TypeError, ValueError):
            return json_error('Fecha inválida', status=400, code='fecha_invalida')
        # Solo aplica a sábados (weekday 5).
        if fecha_obj.weekday() != 5:
            return json_ok({'comprometido': False})
        yo = getattr(request.user, 'empleado', None)
        if not yo:
            return json_ok({'comprometido': False})
        qs = SolicitudCambio.objects.filter(
            explorador_solicitante=yo,
            tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
            estado='aprobada',
            doblada__fecha_pago=fecha_obj,
        ).select_related('doblada')
        _sid = request.GET.get('solicitud_id')
        if _sid:
            qs = qs.exclude(id=_sid)
        # Un sábado se reparte en dos MITADES (AM/PM). Solo se bloquea DURO si el sábado ya está
        # LLENO. Si queda una mitad libre, se permite pagar esta doblada con esa mitad (terminarías
        # doblado, cada mitad pagando a una persona distinta).
        ocupadas = set()
        fecha_cesion_txt = None
        for o in qs:
            jps = (getattr(o.doblada, 'jornada_pago_sabado', '') or '').upper()
            if jps in ('AM', 'PM'):
                ocupadas.add(jps)
            else:
                ocupadas |= {'AM', 'PM'}
            if fecha_cesion_txt is None and o.fecha_cambio_turno:
                fecha_cesion_txt = o.fecha_cambio_turno.strftime('%d/%m/%Y')
        if not ocupadas:
            return json_ok({'comprometido': False})
        libre = sorted({'AM', 'PM'} - ocupadas)
        return json_ok({
            'comprometido': not libre,                       # bloqueo duro solo si está LLENO
            'mitad_ocupada': '/'.join(sorted(ocupadas)),
            'mitad_libre': libre[0] if len(libre) == 1 else None,
            'fecha_cesion': fecha_cesion_txt,
        })
