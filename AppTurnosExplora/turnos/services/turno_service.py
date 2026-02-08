"""
Servicio para gestión de turnos.

Responsabilidad única: Obtener y procesar información de turnos de exploradores.
"""
from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from turnos.models import AsignarJornadaExplorador, Turno, AsignarSalaExplorador
from turnos.services.jornada_service import JornadaService
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from core.utils.jornada_utils import JornadaUtils
from datetime import datetime, timedelta
from django.db.models import Q
import re
import logging
from core.interfaces import ITurnoService

logger = logging.getLogger(__name__)


class TurnoService(ITurnoService):
    @staticmethod
    def get_exploradores_por_jornada(fecha):
        fecha_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha).group(0)
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        exploradores = Empleado.objects.filter(activo=True)
        am, pm = [], []
        for explorador in exploradores:
            turno = Turno.objects.filter(explorador=explorador, fecha=fecha_obj).first()
            if turno:
                jornada = turno.jornada
                tipo = 'cambio'
            else:
                # Las jornadas son indefinidas por defecto (sin fecha_fin)
                asignacion = AsignarJornadaExplorador.objects.filter(
                    explorador=explorador,
                    fecha_inicio__lte=fecha_obj
                ).order_by('-fecha_inicio').first()
                jornada = asignacion.jornada if asignacion else None
                tipo = 'oficial' if jornada else None
            if jornada:
                item = {'id': explorador.id, 'nombre': explorador.nombre, 'apellido': explorador.apellido, 'tipo': tipo}
                if jornada.nombre.strip().lower() == 'am':
                    am.append(item)
                elif jornada.nombre.strip().lower() == 'pm':
                    pm.append(item)
        return {'am': am, 'pm': pm}

    @staticmethod
    def get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin):
        inicio_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha_inicio).group(0)
        fin_str = re.match(r"\d{4}-\d{2}-\d{2}", fecha_fin).group(0)
        inicio = datetime.strptime(inicio_str, '%Y-%m-%d').date()
        fin = datetime.strptime(fin_str, '%Y-%m-%d').date()
        dias = (fin - inicio).days + 1
        resultado = {}
        for i in range(dias):
            dia = inicio + timedelta(days=i)
            resultado[str(dia)] = TurnoService.get_exploradores_por_jornada(str(dia))
        return resultado
    
    @staticmethod
    def get_turno_explorador(explorador_id, fecha):
        """
        Obtiene el turno de un explorador para una fecha específica.
        
        Prioridad:
        1. Turno específico para esa fecha
        2. Jornada predeterminada con asignación de sala especial
        3. Jornada predeterminada con salas de competencia
        
        Args:
            explorador_id: ID del explorador
            fecha: Fecha en formato string 'YYYY-MM-DD'
        
        Returns:
            Diccionario con información del turno o None si hay error
        """
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            explorador = Empleado.objects.get(id=explorador_id)
            
            # 1. Buscar turnos específicos para esa fecha (puede haber múltiples si es doblada)
            turnos = Turno.objects.select_related('jornada', 'sala').filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            )
            
            if turnos.exists():
                # Usar helper para obtener jornada display (detecta dobladas)
                jornada_display = TurnoService.obtener_jornada_display(explorador, fecha_obj)
                
                # Obtener el primer turno para datos de sala y horarios
                turno = turnos.first()
                
                # Si es doblada, obtener horarios combinados (AM inicio, PM fin)
                if jornada_display == 'DOBLADA':
                    turno_am = turnos.filter(jornada__nombre__iexact='AM').first()
                    turno_pm = turnos.filter(jornada__nombre__iexact='PM').first()
                    hora_inicio = turno_am.jornada.hora_inicio.strftime('%H:%M') if turno_am else turno.jornada.hora_inicio.strftime('%H:%M')
                    hora_fin = turno_pm.jornada.hora_fin.strftime('%H:%M') if turno_pm else turno.jornada.hora_fin.strftime('%H:%M')
                else:
                    hora_inicio = turno.jornada.hora_inicio.strftime('%H:%M')
                    hora_fin = turno.jornada.hora_fin.strftime('%H:%M')
                
                return {
                    'id': turno.id,
                    'jornada': jornada_display,  # 'DOBLADA', 'AM', o 'PM'
                    'sala': turno.sala.nombre,
                    'sala_id': turno.sala.id,
                    'hora_inicio': hora_inicio,
                    'hora_fin': hora_fin,
                    'es_turno_virtual': False,
                    'tipo_sala': 'turno',
                    'es_doblada': jornada_display == 'DOBLADA'
                }
            
            # 2. Si no hay turno, calcular jornada usando alternancia de fines de semana
            jornada_predeterminada = JornadaService.get_jornada_predeterminada(explorador)
            jornada_base_obj = jornada_predeterminada.jornada if jornada_predeterminada else None
            
            # Calcular jornada real del día (considera alternancia de fines de semana)
            jornada_dia = None
            if jornada_base_obj:
                try:
                    jornada_dia_calculada = JornadaUtils.calcular_jornada_dia(
                        jornada_base_obj.nombre, fecha_obj
                    )
                    # Si está en descanso, retornar None (no tiene jornada ese día)
                    if jornada_dia_calculada == "Descanso":
                        jornada_dia = None
                    else:
                        # Buscar objeto Jornada con el nombre calculado
                        jornada_dia = Jornada.objects.filter(nombre=jornada_dia_calculada).first()
                except Exception as e:
                    logger.warning(f"Error calculando jornada día para {explorador.id} en {fecha_obj}: {e}")
                    jornada_dia = jornada_base_obj  # Fallback a jornada base
            
            # Si está en descanso (jornada_dia es None), retornar None
            if jornada_dia is None:
                return None
            
            # 2b. Sábado: si por alternancia le corresponde trabajar ese sábado, mostrar DOBLADA (AM+PM)
            if fecha_obj.weekday() == 5:
                jornada_trabaja_sab = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha_obj)
                if jornada_trabaja_sab and jornada_dia.nombre.upper() == jornada_trabaja_sab.upper():
                    jornada_am = Jornada.objects.filter(nombre__iexact='AM').first()
                    jornada_pm = Jornada.objects.filter(nombre__iexact='PM').first()
                    if jornada_am and jornada_pm:
                        competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
                        salas_competencia = [{'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias]
                        return {
                            'id': None,
                            'jornada': 'DOBLADA',
                            'sala': None,
                            'sala_id': None,
                            'hora_inicio': jornada_am.hora_inicio.strftime('%H:%M') if jornada_am.hora_inicio else None,
                            'hora_fin': jornada_pm.hora_fin.strftime('%H:%M') if jornada_pm.hora_fin else None,
                            'es_turno_virtual': True,
                            'tipo_sala': 'competencia',
                            'salas_competencia': salas_competencia,
                            'es_doblada_sabado': True,
                        }
            
            # 3. Buscar sala asignada especial para ese día
            asignacion_sala = AsignarSalaExplorador.objects.select_related('sala').filter(
                explorador=explorador,
                fecha_inicio__lte=fecha_obj
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_obj)
            ).order_by('-fecha_inicio').first()
            
            if asignacion_sala:
                return {
                    'id': None,
                    'jornada': jornada_dia.nombre if jornada_dia else None,
                    'sala': asignacion_sala.sala.nombre,
                    'sala_id': asignacion_sala.sala.id,
                    'hora_inicio': jornada_dia.hora_inicio.strftime('%H:%M') if jornada_dia and jornada_dia.hora_inicio else None,
                    'hora_fin': jornada_dia.hora_fin.strftime('%H:%M') if jornada_dia and jornada_dia.hora_fin else None,
                    'es_turno_virtual': True,
                    'tipo_sala': 'asignacion_especial'
                }
            
            # 4. Si no hay asignación especial, usar todas las salas de competencia
            competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
            salas_competencia = [
                {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
            ]
            return {
                'id': None,
                'jornada': jornada_dia.nombre if jornada_dia else None,
                'sala': None,
                'sala_id': None,
                'hora_inicio': jornada_dia.hora_inicio.strftime('%H:%M') if jornada_dia and jornada_dia.hora_inicio else None,
                'hora_fin': jornada_dia.hora_fin.strftime('%H:%M') if jornada_dia and jornada_dia.hora_fin else None,
                'es_turno_virtual': True,
                'tipo_sala': 'competencia',
                'salas_competencia': salas_competencia
            }
        except ValueError:
            return None
    
    @staticmethod
    def get_salas_explorador(explorador_id):
        """
        Obtiene las salas asignadas a un explorador.
        
        Args:
            explorador_id: ID del explorador
        
        Returns:
            QuerySet de CompetenciaEmpleado
        """
        return CompetenciaEmpleado.objects.filter(
            empleado_id=explorador_id
        ).select_related('sala')
    
    @staticmethod
    def get_turnos_por_fecha(explorador, fecha_inicio, fecha_fin):
        """
        Obtiene turnos de un explorador en un rango de fechas.
        
        Args:
            explorador: Objeto Empleado
            fecha_inicio: Fecha de inicio (date object)
            fecha_fin: Fecha de fin (date object)
        
        Returns:
            Diccionario {fecha: turno} para acceso rápido
        """
        turnos = (
            Turno.objects
            .filter(
                explorador=explorador,
                fecha__gte=fecha_inicio,
                fecha__lte=fecha_fin
            )
            .select_related('jornada', 'sala')
            .order_by('fecha')
        )
        return {t.fecha: t for t in turnos}
    
    @staticmethod
    def obtener_jornada_display(explorador: Empleado, fecha) -> str:
        """
        Obtiene la jornada para mostrar en UI.
        
        Si hay AM+PM en la misma fecha → "DOBLADA"
        Si hay solo AM → "AM"
        Si hay solo PM → "PM"
        Si no hay turnos → jornada predeterminada
        
        Args:
            explorador: Instancia de Empleado
            fecha: Fecha (date object o string 'YYYY-MM-DD')
        
        Returns:
            String con la jornada para mostrar: 'DOBLADA', 'AM', 'PM', o jornada predeterminada
        """
        from datetime import date as date_type
        
        # Convertir fecha a objeto date si es string
        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        elif isinstance(fecha, date_type):
            fecha_obj = fecha
        else:
            fecha_obj = fecha
        
        # Obtener todos los turnos del explorador en esa fecha
        turnos = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha_obj
        ).select_related('jornada')
        
        jornadas = [t.jornada.nombre.upper() for t in turnos]
        
        # Si hay AM+PM → DOBLADA
        if 'AM' in jornadas and 'PM' in jornadas:
            return 'DOBLADA'
        elif 'AM' in jornadas:
            return 'AM'
        elif 'PM' in jornadas:
            return 'PM'
        else:
            # No hay turnos, calcular jornada usando alternancia de fines de semana
            jornada_predeterminada = JornadaService.get_jornada_explorador_fecha(
                explorador.id, fecha_obj.strftime('%Y-%m-%d')
            )
            if jornada_predeterminada:
                try:
                    # Usar JornadaUtils para calcular jornada real del día (considera alternancia)
                    jornada_dia_calculada = JornadaUtils.calcular_jornada_dia(
                        jornada_predeterminada.nombre, fecha_obj
                    )
                    # Si está en descanso, retornar None (no tiene jornada ese día)
                    if jornada_dia_calculada == "Descanso":
                        return None
                    return jornada_dia_calculada.upper()
                except Exception as e:
                    logger.warning(f"Error calculando jornada día para {explorador.id} en {fecha_obj}: {e}")
                    # Fallback a jornada predeterminada si hay error
                    return jornada_predeterminada.nombre.upper()
            return None