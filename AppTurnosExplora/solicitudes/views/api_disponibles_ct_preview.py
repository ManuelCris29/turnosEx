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
import hashlib
import hmac
import logging
from django.core.cache import cache
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error

# Create your views here.

class ObtenerEmpleadosDisponiblesView(LoginRequiredMixin, View):

    @staticmethod
    def _filtrar_por_descanso_receptor(empleados, fecha_descanso_receptor):
        """
        Deja solo los candidatos que SIGUEN descansando `fecha_descanso_receptor`.

        POR QUÉ: en el CAMBIO DESCANSO de entre semana el intercambio se hace contra el descanso
        del grupo contrario en la MISMA semana, que es una fecha distinta de la que se pasa en
        `fecha` (esa es MI descanso). El desplegable se llenaba con `fecha` y la validación decide
        con la otra, así que ofrecía compañeros que luego rechazaba al enviar:
        "Tu compañero ya no descansa el DD/MM (ya lo intercambió o está comprometido)".

        Se usa la MISMA comprobación que la validación (`estado_dia(...)['trabaja']`, ver
        `CambioDescansoStrategy._validar_entre_semana`) para que lo que se ofrece y lo que se
        acepta no puedan divergir. Sin el parámetro no filtra nada: el resto de formularios
        (CT, doblada, CT permanente…) siguen igual.
        """
        if not fecha_descanso_receptor or not empleados:
            return empleados
        fecha_obj = DateUtils.parse_date(fecha_descanso_receptor)
        if not fecha_obj:
            return empleados
        from turnos.services.turno_service import TurnoService
        return [e for e in empleados if not TurnoService.estado_dia(e, fecha_obj)['trabaja']]

    def get(self, request):
        fecha = request.GET.get('fecha')
        tipo_solicitud_id = request.GET.get('tipo_solicitud_id')
        
        # Nuevos parámetros para CT PERMANENTE
        fecha_fin = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')

        # CAMBIO DESCANSO entre semana: el día que el CANDIDATO debe seguir descansando.
        # `fecha` es MI descanso; el intercambio se decide sobre el descanso del grupo contrario
        # en esa misma semana (la `fecha_pago`), que es una fecha DISTINTA. Sin este parámetro el
        # desplegable se filtraba por `fecha` y ofrecía compañeros que la validación luego
        # rechazaba con "Tu compañero ya no descansa el ..." (ver `CambioDescansoStrategy`).
        fecha_descanso_receptor = request.GET.get('fecha_descanso_receptor')
        
        # Logging mejorado para diagnóstico
        logger.info("ObtenerEmpleadosDisponiblesView - Parámetros recibidos", extra={
            'fecha': fecha,
            'tipo_solicitud_id': tipo_solicitud_id,
            'fecha_fin': fecha_fin,
            'usuario_id': request.user.id if request.user.is_authenticated else None,
            'empleado_id': request.user.empleado.id if hasattr(request.user, 'empleado') else None
        })
        
        if not fecha:
            logger.warning("ObtenerEmpleadosDisponiblesView - Fecha no proporcionada")
            return json_ok({'empleados': []})
        
        # Obtener el tipo de solicitud
        tipo_solicitud = None
        if tipo_solicitud_id:
            try:
                tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)  # type: ignore
                logger.info("ObtenerEmpleadosDisponiblesView - Tipo de solicitud obtenido", extra={
                    'tipo_solicitud': tipo_solicitud.nombre,
                    'tipo_id': tipo_solicitud_id,
                    'codigo_estrategia': tipo_solicitud.codigo_estrategia,
                    'activo': tipo_solicitud.activo
                })
                print(f"DEBUG: Tipo de solicitud encontrado - ID: {tipo_solicitud.id}, Nombre: {tipo_solicitud.nombre}, Activo: {tipo_solicitud.activo}")
            except TipoSolicitudCambio.DoesNotExist:  # type: ignore
                logger.warning("ObtenerEmpleadosDisponiblesView - Tipo de solicitud no encontrado", extra={
                    'tipo_id': tipo_solicitud_id
                })
                print(f"DEBUG: Tipo de solicitud NO encontrado - ID: {tipo_solicitud_id}")
        else:
            logger.warning("ObtenerEmpleadosDisponiblesView - tipo_solicitud_id no proporcionado")
            print("DEBUG: tipo_solicitud_id no proporcionado")
        
        # Verificar si el usuario tiene empleado asociado
        if not hasattr(request.user, 'empleado'):
            return json_ok({'empleados': []})
            
        # Parsear dias_seleccionados
        import json
        try:
            dias_seleccionados = json.loads(dias_seleccionados_json)
        except json.JSONDecodeError:
            dias_seleccionados = {}
        
        # Cache para empleados disponibles usando CacheService
        # INCLUIR usuario actual en cache key para evitar contaminación cruzada
        from core.services.cache_service import CacheService
        
        # Clave de caché extendida para incluir parámetros de rango
        cache_params = f"{fecha}_{tipo_solicitud_id or 'default'}_{request.user.empleado.id}"
        if fecha_descanso_receptor:
            # Forma parte de la clave: dos peticiones con la misma `fecha` pero distinta fecha de
            # descanso del receptor producen listas distintas.
            cache_params += f"_r{fecha_descanso_receptor}"
        if fecha_fin:
            import hashlib
            # No es uso criptográfico: solo deriva una clave de caché estable. Se hashea el JSON
            # NORMALIZADO (claves ordenadas, sin espacios), no el texto crudo del parámetro: dos
            # peticiones equivalentes que solo difieran en el orden de las claves o en el espaciado
            # generaban entradas de caché distintas y recalculaban todo el rango.
            dias_norm = json.dumps(dias_seleccionados, sort_keys=True, separators=(',', ':'))
            dias_hash = hashlib.md5(dias_norm.encode(), usedforsecurity=False).hexdigest()
            cache_params += f"_{fecha_fin}_{dias_hash}"
            
        # v6: se añade el filtro por `fecha_descanso_receptor` (el candidato debe SEGUIR
        # descansando ese día); las listas cacheadas en v5 no lo aplican.
        cache_key = f"empleados_disp_v6_{cache_params}"

        def obtener_empleados():
            # Obtener empleados según el tipo de solicitud usando el Factory
            try:
                empleados = SolicitudFactory.get_empleados_disponibles(
                    tipo_solicitud,
                    fecha,
                    request.user.empleado,
                    fecha_fin=fecha_fin,
                    dias_seleccionados=dias_seleccionados
                )
                empleados = ObtenerEmpleadosDisponiblesView._filtrar_por_descanso_receptor(
                    empleados, fecha_descanso_receptor
                )
                logger.info("ObtenerEmpleadosDisponiblesView - Empleados obtenidos desde Factory", extra={
                    'count': len(empleados) if empleados else 0,
                    'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None',
                    'tipo_id': tipo_solicitud_id
                })
                return empleados
            except Exception as e:
                logger.error("ObtenerEmpleadosDisponiblesView - Error obteniendo empleados", extra={
                    'error': str(e),
                    'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None'
                }, exc_info=True)
                return []
        
        from core.services.cache_service import CACHE_TTL_MEDIUM
        
        empleados_disponibles = CacheService.get_or_set(
            cache_key,
            obtener_empleados,
            ttl=CACHE_TTL_MEDIUM
        )
        
        logger.info("ObtenerEmpleadosDisponiblesView - Empleados disponibles finales", extra={
            'count': len(empleados_disponibles) if empleados_disponibles else 0,
            'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None',
            'cache_key': cache_key
        })
        
        # Convertir a formato JSON con metadatos extendidos
        empleados_data = []
        
        # Verificar que empleados_disponibles sea iterable
        if not empleados_disponibles:
            logger.warning("ObtenerEmpleadosDisponiblesView - empleados_disponibles es None o vacío")
            empleados_disponibles = []
        elif not hasattr(empleados_disponibles, '__iter__'):
            logger.error("ObtenerEmpleadosDisponiblesView - empleados_disponibles no es iterable", extra={
                'tipo': type(empleados_disponibles).__name__
            })
            empleados_disponibles = []
        
        for empleado in empleados_disponibles:
            try:
                data = {
                    'id': empleado.id,
                    'nombre': empleado.nombre,
                    'apellido': empleado.apellido,
                }
                # Jornada REAL del día (doblada permanente): etiqueta AM/PM del compañero
                if getattr(empleado, 'jornada_real', None):
                    data['jornada'] = empleado.jornada_real

                # Agregar metadatos de compatibilidad si existen (CT Permanente Best Match)
                if hasattr(empleado, 'compatibilidad_percent'):
                    data['compatibilidad_percent'] = empleado.compatibilidad_percent
                    data['dias_compatibles'] = getattr(empleado, 'dias_compatibles', [])
                    data['dias_incompatibles'] = getattr(empleado, 'dias_incompatibles', [])
                    data['total_dias_rango'] = getattr(empleado, 'total_dias_rango', 0)
                    
                empleados_data.append(data)
            except Exception as e:
                logger.error("ObtenerEmpleadosDisponiblesView - Error serializando empleado", extra={
                    'empleado_id': getattr(empleado, 'id', 'N/A'),
                    'error': str(e)
                }, exc_info=True)
        
        logger.info("ObtenerEmpleadosDisponiblesView - Respuesta JSON preparada", extra={
            'empleados_count': len(empleados_data),
            'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None'
        })
        
        return json_ok({'empleados': empleados_data})


