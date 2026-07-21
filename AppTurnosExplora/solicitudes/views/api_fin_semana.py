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

class DFDSCompanerosView(LoginRequiredMixin, View):
    """
    Compañeros para un cambio de FIN DE SEMANA (D FDS o Cambio de Descanso finde) en el
    finde de cesión dado, CADA UNO con su disponibilidad. Un compañero puede participar si:
    trabaja el OTRO día del finde (su día) y está LIBRE el día que cedes (para poder tomarlo).
    Si ya trabaja los dos días (doblada) no puede. Devuelve `disponible` + `motivo` para
    deshabilitar y explicar en el formulario.

    ?tipo_solicitud_id=  → estrategia a usar para filtrar el grupo contrario
                           (por defecto D FDS). Sirve para ambos formularios de finde.
    """
    def get(self, request):
        from datetime import datetime as _dt, timedelta as _td
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.solicitud_factory import SolicitudFactory
        from solicitudes.models import TipoSolicitudCambio

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'companeros': []})
        try:
            fecha = _dt.strptime(request.GET.get('fecha', ''), '%Y-%m-%d').date()  # tu día (el que cedes)
        except (TypeError, ValueError):
            return json_error('Parámetro fecha inválido', status=400, code='bad_request')
        if fecha.weekday() not in (5, 6):
            return json_error('La fecha debe ser sábado o domingo', status=400, code='no_finde')

        otro = fecha + _td(days=1) if fecha.weekday() == 5 else fecha - _td(days=1)
        dia_otro_nombre = 'sábado' if otro.weekday() == 5 else 'domingo'

        tipo = None
        tsid = request.GET.get('tipo_solicitud_id')
        if tsid and str(tsid).isdigit():
            tipo = TipoSolicitudCambio.objects.filter(id=int(tsid)).first()
        if not tipo:
            tipo = TipoSolicitudCambio.objects.filter(nombre='D FDS').first()
        strat = SolicitudFactory.get_strategy(tipo) if tipo else None
        lista = strat.get_empleados_disponibles(fecha.isoformat(), emp) if strat else []

        companeros = []
        for r in lista:
            trabaja_otro = TurnoService.estado_dia(r, otro)['trabaja']       # trabaja su día
            libre_cesion = not TurnoService.estado_dia(r, fecha)['trabaja']  # libre el día que cedes
            if trabaja_otro and libre_cesion:
                disp, motivo = True, None
            elif not libre_cesion:
                disp, motivo = False, 'ya trabaja los dos días ese finde (doblada)'
            elif not trabaja_otro:
                disp, motivo = False, f'no trabaja el {dia_otro_nombre} de ese finde'
            else:
                disp, motivo = False, 'no disponible ese finde'
            companeros.append({
                'id': r.id, 'nombre': f'{r.nombre} {r.apellido}',
                'dia': dia_otro_nombre, 'dia_fecha': otro.strftime('%d/%m'),
                'disponible': disp, 'motivo': motivo,
            })
        companeros.sort(key=lambda x: (not x['disponible'], x['nombre']))
        return json_ok({'companeros': companeros, 'otro_dia': dia_otro_nombre})


