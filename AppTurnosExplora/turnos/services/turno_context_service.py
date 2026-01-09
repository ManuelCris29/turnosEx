"""
Servicio para preparar el contexto de las vistas de turnos.
Responsabilidad única: Construir estructuras de datos para las vistas de turnos.
"""
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from turnos.models import Turno, AsignarSalaExplorador, AsignarJornadaExplorador
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
import logging

logger = logging.getLogger(__name__)


class TurnoContextService:
    """
    Servicio para preparar el contexto de las vistas de turnos.
    Responsabilidad única: Construir estructuras de datos para las vistas.
    """

    @staticmethod
    def _calcular_jornada_dia(j_base, fecha):
        """Calcula la jornada para un día específico considerando descansos."""
        from core.utils.jornada_utils import JornadaUtils
        return JornadaUtils.calcular_jornada_dia(j_base, fecha)

    @staticmethod
    def get_context_data_for_mis_turnos_view(empleado: Empleado) -> dict:
        """
        Prepara el contexto para MisTurnosView.
        
        Args:
            empleado: Empleado autenticado
            
        Returns:
            Diccionario con datos del calendario de turnos
        """
        fecha_actual = timezone.now().date()
        
        # Calcular solo el mes actual para optimizar rendimiento
        inicio_mes = fecha_actual.replace(day=1)
        if fecha_actual.month == 12:
            fin_mes = fecha_actual.replace(year=fecha_actual.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            fin_mes = fecha_actual.replace(month=fecha_actual.month + 1, day=1) - timedelta(days=1)
        
        # Calcular inicio y fin de la semana actual para el resumen semanal
        inicio_semana = fecha_actual - timedelta(days=fecha_actual.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        
        # Obtener turnos asignados solo para el mes actual (optimizado, evitando N+1)
        turnos_mes = (
            Turno.objects
            .filter(
                explorador=empleado,
                fecha__gte=inicio_mes,
                fecha__lte=fin_mes
            )
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
        
        # Obtener asignaciones de sala activas
        asignaciones_activas = AsignarSalaExplorador.objects.filter(
            explorador=empleado,
            fecha_inicio__lte=fecha_actual,
            fecha_fin__gte=fecha_actual
        ).first()
        
        # Obtener jornada predeterminada vigente
        jornada_predeterminada = (
            AsignarJornadaExplorador.objects
            .filter(explorador=empleado)
            .select_related('jornada')
            .order_by('-fecha_inicio')
            .first()
        )
        jornada_base = (
            jornada_predeterminada.jornada.nombre if jornada_predeterminada else None
        )
        
        # Validar que el empleado tenga jornada asignada
        if not jornada_base:
            logger.warning(f"Empleado {empleado.id} ({empleado.nombre} {empleado.apellido}) no tiene jornada asignada")
            # Si no tiene jornada, no podemos calcular turnos predeterminados
            # Retornar estructura vacía o con error
            return {
                'inicio_semana': inicio_semana,
                'fin_semana': fin_semana,
                'turnos_semana': [],
                'turnos_mes': {},
                'turnos_mes_json_str': '{}',
                'asignaciones_activas': None,
                'fecha_actual': fecha_actual,
                'error': 'El empleado no tiene jornada asignada. Todos los exploradores deben tener una jornada (AM o PM) asignada.'
            }
        
        # Crear estructura de datos solo para el mes actual (optimizado)
        turnos_mes_dict = {}
        for i in range((fin_mes - inicio_mes).days + 1):
            fecha = inicio_mes + timedelta(days=i)
            turnos_dia = turnos_por_fecha.get(fecha, [])
            
            if turnos_dia:
                # Hay turno(s) asignado(s) (puede ser cambio aprobado o doblada)
                # Usar helper para detectar dobladas (AM+PM en misma fecha)
                from turnos.services.turno_service import TurnoService
                jornada_display = TurnoService.obtener_jornada_display(empleado, fecha)
                
                from core.utils.jornada_utils import JornadaUtils
                jornada_predeterminada = JornadaUtils.calcular_jornada_dia(jornada_base, fecha)
                
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
                    sala_display = ', '.join(set(salas))
                
                coincide_con_predeterminada = jornada_display == jornada_predeterminada if jornada_display else False
                
                # Usar el primer turno como referencia (para compatibilidad con código existente)
                turno_principal = turnos_dia[0]
                
                turnos_mes_dict[fecha] = {
                    'turno': turno_principal,  # Primer turno (compatibilidad)
                    'turnos': turnos_dia,  # Lista completa de turnos (nuevo)
                    'jornada': jornada_display,  # Usar jornada_display (puede ser 'DOBLADA')
                    'sala': sala_display,
                    'tipo': 'asignado',
                    'es_cambio': es_cambio,
                    'tipo_cambio': tipo_cambio_principal,
                    'es_doblada': es_doblada,  # Flag para frontend
                    'jornada_predeterminada': jornada_predeterminada,
                    'coincide_con_predeterminada': coincide_con_predeterminada,
                    'turno_id': turno_principal.id
                }
            else:
                # No hay turno asignado, usar jornada predeterminada
                from core.utils.jornada_utils import JornadaUtils
                jornada_nombre = JornadaUtils.calcular_jornada_dia(jornada_base, fecha)
                
                # Intentar obtener sala de asignación activa
                sala_nombre = 'Por asignar'
                if asignaciones_activas:
                    sala_nombre = asignaciones_activas.sala.nombre
                
                turnos_mes_dict[fecha] = {
                    'turno': None,
                    'jornada': jornada_nombre,
                    'sala': sala_nombre,
                    'tipo': 'predeterminado',
                    'es_cambio': False,
                    'jornada_predeterminada': jornada_nombre,
                    'coincide_con_predeterminada': True,
                    'turno_id': None
                }
        
        # Crear estructura de datos para la semana actual (resumen semanal)
        semana_turnos = {}
        for i in range(7):
            fecha = inicio_semana + timedelta(days=i)
            if fecha in turnos_mes_dict:
                semana_turnos[fecha] = turnos_mes_dict[fecha]
            else:
                # Si la fecha no está en el mes actual, usar regla predeterminada
                from core.utils.jornada_utils import JornadaUtils
                jornada_nombre = JornadaUtils.calcular_jornada_dia(jornada_base, fecha)
                
                semana_turnos[fecha] = {
                    'turno': None,
                    'jornada': jornada_nombre,
                    'sala': 'Por asignar',
                    'tipo': 'predeterminado',
                    'es_cambio': False,
                    'jornada_predeterminada': jornada_nombre,
                    'coincide_con_predeterminada': True,
                    'turno_id': None
                }
        
        # Obtener información de solicitudes para turnos con cambios (optimizado)
        # Solo obtener la solicitud MÁS RECIENTE para cada turno
        turnos_con_cambio = [info['turno'] for info in turnos_mes_dict.values() 
                            if info.get('turno') and info.get('es_cambio')]
        solicitudes_info = {}
        if turnos_con_cambio:
            turno_ids = [t.id for t in turnos_con_cambio]
            # Limitar a las 50 solicitudes más recientes para evitar consultas lentas
            solicitudes = SolicitudCambio.objects.filter(
                Q(turno_origen_id__in=turno_ids) | Q(turno_destino_id__in=turno_ids),
                estado='aprobada'
            ).select_related('explorador_solicitante', 'explorador_receptor').order_by('-fecha_resolucion', '-id')[:50]
            
            # Procesar solicitudes en orden descendente (más reciente primero)
            for solicitud in solicitudes:
                # Para turno_origen (solicitante)
                if solicitud.turno_origen_id and solicitud.turno_origen_id in turno_ids:
                    if solicitud.turno_origen_id not in solicitudes_info:
                        solicitudes_info[solicitud.turno_origen_id] = {
                            'solicitud_id': solicitud.id,
                            'companero_nombre': solicitud.explorador_receptor.nombre,
                            'rol': 'solicitante',
                            'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None
                        }
                
                # Para turno_destino (receptor)
                if solicitud.turno_destino_id and solicitud.turno_destino_id in turno_ids:
                    if solicitud.turno_destino_id not in solicitudes_info:
                        solicitudes_info[solicitud.turno_destino_id] = {
                            'solicitud_id': solicitud.id,
                            'companero_nombre': solicitud.explorador_solicitante.nombre,
                            'rol': 'receptor',
                            'fecha_resolucion': solicitud.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_resolucion else None
                        }
        
        # Convertir fechas a strings para JSON (solo mes actual)
        turnos_mes_json = {}
        for fecha, info in turnos_mes_dict.items():
            turno_id = info.get('turno_id')
            solicitud_info = solicitudes_info.get(turno_id) if turno_id else None
            
            turnos_mes_json[fecha.strftime('%Y-%m-%d')] = {
                'jornada': info['jornada'],
                'sala': info['sala'],
                'tipo': info['tipo'],
                'es_cambio': info['es_cambio'],
                'jornada_predeterminada': info.get('jornada_predeterminada', info['jornada']),
                'coincide_con_predeterminada': info.get('coincide_con_predeterminada', True),
                'turno_id': turno_id,
                'solicitud_info': solicitud_info
            }
        
        # Convertir semana_turnos a formato JSON
        semana_turnos_json = {}
        for fecha, info in semana_turnos.items():
            turno_id = info.get('turno_id')
            solicitud_info = solicitudes_info.get(turno_id) if turno_id else None
            
            semana_turnos_json[fecha.strftime('%Y-%m-%d')] = {
                'jornada': info['jornada'],
                'sala': info['sala'],
                'tipo': info['tipo'],
                'es_cambio': info['es_cambio'],
                'jornada_predeterminada': info.get('jornada_predeterminada', info['jornada']),
                'coincide_con_predeterminada': info.get('coincide_con_predeterminada', True),
                'turno_id': turno_id,
                'solicitud_info': solicitud_info
            }
        
        import json
        
        return {
            'turnos_mes': turnos_mes_dict,
            'turnos_semana': semana_turnos,
            'turnos_mes_json': turnos_mes_json,
            'semana_turnos_json': semana_turnos_json,
            'turnos_mes_json_str': json.dumps(turnos_mes_json),
            'inicio_mes': inicio_mes,
            'fin_mes': fin_mes,
            'fecha_actual': fecha_actual,
            'inicio_semana': inicio_semana,
            'fin_semana': fin_semana,
            'jornada_base': jornada_base,
            'asignaciones_activas': asignaciones_activas
        }

