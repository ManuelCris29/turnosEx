from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from django.db.models import Q
# Cache ahora se usa a través de CacheService (importado donde se necesita)
from turnos.models import Turno, AsignarJornadaExplorador, DiaEspecial
from turnos.services.turno_service import TurnoService
from turnos.services.temporada_service import TemporadaService
from datetime import datetime, timedelta, date


class TurnosPorDiaView(LoginRequiredMixin, View):
    def get(self, request):
        try:
            fecha = request.GET.get('fecha')
            if not fecha:
                return JsonResponse({'error': 'Debe seleccionar una fecha'}, status=400)
            data = TurnoService.get_exploradores_por_jornada(fecha)
            # Los datos ya vienen como diccionarios desde el servicio
            # Solo necesitamos retornarlos directamente
            return JsonResponse({'am': data.get('am', []), 'pm': data.get('pm', [])})
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Error en TurnosPorDiaView: {str(e)}', exc_info=True)
            return JsonResponse({'error': f'Error al obtener turnos: {str(e)}'}, status=500)


class TurnosPorMesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        if not fecha_inicio or not fecha_fin:
            return JsonResponse({'error': 'Debe enviar fecha_inicio y fecha_fin'}, status=400)
        data = TurnoService.get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin)
        # Serializar empleados (ya son dicts)
        serializado = {}
        for dia, grupos in data.items():
            serializado[dia] = {
                'am': grupos['am'],
                'pm': grupos['pm'],
            }
        return JsonResponse(serializado)


