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

class ObtenerTurnoExploradorView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        explorador_id = request.GET.get('explorador_id')
        jornada_base = request.GET.get('jornada_base', 'false').lower() == 'true'
        
        if not fecha or not explorador_id:
            return json_error('Faltan parÃ¡metros requeridos', status=400, code='missing_params')
        
        try:
            # Si se solicita jornada base, obtener directamente de AsignarJornadaExplorador
            if jornada_base:
                from turnos.models import AsignarJornadaExplorador
                from datetime import datetime
                from empleados.models import Empleado
                
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
                explorador = Empleado.objects.get(id=explorador_id)
                
                # Obtener jornada base (sin considerar Turnos)
                asignacion_jornada = AsignarJornadaExplorador.objects.select_related('jornada').filter(
                    explorador=explorador,
                    fecha_inicio__lte=fecha_obj
                ).order_by('-fecha_inicio').first()
                
                if asignacion_jornada and asignacion_jornada.jornada:
                    jornada = asignacion_jornada.jornada
                    # Obtener salas de competencia
                    from turnos.models import CompetenciaEmpleado
                    competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
                    salas_competencia = [
                        {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
                    ]
                    
                    turno_dict = {
                        'id': None,
                        'jornada': jornada.nombre,
                        'sala': None,
                        'sala_id': None,
                        'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada.hora_inicio else None,
                        'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada.hora_fin else None,
                        'es_turno_virtual': True,
                        'tipo_sala': 'competencia',
                        'salas_competencia': salas_competencia,
                        'es_jornada_base': True
                    }
                    return json_ok({'turno': turno_dict, 'tiene_turno': True})
                else:
                    return json_ok({'turno': None, 'tiene_turno': False})
            
            # Obtener el tipo de solicitud desde la URL o parÃ¡metros
            tipo_solicitud_id = request.GET.get('tipo_solicitud_id')
            tipo_solicitud = None
            
            if tipo_solicitud_id:
                try:
                    tipo_solicitud = TipoSolicitudCambio.objects.get(id=tipo_solicitud_id)
                except TipoSolicitudCambio.DoesNotExist:
                    pass
            
            # Obtener el turno del explorador usando el Factory
            if tipo_solicitud:
                turno_dict = SolicitudFactory.get_turno_explorador(tipo_solicitud, explorador_id, fecha)
            else:
                # Fallback al servicio original si no hay tipo
                turno_service = get_turno_service()
                turno_dict = turno_service.get_turno_explorador(explorador_id, fecha)
            
            # CORRECCIÓN: Detectar si el explorador tiene doblada (AM + PM) en esta fecha
            # IMPORTANTE: Solo es doblada si hay TURNOS ASIGNADOS (AM+PM), no solo jornada predeterminada
            from turnos.models import Turno
            from datetime import datetime
            
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            turnos_en_fecha = Turno.objects.filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            ).select_related('jornada')
            
            # Normalizar a mayúsculas: en BD a veces viene distinto y fallaba 'AM' in turnos_list
            turnos_list = [t.jornada.nombre.upper() for t in turnos_en_fecha if t.jornada]
            # Doblada real: al menos dos turnos en la fecha y una jornada AM y otra PM
            es_doblada = len(turnos_en_fecha) >= 2 and 'AM' in turnos_list and 'PM' in turnos_list

            # Misma señal que TurnoService.get_turno_explorador (tarjeta de horario / jornada DOBLADA)
            if turno_dict:
                svc_doblada = (
                    turno_dict.get('jornada') == 'DOBLADA'
                    or turno_dict.get('es_doblada')
                    or turno_dict.get('es_doblada_sabado')
                )
                if svc_doblada:
                    es_doblada = True
                    if 'AM' not in turnos_list or 'PM' not in turnos_list:
                        turnos_list = ['AM', 'PM']
            
            # Verificar si es fin de semana y corresponde trabajar (día completo). Usa el
            # grupo EFECTIVO: override manual del supervisor si existe; si no, alternancia.
            es_fin_semana_doblada_predeterminada = False
            if fecha_obj.weekday() in (5, 6):
                from turnos.services.asignacion_especial_service import AsignacionEspecialService
                grupo_finde = AsignacionEspecialService.grupo_trabaja_efectivo(fecha_obj)
                if grupo_finde:
                    from turnos.services.jornada_service import JornadaService
                    jornada_predeterminada = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
                    if jornada_predeterminada and jornada_predeterminada.nombre.upper() == grupo_finde.upper():
                        # En fin de semana, quien trabaja lo hace el día completo (DOBLADA)
                        es_fin_semana_doblada_predeterminada = True
            
            # Detectar caso especial: está descansando por una doblada aprobada (no hay turnos en BD)
            esta_descansando = False
            descanso_info = None
            # Detectar descanso por DOBLADA para cualquier tipo de solicitud (CT, CT permanente, DOBLADA, etc.)
            # Solo aplicamos esta lógica cuando NO hay turnos reales en BD para esa fecha.
            if not turnos_en_fecha:
                from solicitudes.models import SolicitudCambio
                
                # Caso 1: Es SOLICITANTE y cede su jornada en esta fecha (cesión)
                doblada_como_solicitante = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_solicitante_id=explorador_id,
                        tipo_cambio__nombre='DOBLADA',
                        fecha_cambio_turno=fecha_obj,
                        estado='aprobada'
                    )
                    .select_related('doblada', 'explorador_receptor')
                    .first()
                )
                
                # Caso 2: Es RECEPTOR y descansa en fecha de pago de una doblada
                doblada_como_receptor = (
                    SolicitudCambio.objects
                    .filter(
                        explorador_receptor_id=explorador_id,
                        tipo_cambio__nombre='DOBLADA',
                        estado='aprobada',
                        doblada__fecha_pago=fecha_obj
                    )
                    .select_related('doblada', 'explorador_solicitante')
                    .first()
                )
                
                if doblada_como_solicitante or doblada_como_receptor:
                    esta_descansando = True
                    
                    if doblada_como_solicitante:
                        sol = doblada_como_solicitante
                        rol_descanso = 'cedio'
                        companero = sol.explorador_receptor
                    else:
                        sol = doblada_como_receptor
                        rol_descanso = 'pago'
                        companero = sol.explorador_solicitante
                    
                    detalle = getattr(sol, 'doblada', None)
                    fecha_cesion_str = (
                        sol.fecha_cambio_turno.strftime('%d/%m/%Y')
                        if sol.fecha_cambio_turno else None
                    )
                    fecha_pago_str = (
                        detalle.fecha_pago.strftime('%d/%m/%Y')
                        if detalle and detalle.fecha_pago else None
                    )
                    
                    descanso_info = {
                        'tipo': rol_descanso,  # 'cedio' o 'pago'
                        'companero_nombre': f"{companero.nombre} {getattr(companero, 'apellido', '')}".strip(),
                        'companero_id': companero.id,
                        'solicitud_id': sol.id,
                        'fecha_cesion': fecha_cesion_str,
                        'fecha_pago': fecha_pago_str,
                    }
                    
                    # Si está descansando por doblada, no queremos mostrar jornada base
                    turno_dict = None
                    turnos_list = []

                # Otros descansos por solicitud APROBADA: D FDS, CAMBIO DESCANSO y
                # DOBLADA PERMANENTE (el bloque de arriba solo cubre DOBLADA). Usa la fuente
                # de verdad única para que el display coincida con "Mis Turnos".
                if not esta_descansando:
                    from turnos.services.turno_service import TurnoService as _TSv
                    from empleados.models import Empleado as _Emp
                    _emp_obj = _Emp.objects.filter(id=explorador_id).first()
                    _comp = _TSv.dia_comprometido_por_solicitud(_emp_obj, fecha_obj) if _emp_obj else None
                    if _comp:
                        esta_descansando = True
                        _c = _comp.get('companero') or {}
                        descanso_info = {
                            'tipo': 'cedio',
                            'companero_nombre': _c.get('nombre'),
                            'companero_id': _c.get('id'),
                            'motivo': _comp.get('motivo'),
                        }
                        turno_dict = None
                        turnos_list = []

                # Descanso de ENTRE SEMANA (manual de temporada/festivo o lunes de mantenimiento).
                # Debe verse igual que en Mis Turnos: es un descanso, no la jornada predeterminada.
                if not esta_descansando and fecha_obj.weekday() < 5:
                    from turnos.services.descanso_semana_service import DescansoSemanaService
                    from turnos.models import DiaEspecial as _DE
                    from turnos.services.jornada_service import JornadaService as _JS
                    _pred = _JS.get_jornada_explorador_fecha(explorador_id, fecha)
                    _jb = _pred.nombre.upper() if _pred else None
                    _motivo_ds = None
                    if DescansoSemanaService.es_descanso_semana_manual(_jb, fecha_obj):
                        _motivo_ds = 'temporada'
                    elif _DE.es_mantenimiento_efectivo(fecha_obj):
                        _motivo_ds = 'mantenimiento'
                    if _motivo_ds:
                        esta_descansando = True
                        descanso_info = {'tipo': 'descanso_semana', 'motivo': _motivo_ds}
                        turno_dict = None
                        turnos_list = []

            # Regla adicional para festivos de lunes a viernes:
            # - Solo mostrar DOBLADA (AM+PM) si en BD tiene realmente ambos turnos.
            #   Si ya hizo cesión parcial y solo tiene una jornada, mostrar esa jornada, no doblada.
            # - Si NO es el grupo que dobla y la solicitud es de DOBLADA → tratar como día de descanso.
            if not es_doblada and not es_fin_semana_doblada_predeterminada:
                try:
                    from solicitudes.services.solicitud_validator import SolicitudValidator
                    from turnos.services.festivos_rotacion_service import FestivosRotacionService

                    es_festivo_semana = SolicitudValidator.es_festivo_semana(fecha_obj)
                    if es_festivo_semana:
                        # Grupo EFECTIVO del festivo: override manual si existe; si no, rotación.
                        from turnos.services.asignacion_especial_service import AsignacionEspecialService as _AES
                        grupo_que_dobla = (_AES.get_grupo_trabaja(fecha_obj)
                                           or FestivosRotacionService.get_grupo_que_dobla_en_festivo(fecha_obj))
                        jornada_turno = (turno_dict.get('jornada') or '').upper() if turno_dict else None
                        if not jornada_turno and not turnos_list:
                            from turnos.services.jornada_service import JornadaService
                            pred = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
                            jornada_turno = pred.nombre.upper() if pred else None
                        tiene_doblada_real_bd = set(turnos_list) == {'AM', 'PM'}
                        # Festivo sin modificaciones (0 turnos): mostrar DOBLADA por regla si el grupo trabaja
                        if not turnos_list and jornada_turno and jornada_turno == grupo_que_dobla.upper():
                            es_doblada = True
                            turnos_list = ['AM', 'PM']
                        elif tiene_doblada_real_bd and turno_dict and jornada_turno and jornada_turno == grupo_que_dobla.upper():
                            es_doblada = True
                            turnos_list = ['AM', 'PM']
                        elif not tiene_doblada_real_bd and jornada_turno and jornada_turno != grupo_que_dobla.upper():
                            # Festivo donde el solicitante NO es del grupo que dobla → DESCANSA por
                            # rotación. Aplica a CUALQUIER tipo de solicitud (igual que "Mis Turnos");
                            # antes solo se contemplaba para DOBLADA y el Cambio de Turno mostraba la
                            # jornada base por error.
                            turno_dict = None
                            turnos_list = []
                            esta_descansando = True
                            if not descanso_info:
                                descanso_info = {'tipo': 'descanso_semana', 'motivo': 'festivo'}
                except Exception:
                    pass

            # Si el día quedó como DOBLADA (festivo del grupo que dobla o doblada real), la
            # jornada mostrada debe ser 'DOBLADA' (no la base), igual que estado_dia / Mis Turnos.
            if es_doblada and turno_dict and turno_dict.get('jornada') != 'DOBLADA':
                turno_dict['jornada'] = 'DOBLADA'

            # Solo convertir DOBLADA a jornada simple si:
            # 1. NO es doblada real (no hay turnos AM+PM en BD)
            # 2. Y NO es sábado/domingo con doblada predeterminada (porque para fines de semana la predeterminada ES doblada)
            if turno_dict and turno_dict.get('jornada') == 'DOBLADA' and not es_doblada and not es_fin_semana_doblada_predeterminada:
                # Es jornada predeterminada de un día de semana, no doblada real
                # Obtener jornada real del día
                from turnos.services.jornada_service import JornadaService
                jornada_real = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
                if jornada_real:
                    turno_dict['jornada'] = jornada_real.nombre
                    # Ajustar horario según jornada real
                    if jornada_real.hora_inicio and jornada_real.hora_fin:
                        turno_dict['hora_inicio'] = jornada_real.hora_inicio.strftime('%H:%M')
                        turno_dict['hora_fin'] = jornada_real.hora_fin.strftime('%H:%M')
            response_data = {
                'turno': turno_dict,
                'tiene_turno': turno_dict is not None,
                'es_doblada': es_doblada,
                'jornadas': turnos_list if turnos_list else ([turno_dict['jornada']] if turno_dict and 'jornada' in turno_dict and turno_dict['jornada'] != 'DOBLADA' else []),
                'esta_descansando': esta_descansando,
                'descanso_info': descanso_info,
            }
            
            # Si la fecha es sábado, incluir qué jornada trabaja ese sábado (grupo EFECTIVO:
            # override manual o alternancia) — para doblada: ocultar selector si ya le corresponde.
            if fecha_obj.weekday() == 5:
                from turnos.services.asignacion_especial_service import AsignacionEspecialService as _AES2
                from turnos.models import AsignarJornadaExplorador as _AJE2
                _grupo_trabaja_sab = _AES2.grupo_trabaja_efectivo(fecha_obj)
                response_data['jornada_trabaja_sabado'] = _grupo_trabaja_sab
                # ¿Al empleado le corresponde trabajar ese sábado por su GRUPO (alternancia)?
                # Debe basarse en su jornada BASE (AsignarJornadaExplorador), NO en el turno del día
                # (que otra doblada pudo alterar y coincidir con el grupo que trabaja → falso positivo).
                # Si su grupo trabaja → la doblada se devuelve en su jornada habitual (sin elegir);
                # si su grupo descansa → viene especialmente (elige jornada).
                _asig_sab = (_AJE2.objects.filter(explorador_id=explorador_id, fecha_inicio__lte=fecha_obj)
                             .select_related('jornada').order_by('-fecha_inicio').first())
                _jb_sab_nombre = _asig_sab.jornada.nombre.upper() if _asig_sab else None
                response_data['corresponde_trabajar_sabado'] = bool(
                    _grupo_trabaja_sab and _jb_sab_nombre and _jb_sab_nombre == str(_grupo_trabaja_sab).upper()
                )
            
            return json_ok(response_data)
        except Exception as e:
            logger.exception('Error en ObtenerTurnoExploradorView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')