class PrevisualizarCTPermanenteView(LoginRequiredMixin, View):
    """
    Endpoint de previsualización para CT PERMANENTE.
    Usa la misma lógica de negocio del backend para que la vista previa
    coincida exactamente con las fechas que se aplicarán.
    """

    def get(self, request):
        from datetime import datetime, timedelta
        import json
        from django.core.exceptions import ValidationError
        from empleados.models import Empleado
        from ..services.ct_permanente_helper import (
            evaluar_fechas_ct_permanente, precargar_ct_permanente,
        )
        from ..services.solicitud_validator import SolicitudValidator  # type: ignore

        fecha_inicio_str = request.GET.get('fecha_inicio')
        fecha_fin_str = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')
        empleado_receptor_id = request.GET.get('empleado_receptor_id')

        if not fecha_inicio_str or not fecha_fin_str:
            return json_error(
                'Faltan parámetros de fecha_inicio o fecha_fin',
                status=400,
                code='missing_params',
            )

        try:
            fecha_inicio = DateUtils.parse_date(fecha_inicio_str)
            fecha_fin = DateUtils.parse_date(fecha_fin_str)
        except ValueError:
            return json_error(
                'Formato de fecha inválido. Use YYYY-MM-DD.',
                status=400,
                code='invalid_date',
            )

        # Validar que el usuario tenga empleado asociado
        if not hasattr(request.user, 'empleado'):
            return json_error(
                'Usuario sin empleado asociado',
                status=400,
                code='no_empleado',
            )

        solicitante: Empleado = request.user.empleado  # type: ignore

        # Receptor es opcional en la previsualización (antes de escoger compañero)
        receptor: Empleado | None = None  # type: ignore
        if empleado_receptor_id:
            try:
                receptor = Empleado.objects.get(id=empleado_receptor_id)
            except Empleado.DoesNotExist:
                receptor = None

        # Parsear días seleccionados
        try:
            dias_seleccionados = json.loads(dias_seleccionados_json) if dias_seleccionados_json else {}
        except json.JSONDecodeError:
            dias_seleccionados = {}

        try:
            # Validaciones básicas (mismas que al guardar)
            SolicitudValidator.validar_fechas_cambio_permanente(fecha_inicio, fecha_fin)

            if dias_seleccionados:
                SolicitudValidator.validar_dias_seleccionados_permanente(
                    fecha_inicio, fecha_fin, dias_seleccionados
                )

            # Una sola precarga en lote para las DOS pasadas de abajo (la validación de jornada
            # contraria y la evaluación), que barren el mismo rango y los mismos dos empleados.
            # Sin esto cada una resolvía el rango entero por su cuenta, consulta a consulta.
            with precargar_ct_permanente([solicitante, receptor], fecha_inicio, fecha_fin):
                # Jornada contraria en rango solo si hay receptor
                if receptor:
                    SolicitudValidator.validar_jornada_contraria_rango_permanente(
                        solicitante,
                        receptor,
                        fecha_inicio,
                        fecha_fin,
                        dias_seleccionados if dias_seleccionados else None,
                    )

                # MISMA evaluación que usan la validación y la aplicación: lo que se ve aquí es
                # exactamente lo que se va a aplicar. Antes esta vista repetía la expansión y el
                # filtrado por su cuenta (quinta copia de la misma lógica) y no comprobaba que las
                # jornadas fueran contrarias día a día.
                fechas_aplicables_dt, fechas_excluidas_dt = evaluar_fechas_ct_permanente(
                    fecha_inicio, fecha_fin, solicitante, receptor,
                    dias_seleccionados if dias_seleccionados else None,
                    incluir_fines_semana=True,
                )

            fechas_aplicables = [f.strftime('%Y-%m-%d') for f in fechas_aplicables_dt]
            fechas_excluidas = [
                {'fecha': e['fecha'].strftime('%Y-%m-%d'), 'razon': e['razon']}
                for e in fechas_excluidas_dt
            ]

            if not fechas_aplicables:
                raise ValidationError(
                    'No se encontraron días válidos en el rango seleccionado. '
                    'Todos los días quedan excluidos (fin de semana, festivo, mantenimiento, '
                    'temporada, descanso, día ya comprometido o sin jornada contraria).'
                )

            # Resumen informativo del rango (UX): siempre mostrar fines de semana en el rango
            total_dias_rango = (fecha_fin - fecha_inicio).days + 1
            total_fines_semana_rango = sum(
                1 for n in range((fecha_fin - fecha_inicio).days + 1)
                if (fecha_inicio + timedelta(days=n)).weekday() in (5, 6)
            )

            return json_ok(
                {
                    'success': True,
                    'fechas': {
                        'aplicables': fechas_aplicables,
                        'excluidas': fechas_excluidas,
                        'total_aplicables': len(fechas_aplicables),
                        'total_excluidas': len(fechas_excluidas),
                        'resumen': {
                            'total_dias_rango': total_dias_rango,
                            'fines_de_semana_en_rango': total_fines_semana_rango,
                            'prioridad': (
                                'Mantenimiento > Festivo > Temporada > Doblada/Cambio Previo > '
                                'Descanso Solicitante > Descanso Receptor > Sin jornada contraria > '
                                'Fines de semana'
                            ),
                        },
                    },
                }
            )

        except ValidationError as e:
            return json_ok(
                {
                    'success': False,
                    'message': str(e),
                    'fechas': {
                        'aplicables': [],
                        'excluidas': [],
                        'total_aplicables': 0,
                        'total_excluidas': 0,
                    },
                }
            )
        except Exception as e:  # pragma: no cover
            logger.exception('Error en PrevisualizarCTPermanenteView', extra={'error': str(e)})
            return json_error(
                'Error interno al previsualizar el cambio permanente.',
                status=500,
                code='internal_error',
            )


