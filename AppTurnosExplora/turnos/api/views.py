from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import View
from django.http import JsonResponse
from django.db.models import Q
from django.core.cache import cache
from turnos.models import Turno, AsignarJornadaExplorador, AsignarSalaExplorador
from turnos.services.turno_service import TurnoService
from datetime import datetime, timedelta


class TurnosPorDiaView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        if not fecha:
            return JsonResponse({'error': 'Debe seleccionar una fecha'}, status=400)
        data = TurnoService.get_exploradores_por_jornada(fecha)
        # Serializar empleados (solo nombre y apellido)
        am = [{'id': e.id, 'nombre': e.nombre, 'apellido': e.apellido} for e in data['am']]
        pm = [{'id': e.id, 'nombre': e.nombre, 'apellido': e.apellido} for e in data['pm']]
        return JsonResponse({'am': am, 'pm': pm})


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
        cache_key = f'turnos_mes_{empleado.id}_{anio}_{mes}'
        
        # FASE 3.5: Intentar obtener datos del caché
        cached_data = cache.get(cache_key)
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
                .order_by('fecha')
            )
            turnos_por_fecha = {t.fecha: t for t in turnos_mes}
            
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

            def calcular_jornada_dia(j_base, fecha):
                if not j_base:
                    return "PM"
                if j_base == "AM" and fecha.weekday() == 5:  # Sábado
                    return "Descanso"
                if j_base == "PM" and fecha.weekday() == 6:  # Domingo
                    return "Descanso"
                return j_base
            
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
                turno = turnos_por_fecha.get(fecha)
                
                if turno:
                    # Hay turno asignado (puede ser cambio aprobado)
                    jornada_turno = turno.jornada.nombre
                    jornada_predeterminada = calcular_jornada_dia(jornada_base, fecha)
                    es_cambio = turno.tipo_cambio is not None
                    coincide_con_predeterminada = jornada_turno == jornada_predeterminada
                    
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': jornada_turno,
                        'sala': (turno.sala.nombre if turno.sala else 'Por asignar'),
                        'tipo': 'asignado',
                        'es_cambio': es_cambio,
                        'jornada_predeterminada': jornada_predeterminada,
                        'coincide_con_predeterminada': coincide_con_predeterminada,
                        'turno_id': turno.id
                    }
                else:
                    # No hay turno asignado, usar jornada predeterminada
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
                        'jornada_predeterminada': jornada_nombre,
                        'coincide_con_predeterminada': True,
                        'turno_id': None
                    }
            
            # FASE 3.3: Obtener información de solicitudes para turnos con cambios (optimizado)
            # Limitar a las solicitudes más recientes para mejorar rendimiento
            from solicitudes.models import SolicitudCambio
            turno_ids_con_cambio = [t.id for t in turnos_por_fecha.values() if t.tipo_cambio is not None]
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
            
            # FASE 3.5: Guardar en caché por 1 hora (3600 segundos)
            # Los datos de turnos no cambian frecuentemente, así que 1 hora es seguro
            cache.set(cache_key, turnos_mes_dict, 3600)
            
            return JsonResponse(turnos_mes_dict)
            
        except Exception as e:
            return JsonResponse({'error': f'Error al procesar fechas: {str(e)}'}, status=400)