class VerificarCoincidenciaJornadasView(LoginRequiredMixin, View):
    """
    Endpoint para validar en tiempo real si hay coincidencia de jornadas en fecha de pago.
    Útil para DOBLADA para verificar el caso crítico antes de enviar la solicitud.
    
    Parámetros:
    - deudor_id: ID del explorador deudor (solicitante)
    - acreedor_id: ID del explorador acreedor (receptor)
    - fecha_pago: Fecha de pago en formato YYYY-MM-DD
    """
    def get(self, request):
        deudor_id = request.GET.get('deudor_id')
        acreedor_id = request.GET.get('acreedor_id')
        fecha_pago = request.GET.get('fecha_pago')
        
        if not all([deudor_id, acreedor_id, fecha_pago]):
            return json_error('Faltan parámetros requeridos (deudor_id, acreedor_id, fecha_pago)', 
                            status=400, code='missing_params')
        
        try:
            from empleados.models import Empleado
            from solicitudes.services.solicitud_validator import SolicitudValidator
            
            deudor = Empleado.objects.get(id=deudor_id)
            acreedor = Empleado.objects.get(id=acreedor_id)
            
            # Validar coincidencia de jornadas
            resultado = SolicitudValidator.validar_coincidencia_jornadas_pago(
                deudor,
                acreedor,
                fecha_pago
            )
            
            # Construir respuesta
            respuesta = {
                'coinciden': resultado['coinciden'],
                'jornada_comun': resultado.get('jornada_comun'),
                'requiere_cambio_turno': resultado.get('requiere_cambio_turno', False)
            }
            
            # Agregar mensaje explicativo
            if resultado['requiere_cambio_turno']:
                respuesta['mensaje'] = (
                    f"No se puede pagar trabajando dos veces la misma jornada ({resultado.get('jornada_comun', '')}). "
                    "Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago."
                )
                respuesta['url_redireccion'] = f'/solicitudes/cambio-turno/solicitar/?tipo_id=1&fecha_solicitud={fecha_pago}'
            elif resultado['coinciden']:
                respuesta['mensaje'] = f"Ambos exploradores tienen la misma jornada ({resultado.get('jornada_comun', '')}) en la fecha de pago."
            else:
                respuesta['mensaje'] = 'Las jornadas son contrarias. Puedes proceder con la doblada.'
            
            return json_ok(respuesta)
            
        except Empleado.DoesNotExist:
            return json_error('Empleado no encontrado', status=404, code='empleado_not_found')
        except Exception as e:
            logger.exception('Error en VerificarCoincidenciaJornadasView')
            return json_error('Error al procesar la solicitud', status=500, code='internal_error')