class PrevisualizarDobladaPermanenteView(LoginRequiredMixin, View):
    """
    Preview de días APLICABLES / OMITIDOS para DOBLADA PERMANENTE (solo lunes-viernes).

    Enfocado en el SOLICITANTE: festivos, mantenimiento, temporada, sus descansos y sus días
    ya comprometidos (doblada/CT/D FDS). Las exclusiones del/los compañero(s) se validan al
    guardar (la doblada permanente admite distinto compañero por día). Misma lógica de exclusión
    que la aplicación, para que el preview coincida con lo que realmente se aplicará.
    """

    def get(self, request):
        import json
        from datetime import datetime, timedelta
        from ..services.ct_permanente_helper import (
            _motivo_no_doblada_perm, precargar_ct_permanente,
        )

        fi_s = request.GET.get('fecha_inicio')
        ff_s = request.GET.get('fecha_fin')
        dias_s = request.GET.get('dias', '')  # csv de weekdays (cesión ∪ devolución)
        dias_comp_json = request.GET.get('dias_companeros', '')  # {"weekday": companero_id}

        if not fi_s or not ff_s:
            return json_error('Faltan fecha_inicio o fecha_fin', status=400, code='missing_params')
        try:
            fi = DateUtils.parse_date(fi_s)
            ff = DateUtils.parse_date(ff_s)
        except ValueError:
            return json_error('Formato de fecha inválido (YYYY-MM-DD)', status=400, code='invalid_date')
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario sin empleado asociado', status=400, code='no_empleado')

        solicitante = request.user.empleado
        try:
            dias_comp = json.loads(dias_comp_json) if dias_comp_json else {}
        except json.JSONDecodeError:
            dias_comp = {}

        dias = {int(x) for x in dias_s.split(',') if x.strip().isdigit() and 0 <= int(x) < 5}
        dias |= {int(k) for k in dias_comp.keys() if str(k).isdigit() and 0 <= int(k) < 5}

        # Se listan las omisiones que dependen del SOLICITANTE según su estado REAL ("Mis Turnos"):
        # ya doblada, festivo, temporada, mantenimiento, fin de semana o descanso. La cobertura por
        # COMPAÑERO (jornadas contrarias) se muestra por fila con sus casillas —un mismo día puede ir
        # con varios compañeros—, así que aquí NO se evalúa el compañero.
        aplicables, excluidas = [], []
        if dias and ff >= fi:
            # Precarga en lote del estado del solicitante en todo el rango: el barrido de abajo
            # lo resolvía día a día (~13 consultas por día).
            with precargar_ct_permanente([solicitante], fi, ff):
                d = fi
                while d <= ff:
                    wd = d.weekday()
                    if wd in dias:
                        razon = _motivo_no_doblada_perm(solicitante, d)
                        if razon:
                            excluidas.append({'fecha': d.strftime('%Y-%m-%d'), 'razon': razon})
                        else:
                            aplicables.append(d.strftime('%Y-%m-%d'))
                    d += timedelta(days=1)

        return json_ok({
            'aplicables': aplicables,
            'excluidas': excluidas,
            'total_aplicables': len(aplicables),
            'total_excluidas': len(excluidas),
        })


