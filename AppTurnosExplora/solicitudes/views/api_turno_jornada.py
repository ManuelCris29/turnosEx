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
                response_data['jornada_trabaja_sabado'] = _AES2.grupo_trabaja_efectivo(fecha_obj)
            
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
                    'fecha_aprobacion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else 'N/A',
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


class DobladasSemanaView(LoginRequiredMixin, View):
    """
    Dobladas reales (Turno AM+PM, lun-vie) de la semana de la fecha dada, de OTROS
    empleados. Alimenta el sub-flujo "cambio de doblada" del Cambio de Día de
    Descanso entre semana: el solicitante elige cuál doblada de la semana tomar.
    """
    def get(self, request):
        from datetime import datetime as _dt, timedelta as _td
        from collections import defaultdict
        from turnos.models import Turno

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

        dobladas = [
            {'empleado_id': emp_id, 'nombre': nombres[emp_id], 'fecha': f.isoformat()}
            for (emp_id, f), js in sorted(pares.items(), key=lambda kv: (kv[0][1], nombres[kv[0][0]]))
            if {'AM', 'PM'} <= js
        ]
        return json_ok({'dobladas': dobladas})


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

            # Días COMPROMETIDOS: turno creado por otra solicitud aprobada.
            # Regla diferenciada:
            #   - CAMBIO DESCANSO < 30 min → sigue bloqueado (aún cancelable, si se reemplaza se pierden datos)
            #   - CAMBIO DESCANSO >= 30 min → ya NO es cancelable; se puede reemplazar con nuevo cambio
            #   - Cualquier otro tipo (DOBLADA, D FDS, CT…) → siempre bloqueado
            from django.utils import timezone as _tz
            from datetime import timedelta as _tdt
            from django.db.models import Q as _Q
            from solicitudes.models import SolicitudCambio as _SC
            from solicitudes.repositories.turno_repository import TurnoRepository
            from solicitudes.repositories.solicitud_repository import SolicitudRepository

            VENTANA_CANCELACION = _tdt(minutes=30)
            ahora = _tz.now()

            # Fechas con turno de CUALQUIER tipo_cambio (via Repository)
            all_comp_qs = TurnoRepository.comprometidos_por_tipo_cambio(emp, anio, mes)
            comprometidos_fijos = set()      # DOBLADA, D FDS, CT, etc. → siempre bloqueados
            comprometidos_cd = set()          # CAMBIO DESCANSO → solo si < 30 min

            for fecha_tc, tipo_tc in all_comp_qs:
                if tipo_tc == 'CAMBIO DESCANSO':
                    comprometidos_cd.add(fecha_tc)
                else:
                    comprometidos_fijos.add(fecha_tc)

            # De los CAMBIO DESCANSO, solo bloquear los que aún están en ventana de cancelación
            cancelables_cd = set()
            if comprometidos_cd:
                from datetime import timedelta as _td2
                qs_recientes = _SC.objects.filter(
                    tipo_cambio__nombre='CAMBIO DESCANSO',
                    estado='aprobada',
                    fecha_resolucion__gte=ahora - VENTANA_CANCELACION,
                ).filter(
                    _Q(explorador_solicitante=emp) | _Q(explorador_receptor=emp)
                ).select_related('doblada')

                def _otro(f):
                    return f + _tdt(days=1) if f.weekday() == 5 else f - _tdt(days=1)

                for s in qs_recientes:
                    det = getattr(s, 'doblada', None)
                    if not det:
                        continue
                    from datetime import datetime as _dt
                    fc = s.fecha_cambio_turno if isinstance(s.fecha_cambio_turno, _date) else _date.fromisoformat(str(s.fecha_cambio_turno))
                    fp_raw = det.fecha_pago
                    fp = fp_raw if isinstance(fp_raw, _date) else _date.fromisoformat(str(fp_raw))
                    es_sol = s.explorador_solicitante_id == emp.id
                    if es_sol:
                        cancelables_cd.add(_otro(fc))
                        cancelables_cd.add(_otro(fp))
                    else:
                        cancelables_cd.add(fc)
                        cancelables_cd.add(fp)

            comprometidos = comprometidos_fijos | (comprometidos_cd & cancelables_cd)

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
                # Si el día que trabaja está comprometido en otra solicitud, NO es seleccionable.
                dia_comprometido = (
                    (dia_trabajo == 'sabado' and sabado in comprometidos)
                    or (dia_trabajo == 'domingo' and domingo in comprometidos)
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