class ObtenerJornadasRangoView(LoginRequiredMixin, View):
    """
    Endpoint para obtener jornadas día a día de un explorador en un rango de fechas.
    Útil para CT PERMANENTE para mostrar desglose de jornadas en el rango.
    """
    def get(self, request):
        explorador_id = request.GET.get('explorador_id')
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        dias_seleccionados_json = request.GET.get('dias_seleccionados', '{}')
        
        if not all([explorador_id, fecha_inicio, fecha_fin]):
            return json_error('Faltan parámetros requeridos (explorador_id, fecha_inicio, fecha_fin)', 
                            status=400, code='missing_params')
        
        try:
            from datetime import datetime, date, timedelta
            from turnos.services.jornada_service import JornadaService
            import json
            
            fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            
            # Parsear días seleccionados
            try:
                dias_seleccionados = json.loads(dias_seleccionados_json) if dias_seleccionados_json else {}
            except json.JSONDecodeError:
                dias_seleccionados = {}
            
            # Generar fechas válidas del rango (similar a CTPermanenteStrategy)
            fechas_validas = []
            dias_semana_list = dias_seleccionados.get('dias_semana', [])
            
            if dias_semana_list:
                # Solo días de semana seleccionados
                fecha_actual = fecha_inicio_obj
                while fecha_actual <= fecha_fin_obj:
                    # weekday(): 0=lunes, 6=domingo
                    dia_semana = fecha_actual.weekday()
                    # Convertir a formato del backend (0=lunes, 4=viernes)
                    if dia_semana < 5 and dia_semana in dias_semana_list:  # Solo lunes-viernes
                        fechas_validas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
            else:
                # Todos los días hábiles del rango
                fecha_actual = fecha_inicio_obj
                while fecha_actual <= fecha_fin_obj:
                    if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                        fechas_validas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
            
            # Obtener jornada para cada fecha
            from django.utils import formats
            dias_semana_es = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
            
            from turnos.models import Turno, Jornada
            from turnos.services.turno_service import TurnoService as _TSrango
            from empleados.models import Empleado as _EmpRango
            from solicitudes.services.ct_permanente_helper import (
                _es_festivo, _es_mantenimiento, _es_temporada,
            )
            _emp_rango = _EmpRango.objects.filter(id=explorador_id).first()
            jornadas_por_dia = []
            for fecha_obj in fechas_validas:
                dia_semana_num = fecha_obj.weekday()
                # Reflejar el estado REAL del día, coherente con lo que se aplicará en el CT
                # permanente. Prioridad (igual que la exclusión real):
                #   Doblada (turno real) > Comprometido por solicitud > Mantenimiento >
                #   Festivo > Temporada > jornada AM/PM (real del día).
                turnos_dia = list(
                    Turno.objects.filter(explorador_id=explorador_id, fecha=fecha_obj)
                    .select_related('jornada')
                )
                if len(turnos_dia) >= 2:
                    jornada_nombre, jornada_id = 'DOBLADA', None
                elif _emp_rango and _TSrango.dia_comprometido_por_solicitud(_emp_rango, fecha_obj):
                    # Día ya cedido/comprometido en otra solicitud aprobada (L2): no aplica.
                    jornada_nombre, jornada_id = 'COMPROMETIDO', None
                elif _es_mantenimiento(fecha_obj):
                    jornada_nombre, jornada_id = 'MANTENIMIENTO', None
                elif _es_festivo(fecha_obj):
                    jornada_nombre, jornada_id = 'FESTIVO', None
                elif _es_temporada(fecha_obj):
                    jornada_nombre, jornada_id = 'TEMPORADA', None
                elif len(turnos_dia) == 1 and turnos_dia[0].jornada:
                    # Turno real único: la jornada REAL de ese día (no la predeterminada)
                    jornada_nombre = turnos_dia[0].jornada.nombre
                    jornada_id = turnos_dia[0].jornada.id
                elif _emp_rango:
                    # FUENTE DE VERDAD (estado_dia): igual que Mis Turnos. Cubre descanso de
                    # temporada por DescansoSemanaManual, día completo (grupo contrario
                    # descansa), festivos por rotación/override y demás capas.
                    _est = _TSrango.estado_dia(_emp_rango, fecha_obj)
                    if not _est['trabaja']:
                        _map_fuente = {'temporada': 'TEMPORADA', 'mantenimiento': 'MANTENIMIENTO',
                                       'festivo': 'FESTIVO', 'solicitud': 'COMPROMETIDO'}
                        jornada_nombre = _map_fuente.get(_est['fuente'], 'DESCANSO')
                        jornada_id = None
                    elif _est['jornada'] == 'DOBLADA':
                        jornada_nombre, jornada_id = 'DOBLADA', None
                    else:
                        _j_obj = Jornada.objects.filter(nombre__iexact=_est['jornada']).first() if _est['jornada'] else None
                        jornada_nombre = _j_obj.nombre if _j_obj else _est['jornada']
                        jornada_id = _j_obj.id if _j_obj else None
                else:
                    jornada = JornadaService.get_jornada_explorador_fecha(explorador_id, fecha_obj)
                    jornada_nombre = jornada.nombre if jornada else None
                    jornada_id = jornada.id if jornada else None
                jornadas_por_dia.append({
                    'fecha': fecha_obj.strftime('%Y-%m-%d'),
                    'fecha_formateada': fecha_obj.strftime('%d/%m/%Y'),
                    'dia_semana': dias_semana_es[dia_semana_num] if dia_semana_num < len(dias_semana_es) else fecha_obj.strftime('%A'),
                    'jornada': jornada_nombre,
                    'jornada_id': jornada_id
                })

            # Etiquetas que NO son una jornada aplicable (el día queda excluido del cambio)
            _NO_APLICAN = {'DOBLADA', 'MANTENIMIENTO', 'FESTIVO', 'TEMPORADA', 'COMPROMETIDO', 'DESCANSO'}
            # Calcular resumen
            resumen = {
                'total_dias': len(jornadas_por_dia),
                'dias_am': len([j for j in jornadas_por_dia if j['jornada'] == 'AM']),
                'dias_pm': len([j for j in jornadas_por_dia if j['jornada'] == 'PM']),
                'dias_doblada': len([j for j in jornadas_por_dia if j['jornada'] == 'DOBLADA']),
                'dias_mantenimiento': len([j for j in jornadas_por_dia if j['jornada'] == 'MANTENIMIENTO']),
                'dias_festivo': len([j for j in jornadas_por_dia if j['jornada'] == 'FESTIVO']),
                'dias_temporada': len([j for j in jornadas_por_dia if j['jornada'] == 'TEMPORADA']),
                'dias_no_aplican': len([j for j in jornadas_por_dia if j['jornada'] in _NO_APLICAN]),
                'dias_sin_jornada': len([j for j in jornadas_por_dia if j['jornada'] is None])
            }
            
            return json_ok({
                'jornadas': jornadas_por_dia,
                'resumen': resumen
            })
            
        except Exception as e:
            logger.exception('Error en ObtenerJornadasRangoView')
            return json_error(f'Error al procesar la solicitud: {str(e)}', status=500, code='internal_error')