class DiasDisponiblesDobladaPermanenteView(LoginRequiredMixin, View):
    """
    Cuenta, por día de la semana (lun=0 … vie=4), cuántas fechas VÁLIDAS hay en el rango para
    el SOLICITANTE (descontando fin de semana, festivo, temporada, mantenimiento y sus descansos
    o días ya comprometidos). Sirve para deshabilitar/anotar los días en el selector del
    formulario, y así no dejar elegir un día que no tiene ocurrencias válidas en el rango.
    """

    def get(self, request):
        import json
        from datetime import datetime, timedelta
        from empleados.models import Empleado
        from ..services.ct_permanente_helper import (
            _jornada_doblada_perm, _motivo_no_cubre_companero,
            bloque_calendario_no_apto, precargar_ct_permanente,
        )

        fi_s = request.GET.get('fecha_inicio')
        ff_s = request.GET.get('fecha_fin')
        if not fi_s or not ff_s:
            return json_error('Faltan fecha_inicio o fecha_fin', status=400, code='missing_params')
        try:
            fi = DateUtils.parse_date(fi_s)
            ff = DateUtils.parse_date(ff_s)
        except ValueError:
            return json_error('Formato de fecha inválido (YYYY-MM-DD)', status=400, code='invalid_date')
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario sin empleado asociado', status=400, code='no_empleado')

        solicitante = request.user.empleado
        # `pares`: lista [{dia, comp}] — un mismo día de la semana PUEDE ir con varios compañeros
        # (para cubrir sus fechas AM con uno y las PM con otro). Se calcula la disponibilidad por
        # PAR (día+compañero). Compat: si viene el formato viejo {"weekday": comp}, se convierte.
        try:
            pares_in = json.loads(request.GET.get('pares', '') or '[]')
        except json.JSONDecodeError:
            pares_in = []
        if not pares_in:
            try:
                dc = json.loads(request.GET.get('dias_companeros', '') or '{}')
                pares_in = [{'dia': k, 'comp': v} for k, v in dc.items() if v]
            except json.JSONDecodeError:
                pares_in = []

        emp_cache = {}
        def _emp(cid):
            if cid not in emp_cache:
                emp_cache[cid] = Empleado.objects.filter(id=cid).first()
            return emp_cache[cid]

        # Pares normalizados: {(weekday:int, comp_id:str): Empleado}
        pares_norm = {}
        for p in (pares_in or []):
            try:
                wd = int(p.get('dia'))
            except (TypeError, ValueError):
                continue
            cid = p.get('comp')
            if 0 <= wd < 5 and cid:
                pares_norm[(wd, str(cid))] = _emp(str(cid))

        def _sol_jornada(d):
            """Jornada real (AM/PM) del solicitante ese día según Mis Turnos; None si no puede doblar
            (doblada, descanso, festivo, etc.). Fin de semana no aplica a la doblada permanente."""
            if d.weekday() >= 5:
                return None
            return _jornada_doblada_perm(solicitante, d)

        # por_dia["wd"]: por cada día de semana, las fechas del SOLICITANTE con SU jornada real
        # {f: fecha, ys: 'AM'/'PM'} — para que el formulario indique, ANTES de elegir compañero, en
        # qué fechas estás AM y en cuáles PM (y así saber si necesitas un compañero PM o AM). El
        # contador del selector usa la longitud. por_par["wd|comp"]: por cada fecha válida del par,
        # {f, ys, yc} (jornada de ambos) — para la mini-tabla.
        #
        # no_cubre["wd|comp"]: las fechas del solicitante que ese compañero NO puede cubrir, con el
        # MOTIVO real ({f, ys, tipo, razon}). Sin esto el formulario tenía que adivinar la causa a
        # partir de la jornada del solicitante y siempre concluía "necesitas un compañero de la
        # jornada contraria" — falso cuando el compañero sí es contrario pero ya está doblado o
        # descansa por otro acuerdo, que es el caso que hacía ilegible la advertencia.
        por_dia = {w: [] for w in range(5)}
        por_par = {f"{wd}|{cid}": [] for (wd, cid) in pares_norm}
        no_cubre = {f"{wd}|{cid}": [] for (wd, cid) in pares_norm}
        if ff >= fi:
            # Precarga en lote del solicitante y de todos los compañeros implicados: este bucle
            # es una matriz empleado×día y sin la precarga cada celda iba a la base de datos.
            with precargar_ct_permanente(
                [solicitante, *pares_norm.values()], fi, ff
            ):
                d = fi
                while d <= ff:
                    js = _sol_jornada(d)
                    if js:
                        w = d.weekday()
                        ds = d.strftime('%Y-%m-%d')
                        por_dia[w].append({'f': ds, 'ys': js})
                        for (wd, cid), comp in pares_norm.items():
                            if wd != w:
                                continue
                            jr = _jornada_doblada_perm(comp, d) if comp else None
                            if jr and jr != js:
                                por_par[f"{wd}|{cid}"].append({'f': ds, 'ys': js, 'yc': jr})
                            else:
                                # Solo aquí se paga el costo de reconstruir el estado del compañero.
                                motivo = _motivo_no_cubre_companero(comp, d, js)
                                no_cubre[f"{wd}|{cid}"].append(
                                    {'f': ds, 'ys': js, 'tipo': motivo['tipo'], 'razon': motivo['razon']}
                                )
                    d += timedelta(days=1)

        # El calendario del formulario deshabilita temporada, festivo y mantenimiento, así que al
        # arrastrar el "Hasta" el rango se corta SOLO, sin decir por qué: el usuario cree haber
        # elegido "hasta diciembre" y en realidad eligió hasta la víspera de la temporada, con la
        # mitad de los días que esperaba. Si el rango termina pegado a un bloque bloqueado, se
        # informa desde dónde y hasta cuándo, para que el formulario lo diga en vez de callarlo.
        # El tramo empieza en `ff + 1`, FUERA del rango precargado, así que se resuelve con su
        # propia consulta única en vez de día a día (ver `bloque_calendario_no_apto`).
        corte = bloque_calendario_no_apto(ff + timedelta(days=1))

        return json_ok({
            'por_dia': por_dia, 'por_par': por_par, 'no_cubre': no_cubre,
            'rango': {
                'inicio': fi.strftime('%Y-%m-%d'),
                'fin': ff.strftime('%Y-%m-%d'),
                'corte': corte,
            },
        })


