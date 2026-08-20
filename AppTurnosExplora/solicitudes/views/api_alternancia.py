from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from ..models import SolicitudCambio
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok

# Create your views here.

class AlternanciaMesView(LoginRequiredMixin, View):
    """
    Fines de semana de un mes para la Doblada de Fin de Semana (tarjetas).

    Sin parámetros o con ?anio=&mes=: devuelve TODOS los fines de semana cuyo sábado cae en
    el mes, cada uno con la jornada (AM/PM) del sábado y del domingo, y QUÉ DÍA trabaja el
    usuario (fuente de verdad estado_dia). Así el formulario muestra de un vistazo, sin tener
    que seleccionar, cuál día es el suyo. También devuelve la lista de meses disponibles.

    Cada día del finde se evalúa por SEPARADO (`cedible`), porque un explorador puede trabajar
    los dos días —su día más uno que cubre por un favor— y debe poder ceder cualquiera de ellos.

    Cada finde:
      {sabado:{fecha, dia, jornada, mio, jornada_real, completo, del_mes, cerrado,
               cedible, motivo_no_cedible},
       domingo:{...}, mi_dia:'sabado'|'domingo'|null, trabaja_ambos:bool,
       seleccionable:bool, motivo_no_seleccionable:str|null}
    """
    def get(self, request):
        from datetime import date as _date, timedelta as _td
        from calendar import monthrange
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        from turnos.services.turno_service import TurnoService

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_ok({'findes': [], 'meses': []})

        hoy = timezone.localdate()
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

        def _estado(d, e_estados, e_emp):
            """Estado real del día (fuente única). `estado_mes` no cubre días de otro mes."""
            return e_estados.get(d) or TurnoService.estado_dia(e_emp, d)

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

        # Cierre semanal: se marca cada finde para que el formulario no ofrezca días que el
        # servidor rechazará al enviar.
        def _cerrado(f):
            try:
                from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService
                return CierreSolicitudesService.fecha_bloqueada(f)
            except Exception:
                logger.warning('No se pudo evaluar el cierre semanal para %s', f, exc_info=True)
                return False

        findes = []
        _, ultimo = monthrange(anio, mes)
        fin_mes = _date(anio, mes, ultimo)

        # Días que se trabajan porque se CUBRE a un tercero por un favor (se recibió su día, o se
        # está pagando el propio). Importan por los dos lados:
        #   - los MÍOS: se pueden ceder igual (el sustituto trabajará el día completo), pero el
        #     formulario advierte a quién afecta;
        #   - los del RECEPTOR: NO sirven como fecha de pago. Devolverle un día que no es suyo no
        #     le devuelve nada —solo lo libera de un compromiso con un tercero, cuya deuda
        #     quedaría en el aire—. El servidor lo rechaza, así que el formulario tampoco debe
        #     ofrecerlo.
        # Se resuelve en 1 consulta por persona para todo el mes, no una por día.
        desde, hasta = _date(anio, mes, 1) - _td(days=6), fin_mes + _td(days=1)

        def _coberturas(persona):
            """{fecha: {companero, solicitud_id, tipo}} de los días que `persona` cubre por favor."""
            if not persona:
                return {}
            out = {}
            try:
                from django.db.models import Q as _Q
                for s in (SolicitudCambio.objects
                          .filter(estado='aprobada', doblada__isnull=False,
                                  tipo_cambio__nombre__in=['DOBLADA', 'D FDS'])
                          .filter(_Q(explorador_receptor=persona, fecha_cambio_turno__range=(desde, hasta))
                                  | _Q(explorador_solicitante=persona, doblada__fecha_pago__range=(desde, hasta)))
                          .select_related('doblada', 'explorador_solicitante', 'explorador_receptor')
                          .order_by('-id')):
                    es_pago = s.explorador_solicitante_id == persona.id
                    fecha_cob = s.doblada.fecha_pago if es_pago else s.fecha_cambio_turno
                    otro = s.explorador_receptor if es_pago else s.explorador_solicitante
                    if fecha_cob:
                        out.setdefault(fecha_cob, {
                            'companero': f'{otro.nombre} {otro.apellido}',
                            'solicitud_id': s.id,
                            'tipo': 'pago' if es_pago else 'cubre_cesion',
                        })
            except Exception:
                logger.warning('No se pudieron cargar las coberturas de %s', persona, exc_info=True)
            return out

        cobertura_por_fecha = _coberturas(emp)
        cobertura_receptor = _coberturas(receptor)
        # Se empieza 6 días ANTES del día 1 para incluir el finde a caballo entre dos meses
        # (sábado 31/07 – domingo 01/08): antes solo aparecía en el mes del sábado, así que un
        # domingo trabajado el día 1 era inalcanzable desde su propio mes, y seleccionarlo desde
        # el mes anterior hacía imposible encontrar un pago del mismo mes.
        d = _date(anio, mes, 1) - _td(days=6)
        while d <= fin_mes:
            if d.weekday() == 5:  # sábado ancla del finde
                sab = d
                dom = sab + _td(days=1)
                # Solo interesa el finde si alguno de sus dos días cae en el mes consultado.
                if not (sab.month == mes and sab.year == anio) and not (dom.month == mes and dom.year == anio):
                    d += _td(days=1)
                    continue
                est_sab = _estado(sab, estados, emp)
                est_dom = _estado(dom, estados, emp)
                mio_sab = bool(est_sab['trabaja'])
                mio_dom = bool(est_dom['trabaja'])
                trabaja_ambos = mio_sab and mio_dom

                def _dia(fecha, est, jornada_alt):
                    """
                    Bloque de un día del finde. `cedible` decide si ESE día se puede ceder, mirando
                    el estado REAL (no la alternancia teórica): hay que trabajarlo a día completo.

                    Antes se calculaba un único "mi_dia" por finde, así que quien trabaja sábado Y
                    domingo (su día + uno que cubre por un favor) no podía ceder ninguno de los dos:
                    el finde entero salía no seleccionable. Ahora cada día se evalúa por separado.
                    """
                    del_mes_d = fecha.month == mes and fecha.year == anio
                    cerrado_d = _cerrado(fecha)
                    trabaja_d = bool(est['trabaja'])
                    # En finde, un día trabajado completo es 'DOBLADA' (AM+PM). 'AM'/'PM' sueltos
                    # son media jornada por un cambio previo: no hay día completo que ceder.
                    completo = trabaja_d and est.get('jornada') == 'DOBLADA'
                    cedible = bool(completo and fecha > hoy and del_mes_d and not cerrado_d)
                    if cedible:
                        motivo = None
                    elif not trabaja_d:
                        motivo = 'descansas ese día'
                    elif not completo:
                        motivo = (f"solo tienes media jornada ({est.get('jornada') or 'parcial'}) "
                                  f"ese día por un cambio previo")
                    elif cerrado_d:
                        motivo = 'la programación de ese fin de semana ya está cerrada'
                    elif not del_mes_d:
                        motivo = 'ese día pertenece a otro mes: elígelo desde su propio mes'
                    else:
                        motivo = 'ya pasó'
                    return {
                        'fecha': fecha.isoformat(), 'dia': fecha.strftime('%d/%m'),
                        'jornada': jornada_alt,
                        'mio': trabaja_d,
                        'jornada_real': est.get('jornada'),
                        'completo': completo,
                        'del_mes': del_mes_d,
                        'cerrado': cerrado_d,
                        'cedible': cedible,
                        'motivo_no_cedible': motivo,
                        # Si ese día se trabaja cubriendo a un tercero, el formulario lo advierte.
                        'cobertura': cobertura_por_fecha.get(fecha) if trabaja_d else None,
                    }

                # Alternancia PUBLICADA (None si el año no está sembrado).
                bloque_sab = _dia(sab, est_sab, AsignacionEspecialService.grupo_trabaja(sab))
                bloque_dom = _dia(dom, est_dom, AsignacionEspecialService.grupo_trabaja(dom))

                # `mi_dia` se conserva por compatibilidad: el día propio cuando solo hay uno.
                if trabaja_ambos:
                    mi_dia = None
                elif mio_sab:
                    mi_dia = 'sabado'
                elif mio_dom:
                    mi_dia = 'domingo'
                else:
                    mi_dia = None

                seleccionable = bloque_sab['cedible'] or bloque_dom['cedible']
                motivos = [b['motivo_no_cedible'] for b in (bloque_sab, bloque_dom)
                           if b['mio'] and b['motivo_no_cedible']]
                item = {
                    'sabado': bloque_sab,
                    'domingo': bloque_dom,
                    'mi_dia': mi_dia,
                    'trabaja_ambos': trabaja_ambos,
                    'seleccionable': seleccionable,
                    # Motivo cuando trabajas algún día del finde pero no puedes cederlo.
                    'motivo_no_seleccionable': (None if seleccionable else (motivos[0] if motivos else None)),
                }
                if receptor:
                    est_r_sab = _estado(sab, rec_estados, receptor)
                    est_r_dom = _estado(dom, rec_estados, receptor)
                    r_sab = bool(est_r_sab['trabaja'])
                    r_dom = bool(est_r_dom['trabaja'])
                    item['receptor'] = {
                        'sabado_mio': r_sab, 'domingo_mio': r_dom,
                        'trabaja_ambos': r_sab and r_dom,
                        # Día completo (DOBLADA) vs media jornada: solo se puede cubrir/recibir un
                        # día completo, así que el formulario necesita distinguirlo.
                        'sabado_completo': r_sab and est_r_sab.get('jornada') == 'DOBLADA',
                        'domingo_completo': r_dom and est_r_dom.get('jornada') == 'DOBLADA',
                        # `propio` = lo trabaja porque es SU día, no cubriendo a un tercero. Solo
                        # un día propio sirve como fecha de pago.
                        'sabado_propio': r_sab and sab not in cobertura_receptor,
                        'domingo_propio': r_dom and dom not in cobertura_receptor,
                        'sabado_cobertura': cobertura_receptor.get(sab),
                        'domingo_cobertura': cobertura_receptor.get(dom),
                    }
                findes.append(item)
            d += _td(days=1)
        return json_ok({'findes': findes, 'meses': meses, 'anio': anio, 'mes': mes})