class DescansosSemanaUsuarioView(LoginRequiredMixin, View):
    """
    Devuelve los días de descanso de ENTRE SEMANA del usuario en un año: el día manual de
    su jornada (temporada/festivo) y el lunes de mantenimiento efectivo. Sirve para marcar
    esos días en el formulario de Cambio de Día de Descanso (modalidad entre semana).
    """
    def get(self, request):
        from datetime import date as _date
        from turnos.models import AsignarJornadaExplorador, DiaEspecial, DescansoSemanaManual
        try:
            anio = int(request.GET.get('anio'))
        except (TypeError, ValueError):
            anio = _date.today().year
        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'descansos': {}})
        # Permite consultar el grupo contrario (?jornada=PM) para el intercambio entre semana.
        jornada_param = (request.GET.get('jornada') or '').upper()
        if jornada_param in ('AM', 'PM'):
            jornada = jornada_param
        else:
            asg = (AsignarJornadaExplorador.objects
                   .filter(explorador=emp, fecha_inicio__lte=_date(anio, 12, 31))
                   .select_related('jornada').order_by('-fecha_inicio').first())
            jornada = asg.jornada.nombre.upper() if asg else None
        # ¿Es la consulta de MIS PROPIOS descansos? (sin ?jornada=). En ese caso reflejamos la
        # REALIDAD con la fuente de verdad (estado_dia): un descanso de temporada que el usuario
        # YA cedió en un cambio de descanso (ahora trabaja ese día) NO debe ofrecerse como
        # disponible. La consulta del grupo contrario (?jornada=) se queda con la config (es a
        # nivel grupo, sin persona concreta); esa la protege la validación del servidor al aprobar.
        es_propio = not jornada_param
        res = {}
        if jornada:
            from turnos.services.turno_service import TurnoService
            for d in DescansoSemanaManual.objects.filter(
                    fecha__year=anio, activo=True, jornada__nombre__iexact=jornada):
                if d.fecha.weekday() >= 5:
                    continue
                if es_propio and TurnoService.estado_dia(emp, d.fecha)['trabaja']:
                    continue  # ya lo cedió: hoy trabaja ese día, no es descanso disponible
                res[d.fecha.isoformat()] = 'temporada'
        for de in DiaEspecial.objects.filter(fecha__year=anio, tipo='mantenimiento', activo=True):
            if de.fecha.weekday() < 5 and DiaEspecial.es_mantenimiento_efectivo(de.fecha):
                res.setdefault(de.fecha.isoformat(), 'mantenimiento')

        # Cambios de descanso de temporada YA realizados (aprobados) este año: permite que el
        # formulario explique "ya hiciste el cambio con X" en vez de mostrar un mensaje que
        # parece un error cuando el único día de temporada del mes ya fue cedido. Solo aplica a
        # la consulta de MIS descansos (es_propio); la del grupo contrario no lo necesita.
        cambios_temporada = {}
        if es_propio:
            from django.db.models import Q as _Q
            from ..models import SolicitudCambio
            aprobadas = (SolicitudCambio.objects
                         .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='aprobada',
                                 fecha_cambio_turno__year=anio)
                         .filter(_Q(explorador_solicitante=emp) | _Q(explorador_receptor=emp))
                         .select_related('explorador_solicitante', 'explorador_receptor'))
            for s in aprobadas:
                f = s.fecha_cambio_turno
                if not f or f.weekday() >= 5:
                    continue  # los de fin de semana no son intercambios "entre semana" de temporada
                contraparte = (s.explorador_receptor if s.explorador_solicitante_id == emp.id
                               else s.explorador_solicitante)
                nombre = getattr(contraparte, 'nombre', None) or str(contraparte)
                cambios_temporada.setdefault(f.isoformat(), [])
                if nombre not in cambios_temporada[f.isoformat()]:
                    cambios_temporada[f.isoformat()].append(nombre)

        # Permisos de MEDIA JORNADA de temporada aprobados este año: consumen el día de descanso
        # (fecha_compensacion), por eso ese mes no hay descanso disponible. Se devuelve para que
        # el formulario explique el porqué en vez de mostrar el mensaje genérico.
        permisos_temporada = {}
        if es_propio:
            from permisos.models import PermisoEspecial
            for p in PermisoEspecial.objects.filter(
                    empleado=emp, tipo='MEDIA_JORNADA_TEMPORADA', estado='APROBADO',
                    fecha_inicio__year=anio):
                fcomp = getattr(p, 'fecha_compensacion', None)
                if not fcomp:
                    continue
                permisos_temporada[fcomp.isoformat()] = {
                    'fecha_trabajo': p.fecha_inicio.isoformat() if p.fecha_inicio else None,
                    'jornada_trabaja': getattr(p, 'jornada_trabaja', None),
                }

        return json_ok({'descansos': res, 'jornada': jornada,
                        'cambios_temporada': cambios_temporada,
                        'permisos_temporada': permisos_temporada})