class ObtenerCambioAprobadoView(LoginRequiredMixin, View):
    """
    FASE 2.5: Endpoint para verificar si el usuario ya tiene un cambio aprobado para una fecha.
    Devuelve informaciÃ³n sobre la solicitud que creÃ³ el turno si existe.
    """
    def get(self, request):
        fecha = request.GET.get('fecha')
        
        if not fecha:
            return json_error('Falta el parÃ¡metro fecha', status=400, code='missing_fecha')
        
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=400, code='no_empleado')
        
        try:
            from datetime import datetime
            from django.db.models import Q
            from turnos.models import Turno
            
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            empleado = request.user.empleado
            
            # Buscar si existe un Turno para este empleado y fecha
            turno = Turno.objects.filter(
                explorador=empleado,
                fecha=fecha_obj
            ).first()
            
            if not turno:
                return json_ok({
                    'tiene_cambio_aprobado': False,
                    'mensaje': None,
                    'informacion_cambio': None
                })
            
            # Si existe turno, buscar la solicitud que lo creÃ³
            solicitud = SolicitudCambio.objects.filter(
                Q(turno_origen=turno) | Q(turno_destino=turno),
                estado='aprobada'
            ).order_by('-fecha_resolucion').select_related(
                'explorador_solicitante',
                'explorador_receptor'
            ).first()
            
            if solicitud:
                # Determinar si el empleado es el solicitante o receptor
                es_solicitante = solicitud.explorador_solicitante.id == empleado.id
                companero = solicitud.explorador_receptor if es_solicitante else solicitud.explorador_solicitante
                
                informacion_cambio = {
                    'solicitud_id': solicitud.id,
                    'jornada_actual': turno.jornada.nombre if turno.jornada else 'N/A',
                    'companero_nombre': f"{companero.nombre} {companero.apellido}",
                    'fecha_aprobacion': DateUtils.format_datetime_display(solicitud.fecha_resolucion) or 'N/A',
                    'es_solicitante': es_solicitante
                }
                
                mensaje = (
                    f"Ya tienes un cambio aprobado para esta fecha. "
                    f"Tu jornada actual es {turno.jornada.nombre} (intercambio con {companero.nombre} {companero.apellido}). "
                    f"Este nuevo cambio lo reemplazarÃ¡."
                )
                
                return json_ok({
                    'tiene_cambio_aprobado': True,
                    'mensaje': mensaje,
                    'informacion_cambio': informacion_cambio
                })
            else:
                # Hay turno pero no se encontrÃ³ la solicitud (caso raro)
                return json_ok({
                    'tiene_cambio_aprobado': True,
                    'mensaje': f"Ya tienes un turno asignado para esta fecha (jornada: {turno.jornada.nombre if turno.jornada else 'N/A'}). Este nuevo cambio lo reemplazarÃ¡.",
                    'informacion_cambio': {
                        'jornada_actual': turno.jornada.nombre if turno.jornada else 'N/A',
                        'solicitud_id': None
                    }
                })
                
        except Exception as e:
            logger.exception('Error en ObtenerCambioAprobadoView')
            return json_error('Error al verificar cambio aprobado', status=500, code='internal_error')