class MisTurnosPorMesView(LoginRequiredMixin, View):
    """Vista para obtener jornadas de un mes específico (cálculo dinámico)
    FASE 3.5: Optimizada con caché para mejorar rendimiento
    """
    
    def get(self, request):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({'error': 'Usuario no es empleado'}, status=400)
        
        empleado = request.user.empleado
        mes = request.GET.get('mes')  # formato: '08' o '8'
        anio = request.GET.get('anio')  # formato: '2025'
        
        if not mes or not anio:
            return JsonResponse({'error': 'Debe enviar mes y anio'}, status=400)
        
        # Validación y normalización de mes/año
        try:
            mes_int = int(mes)
            anio_int = int(anio)
            if not (1 <= mes_int <= 12):
                return JsonResponse({'error': 'Mes invalido'}, status=400)
            # Normalizar representaciones
            mes = f"{mes_int:02d}"
            anio = str(anio_int)
        except ValueError:
            return JsonResponse({'error': 'anio/mes deben ser numéricos'}, status=400)
        
        # FASE 3.5: Generar clave de caché única para este empleado y mes (normalizados)
        from core.services.cache_service import CacheService
        
        cache_key = f'turnos_mes_{empleado.id}_{anio}_{mes}'
        
        # FASE 3.5: Intentar obtener datos del caché
        cached_data = CacheService.get(cache_key)
        if cached_data is not None:
            return JsonResponse(cached_data)
        
        try:
            # Calcular inicio y fin del mes solicitado
            fecha_inicio = datetime.strptime(f"{anio}-{mes}-01", "%Y-%m-%d").date()
            if int(mes) == 12:
                fecha_fin = datetime.strptime(f"{int(anio)+1}-01-01", "%Y-%m-%d").date() - timedelta(days=1)
            else:
                fecha_fin = datetime.strptime(f"{anio}-{int(mes)+1:02d}-01", "%Y-%m-%d").date() - timedelta(days=1)
            
            # Obtener turnos del mes solicitado (optimizado, evitando N+1)
            turnos_mes = (
                Turno.objects
                .filter(explorador=empleado, fecha__gte=fecha_inicio, fecha__lte=fecha_fin)
                .select_related('jornada', 'sala')
                .order_by('fecha', 'jornada__nombre')
            )
            
            # CORRECCIÓN: Agrupar turnos por fecha para manejar dobladas (AM+PM)
            # En lugar de sobrescribir, crear listas de turnos por fecha
            turnos_por_fecha = {}
            for t in turnos_mes:
                if t.fecha not in turnos_por_fecha:
                    turnos_por_fecha[t.fecha] = []
                turnos_por_fecha[t.fecha].append(t)
            
            # FASE 3.2: Obtener jornada predeterminada (usar first() en lugar de get() para evitar errores)
            # Obtener la jornada más reciente por fecha_inicio
            jornada_predeterminada = (
                AsignarJornadaExplorador.objects
                .filter(explorador=empleado)
                .select_related('jornada')
                .order_by('-fecha_inicio')
                .first()
            )
            jornada_base = (jornada_predeterminada.jornada.nombre if jornada_predeterminada else None)
            
            # Validar que el empleado tenga jornada asignada
            if not jornada_base:
                return JsonResponse({
                    'error': f'El empleado {empleado.nombre} {empleado.apellido} no tiene jornada asignada. '
                             'Todos los exploradores deben tener una jornada (AM o PM) asignada.'
                }, status=400)

            from core.utils.jornada_utils import JornadaUtils
            def calcular_jornada_dia(j_base, fecha):
                return JornadaUtils.calcular_jornada_dia(j_base, fecha)

            # FUENTE DE VERDAD ÚNICA (batch): estado predeterminado/calculado por día
            # (alternancia de finde, temporada, mantenimiento, base). Reemplaza la lógica
            # de capas duplicada que antes vivía en este bucle. Ver
            # docs/AUDITORIA_FUENTE_VERDAD_TURNOS.md
            from turnos.services.turno_service import TurnoService as _TSestado
            estados_mes = _TSestado.estado_mes(empleado, int(anio), int(mes))
            
            # La sala es informativa (especialidad del explorador vía CompetenciaEmpleado);
            # ya no existe asignación de sala por período.
            asignaciones_activas = None

            # OPTIMIZACIÓN: Precargar dobladas donde el empleado descansa (solicitante o receptor)
            # Evita 2 consultas por cada día sin turnos
            from solicitudes.models import SolicitudCambio
            # Incluye DOBLADA y D FDS: en ambas el solicitante descansa en fecha de
            # cesión y el receptor descansa en fecha de pago (D FDS reutiliza DobladaDetalle).
            solicitudes_descanso_solicitante = {
                s.fecha_cambio_turno: s
                for s in SolicitudCambio.objects.filter(
                    explorador_solicitante=empleado,
                    tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                    fecha_cambio_turno__gte=fecha_inicio,
                    fecha_cambio_turno__lte=fecha_fin,
                    estado='aprobada'
                ).select_related('explorador_receptor', 'doblada')
            }
            solicitudes_descanso_receptor = {}
            for s in SolicitudCambio.objects.filter(
                explorador_receptor=empleado,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                estado='aprobada',
                doblada__fecha_pago__gte=fecha_inicio,
                doblada__fecha_pago__lte=fecha_fin
            ).select_related('explorador_solicitante', 'doblada'):
                fp = s.doblada.fecha_pago if s.doblada else None
                if fp:
                    solicitudes_descanso_receptor[fp] = s

            # DOBLADA PERMANENTE: descansos recurrentes (este empleado es cubierto esos días).
            # Solicitante descansa en sus días de cesión; receptor descansa en los de devolución.
            from solicitudes.services.ct_permanente_helper import _es_festivo
            descansos_perm = {}  # fecha -> {'companero_nombre', 'tipo'}
            perm_qs = (
                SolicitudCambio.objects
                .filter(tipo_cambio__nombre='DOBLADA PERMANENTE', estado='aprobada')
                .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado))
                .select_related('explorador_solicitante', 'explorador_receptor', 'doblada_permanente')
            )
            for s in perm_qs:
                det = getattr(s, 'doblada_permanente', None)
                if not det:
                    continue
                es_sol = s.explorador_solicitante_id == empleado.id
                dias_txt = det.dias_cesion if es_sol else det.dias_devolucion
                dias_set = {int(x) for x in dias_txt.split(',') if x.strip().isdigit()}
                if not dias_set:
                    continue
                companero = s.explorador_receptor if es_sol else s.explorador_solicitante
                comp_nombre = f"{companero.nombre} {companero.apellido}"
                ini = max(det.fecha_inicio, fecha_inicio)
                fin = min(det.fecha_fin, fecha_fin)
                d = ini
                while d <= fin:
                    if d.weekday() in dias_set and d.weekday() != 6 and not _es_festivo(d):
                        descansos_perm[d] = {
                            'companero_nombre': comp_nombre,
                            'tipo': 'cedio' if es_sol else 'pago',
                        }
                    d += timedelta(days=1)

            # CAMBIO DESCANSO: el empleado pasa a DESCANSAR el día que cedió (su trabajo se
            # materializó como Turno en el otro día). Aquí marcamos el día de descanso, que el
            # calendario calcularía como trabajado. Se mira Turno primero (arriba); esto cubre
            # el día sin Turno que ahora descansa.
            descansos_cd = {}  # fecha -> {'companero_nombre','companero_id','tipo','solicitud_id'}

            def _otro_dia_cd(f):
                if not f:
                    return None
                if f.weekday() == 5:
                    return f + timedelta(days=1)
                if f.weekday() == 6:
                    return f - timedelta(days=1)
                return None

            cd_qs = (
                SolicitudCambio.objects
                .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='aprobada')
                .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado))
                .select_related('explorador_solicitante', 'explorador_receptor', 'doblada')
            )
            for s in cd_qs:
                det = getattr(s, 'doblada', None)
                if not det:
                    continue
                fc = s.fecha_cambio_turno
                fp = det.fecha_pago
                es_sol = s.explorador_solicitante_id == empleado.id
                es_finde = bool(fc) and fc.weekday() in (5, 6)
                if es_finde:
                    # Solicitante descansa sus días originales (cesión y pago);
                    # receptor descansa los días contrarios de cada finde.
                    rest_days = [fc, fp] if es_sol else [_otro_dia_cd(fc), _otro_dia_cd(fp)]
                else:
                    # Entre semana (intercambio directo, sin devolución).
                    rest_days = [fp] if es_sol else [fc]
                companero = s.explorador_receptor if es_sol else s.explorador_solicitante
                for rd in rest_days:
                    if rd and fecha_inicio <= rd <= fecha_fin:
                        descansos_cd[rd] = {
                            'companero_nombre': f"{companero.nombre} {companero.apellido}",
                            'companero_id': companero.id,
                            'tipo': 'cedio' if es_sol else 'pago',
                            'origen': 'cambio_descanso',
                            'solicitud_id': s.id,
                        }

            # PERMISOS ESPECIALES del explorador que caen en el mes (puntual o permanente).
            # No cambian la jornada; se muestran como indicador en el día.
            from permisos.models import PermisoEspecial
            permisos_por_fecha = {}
            pe_qs = (
                PermisoEspecial.objects
                .filter(empleado=empleado, estado__in=['APROBADO', 'PENDIENTE'],
                        fecha_inicio__lte=fecha_fin, fecha_fin__gte=fecha_inicio)
                .select_related('cubre')
            )
            for p in pe_qs:
                p_info = {
                    'horas': float(p.tiempo or 0),
                    'especificacion': p.especificacion or '',
                    'tipo': p.get_tipo_display(),
                    'cubre': f"{p.cubre.nombre} {p.cubre.apellido}" if p.cubre else None,
                    'estado': p.estado,
                    'es_permanente': p.es_permanente,
                }
                if p.es_permanente:
                    dias_set = {int(x) for x in p.dias_semana.split(',') if x.strip().isdigit()}
                    di = max(p.fecha_inicio, fecha_inicio)
                    dfin = min(p.fecha_fin, fecha_fin)
                    while di <= dfin:
                        if di.weekday() in dias_set:
                            permisos_por_fecha[di.strftime('%Y-%m-%d')] = p_info
                        di += timedelta(days=1)
                elif fecha_inicio <= p.fecha_inicio <= fecha_fin:
                    permisos_por_fecha[p.fecha_inicio.strftime('%Y-%m-%d')] = p_info

            # RESTRICCIONES del empleado vigentes en el mes (aplican TODOS los días del rango;
            # fecha_fin nula = indefinida/en curso).
            from empleados.models import RestriccionEmpleado
            restricciones_por_fecha = {}
            rest_qs = RestriccionEmpleado.objects.filter(
                empleado=empleado, fecha_inicio__lte=fecha_fin
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
            for r in rest_qs:
                r_info = {
                    'tipo': r.tipo_restriccion or 'Restricción',
                    'recomendacion': r.recomendacion or '',
                    'indefinida': r.fecha_fin is None,
                }
                ini = max(r.fecha_inicio, fecha_inicio)
                fin = min(r.fecha_fin, fecha_fin) if r.fecha_fin else fecha_fin
                di = ini
                while di <= fin:
                    restricciones_por_fecha[di.strftime('%Y-%m-%d')] = r_info
                    di += timedelta(days=1)

            # SANCIONES del empleado vigentes en el mes (no puede solicitar nada esos días)
            from empleados.models import SancionEmpleado
            sanciones_por_fecha = {}
            sanc_qs = SancionEmpleado.objects.filter(
                explorador=empleado, fecha_inicio__lte=fecha_fin
            ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio))
            for s in sanc_qs:
                s_info = {
                    'motivo': s.motivo or '',
                    'desde': s.fecha_inicio.strftime('%d/%m/%Y'),
                    'hasta': s.fecha_fin.strftime('%d/%m/%Y') if s.fecha_fin else None,
                }
                ini = max(s.fecha_inicio, fecha_inicio)
                fin = min(s.fecha_fin, fecha_fin) if s.fecha_fin else fecha_fin
                di = ini
                while di <= fin:
                    sanciones_por_fecha[di.strftime('%Y-%m-%d')] = s_info
                    di += timedelta(days=1)

            # Crear estructura de datos para el mes
            turnos_mes_dict = {}
            dias_mes = (fecha_fin - fecha_inicio).days + 1
            for i in range(dias_mes):
                fecha = fecha_inicio + timedelta(days=i)
                turnos_dia = turnos_por_fecha.get(fecha, [])

                # FESTIVO entre semana: la fuente de verdad manda sobre el horario
                # predeterminado (la jornada que dobla por rotación trabaja AM+PM, la otra
                # descansa). Solo un cambio EXPLÍCITO se respeta: en ese caso estado_mes
                # devuelve fuente='turno' y caemos al flujo normal de abajo.
                _est_fv = estados_mes.get(fecha)
                if _est_fv and _est_fv.get('fuente') == 'festivo':
                    if _est_fv['trabaja']:
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': 'DOBLADA',
                            'sala': 'Por asignar',
                            'tipo': 'predeterminado',
                            'es_cambio': False,
                            'es_doblada': True,
                            'jornada_predeterminada': 'DOBLADA',
                            'coincide_con_predeterminada': True,
                            'turno_id': None,
                            'es_festivo': True,
                        }
                    else:
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': None,
                            'sala': None,
                            'tipo': 'descanso',
                            'es_cambio': False,
                            'es_descanso': True,
                            'jornada_predeterminada': None,
                            'coincide_con_predeterminada': False,
                            'turno_id': None,
                            'es_festivo': True,
                            'descanso_info': {'tipo': 'festivo'},
                        }
                    continue

                if turnos_dia:
                    # Hay turno(s) asignado(s) (puede ser cambio aprobado o doblada)
                    # OPTIMIZACIÓN: Calcular jornada_display desde turnos_dia sin consultas extra
                    jornadas_turnos = [t.jornada.nombre.upper() for t in turnos_dia if t.jornada]
                    if 'AM' in jornadas_turnos and 'PM' in jornadas_turnos:
                        jornada_display = 'DOBLADA'
                    elif 'AM' in jornadas_turnos:
                        jornada_display = 'AM'
                    elif 'PM' in jornadas_turnos:
                        jornada_display = 'PM'
                    else:
                        jornada_display = calcular_jornada_dia(jornada_base, fecha) or ''
                    
                    jornada_predeterminada = calcular_jornada_dia(jornada_base, fecha)
                    
                    # Detectar si es doblada
                    es_doblada = jornada_display == 'DOBLADA'

                    # Determinar tipo de cambio (si todos los turnos tienen el mismo tipo_cambio)
                    tipos_cambio = [t.tipo_cambio for t in turnos_dia if t.tipo_cambio]
                    es_cambio = len(tipos_cambio) > 0
                    tipo_cambio_principal = tipos_cambio[0] if tipos_cambio else None
                    
                    # Determinar sala(s)
                    salas = [t.sala.nombre for t in turnos_dia if t.sala]
                    if len(set(salas)) == 1:
                        # Todas las salas son iguales
                        sala_display = salas[0]
                    else:
                        # Salas diferentes (raro, pero posible)
                        sala_display = ', '.join(set(salas)) if salas else 'Por asignar'
                    
                    coincide_con_predeterminada = jornada_display == jornada_predeterminada if jornada_display else False
                    
                    # Usar el primer turno como referencia (para compatibilidad con código existente)
                    turno_principal = turnos_dia[0]
                    
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': jornada_display,  # Usar jornada_display (puede ser 'DOBLADA')
                        'sala': sala_display,
                        # 'asignado' solo cuando fue creado por CT/DOBLADA (tipo_cambio != null).
                        # 'predeterminado' cuando el turno existe en BD pero sin tipo_cambio (horario importado).
                        'tipo': 'asignado' if es_cambio else 'predeterminado',
                        'es_cambio': es_cambio,
                        'es_doblada': es_doblada,  # Flag para frontend
                        'jornada_predeterminada': jornada_predeterminada,
                        'coincide_con_predeterminada': coincide_con_predeterminada,
                        'turno_id': turno_principal.id
                    }
                else:
                    # No hay turno asignado
                    # OPTIMIZACIÓN: Usar dicts precargados en vez de 2 consultas por día
                    solicitud_como_solicitante = solicitudes_descanso_solicitante.get(fecha)
                    solicitud_como_receptor = solicitudes_descanso_receptor.get(fecha)
                    descanso_perm = descansos_perm.get(fecha)
                    descanso_cd = descansos_cd.get(fecha)
                    esta_descansando = (
                        solicitud_como_solicitante is not None
                        or solicitud_como_receptor is not None
                        or descanso_perm is not None
                        or descanso_cd is not None
                    )

                    if esta_descansando:
                        # Determinar información detallada del descanso
                        companero_nombre = None
                        companero_id = None
                        tipo_descanso = None  # 'cedio' o 'pago'
                        solicitud_id = None
                        fecha_relacionada = None
                        fecha_solicitud = None
                        fecha_aprobacion = None
                        tipo_cesion = None
                        jornada_cedida = None
                        fecha_cesion = None
                        fecha_pago = None
                        origen_descanso = None  # p. ej. 'cambio_descanso' (intercambio de día)

                        if solicitud_como_solicitante:
                            # Está descansando porque CEDIÓ su jornada
                            detalle = solicitud_como_solicitante.doblada
                            companero_nombre = f"{solicitud_como_solicitante.explorador_receptor.nombre} {solicitud_como_solicitante.explorador_receptor.apellido}"
                            companero_id = solicitud_como_solicitante.explorador_receptor.id
                            tipo_descanso = 'cedio'
                            solicitud_id = solicitud_como_solicitante.id
                            fecha_cesion = solicitud_como_solicitante.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud_como_solicitante.fecha_cambio_turno else None
                            fecha_pago = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle and detalle.fecha_pago else None
                            fecha_relacionada = fecha_pago
                            fecha_solicitud = solicitud_como_solicitante.fecha_solicitud.strftime('%d/%m/%Y %H:%M') if solicitud_como_solicitante.fecha_solicitud else None
                            fecha_aprobacion = solicitud_como_solicitante.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud_como_solicitante.fecha_resolucion else None
                            tipo_cesion = detalle.get_tipo_cesion_display() if detalle else None
                            jornada_cedida = detalle.jornada_cedida if detalle and detalle.jornada_cedida else None
                        elif solicitud_como_receptor:
                            # Está descansando porque está PAGANDO una doblada
                            detalle = solicitud_como_receptor.doblada
                            companero_nombre = f"{solicitud_como_receptor.explorador_solicitante.nombre} {solicitud_como_receptor.explorador_solicitante.apellido}"
                            companero_id = solicitud_como_receptor.explorador_solicitante.id
                            tipo_descanso = 'pago'
                            solicitud_id = solicitud_como_receptor.id
                            fecha_cesion = solicitud_como_receptor.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud_como_receptor.fecha_cambio_turno else None
                            fecha_pago = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle and detalle.fecha_pago else None
                            fecha_relacionada = fecha_cesion
                            fecha_solicitud = solicitud_como_receptor.fecha_solicitud.strftime('%d/%m/%Y %H:%M') if solicitud_como_receptor.fecha_solicitud else None
                            fecha_aprobacion = solicitud_como_receptor.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud_como_receptor.fecha_resolucion else None
                            tipo_cesion = detalle.get_tipo_cesion_display() if detalle else None
                            jornada_cedida = detalle.jornada_cedida if detalle and detalle.jornada_cedida else None
                        elif descanso_perm:
                            # Descanso recurrente por DOBLADA PERMANENTE (cubierto por el compañero)
                            companero_nombre = descanso_perm['companero_nombre']
                            tipo_descanso = descanso_perm['tipo']  # 'cedio' o 'pago'
                        elif descanso_cd:
                            # Descanso por CAMBIO DE DÍA DE DESCANSO (intercambio de día con compañero)
                            companero_nombre = descanso_cd['companero_nombre']
                            companero_id = descanso_cd['companero_id']
                            tipo_descanso = descanso_cd['tipo']  # 'cedio' o 'pago'
                            solicitud_id = descanso_cd['solicitud_id']
                            origen_descanso = descanso_cd.get('origen')  # 'cambio_descanso'

                        # Usuario está descansando
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': None,  # Sin jornada porque está descansando
                            'sala': None,
                            'tipo': 'descanso',
                            'es_cambio': False,
                            'es_descanso': True,  # Flag para frontend
                            'jornada_predeterminada': calcular_jornada_dia(jornada_base, fecha),
                            'coincide_con_predeterminada': False,
                            'turno_id': None,
                            'descanso_info': {  # ✅ MEJORADO: Información detallada sobre el descanso
                                'tipo': tipo_descanso,  # 'cedio' o 'pago'
                                'origen': origen_descanso,  # 'cambio_descanso' → es un INTERCAMBIO de descanso
                                'companero_nombre': companero_nombre,
                                'companero_id': companero_id,
                                'solicitud_id': solicitud_id,
                                'fecha_relacionada': fecha_relacionada,
                                'fecha_cesion': fecha_cesion,
                                'fecha_pago': fecha_pago,
                                'fecha_solicitud': fecha_solicitud,
                                'fecha_aprobacion': fecha_aprobacion,
                                'tipo_cesion': tipo_cesion,
                                'jornada_cedida': jornada_cedida
                            }
                        }
                    else:
                        # No hay turno asignado: el estado lo resuelve la FUENTE DE VERDAD
                        # única (estado_mes), que ya aplica alternancia de finde, temporada y
                        # mantenimiento en el orden correcto. Antes esta lógica estaba duplicada
                        # aquí; ahora solo se mapea su resultado al formato de la respuesta.
                        est = estados_mes.get(fecha) or {}

                        if est.get('trabaja') and est.get('jornada') == 'DOBLADA':
                            # Fin de semana que le corresponde trabajar → jornada predeterminada DOBLADA
                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': 'DOBLADA',
                                'sala': 'Por asignar',
                                'tipo': 'predeterminado',
                                'es_cambio': False,
                                'es_doblada': True,  # Flag para frontend
                                'jornada_predeterminada': 'DOBLADA',
                                'coincide_con_predeterminada': True,
                                'turno_id': None
                            }
                        elif (not est.get('trabaja')) and est.get('fuente') in ('temporada', 'mantenimiento'):
                            # Descanso de ENTRE SEMANA (temporada/mantenimiento)
                            motivo_descanso_semana = 'temporada' if est.get('fuente') == 'temporada' else 'mantenimiento'
                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': None,
                                'sala': None,
                                'tipo': 'descanso',
                                'es_cambio': False,
                                'es_descanso': True,
                                'jornada_predeterminada': calcular_jornada_dia(jornada_base, fecha),
                                'coincide_con_predeterminada': False,
                                'turno_id': None,
                                'descanso_info': {
                                    'tipo': 'descanso_semana',
                                    'motivo': motivo_descanso_semana,  # 'manual' o 'mantenimiento'
                                },
                            }
                        else:
                            # Día normal (jornada base entre semana) o descanso de fin de semana
                            # (que conserva el comportamiento histórico: jornada = "Descanso").
                            jornada_nombre = calcular_jornada_dia(jornada_base, fecha)

                            sala_nombre = 'Por asignar'
                            if asignaciones_activas:
                                sala_nombre = asignaciones_activas.sala.nombre

                            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                                'jornada': jornada_nombre,
                                'sala': sala_nombre,
                                'tipo': 'predeterminado',
                                'es_cambio': False,
                                'es_descanso': False,
                                'jornada_predeterminada': jornada_nombre,
                                'coincide_con_predeterminada': True,
                                'turno_id': None
                            }
            
            # FASE 3.3: Obtener información de solicitudes para turnos con cambios (optimizado)
            # Limitar a las solicitudes más recientes para mejorar rendimiento
            from solicitudes.models import SolicitudCambio
            # CORRECCIÓN: turnos_por_fecha ahora contiene listas de turnos, no turnos individuales
            turno_ids_con_cambio = []
            for turnos_lista in turnos_por_fecha.values():
                for turno in turnos_lista:
                    if turno.tipo_cambio is not None:
                        turno_ids_con_cambio.append(turno.id)
            solicitudes_info = {}
            
            if turno_ids_con_cambio:
                # FASE 3.3: Limitar a las 50 solicitudes más recientes para evitar consultas lentas
                # Obtener todas las solicitudes que afectaron estos turnos
                solicitudes = SolicitudCambio.objects.filter(
                    Q(turno_origen_id__in=turno_ids_con_cambio) | Q(turno_destino_id__in=turno_ids_con_cambio),
                    estado='aprobada'
                ).select_related('explorador_solicitante', 'explorador_receptor').order_by('-fecha_resolucion', '-id')[:50]
                
                # Procesar solicitudes en orden descendente (más reciente primero)
                # Para cada turno, solo guardar la primera solicitud encontrada (más reciente)
                for solicitud in solicitudes:
                    # Para turno_origen (solicitante)
                    if solicitud.turno_origen_id and solicitud.turno_origen_id in turno_ids_con_cambio:
                        if solicitud.turno_origen_id not in solicitudes_info:
                            solicitudes_info[solicitud.turno_origen_id] = {
                                'solicitud_id': solicitud.id,
                                'companero_nombre': solicitud.explorador_receptor.nombre,
                                'rol': 'solicitante',
                                'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None
                            }
                    
                    # Para turno_destino (receptor)
                    if solicitud.turno_destino_id and solicitud.turno_destino_id in turno_ids_con_cambio:
                        if solicitud.turno_destino_id not in solicitudes_info:
                            solicitudes_info[solicitud.turno_destino_id] = {
                                'solicitud_id': solicitud.id,
                                'companero_nombre': solicitud.explorador_solicitante.nombre,
                                'rol': 'receptor',
                                'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None
                            }
            
            # Agregar información de solicitudes a los turnos
            # Para dobladas, buscar en todos los turnos de esa fecha
            for fecha_str, info in turnos_mes_dict.items():
                turno_id = info.get('turno_id')
                solicitud_encontrada = None
                
                # Si hay turno_id, buscar directamente
                if turno_id and turno_id in solicitudes_info:
                    solicitud_encontrada = solicitudes_info[turno_id]
                else:
                    # Si no se encontró, puede ser una doblada con múltiples turnos
                    # Buscar en todos los turnos de esa fecha
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    turnos_fecha = turnos_por_fecha.get(fecha_obj, [])
                    for turno in turnos_fecha:
                        if turno.id in solicitudes_info:
                            solicitud_encontrada = solicitudes_info[turno.id]
                            break  # Usar la primera encontrada
                
                info['solicitud_info'] = solicitud_encontrada
            
            # BÚSQUEDA ADICIONAL PARA DOBLADAS
            # Las dobladas no tienen turno_origen/turno_destino asignados, así que buscamos por fecha y empleado
            # Solo buscar para fechas que aún no tienen solicitud_info y tienen cambios (es_cambio o es_doblada)
            fechas_sin_solicitud = [
                fecha_str for fecha_str, info in turnos_mes_dict.items()
                if not info.get('solicitud_info') and (info.get('es_cambio', False) or info.get('es_doblada', False))
            ]
            
            if fechas_sin_solicitud:
                # Convertir fechas string a objetos date
                fechas_obj = [datetime.strptime(f, '%Y-%m-%d').date() for f in fechas_sin_solicitud]
                
                # IMPORTANTE: Para dobladas, necesitamos buscar en ambos escenarios:
                # 1. Empleado como SOLICITANTE en fecha de cesión (empleado cedió, receptor trabaja)
                # 2. Empleado como RECEPTOR en fecha de cesión (empleado trabaja/dobla, solicitante descansa)
                # 3. Empleado como RECEPTOR en fecha de pago (empleado descansa, solicitante trabaja/dobla)
                # 4. Empleado como SOLICITANTE en fecha de pago (empleado trabaja/dobla, receptor descansa)
                
                # Buscar donde el empleado es SOLICITANTE y la fecha es de CESIÓN (empleado descansa, receptor trabaja)
                solicitudes_solicitante_cesion = SolicitudCambio.objects.filter(
                    explorador_solicitante=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_receptor', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Buscar donde el empleado es RECEPTOR y la fecha es de CESIÓN (empleado trabaja/dobla, solicitante descansa)
                solicitudes_receptor_cesion = SolicitudCambio.objects.filter(
                    explorador_receptor=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    fecha_cambio_turno__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_solicitante', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Buscar donde el empleado es RECEPTOR y la fecha es de PAGO (empleado descansa, solicitante trabaja/dobla)
                solicitudes_receptor_pago = SolicitudCambio.objects.filter(
                    explorador_receptor=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    doblada__fecha_pago__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_solicitante', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Buscar donde el empleado es SOLICITANTE y la fecha es de PAGO (empleado trabaja/dobla, receptor descansa)
                solicitudes_solicitante_pago = SolicitudCambio.objects.filter(
                    explorador_solicitante=empleado,
                    tipo_cambio__nombre='DOBLADA',
                    doblada__fecha_pago__in=fechas_obj,
                    estado='aprobada'
                ).select_related('explorador_receptor', 'tipo_cambio', 'doblada').order_by('-fecha_resolucion', '-id')
                
                # Crear diccionarios para búsqueda rápida (solo la más reciente por fecha)
                dobladas_dict = {}
                
                # Solicitudes donde empleado es solicitante en fecha de cesión
                for sol in solicitudes_solicitante_cesion:
                    fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                    if fecha_str not in dobladas_dict:
                        dobladas_dict[fecha_str] = {
                            'solicitud': sol,
                            'companero': sol.explorador_receptor.nombre,
                            'rol': 'solicitante'
                        }
                
                # Solicitudes donde empleado es receptor en fecha de cesión
                for sol in solicitudes_receptor_cesion:
                    fecha_str = sol.fecha_cambio_turno.strftime('%Y-%m-%d')
                    if fecha_str not in dobladas_dict:
                        dobladas_dict[fecha_str] = {
                            'solicitud': sol,
                            'companero': sol.explorador_solicitante.nombre,
                            'rol': 'receptor'
                        }
                
                # Solicitudes donde empleado es receptor en fecha de pago
                for sol in solicitudes_receptor_pago:
                    if sol.doblada and sol.doblada.fecha_pago:
                        fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                        if fecha_str not in dobladas_dict:
                            dobladas_dict[fecha_str] = {
                                'solicitud': sol,
                                'companero': sol.explorador_solicitante.nombre,
                                'rol': 'receptor'
                            }
                
                # Solicitudes donde empleado es solicitante en fecha de pago
                for sol in solicitudes_solicitante_pago:
                    if sol.doblada and sol.doblada.fecha_pago:
                        fecha_str = sol.doblada.fecha_pago.strftime('%Y-%m-%d')
                        if fecha_str not in dobladas_dict:
                            dobladas_dict[fecha_str] = {
                                'solicitud': sol,
                                'companero': sol.explorador_receptor.nombre,
                                'rol': 'solicitante'
                            }
                
                # Asociar información de dobladas a los turnos
                for fecha_str in fechas_sin_solicitud:
                    if fecha_str not in turnos_mes_dict:
                        continue
                    
                    info = turnos_mes_dict[fecha_str]
                    if info.get('solicitud_info'):
                        continue  # Ya tiene información
                    
                    doblada_info = dobladas_dict.get(fecha_str)
                    if doblada_info:
                        sol = doblada_info['solicitud']
                        info['solicitud_info'] = {
                            'solicitud_id': sol.id,
                            'companero_nombre': doblada_info['companero'],
                            'rol': doblada_info['rol'],
                            'fecha_resolucion': sol.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if sol.fecha_resolucion else None
                        }
            
            # Adjuntar el permiso especial (si lo hay) a cada día — antes de cachear
            for _fstr, _pinfo in permisos_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['permiso'] = _pinfo

            # Adjuntar la restricción (si la hay) a cada día
            for _fstr, _rinfo in restricciones_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['restriccion'] = _rinfo

            # Adjuntar la sanción (si la hay) a cada día
            for _fstr, _sinfo in sanciones_por_fecha.items():
                if _fstr in turnos_mes_dict:
                    turnos_mes_dict[_fstr]['sancion'] = _sinfo

            # FASE 3.5: Guardar en caché usando CacheService
            # Los datos de turnos no cambian frecuentemente, así que 1 hora es seguro
            from core.services.cache_service import CACHE_TTL_LONG
            CacheService.set(cache_key, turnos_mes_dict, ttl=CACHE_TTL_LONG)

            return JsonResponse(turnos_mes_dict)
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"ERROR en MisTurnosPorMesView: {str(e)}")
            print(f"Traceback: {error_trace}")
            return JsonResponse({
                'error': f'Error al procesar fechas: {str(e)}',
                'traceback': error_trace if request.user.is_staff else None  # Solo mostrar traceback a staff
            }, status=400)


class DiasFestivosView(LoginRequiredMixin, View):
    """
    Vista para obtener días festivos.
    Útil para mostrar en calendarios y validaciones.
    
    ESTRATEGIA HÍBRIDA:
    1. Intenta usar biblioteca calendario-colombiano (más precisa)
    2. Si no está disponible, usa festivos de BD
    3. Combina ambos para máxima precisión
    
    OPTIMIZACIÓN: Usa caché para evitar consultas repetidas a la BD.
    Los festivos no cambian frecuentemente, así que se cachean por 1 hora.
    """
    
    def _obtener_festivos_calculados(self, año_inicio, año_fin):
        """
        Obtiene festivos calculados usando biblioteca externa si está disponible.
        Retorna dict con fecha (YYYY-MM-DD) como clave y descripción como valor.
        """
        festivos_calculados = {}
        
        try:
            # Intentar usar biblioteca calendario-colombiano
            from calendario_colombiano import CalendarioColombiano
            from datetime import date, timedelta
            
            calendario = CalendarioColombiano()
            
            # Obtener festivos para el rango de años
            fecha_inicio = date(año_inicio, 1, 1)
            fecha_fin = date(año_fin, 12, 31)
            fecha_actual = fecha_inicio
            
            while fecha_actual <= fecha_fin:
                if calendario.es_festivo(fecha_actual):
                    fecha_str = fecha_actual.strftime('%Y-%m-%d')
                    # Obtener nombre del festivo si es posible
                    nombre = getattr(calendario, 'nombre_festivo', lambda d: 'Día festivo')(fecha_actual)
                    festivos_calculados[fecha_str] = nombre
                fecha_actual += timedelta(days=1)
                
        except ImportError:
            # Si no está instalada la biblioteca, retornar vacío
            # El frontend usará su cálculo JavaScript como respaldo
            pass
        except Exception as e:
            # En caso de error, continuar sin festivos calculados
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f'Error al calcular festivos con biblioteca externa: {e}')
        
        return festivos_calculados
    
    def get(self, request):
        """
        Obtener días festivos.
        
        Parámetros opcionales:
        - fecha_inicio: Fecha de inicio (formato: YYYY-MM-DD)
        - fecha_fin: Fecha de fin (formato: YYYY-MM-DD)
        - anio: Año específico (formato: YYYY)
        - mes: Mes específico (formato: MM)
        - sin_cache: Si es 'true', omite el caché (útil para testing)
        
        Si no se proporcionan parámetros, devuelve todos los festivos activos.
        """
        try:
            fecha_inicio = request.GET.get('fecha_inicio')
            fecha_fin = request.GET.get('fecha_fin')
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            sin_cache = request.GET.get('sin_cache', 'false').lower() == 'true'
            
            # Generar clave de caché basada en los filtros
            cache_key = 'dias_festivos'
            if fecha_inicio:
                cache_key += f'_desde_{fecha_inicio}'
            if fecha_fin:
                cache_key += f'_hasta_{fecha_fin}'
            if anio:
                cache_key += f'_anio_{anio}'
            if mes:
                cache_key += f'_mes_{mes}'
            
            # Intentar obtener del caché usando CacheService (solo si no se solicita sin caché)
            if not sin_cache:
                from core.services.cache_service import CacheService
                cached_data = CacheService.get(cache_key)
                if cached_data is not None:
                    return JsonResponse(cached_data)
            
            # Construir query base
            festivos = DiaEspecial.objects.filter(
                tipo='festivo',
                activo=True
            )
            
            # Filtrar por rango de fechas si se proporciona
            if fecha_inicio and fecha_fin:
                fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                festivos = festivos.filter(fecha__gte=fecha_inicio_obj, fecha__lte=fecha_fin_obj)
            elif fecha_inicio:
                fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                festivos = festivos.filter(fecha__gte=fecha_inicio_obj)
            elif fecha_fin:
                fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                festivos = festivos.filter(fecha__lte=fecha_fin_obj)
            
            # Filtrar por año si se proporciona
            if anio:
                festivos = festivos.filter(fecha__year=int(anio))
            
            # Filtrar por mes si se proporciona
            if mes:
                festivos = festivos.filter(fecha__month=int(mes))
            
            # Serializar resultados de BD
            festivos_list = []
            festivos_bd = {}  # Dict para fácil combinación
            
            for festivo in festivos.order_by('fecha'):
                fecha_str = festivo.fecha.strftime('%Y-%m-%d')
                festivos_bd[fecha_str] = festivo.descripcion or 'Día festivo'
                festivos_list.append({
                    'fecha': fecha_str,
                    'descripcion': festivo.descripcion or '',
                    'recurrente': festivo.recurrente
                })
            
            # Obtener festivos calculados
            # Si no se especifica año, calcular para un rango amplio (año actual - 1 a + 10)
            año_actual = datetime.now().year
            
            if anio:
                # Si se especifica un año, calcular solo para ese año
                año_inicio = int(anio)
                año_fin = int(anio)
            else:
                # Si no se especifica, calcular para un rango amplio
                año_inicio = año_actual - 1
                año_fin = año_actual + 10
            
            # Combinar festivos calculados con los de BD
            festivos_calculados = self._obtener_festivos_calculados(año_inicio, año_fin)
            
            # Los festivos de BD tienen prioridad, pero agregamos los calculados que no estén en BD
            for fecha_calc, descripcion_calc in festivos_calculados.items():
                if fecha_calc not in festivos_bd:
                    festivos_list.append({
                        'fecha': fecha_calc,
                        'descripcion': descripcion_calc,
                        'recurrente': False
                    })
            
            # Ordenar por fecha
            festivos_list.sort(key=lambda x: x['fecha'])
            
            response_data = {
                'festivos': festivos_list,
                'total': len(festivos_list),
                'fuente': 'bd_y_calculado' if festivos_calculados else 'bd'
            }
            
            # Guardar en caché usando CacheService
            # Los festivos no cambian frecuentemente
            if not sin_cache:
                from core.services.cache_service import CacheService
                from core.services.cache_service import CACHE_TTL_LONG
                CacheService.set(cache_key, response_data, ttl=CACHE_TTL_LONG)
            
            return JsonResponse(response_data)
            
        except ValueError as e:
            return JsonResponse({'error': f'Formato de fecha inválido: {str(e)}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'Error al obtener festivos: {str(e)}'}, status=500)


class DiasTemporadaView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener días de temporada por año y mes.
    
    Parámetros:
    - anio: Año (requerido)
    - mes: Mes opcional (1-12)
    
    Retorna JSON con días de temporada agrupados por mes.
    """
    
    def get(self, request):
        try:
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            
            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)
            
            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)
            
            if mes:
                try:
                    mes = int(mes)
                    if mes < 1 or mes > 12:
                        return JsonResponse({'error': 'El mes debe estar entre 1 y 12'}, status=400)
                    
                    # Obtener días de temporada del mes específico
                    dias_temporada = TemporadaService.obtener_dias_temporada_mes(anio, mes)
                    temporadas = [
                        {
                            'fecha': dia.fecha.strftime('%Y-%m-%d'),
                            'mes': dia.mes or dia.fecha.month,
                            'dia': dia.fecha.day,
                            'descripcion': dia.descripcion or 'Día de temporada'
                        }
                        for dia in dias_temporada
                    ]
                    
                    return JsonResponse({
                        'temporadas': temporadas,
                        'total': len(temporadas),
                        'anio': anio,
                        'mes': mes
                    })
                except ValueError:
                    return JsonResponse({'error': 'El mes debe ser un número válido'}, status=400)
            else:
                # Obtener todos los días de temporada del año, agrupados por mes
                dias_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio)
                dias_temporada = TemporadaService.obtener_dias_temporada_anio(anio)
                
                temporadas = [
                    {
                        'fecha': dia.fecha.strftime('%Y-%m-%d'),
                        'mes': dia.mes or dia.fecha.month,
                        'dia': dia.fecha.day,
                        'descripcion': dia.descripcion or 'Día de temporada'
                    }
                    for dia in dias_temporada
                ]
                
                return JsonResponse({
                    'temporadas': temporadas,
                    'por_mes': dias_por_mes,
                    'total': len(temporadas),
                    'anio': anio
                })
                
        except Exception as e:
            return JsonResponse({'error': f'Error al obtener temporadas: {str(e)}'}, status=500)


class DiasEspecialesPorTipoView(LoginRequiredMixin, View):
    """
    Endpoint API para obtener días especiales (festivos o mantenimiento) por tipo, año y mes.
    
    Parámetros:
    - tipo: Tipo de día especial ('festivo' o 'mantenimiento') (requerido)
    - anio: Año (requerido)
    - mes: Mes opcional (1-12)
    
    Retorna JSON con días especiales agrupados por mes.
    """
    
    def get(self, request):
        try:
            tipo = request.GET.get('tipo')
            anio = request.GET.get('anio')
            mes = request.GET.get('mes')
            
            if not tipo:
                return JsonResponse({'error': 'El parámetro "tipo" es requerido'}, status=400)
            
            if tipo not in ['festivo', 'mantenimiento']:
                return JsonResponse({'error': 'El tipo debe ser "festivo" o "mantenimiento"'}, status=400)
            
            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)
            
            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)
            
            from turnos.services.dia_especial_service import DiaEspecialService
            
            if mes:
                try:
                    mes = int(mes)
                    if mes < 1 or mes > 12:
                        return JsonResponse({'error': 'El mes debe estar entre 1 y 12'}, status=400)
                    
                    # Obtener días del tipo del mes específico
                    dias_especiales = DiaEspecialService.obtener_dias_por_tipo_mes(tipo, anio, mes)
                    dias_list = [
                        {
                            'fecha': dia.fecha.strftime('%Y-%m-%d'),
                            'mes': dia.mes or dia.fecha.month,
                            'dia': dia.fecha.day,
                            'descripcion': dia.descripcion or f'Día de {tipo}'
                        }
                        for dia in dias_especiales
                    ]
                    
                    return JsonResponse({
                        'dias': dias_list,
                        'total': len(dias_list),
                        'tipo': tipo,
                        'anio': anio,
                        'mes': mes
                    })
                except ValueError:
                    return JsonResponse({'error': 'El mes debe ser un número válido'}, status=400)
            else:
                # Obtener todos los días del tipo del año, agrupados por mes
                dias_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes(tipo, anio)
                dias_especiales = DiaEspecialService.obtener_dias_por_tipo_anio(tipo, anio)
                
                dias_list = [
                    {
                        'fecha': dia.fecha.strftime('%Y-%m-%d'),
                        'mes': dia.mes or dia.fecha.month,
                        'dia': dia.fecha.day,
                        'descripcion': dia.descripcion or f'Día de {tipo}'
                    }
                    for dia in dias_especiales
                ]
                
                return JsonResponse({
                    'dias': dias_list,
                    'por_mes': dias_por_mes,
                    'total': len(dias_list),
                    'tipo': tipo,
                    'anio': anio
                })
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al obtener días especiales por tipo: {e}")
            return JsonResponse({'error': f'Error al obtener días especiales: {str(e)}'}, status=500)


class CalcularMantenimientoAutomaticoView(LoginRequiredMixin, View):
    """
    Endpoint API para calcular automáticamente los días de mantenimiento para un año.
    
    Parámetros:
    - anio: Año (requerido)
    
    Retorna JSON con días de mantenimiento calculados automáticamente, agrupados por mes.
    """
    
    def get(self, request):
        try:
            anio = request.GET.get('anio')
            
            if not anio:
                return JsonResponse({'error': 'El parámetro "anio" es requerido'}, status=400)
            
            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)
            
            from turnos.services.dia_especial_service import DiaEspecialService
            
            # Calcular días de mantenimiento automático
            dias_por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(anio)
            
            # Convertir a formato de lista para compatibilidad
            dias_list = []
            for mes, dias in dias_por_mes.items():
                for dia in dias:
                    fecha = date(anio, mes, dia)
                    dias_list.append({
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'mes': mes,
                        'dia': dia,
                        'descripcion': 'Día de mantenimiento'
                    })
            
            return JsonResponse({
                'dias': dias_list,
                'por_mes': dias_por_mes,
                'total': len(dias_list),
                'tipo': 'mantenimiento',
                'anio': anio
            })
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al calcular días de mantenimiento automático: {e}")
            return JsonResponse({'error': f'Error al calcular días de mantenimiento: {str(e)}'}, status=500)


class CalcularFestivosAutomaticoView(LoginRequiredMixin, View):
    """
    Endpoint API para generar y obtener automáticamente los días festivos para un año.

    Parámetros:
    - anio: Año (requerido)

    Retorna JSON con días festivos calculados y/o generados en BD, agrupados por mes.
    """

    def get(self, request):
        try:
            anio = request.GET.get('anio')

            if not anio:
                return JsonResponse({'error': 'El parámetro \"anio\" es requerido'}, status=400)

            try:
                anio = int(anio)
            except ValueError:
                return JsonResponse({'error': 'El año debe ser un número válido'}, status=400)

            # Validar año mínimo (solo para evitar años históricos muy antiguos)
            if anio < 2000:
                return JsonResponse({
                    'error': f'El año debe ser mayor o igual a 2000. Año proporcionado: {anio}'
                }, status=400)

            from turnos.services.dia_especial_service import DiaEspecialService

            # Generar (si faltan) y obtener festivos automáticos
            dias_por_mes = DiaEspecialService.generar_festivos_automaticos(anio)

            # Convertir a formato de lista para compatibilidad
            dias_list = []
            for mes, dias in dias_por_mes.items():
                for dia in dias:
                    fecha = date(anio, mes, dia)
                    dias_list.append({
                        'fecha': fecha.strftime('%Y-%m-%d'),
                        'mes': mes,
                        'dia': dia,
                        'descripcion': 'Día festivo'
                    })

            return JsonResponse({
                'dias': dias_list,
                'por_mes': dias_por_mes,
                'total': len(dias_list),
                'tipo': 'festivo',
                'anio': anio
            })

        except ValueError as e:
            # Capturar errores de validación de rango de años
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Intento de generar festivos con año inválido: {e}")
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al calcular festivos automáticos: {e}")
            return JsonResponse({'error': f'Error al calcular festivos automáticos: {str(e)}'}, status=500)