class CoberturaCandidatosView(LoginRequiredMixin, View):
    """
    Candidatos para "Que me cubran mi día" (cobertura de temporada), evaluados en el
    DÍA DE TRABAJO (`fecha_trabajo`) para la jornada `opcion` (AM o PM).

    Regla: para cubrir mi jornada `opcion` ese día, el compañero NO debe trabajar YA esa
    jornada (dejaría un hueco). Puede estar:
      - libre/descansando ese día  → cubre sin deuda,
      - trabajando la jornada CONTRARIA → cubre pero dobla sobre su jornada → 30 min de deuda.
    Se descarta a quien ya trabaja `opcion`, a quien ya tiene el día completo, o a quien
    tiene el día comprometido en otra solicitud. Devuelve tarjetas con disponibilidad +
    motivo + su jornada el día que cubre y el día de pago (informativo para el front).
    """
    def get(self, request):
        from datetime import datetime as _dt
        from empleados.models import Empleado
        from turnos.models import AsignarJornadaExplorador
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService as _App

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'candidatos': []})

        def _fecha(k):
            v = request.GET.get(k)
            try:
                return _dt.strptime(v, '%Y-%m-%d').date() if v else None
            except ValueError:
                return None

        fecha_trabajo = _fecha('fecha_trabajo')
        fecha_pago = _fecha('fecha_pago')
        opcion = (request.GET.get('opcion') or '').upper()
        if not fecha_trabajo or opcion not in ('AM', 'PM'):
            return json_error('Parámetros inválidos (fecha_trabajo, opcion=AM|PM)',
                              status=400, code='bad_request')

        # Grupo contrario (quienes descansan mi día de trabajo por temporada).
        asg = (AsignarJornadaExplorador.objects.filter(explorador=emp, fecha_inicio__lte=fecha_trabajo)
               .select_related('jornada').order_by('-fecha_inicio').first())
        mi_grupo = asg.jornada.nombre.upper() if asg else None
        contrario = 'PM' if mi_grupo == 'AM' else 'AM'

        empleados = list(Empleado.objects.filter(activo=True).exclude(id=emp.id).select_related('user'))
        bases = {}
        for a in (AsignarJornadaExplorador.objects.filter(explorador__in=empleados, fecha_inicio__lte=fecha_trabajo)
                  .select_related('jornada').order_by('explorador_id', '-fecha_inicio')):
            bases.setdefault(a.explorador_id, a.jornada.nombre.upper())

        def _label(js):
            if js >= {'AM', 'PM'}:
                return 'DOBLADA'
            if 'AM' in js:
                return 'AM'
            if 'PM' in js:
                return 'PM'
            return 'DESCANSO'

        candidatos = []
        for c in empleados:
            if bases.get(c.id) != contrario:
                continue
            work = _App._jornadas_actuales(c, fecha_trabajo)
            disponible, motivo, genera_deuda = True, '', False
            comprometido = TurnoService.dia_comprometido_por_solicitud(c, fecha_trabajo)
            if opcion in work:
                disponible = False
                motivo = f'Ya trabaja {opcion} el {fecha_trabajo:%d/%m}; no puede cubrir esa jornada.'
            elif work >= {'AM', 'PM'}:
                disponible = False
                motivo = f'Ya tiene el día completo (AM+PM) el {fecha_trabajo:%d/%m}.'
            elif comprometido:
                disponible = False
                motivo = f'Ese día ya está comprometido en otra solicitud ({comprometido.get("motivo")}).'
            else:
                # Libre → sin deuda; trabaja la jornada contraria → dobla → 30 min de deuda.
                genera_deuda = bool(work)

            jornada_pago = _label(_App._jornadas_actuales(c, fecha_pago)) if fecha_pago else None
            candidatos.append({
                'id': c.id,
                'nombre': c.nombre,
                'apellido': c.apellido,
                'jornada_cubre': _label(work),
                'jornada_pago': jornada_pago,
                'disponible': disponible,
                'genera_deuda': genera_deuda,
                'motivo': motivo,
            })

        candidatos.sort(key=lambda x: (not x['disponible'], x['nombre']))
        # MI jornada en el día de pago (para mostrar "tú tienes X · el compañero tiene Y").
        mi_jornada_pago = _label(_App._jornadas_actuales(emp, fecha_pago)) if fecha_pago else None
        return json_ok({'candidatos': candidatos, 'opcion': opcion, 'mi_jornada_pago': mi_jornada_pago})


