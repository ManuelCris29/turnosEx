from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from django.db.models import Q
# Cache ahora se usa a través de CacheService (importado donde se necesita)
from turnos.models import Turno, AsignarJornadaExplorador, AsignarSalaExplorador, DiaEspecial
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
        
        # FASE 3.5: Generar clave de caché única para este empleado y mes
        from core.services.cache_service import CacheService
        
        cache_key = f'turnos_mes_{empleado.id}_{anio}_{mes}'
        
        # FASE 3.5: Intentar obtener datos del caché
        cached_data = CacheService.get(cache_key)
        if cached_data is not None:
            return JsonResponse(cached_data)
        # Validación y normalización de mes/año
        try:
            mes_int = int(mes)
            anio_int = int(anio)
            if not (1 <= mes_int <= 12):
                return JsonResponse({'error': 'Mes invalido'}, status=400)
            mes = f"{mes_int:02d}"
        except ValueError:
            return JsonResponse({'error': 'anio/mes deben ser numéricos'}, status=400)
        
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
            
            # Obtener asignaciones de sala activas para el mes
            asignaciones_activas = AsignarSalaExplorador.objects.filter(
                explorador=empleado,
                fecha_inicio__lte=fecha_fin
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_inicio)
            ).first()
            
            # Crear estructura de datos para el mes
            turnos_mes_dict = {}
            dias_mes = (fecha_fin - fecha_inicio).days + 1
            for i in range(dias_mes):
                fecha = fecha_inicio + timedelta(days=i)
                turnos_dia = turnos_por_fecha.get(fecha, [])
                
                if turnos_dia:
                    # Hay turno(s) asignado(s) (puede ser cambio aprobado o doblada)
                    # Usar helper para detectar dobladas (AM+PM en misma fecha)
                    from turnos.services.turno_service import TurnoService
                    jornada_display = TurnoService.obtener_jornada_display(empleado, fecha)
                    
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
                        'tipo': 'asignado',
                        'es_cambio': es_cambio,
                        'es_doblada': es_doblada,  # Flag para frontend
                        'jornada_predeterminada': jornada_predeterminada,
                        'coincide_con_predeterminada': coincide_con_predeterminada,
                        'turno_id': turno_principal.id
                    }
                else:
                    # No hay turno asignado
                    # Verificar si está descansando por doblada (dos casos posibles):
                    from solicitudes.models import SolicitudCambio, DobladaDetalle
                    
                    # CASO 1: Usuario es SOLICITANTE (cedió su jornada) en fecha de cesión
                    esta_descansando_como_solicitante = SolicitudCambio.objects.filter(
                        explorador_solicitante=empleado,  # Es solicitante (quien cedió)
                        tipo_cambio__nombre='DOBLADA',
                        fecha_cambio_turno=fecha,  # La fecha de cesión es esta fecha (él descansa)
                        estado='aprobada'
                    ).exists()
                    
                    # CASO 2: Usuario es RECEPTOR (quien cubrió) en fecha de pago
                    esta_descansando_como_receptor = SolicitudCambio.objects.filter(
                        explorador_receptor=empleado,  # Es receptor (quien cubrió)
                        tipo_cambio__nombre='DOBLADA',
                        estado='aprobada',
                        doblada__fecha_pago=fecha  # La fecha de pago es esta fecha (él descansa)
                    ).exists()
                    
                    esta_descansando = esta_descansando_como_solicitante or esta_descansando_como_receptor
                    
                    if esta_descansando:
                        # Usuario está descansando (cedió su jornada)
                        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                            'jornada': None,  # Sin jornada porque está descansando
                            'sala': None,
                            'tipo': 'descanso',
                            'es_cambio': False,
                            'es_descanso': True,  # Flag para frontend
                            'jornada_predeterminada': calcular_jornada_dia(jornada_base, fecha),
                            'coincide_con_predeterminada': False,
                            'turno_id': None
                        }
                    else:
                        # No hay turno, usar jornada predeterminada (día normal)
                        jornada_nombre = calcular_jornada_dia(jornada_base, fecha)
                        
                        # Intentar obtener sala de asignación activa
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
            for fecha_str, info in turnos_mes_dict.items():
                turno_id = info.get('turno_id')
                if turno_id and turno_id in solicitudes_info:
                    info['solicitud_info'] = solicitudes_info[turno_id]
                else:
                    info['solicitud_info'] = None
            
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
