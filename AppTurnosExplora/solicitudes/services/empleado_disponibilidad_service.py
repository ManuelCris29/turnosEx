"""
Servicio para gestión de disponibilidad de empleados.

Responsabilidad única: Buscar y filtrar empleados según criterios de disponibilidad.
"""
import logging

from core.interfaces import IEmpleadoDisponibilidadService
from core.utils.date_utils import DateUtils
from empleados.models import Empleado
from turnos.models import AsignarJornadaExplorador, Turno

logger = logging.getLogger(__name__)


class EmpleadoDisponibilidadService(IEmpleadoDisponibilidadService):
    """
    Servicio para obtener empleados disponibles según diferentes criterios.
    
    Responsabilidad única: Búsqueda y filtrado de empleados por disponibilidad.
    """
    
    @staticmethod
    def get_empleados_disponibles(fecha, usuario_actual=None, solo_jornada_contraria=False):
        """
        Obtiene los empleados candidatos, opcionalmente filtrados por jornada contraria.

        Args:
            fecha: Fecha para la cual buscar empleados (string 'YYYY-MM-DD'). OJO: solo se usa
                cuando `solo_jornada_contraria=True`. En el caso por defecto la lista es la de
                todos los activos no administradores, sin ningún filtro por día: quien necesite
                disponibilidad REAL por fecha debe evaluarla aparte (p. ej. el CT permanente lo
                hace día a día con `razones_exclusion_ct_permanente`).
            usuario_actual: Usuario actual (para excluirlo de la lista)
            solo_jornada_contraria: Si True, solo devuelve empleados de jornada contraria

        Returns:
            QuerySet de Empleado
        """
        if solo_jornada_contraria:
            return EmpleadoDisponibilidadService.get_empleados_jornada_contraria(fecha, usuario_actual)
        
        # Lógica original: todos los empleados activos (no administradores)
        # El modelo Empleado tiene relación 'user' (OneToOneField a User), no 'usuario'
        empleados = (
            Empleado.objects
            .filter(
                activo=True,
                user__is_staff=False,
                user__is_superuser=False
            )
            .select_related('supervisor')
        )
        
        # Excluir al usuario actual si se proporciona (Empleado o User con .empleado)
        if usuario_actual:
            if isinstance(usuario_actual, Empleado):
                empleados = empleados.exclude(id=usuario_actual.id)
            elif hasattr(usuario_actual, 'empleado') and usuario_actual.empleado:
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
        
        logger.info("get_empleados_jornada_contraria - Iniciando", extra={
            'fecha': fecha,
            'usuario_id': getattr(getattr(usuario_actual, 'empleado', None), 'id', None),
            'usuario_tipo': type(usuario_actual).__name__
        })
        
        # Verificar si es un objeto Empleado o User
        if isinstance(usuario_actual, Empleado):
            empleado_actual = usuario_actual
        elif hasattr(usuario_actual, 'empleado'):
            empleado_actual = usuario_actual.empleado
        else:
            logger.warning("get_empleados_jornada_contraria - No hay usuario actual o no tiene empleado asociado", extra={
                'usuario_actual': str(usuario_actual) if usuario_actual else None
            })
            return Empleado.objects.none()
        
        logger.info("get_empleados_jornada_contraria - Empleado actual identificado", extra={
            'empleado_id': empleado_actual.id,
            'empleado_nombre': empleado_actual.nombre
        })
        
        # Jornada REAL del usuario ese día (fuente de verdad estado_dia, igual que Mis Turnos).
        # Si ese día trabaja DOBLADA (día completo) o descansa, no hay "jornada contraria"
        # para un CT sencillo: se devuelve vacío (la validación del servidor igual lo bloquearía).
        from turnos.services.turno_service import TurnoService as _TS
        _fecha_obj = DateUtils.parse_date(fecha) if isinstance(fecha, str) else fecha
        _estado = _TS.estado_dia(empleado_actual, _fecha_obj)
        _jornada_real = _estado['jornada'] if _estado['trabaja'] else None

        logger.info("get_empleados_jornada_contraria - Jornada REAL del usuario", extra={
            'jornada_real': _jornada_real,
            'fuente': _estado['fuente'],
            'trabaja': _estado['trabaja'],
        })

        if not _estado['trabaja']:
            logger.warning("get_empleados_jornada_contraria - El usuario no trabaja ese día (%s)",
                           _estado.get('motivo'), extra={'empleado_id': empleado_actual.id, 'fecha': fecha})
            return Empleado.objects.none()

        # Determinar la jornada contraria a partir de la jornada REAL
        if _jornada_real == 'AM':
            jornada_contraria = 'PM'
        elif _jornada_real == 'PM':
            jornada_contraria = 'AM'
        else:
            # DOBLADA (día completo): un CT sencillo no aplica ese día
            logger.warning("get_empleados_jornada_contraria - Jornada %s sin contraria (día completo)",
                           _jornada_real, extra={'empleado_id': empleado_actual.id})
            return Empleado.objects.none()
        
        logger.info("get_empleados_jornada_contraria - Jornada contraria determinada", extra={
            'jornada_usuario': _jornada_real,
            'jornada_contraria': jornada_contraria
        })
        
        # Buscar empleados que tengan la jornada contraria asignada
        empleados_contrarios = []
        empleados_activos = (
            Empleado.objects
            .filter(activo=True)
            .exclude(id=empleado_actual.id)
            .select_related('supervisor')
        )
        
        total_activos = empleados_activos.count()
        logger.info("get_empleados_jornada_contraria - Empleados activos encontrados", extra={
            'total_activos': total_activos,
            'excluyendo_empleado_id': empleado_actual.id
        })
        
        if total_activos == 0:
            logger.warning("get_empleados_jornada_contraria - No hay empleados activos disponibles")
            return empleados_contrarios
        
        # OPTIMIZACIÓN - Pre-cargar Turnos de la fecha en una sola consulta
        fecha_obj = DateUtils.parse_date(fecha)
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

        logger.info("get_empleados_jornada_contraria - Turnos pre-cargados", extra={
            'total_turnos': len(turnos_por_explorador),
            'fecha': str(fecha_obj)
        })

        # Pre-cargar IDs de empleados que descansan por solicitud aprobada (L2).
        # Solo afecta a empleados sin Turno real (si hay Turno en DB, L1 ya es la fuente de verdad).
        # Dos queries batch en lugar de N llamadas a estado_dia().
        from solicitudes.models import SolicitudCambio as _SC
        _ids_sin_turno = set(ids_empleados_activos) - set(turnos_por_explorador.keys())
        _descansando_por_solicitud = set()
        if _ids_sin_turno:
            # Cedió su jornada ese día
            _descansando_por_solicitud.update(
                _SC.objects.filter(
                    tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                    estado='aprobada',
                    explorador_solicitante_id__in=_ids_sin_turno,
                    fecha_cambio_turno=fecha_obj,
                ).values_list('explorador_solicitante_id', flat=True)
            )
            # Paga doblada ese día (receptor descansa mientras el solicitante dobla)
            _descansando_por_solicitud.update(
                _SC.objects.filter(
                    tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                    estado='aprobada',
                    explorador_receptor_id__in=_ids_sin_turno,
                    doblada__fecha_pago=fecha_obj,
                ).values_list('explorador_receptor_id', flat=True)
            )
        logger.info("get_empleados_jornada_contraria - Empleados descansando por solicitud (L2): %d", len(_descansando_por_solicitud))
        
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
        
        logger.info("get_empleados_jornada_contraria - Asignaciones pre-cargadas", extra={
            'total_asignaciones': len(asignaciones_por_explorador)
        })
        
        # Contadores para diagnóstico
        empleados_con_turno = 0
        empleados_con_asignacion = 0
        empleados_sin_jornada = 0
        empleados_jornada_incorrecta = 0
        
        # OPTIMIZACIÓN - Procesar en memoria usando datos pre-cargados
        # Iterar sobre empleados y buscar jornada en diccionarios (sin consultas DB)
        for empleado in empleados_activos:
            jornada_empleado = None
            fuente_jornada = None
            
            # 1. Buscar primero en Turnos (cambios aprobados tienen prioridad)
            turno = turnos_por_explorador.get(empleado.id)
            if turno:
                jornada_empleado = turno.jornada
                fuente_jornada = 'Turno'
                empleados_con_turno += 1
            elif empleado.id in _descansando_por_solicitud:
                # L2: el empleado descansa ese día por solicitud aprobada — excluirlo del picker
                logger.debug("get_empleados_jornada_contraria - Empleado descansa por solicitud L2, excluido", extra={
                    'empleado_id': empleado.id,
                    'empleado_nombre': empleado.nombre
                })
                continue
            else:
                # 2. Si no hay turno ni solicitud que lo comprometa, buscar en asignaciones fijas
                asignacion = asignaciones_por_explorador.get(empleado.id)
                if asignacion:
                    jornada_empleado = asignacion.jornada
                    fuente_jornada = 'Asignacion'
                    empleados_con_asignacion += 1
                else:
                    empleados_sin_jornada += 1
                    logger.debug("get_empleados_jornada_contraria - Empleado sin jornada", extra={
                        'empleado_id': empleado.id,
                        'empleado_nombre': empleado.nombre
                    })
            
            # 3. Comparar jornada con jornada contraria
            if jornada_empleado:
                if jornada_empleado.nombre == jornada_contraria:
                    empleados_contrarios.append(empleado)
                    logger.debug("get_empleados_jornada_contraria - Empleado compatible encontrado", extra={
                        'empleado_id': empleado.id,
                        'empleado_nombre': empleado.nombre,
                        'jornada_empleado': jornada_empleado.nombre,
                        'jornada_contraria': jornada_contraria,
                        'fuente': fuente_jornada
                    })
                else:
                    empleados_jornada_incorrecta += 1
                    logger.debug("get_empleados_jornada_contraria - Empleado con jornada incorrecta", extra={
                        'empleado_id': empleado.id,
                        'empleado_nombre': empleado.nombre,
                        'jornada_empleado': jornada_empleado.nombre,
                        'jornada_contraria': jornada_contraria,
                        'fuente': fuente_jornada
                    })
        
        logger.info("get_empleados_jornada_contraria - Resumen de búsqueda", extra={
            'total_activos': total_activos,
            'con_turno': empleados_con_turno,
            'con_asignacion': empleados_con_asignacion,
            'sin_jornada': empleados_sin_jornada,
            'jornada_incorrecta': empleados_jornada_incorrecta,
            'compatibles': len(empleados_contrarios),
            'jornada_buscada': jornada_contraria
        })
        
        return empleados_contrarios