class CambioDescansoFindesView(LoginRequiredMixin, View):
    """
    Fines de semana del usuario para el Cambio de Día de Descanso (modalidad fin de semana).

    - Sin parámetros: devuelve la lista de MESES disponibles (desde el mes actual, 7 meses)
      para llenar el selector de mes, además de los findes del primer mes con opciones.
    - Con ?anio=2026&mes=7: devuelve TODOS los fines de semana de ese mes con el día que el
      usuario TRABAJA según sus TURNOS REALES.

    Cada finde: {sabado, domingo, dia_trabajo: 'sabado'|'domingo'|null, seleccionable: bool}
      - dia_trabajo: el día con turnos (null si descansa ambos o trabaja ambos).
      - seleccionable: True si trabaja exactamente un día y el sábado no es pasado.
    """
    def get(self, request):
        from datetime import date as _date, timedelta as _td
        from calendar import monthrange
        from turnos.models import AsignarJornadaExplorador
        from turnos.services.turno_service import TurnoService

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'findes': [], 'meses': [], 'jornada_base': None})

        hoy = _date.today()

        def findes_de(anio, mes):
            """Todos los findes cuyo sábado cae en el mes, con el día que trabaja el usuario.

            Usa la FUENTE DE VERDAD ÚNICA (estado_mes), las MISMAS 6 capas que pinta "Mis
            Turnos": Turno real → día comprometido por otra solicitud aprobada (doblada/d_fds/
            cambio descanso/perm) → festivo → fin de semana → temporada → mantenimiento → base.
            Así el formulario y "Mis Turnos" siempre coinciden (antes el form usaba
            get_turno_explorador, que ignoraba las cesiones de doblada y ofrecía días que la
            persona ya había cedido).
            """
            estados = TurnoService.estado_mes(emp, anio, mes)

            # Día COMPROMETIDO (no seleccionable): fuente única de verdad, compartida con la
            # validación del backend (CambioDescansoStrategy._trabaja_dia), para que el selector y
            # el envío del formulario respondan siempre lo mismo. Regla (ver
            # dia_bloqueado_para_nuevo_cambio): otro tipo de cambio (DOBLADA, D FDS, CT…) → siempre
            # bloqueado; un CAMBIO DESCANSO previo → solo bloqueado dentro de los 30 min de su
            # ventana de cancelación.
            from solicitudes.services.cambio_descanso_aplicacion_service import (
                CambioDescansoAplicacionService as _CDAS,
            )

            def trabaja(fecha):
                e = estados.get(fecha)
                if e is None:  # p. ej. domingo que cae en el mes siguiente
                    e = TurnoService.estado_dia(emp, fecha)
                return e['trabaja']

            out = []
            d = _date(anio, mes, 1)
            while d.weekday() != 5:  # primer sábado
                d += _td(days=1)
            ultimo = _date(anio, mes, monthrange(anio, mes)[1])
            while d <= ultimo:
                sabado = d
                domingo = d + _td(days=1)
                trabaja_sab = trabaja(sabado)
                trabaja_dom = trabaja(domingo)
                dia_trabajo = None
                if trabaja_sab and not trabaja_dom:
                    dia_trabajo = 'sabado'
                elif trabaja_dom and not trabaja_sab:
                    dia_trabajo = 'domingo'
                # Si el día que trabaja está comprometido (bloqueado), NO es seleccionable.
                dia_comprometido = bool(dia_trabajo) and _CDAS.dia_bloqueado_para_nuevo_cambio(
                    emp, sabado if dia_trabajo == 'sabado' else domingo
                )
                seleccionable = bool(dia_trabajo) and sabado >= hoy and not dia_comprometido
                # Motivo por el cual NO es seleccionable (para mostrarlo en la tarjeta).
                motivo = None
                if not seleccionable:
                    if sabado < hoy:
                        motivo = 'Fin de semana pasado'
                    elif dia_comprometido:
                        motivo = 'Ese día ya está comprometido en otra solicitud aprobada'
                    elif trabaja_sab and trabaja_dom:
                        motivo = 'Trabajas los dos días — no hay un solo día para intercambiar'
                    elif not trabaja_sab and not trabaja_dom:
                        motivo = 'Descansas todo el fin de semana — nada que intercambiar'
                    else:
                        motivo = 'No disponible para cambio'
                out.append({
                    'sabado': sabado.isoformat(),
                    'domingo': domingo.isoformat(),
                    'dia_trabajo': dia_trabajo,
                    'seleccionable': seleccionable,
                    'motivo': motivo,
                })
                d += _td(days=7)
            return out

        # Lista de meses (mes actual + 6 siguientes). El calendario es calculado: siempre existe.
        MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        meses = []
        y, m = hoy.year, hoy.month
        for _ in range(7):
            meses.append({'anio': y, 'mes': m, 'label': f'{MESES_ES[m]} {y}', 'tiene_turnos': True})
            m += 1
            if m > 12:
                m = 1
                y += 1

        # Mes solicitado: el del request, o el PRIMERO con findes seleccionables, o el actual.
        mes_param = request.GET.get('mes')
        anio_param = request.GET.get('anio')
        if mes_param and anio_param:
            try:
                anio, mes = int(anio_param), int(mes_param)
            except (TypeError, ValueError):
                anio, mes = hoy.year, hoy.month
            findes = findes_de(anio, mes)
        else:
            anio, mes = hoy.year, hoy.month
            findes = findes_de(anio, mes)
            if not any(f['seleccionable'] for f in findes):
                for mm in meses:
                    cand = findes_de(mm['anio'], mm['mes'])
                    if any(f['seleccionable'] for f in cand):
                        anio, mes, findes = mm['anio'], mm['mes'], cand
                        break

        asg = (AsignarJornadaExplorador.objects
               .filter(explorador=emp, fecha_inicio__lte=_date(anio, mes, monthrange(anio, mes)[1]))
               .select_related('jornada').order_by('-fecha_inicio').first())
        jornada_base = asg.jornada.nombre.upper() if asg else None

        return json_ok({'findes': findes, 'meses': meses, 'anio': anio, 'mes': mes,
                        'sin_turnos_mes': False, 'jornada_base': jornada_base})


