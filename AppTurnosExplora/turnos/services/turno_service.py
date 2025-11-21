"""
Servicio para gestión de turnos.

Responsabilidad única: Obtener y procesar información de turnos de exploradores.
"""
from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from turnos.models import AsignarJornadaExplorador, Turno, AsignarSalaExplorador
from turnos.services.jornada_service import JornadaService
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
            
            # 1. Buscar turno específico para esa fecha
            turno = Turno.objects.select_related('jornada', 'sala').filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            ).first()
            
            if turno:
                return {
                    'id': turno.id,
                    'jornada': turno.jornada.nombre,
                    'sala': turno.sala.nombre,
                    'sala_id': turno.sala.id,
                    'hora_inicio': turno.jornada.hora_inicio.strftime('%H:%M'),
                    'hora_fin': turno.jornada.hora_fin.strftime('%H:%M'),
                    'es_turno_virtual': False,
                    'tipo_sala': 'turno'
                }
            
            # 2. Si no hay turno, buscar jornada predeterminada
            jornada_predeterminada = JornadaService.get_jornada_predeterminada(explorador)
            jornada = jornada_predeterminada.jornada if jornada_predeterminada else None
            
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
                    'jornada': jornada.nombre if jornada else None,
                    'sala': asignacion_sala.sala.nombre,
                    'sala_id': asignacion_sala.sala.id,
                    'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada else None,
                    'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada else None,
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
                'jornada': jornada.nombre if jornada else None,
                'sala': None,
                'sala_id': None,
                'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada else None,
                'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada else None,
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