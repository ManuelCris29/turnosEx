"""
Servicio para gestión de disponibilidad de empleados.

Responsabilidad única: Buscar y filtrar empleados según criterios de disponibilidad.
"""
from django.db.models import Q
from empleados.models import Empleado
from turnos.models import Turno, AsignarJornadaExplorador
from datetime import datetime
import logging
from core.interfaces import IEmpleadoDisponibilidadService

logger = logging.getLogger(__name__)


class EmpleadoDisponibilidadService(IEmpleadoDisponibilidadService):
    """
    Servicio para obtener empleados disponibles según diferentes criterios.
    
    Responsabilidad única: Búsqueda y filtrado de empleados por disponibilidad.
    """
    
    @staticmethod
    def get_empleados_disponibles(fecha, usuario_actual=None, solo_jornada_contraria=False):
        """
        Obtiene los empleados disponibles para una fecha específica.
        
        Args:
            fecha: Fecha para la cual buscar empleados (string 'YYYY-MM-DD')
            usuario_actual: Usuario actual (para excluirlo de la lista)
            solo_jornada_contraria: Si True, solo devuelve empleados de jornada contraria
        
        Returns:
            QuerySet de Empleado disponibles
        """
        if solo_jornada_contraria:
            return EmpleadoDisponibilidadService.get_empleados_jornada_contraria(fecha, usuario_actual)
        
        # Lógica original: todos los empleados activos
        # Optimización: solo los campos necesarios y relaciones frecuentes
        empleados = (
            Empleado.objects
            .filter(activo=True)
            .select_related('supervisor')
        )
        
        # Excluir al usuario actual si se proporciona
        if usuario_actual and hasattr(usuario_actual, 'empleado'):
            empleados = empleados.exclude(id=usuario_actual.empleado.id)
        
        return empleados

    @staticmethod
    def get_empleados_jornada_contraria(fecha, usuario_actual=None):
        """
        Obtiene los empleados que están en la jornada contraria al usuario actual
        para una fecha específica.
        
        Args:
            fecha: Fecha para la cual buscar (string 'YYYY-MM-DD')
            usuario_actual: Usuario actual (User o Empleado)
        
        Returns:
            Lista de Empleado con jornada contraria
        """
        # Importar aquí para evitar dependencia circular
        from turnos.services.jornada_service import JornadaService
        
        logger.debug("get_empleados_jornada_contraria", extra={
            'fecha': fecha,
            'usuario_id': getattr(getattr(usuario_actual, 'empleado', None), 'id', None)
        })
        
        # Verificar si es un objeto Empleado o User
        if isinstance(usuario_actual, Empleado):
            empleado_actual = usuario_actual
        elif hasattr(usuario_actual, 'empleado'):
            empleado_actual = usuario_actual.empleado
        else:
            logger.debug("No hay usuario actual o no tiene empleado asociado")
            return Empleado.objects.none()
        
        # Obtener la jornada del usuario actual para esa fecha
        jornada_usuario = JornadaService.get_jornada_explorador_fecha(
            empleado_actual.id, fecha
        )
        
        logger.debug("jornada_usuario", extra={'jornada': getattr(jornada_usuario, 'nombre', None)})
        
        if not jornada_usuario:
            logger.debug("Usuario no tiene jornada asignada")
            return Empleado.objects.none()
        
        # Determinar la jornada contraria
        jornada_contraria = None
        if jornada_usuario.nombre == 'AM':
            jornada_contraria = 'PM'
        elif jornada_usuario.nombre == 'PM':
            jornada_contraria = 'AM'
        else:
            # Si no es AM ni PM, no hay jornada contraria definida
            logger.debug(f"Jornada no reconocida: {jornada_usuario.nombre}")
            return Empleado.objects.none()
        
        logger.debug("jornada_contraria", extra={'jornada_contraria': jornada_contraria})
        
        # Buscar empleados que tengan la jornada contraria asignada
        empleados_contrarios = []
        empleados_activos = (
            Empleado.objects
            .filter(activo=True)
            .exclude(id=empleado_actual.id)
            .select_related('supervisor')
        )
        
        logger.debug("empleados_activos_count", extra={'count': empleados_activos.count()})
        
        # OPTIMIZACIÓN - Pre-cargar Turnos de la fecha en una sola consulta
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        ids_empleados_activos = list(empleados_activos.values_list('id', flat=True))
        
        # Consulta batch: traer todos los Turnos de la fecha para los empleados activos
        turnos_fecha = Turno.objects.filter(
            fecha=fecha_obj,
            explorador_id__in=ids_empleados_activos
        ).select_related('jornada', 'explorador')
        
        # Crear diccionario para acceso rápido: {explorador_id: turno}
        turnos_por_explorador = {
            turno.explorador_id: turno
            for turno in turnos_fecha
        }
        
        logger.debug("turnos_precargados_count", extra={'count': len(turnos_por_explorador)})
        
        # OPTIMIZACIÓN - Pre-cargar Asignaciones de Jornada en una sola consulta
        # Traer todas las asignaciones relevantes (fecha_inicio <= fecha_obj)
        asignaciones_fecha = AsignarJornadaExplorador.objects.filter(
            explorador_id__in=ids_empleados_activos,
            fecha_inicio__lte=fecha_obj
        ).select_related('jornada', 'explorador').order_by('explorador', '-fecha_inicio')
        
        # Agrupar por explorador y tomar la más reciente (primera de cada grupo por orden DESC)
        asignaciones_por_explorador = {}
        for asignacion in asignaciones_fecha:
            # Solo guardar la primera (más reciente) para cada explorador
            if asignacion.explorador_id not in asignaciones_por_explorador:
                asignaciones_por_explorador[asignacion.explorador_id] = asignacion
        
        logger.debug("asignaciones_precargadas_count", extra={'count': len(asignaciones_por_explorador)})
        
        # OPTIMIZACIÓN - Procesar en memoria usando datos pre-cargados
        # Iterar sobre empleados y buscar jornada en diccionarios (sin consultas DB)
        for empleado in empleados_activos:
            jornada_empleado = None
            
            # 1. Buscar primero en Turnos (cambios aprobados tienen prioridad)
            turno = turnos_por_explorador.get(empleado.id)
            if turno:
                jornada_empleado = turno.jornada
            else:
                # 2. Si no hay turno, buscar en asignaciones fijas
                asignacion = asignaciones_por_explorador.get(empleado.id)
                if asignacion:
                    jornada_empleado = asignacion.jornada
            
            # 3. Comparar jornada con jornada contraria
            if jornada_empleado and jornada_empleado.nombre == jornada_contraria:
                empleados_contrarios.append(empleado)
        
        logger.debug("empleados_contrarios_count", extra={'count': len(empleados_contrarios)})
        return empleados_contrarios

