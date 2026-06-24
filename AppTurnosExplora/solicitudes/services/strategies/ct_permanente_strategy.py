"""
CT Permanente Strategy - Implementation for "CT PERMANENTE" solicitud type

This strategy implements the specific logic for "CT PERMANENTE" solicitudes,
which are requests for permanent shift changes.
"""

import logging
from typing import Dict, Any, Tuple, Optional, List, Set
from datetime import date, timedelta
from solicitudes.models import SolicitudCambio, CambioPermanenteDetalle, CambioPermanenteDia
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from core.services import get_empleado_disponibilidad_service, get_turno_service

logger = logging.getLogger(__name__)


class CTPermanenteStrategy(SolicitudStrategy):
    """
    Strategy for "CT PERMANENTE" solicitudes.
    
    This implements the specific logic for permanent shift change requests,
    including validation, creation, and application of changes.
    """
    
    def __init__(self):
        super().__init__("CT PERMANENTE")
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate CT permanente specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance
                - fecha_inicio: Date string
                - fecha_fin: Date string (optional)
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_validator import SolicitudValidator
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha_inicio = datos.get('fecha_inicio')
            fecha_fin = datos.get('fecha_fin')
            dias_seleccionados = datos.get('dias_seleccionados', {})
            comentario = datos.get('comentario') or ''
            
            # Validar datos básicos
            if not all([explorador_solicitante, explorador_receptor, fecha_inicio, fecha_fin]):
                return False, "Faltan datos requeridos para la validación (fecha_fin es obligatoria)"
            
            # Validaciones básicas (empleados activos, no mismo empleado)
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            # Comentario obligatorio
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de cambio de turno permanente')
            
            # Validaciones específicas de CT PERMANENTE
            SolicitudValidator.validar_fechas_cambio_permanente(fecha_inicio, fecha_fin)
            
            # Validar días seleccionados si existen
            if dias_seleccionados:
                SolicitudValidator.validar_dias_seleccionados_permanente(fecha_inicio, fecha_fin, dias_seleccionados)
            
            # Validar jornadas contrarias:
            # - Si hay fechas_especificas, omitir validación (ya se evaluó día a día en get_empleados_disponibles)
            # - Si no hay fechas_especificas, validar que haya al menos un día en el rango con jornadas contrarias
            fechas_especificas = dias_seleccionados.get('fechas_especificas', []) if dias_seleccionados else []
            if not fechas_especificas:
                # No hay fechas específicas, validar jornadas contrarias en todo el rango
                SolicitudValidator.validar_jornada_contraria_rango_permanente(
                    explorador_solicitante, 
                    explorador_receptor, 
                    fecha_inicio, 
                    fecha_fin,
                    dias_seleccionados if dias_seleccionados else None
                )
            # Si hay fechas_especificas, confiar en la evaluación previa del sistema de compatibilidad parcial
            
            # Validar rango completo (todos los días o días seleccionados)
            SolicitudValidator.validar_rango_completo_cambio_permanente(
                explorador_solicitante, 
                explorador_receptor, 
                fecha_inicio, 
                fecha_fin,
                dias_seleccionados if dias_seleccionados else None
            )
            
            # Validar superposición con otros cambios permanentes
            SolicitudValidator.validar_no_cambio_permanente_superpuesto(
                explorador_solicitante, explorador_receptor, fecha_inicio, fecha_fin
            )
            
            return True, "Solicitud de CT permanente válida"
            
        except Exception as e:
            return False, str(e)
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a CT permanente solicitud.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            from django.utils import timezone
            from datetime import datetime
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_inicio = datos.get('fecha_inicio')
            fecha_fin = datos.get('fecha_fin')
            dias_seleccionados = datos.get('dias_seleccionados', {})  # Dict con 'fechas_especificas' y 'dias_semana'
            
            # Convert fecha_inicio to date for the main solicitud
            fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            
            # Create the main solicitud
            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_inicio_obj,  # Use fecha_inicio as the main date
                estado='pendiente'
            )
            
            # Create the CT permanente detail
            fecha_fin_obj = None
            if fecha_fin:
                fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            
            detalle = CambioPermanenteDetalle.objects.create(
                solicitud=solicitud,
                fecha_inicio=fecha_inicio_obj,
                fecha_fin=fecha_fin_obj
            )
            
            # Crear registros de días seleccionados si existen
            if dias_seleccionados:
                dias_semana = dias_seleccionados.get('dias_semana', [])
                fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
                
                # Crear registros para días de semana
                for dia_semana in dias_semana:
                    CambioPermanenteDia.objects.create(
                        cambio_permanente=detalle,
                        dia_semana=int(dia_semana),
                        tipo='dia_semana'
                    )
                
                # Crear registros para fechas específicas (compatibilidad parcial)
                for fecha_str in fechas_especificas:
                    try:
                        if isinstance(fecha_str, str):
                            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                        else:
                            fecha_obj = fecha_str
                        
                        CambioPermanenteDia.objects.create(
                            cambio_permanente=detalle,
                            fecha_especifica=fecha_obj,
                            tipo='fecha_especifica'
                        )
                    except (ValueError, TypeError) as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Error procesando fecha específica {fecha_str}: {e}")
                        continue
            
            # Crear notificaciones y enviar emails
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Error creando notificaciones para CT PERMANENTE")
            
            return solicitud, "Solicitud de CT permanente creada correctamente"
            
        except Exception as e:
            return None, f"Error creando solicitud de CT permanente: {str(e)}"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply permanent change when solicitud is approved.
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        try:
            from datetime import datetime, date, timedelta
            from turnos.models import AsignarJornadaExplorador, Turno
            from django.utils import timezone
            
            # Obtener el detalle del cambio permanente
            detalle = solicitud.cambio_permanente
            if not detalle:
                return False, "No se encontró el detalle del cambio permanente"
            
            # Obtener las jornadas actuales de ambos empleados
            
            # Las jornadas son indefinidas por defecto (sin fecha_fin)
            jornada_solicitante = AsignarJornadaExplorador.objects.filter(
                explorador=solicitud.explorador_solicitante,
                fecha_inicio__lte=detalle.fecha_inicio
            ).order_by('-fecha_inicio').first()
            
            jornada_receptor = AsignarJornadaExplorador.objects.filter(
                explorador=solicitud.explorador_receptor,
                fecha_inicio__lte=detalle.fecha_inicio
            ).order_by('-fecha_inicio').first()
            
            if not jornada_solicitante or not jornada_receptor:
                return False, "No se encontraron las jornadas de los empleados"
            
            # Obtener las jornadas actuales
            jornada_solicitante_actual = jornada_solicitante.jornada
            jornada_receptor_actual = jornada_receptor.jornada
            
            # Buscar la jornada contraria para cada uno
            from empleados.models import Jornada
            jornada_contraria_solicitante = Jornada.objects.exclude(id=jornada_solicitante_actual.id).first()
            jornada_contraria_receptor = Jornada.objects.exclude(id=jornada_receptor_actual.id).first()
            
            if not jornada_contraria_solicitante or not jornada_contraria_receptor:
                return False, "No se encontraron jornadas contrarias"
            
            # Calcular fecha fin del cambio permanente
            fecha_fin_cambio = detalle.fecha_fin
            if not fecha_fin_cambio:
                # Si no hay fecha fin, usar fin de año
                fecha_fin_cambio = date(detalle.fecha_inicio.year, 12, 31)
            
            # 1. Las jornadas son indefinidas por defecto, no necesitan finalización
            # Las jornadas se mantienen activas hasta que se cree una nueva asignación
            
            # 2. Generar lista de fechas válidas según días seleccionados o rango completo
            fechas_validas = self._generar_fechas_validas(detalle, fecha_fin_cambio)
            
            if not fechas_validas:
                return False, "No se encontraron días válidos para aplicar el cambio permanente"
            
            # 3. Crear registros en Turno para el período de cambio permanente
            from turnos.models import Turno
            
            turnos_creados = []
            dias_omitidos = []
            dias_procesados = 0
            
            # Obtener la sala (especialidad) de cada empleado vía CompetenciaEmpleado
            from empleados.models import CompetenciaEmpleado
            sala_solicitante = CompetenciaEmpleado.objects.filter(
                empleado=solicitud.explorador_solicitante
            ).select_related('sala').first()

            sala_receptor = CompetenciaEmpleado.objects.filter(
                empleado=solicitud.explorador_receptor
            ).select_related('sala').first()

            # Si no se encuentran salas asignadas, usar la primera sala disponible
            if not sala_solicitante:
                from turnos.models import Sala
                sala_default = Sala.objects.first()
                if not sala_default:
                    return False, "No se encontraron salas disponibles en el sistema"
                sala_solicitante = type('obj', (object,), {'sala': sala_default})()
                print(f"Usando sala por defecto para {solicitud.explorador_solicitante.nombre}: {sala_default.nombre}")
            
            if not sala_receptor:
                from turnos.models import Sala
                sala_default = Sala.objects.first()
                if not sala_default:
                    return False, "No se encontraron salas disponibles en el sistema"
                sala_receptor = type('obj', (object,), {'sala': sala_default})()
                print(f"Usando sala por defecto para {solicitud.explorador_receptor.nombre}: {sala_default.nombre}")
            
            # Procesar solo las fechas válidas generadas
            for fecha_actual in fechas_validas:
                # Verificar si es día válido (no sábado, no domingo, no festivo, no mantenimiento, no descanso)
                # IMPORTANTE: CT PERMANENTE solo permite lunes-viernes (weekday 0-4)
                # Nota: Los días de descanso ya deberían estar excluidos en la validación,
                # pero verificamos aquí como medida de seguridad
                es_sabado = fecha_actual.weekday() == 5
                es_domingo = fecha_actual.weekday() == 6
                es_festivo = self._es_festivo(fecha_actual)
                es_mantenimiento = self._es_mantenimiento(fecha_actual)
                es_descanso_solicitante = self._es_dia_descanso(solicitud.explorador_solicitante, fecha_actual)
                es_descanso_receptor = self._es_dia_descanso(solicitud.explorador_receptor, fecha_actual)
                # Día ya cambiado (doblada / CT sencillo / D FDS): no está en jornada
                # predeterminada, por lo que el CT permanente NO puede aplicarse ese día.
                tipo_previo_solicitante = self._tipo_cambio_previo(solicitud.explorador_solicitante, fecha_actual)
                tipo_previo_receptor = self._tipo_cambio_previo(solicitud.explorador_receptor, fecha_actual)

                # Determinar si el día es válido
                es_valido = (not es_sabado and
                            not es_domingo and
                            not es_festivo and
                            not es_mantenimiento and
                            not es_descanso_solicitante and
                            not es_descanso_receptor and
                            not tipo_previo_solicitante and
                            not tipo_previo_receptor)
                
                if es_valido:
                    # Crear turnos solo para días válidos
                    turno_solicitante = Turno.objects.create(
                        explorador=solicitud.explorador_solicitante,
                        fecha=fecha_actual,
                        jornada=jornada_contraria_solicitante,
                        sala=sala_solicitante.sala,
                        tipo_cambio='CT PERMANENTE'
                    )
                    
                    turno_receptor = Turno.objects.create(
                        explorador=solicitud.explorador_receptor,
                        fecha=fecha_actual,
                        jornada=jornada_contraria_receptor,
                        sala=sala_receptor.sala,
                        tipo_cambio='CT PERMANENTE'
                    )
                    
                    turnos_creados.append((turno_solicitante, turno_receptor))
                    dias_procesados += 1
                else:
                    # Registrar día omitido con razón específica
                    razon = self._obtener_razon_dia_invalido_detallada(
                        fecha_actual,
                        es_sabado,
                        es_domingo,
                        es_festivo,
                        es_mantenimiento,
                        es_descanso_solicitante,
                        es_descanso_receptor,
                        tipo_previo_solicitante,
                        tipo_previo_receptor
                    )
                    dias_omitidos.append(f"{fecha_actual.strftime('%d/%m/%Y')} ({razon})")
            
            # 3. Actualizar la solicitud con las referencias a los turnos creados
            # Para CT PERMANENTE, usamos el primer turno creado como referencia
            if turnos_creados:
                primer_turno_solicitante, primer_turno_receptor = turnos_creados[0]
                solicitud.turno_origen = primer_turno_solicitante
                solicitud.turno_destino = primer_turno_receptor
                solicitud.save()
            
            # 3. No necesitamos jornadas de retorno - la jornada predeterminada se usará automáticamente
            # después de la fecha_fin_cambio cuando no haya registros en Turno
            
            # 4. Actualizar el estado de la solicitud
            solicitud.estado = 'aprobada'
            solicitud.fecha_resolucion = timezone.now()
            solicitud.save()
            
            # 5. Invalidar caché para todos los meses afectados por el cambio permanente
            from core.services.cache_service import CacheService
            # Calcular meses únicos en el rango
            meses_afectados = set()
            fecha_actual = detalle.fecha_inicio
            while fecha_actual <= fecha_fin_cambio:
                meses_afectados.add((fecha_actual.year, fecha_actual.month))
                # Avanzar al primer día del siguiente mes
                if fecha_actual.month == 12:
                    fecha_actual = date(fecha_actual.year + 1, 1, 1)
                else:
                    fecha_actual = date(fecha_actual.year, fecha_actual.month + 1, 1)
            
            # Invalidar caché para cada mes afectado
            for anio, mes in meses_afectados:
                CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, mes, anio)
                CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, mes, anio)
                logger.info(
                    f"CT PERMANENTE: Caché invalidado para solicitante (ID: {solicitud.explorador_solicitante.id}) "
                    f"y receptor (ID: {solicitud.explorador_receptor.id}) en {mes}/{anio}"
                )
            
            # Construir mensaje informativo
            mensaje = f"Cambio permanente aplicado para {dias_procesados} días"
            if dias_omitidos:
                mensaje += f". Días omitidos: {', '.join(dias_omitidos)}"
            
            return True, mensaje
            
        except Exception as e:
            return False, f"Error aplicando cambio permanente: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for CT permanente with 'Best Match' logic.
        
        Args:
            fecha: Date string in YYYY-MM-DD format (start date)
            usuario_actual: Current user's empleado instance
            **kwargs:
                - fecha_fin: Date string (optional)
                - dias_seleccionados: Dict with 'dias_semana' and 'fechas_especificas'
            
        Returns:
            List of available empleados with compatibility metadata
        """
        try:
            from datetime import datetime
            from turnos.services.jornada_service import JornadaService
            
            fecha_inicio_str = fecha
            fecha_fin_str = kwargs.get('fecha_fin')
            dias_seleccionados = kwargs.get('dias_seleccionados', {})
            
            # Si no hay rango o días seleccionados, usar comportamiento por defecto (solo fecha inicio)
            if not fecha_fin_str:
                return super().get_empleados_disponibles(fecha, usuario_actual)
            
            # Convertir fechas
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            
            # 1. Generar todas las fechas válidas del rango
            fechas_a_evaluar = self._generar_fechas_validas_params(
                fecha_inicio, 
                fecha_fin, 
                dias_seleccionados
            )
            
            if not fechas_a_evaluar:
                return []
            
            # 2. Obtener todos los empleados activos (candidatos base)
            servicio_disp = get_empleado_disponibilidad_service()
            # IMPORTANTE: El servicio espera un User (con atributo empleado), pero recibimos un Empleado
            # Por lo tanto, pasamos None y filtramos manualmente después
            candidatos_base = servicio_disp.get_empleados_disponibles(fecha_inicio_str, None)
            
            # Asegurar que el usuario actual no esté en la lista
            # Convertir a lista si es QuerySet para manejar ambos casos de forma consistente
            import logging
            logger = logging.getLogger(__name__)
            
            # Contar antes de filtrar (evaluar QuerySet si es necesario)
            total_antes = candidatos_base.count() if hasattr(candidatos_base, 'count') else len(candidatos_base) if hasattr(candidatos_base, '__len__') else 0
            logger.debug(f"Filtrando usuario actual (ID: {usuario_actual.id}, Nombre: {usuario_actual.nombre}) de candidatos. Total antes: {total_antes}")
            
            # Filtrar el usuario actual
            if hasattr(candidatos_base, 'exclude'):
                # Es un QuerySet, excluir y convertir a lista
                candidatos_base = list(candidatos_base.exclude(id=usuario_actual.id))
            else:
                # Es una lista, filtrar manualmente
                candidatos_base = [c for c in candidatos_base if hasattr(c, 'id') and c.id != usuario_actual.id]
            
            # Verificar que el usuario actual no esté en la lista
            ids_candidatos = [c.id for c in candidatos_base if hasattr(c, 'id')]
            if usuario_actual.id in ids_candidatos:
                logger.warning(f"ERROR: Usuario actual (ID: {usuario_actual.id}) aún está en la lista de candidatos después del filtro!")
                # Filtrar nuevamente de forma más estricta
                candidatos_base = [c for c in candidatos_base if hasattr(c, 'id') and c.id != usuario_actual.id]
            
            logger.debug(f"Total candidatos después de filtrar: {len(candidatos_base)}. IDs: {ids_candidatos}")
            
            # Mapa de compatibilidad: {empleado_id: {'compatibles': [], 'incompatibles': [], 'empleado': obj}}
            mapa_compatibilidad = {}
            for cand in candidatos_base:
                mapa_compatibilidad[cand.id] = {
                    'empleado': cand,
                    'dias_compatibles': [],
                    'dias_incompatibles': []
                }
            
            # 3. Evaluar día a día
            logger.debug(f"Iniciando evaluación día a día para {len(fechas_a_evaluar)} fechas")
            for fecha_eval in fechas_a_evaluar:
                # Obtener jornada del usuario actual para este día
                jornada_usuario = JornadaService.get_jornada_explorador_fecha(usuario_actual.id, fecha_eval)
                
                if not jornada_usuario:
                    logger.debug(f"Usuario {usuario_actual.id} ({usuario_actual.nombre}) no tiene jornada para {fecha_eval}")
                    continue
                
                # Determinar jornada contraria necesaria
                nombre_contraria = 'PM' if jornada_usuario.nombre == 'AM' else 'AM'
                logger.debug(f"Fecha {fecha_eval}: Usuario {usuario_actual.id} tiene jornada {jornada_usuario.nombre}, necesita {nombre_contraria}")
                
                # Evaluar cada candidato
                for cand_id, info in mapa_compatibilidad.items():
                    # Obtener jornada del candidato
                    jornada_cand = JornadaService.get_jornada_explorador_fecha(cand_id, fecha_eval)
                    
                    es_compatible = False
                    if jornada_cand:
                        if jornada_cand.nombre == nombre_contraria:
                            es_compatible = True
                            logger.debug(f"  ✓ Candidato {cand_id} ({info['empleado'].nombre}): {jornada_cand.nombre} == {nombre_contraria} → COMPATIBLE")
                        else:
                            logger.debug(f"  ✗ Candidato {cand_id} ({info['empleado'].nombre}): {jornada_cand.nombre} != {nombre_contraria} → INCOMPATIBLE (misma jornada o diferente)")
                    else:
                        logger.debug(f"  ✗ Candidato {cand_id} ({info['empleado'].nombre}): Sin jornada para {fecha_eval} → INCOMPATIBLE")
                    
                    fecha_fmt = fecha_eval.strftime('%Y-%m-%d')
                    if es_compatible:
                        info['dias_compatibles'].append(fecha_fmt)
                    else:
                        info['dias_incompatibles'].append(fecha_fmt)
            
            # 4. Construir lista de resultados con metadatos
            resultados = []
            total_dias = len(fechas_a_evaluar)
            
            logger.debug(f"Construyendo resultados. Total días en rango: {total_dias}")
            for info in mapa_compatibilidad.values():
                empleado = info['empleado']
                compatibles_count = len(info['dias_compatibles'])
                incompatibles_count = len(info['dias_incompatibles'])
                
                logger.debug(f"Empleado {empleado.id} ({empleado.nombre}): {compatibles_count} días compatibles, {incompatibles_count} días incompatibles")
                
                # Solo incluir si tiene al menos un día compatible
                if compatibles_count > 0:
                    # Inyectar metadatos en el objeto empleado (temporalmente para serialización)
                    empleado.compatibilidad_percent = int((compatibles_count / total_dias) * 100)
                    empleado.dias_compatibles = info['dias_compatibles']
                    empleado.dias_incompatibles = info['dias_incompatibles']
                    empleado.total_dias_rango = total_dias
                    resultados.append(empleado)
                    logger.debug(f"  → INCLUIDO con {empleado.compatibilidad_percent}% de compatibilidad")
                else:
                    logger.debug(f"  → EXCLUIDO (0% compatibilidad - misma jornada en todos los días o sin jornada)")
            
            # 5. Ordenar por porcentaje de compatibilidad descendente
            resultados.sort(key=lambda x: x.compatibilidad_percent, reverse=True)
            
            logger.debug(f"Total resultados finales: {len(resultados)} empleados con compatibilidad > 0%")
            
            return resultados
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error en get_empleados_disponibles CT PERMANENTE (Rango)")
            return []

    def _generar_fechas_validas_params(self, fecha_inicio: date, fecha_fin: date, dias_seleccionados: dict) -> List[date]:
        """
        Genera lista de fechas válidas basado en parámetros directos (no objeto DB).
        """
        from datetime import datetime
        
        fechas_validas: Set[date] = set()
        
        # Extraer listas del dict
        dias_semana_list = dias_seleccionados.get('dias_semana', [])
        fechas_especificas_list = dias_seleccionados.get('fechas_especificas', []) 
        
        # Lógica para fechas específicas (tiene prioridad si existe)
        if fechas_especificas_list:
            for fecha_str in fechas_especificas_list:
                try:
                    if isinstance(fecha_str, str):
                        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    else:
                        fecha_obj = fecha_str
                    
                    # Solo agregar si está dentro del rango y es lunes-viernes
                    if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                        fechas_validas.add(fecha_obj)
                except (ValueError, TypeError):
                    continue
        
        # Lógica para días de semana (solo si no hay fechas específicas)
        if dias_semana_list and not fechas_especificas_list:
            for dia_str in dias_semana_list:
                try:
                    dia_semana_buscado = int(dia_str)
                    fecha_actual = fecha_inicio
                    
                    # Avanzar al primer día correspondiente
                    dias_hasta = (dia_semana_buscado - fecha_actual.weekday()) % 7
                    if dias_hasta > 0:
                        fecha_actual += timedelta(days=dias_hasta)
                    
                    while fecha_actual <= fecha_fin:
                        # Solo lunes-viernes
                        if fecha_actual.weekday() < 5:
                            fechas_validas.add(fecha_actual)
                        fecha_actual += timedelta(days=7)
                except ValueError:
                    continue
        
        # Si no hay días seleccionados explícitos, usar rango completo (lunes-viernes)
        if not dias_semana_list and not fechas_especificas_list:
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:
                    fechas_validas.add(fecha_actual)
                fecha_actual += timedelta(days=1)
                
        return sorted(list(fechas_validas))

    def _generar_fechas_validas(self, detalle: CambioPermanenteDetalle, fecha_fin: date) -> List[date]:
        """
        Wrapper para mantener compatibilidad con el método original que usa el objeto detalle.
        """
        dias_semana = []
        fechas_especificas = []
        
        for dia in detalle.dias.all():
            if dia.tipo == 'dia_semana' and dia.dia_semana is not None:
                dias_semana.append(dia.dia_semana)
            elif dia.tipo == 'fecha_especifica' and dia.fecha_especifica:
                fechas_especificas.append(dia.fecha_especifica)
                
        dias_seleccionados = {
            'dias_semana': dias_semana,
            'fechas_especificas': fechas_especificas
        }
        
        return self._generar_fechas_validas_params(detalle.fecha_inicio, fecha_fin, dias_seleccionados)
    
    def _tipo_cambio_previo(self, explorador: Empleado, fecha: date):
        """
        Devuelve el tipo de cambio que ya tiene el explorador ese día si su turno NO es la
        jornada predeterminada (doblada, CT sencillo, D FDS, etc.), o None si el día está en
        su estado predeterminado (sin turno o turno del horario importado con tipo_cambio NULL).

        El CT PERMANENTE intercambia las jornadas PREDETERMINADAS; si ese día el explorador ya
        no está en su jornada predeterminada, ese día debe OMITIRSE.
        """
        from turnos.models import Turno
        turnos = list(
            Turno.objects
            .filter(explorador=explorador, fecha=fecha)
            .exclude(tipo_cambio__isnull=True)
            .exclude(tipo_cambio='')
        )
        if not turnos:
            return None
        tipos = {t.tipo_cambio for t in turnos}
        # Una doblada deja 2 turnos (día completo): priorizar reportarla como doblada.
        if len(turnos) >= 2 or tipos & {'DOBLADA', 'DOBLADA PERM'}:
            return 'DOBLADA PERM' if 'DOBLADA PERM' in tipos else 'DOBLADA'
        return next(iter(tipos))

    @staticmethod
    def _razon_tipo_cambio_previo(tipo: str) -> str:
        """Texto legible para el aviso de día omitido por cambio previo."""
        return {
            'DOBLADA': 'ya tiene una doblada ese día',
            'DOBLADA PERM': 'ya tiene una doblada permanente ese día',
            'CT': 'ya cambió su turno (CT sencillo) ese día',
            'D FDS': 'ya tiene una doblada de fin de semana ese día',
            'CT PERMANENTE': 'ya tiene otro cambio permanente ese día',
        }.get(tipo, f'ya tiene un cambio previo ({tipo}) ese día')

    def _es_dia_descanso(self, explorador: Empleado, fecha: date) -> bool:
        """
        Verificar si un explorador está descansando en una fecha específica.
        
        Args:
            explorador: Instancia de Empleado
            fecha: Fecha a verificar
            
        Returns:
            True si el explorador está descansando, False en caso contrario
        """
        try:
            from core.utils.jornada_utils import JornadaUtils
            from turnos.services.jornada_service import JornadaService
            
            # Obtener jornada base del explorador
            jornada_base = JornadaService.get_jornada_explorador_fecha(explorador.id, fecha.strftime('%Y-%m-%d'))
            
            if not jornada_base:
                return False
            
            # Descanso por rotación predeterminada (fin de semana).
            if JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha) == "Descanso":
                return True
            # Descanso de SEMANA manual (temporada/festivo configurado por jornada) entre semana.
            from turnos.services.descanso_semana_service import DescansoSemanaService
            if DescansoSemanaService.es_descanso_semana_manual(jornada_base.nombre, fecha):
                return True
            return False
        except Exception:
            return False
    
    def _es_festivo(self, fecha):
        """Verificar si es festivo"""
        try:
            from turnos.models import DiaEspecial
            return DiaEspecial.objects.filter(fecha=fecha, tipo='festivo', activo=True).exists()
        except:
            return False

    def _es_mantenimiento(self, fecha):
        """Verificar si es día de mantenimiento EFECTIVO (temporada manda sobre mantenimiento)."""
        try:
            from turnos.models import DiaEspecial
            return DiaEspecial.es_mantenimiento_efectivo(fecha)
        except:
            return False
    
    def _obtener_razon_dia_invalido(self, fecha):
        """Obtener la razón por la cual un día es inválido"""
        if fecha.weekday() == 5:  # Sábado
            return "sábado"
        elif fecha.weekday() == 6:  # Domingo
            return "domingo"
        elif self._es_festivo(fecha):
            return "festivo"
        elif self._es_mantenimiento(fecha):
            return "mantenimiento"
        else:
            return "no válido"
    
    def _obtener_razon_dia_invalido_detallada(self, fecha, es_sabado, es_domingo, es_festivo, es_mantenimiento, es_descanso_solicitante, es_descanso_receptor, tipo_previo_solicitante=None, tipo_previo_receptor=None):
        """Obtener la razón detallada por la cual un día es inválido"""
        razones = []
        if es_sabado:
            razones.append("sábado")
        if es_domingo:
            razones.append("domingo")
        if es_festivo:
            razones.append("festivo")
        if es_mantenimiento:
            razones.append("mantenimiento")
        if es_descanso_solicitante:
            razones.append("descanso solicitante")
        if es_descanso_receptor:
            razones.append("descanso receptor")
        if tipo_previo_solicitante:
            razones.append(f"el solicitante {self._razon_tipo_cambio_previo(tipo_previo_solicitante)}; para incluirlo, ese día debe quedar en su jornada predeterminada")
        if tipo_previo_receptor:
            razones.append(f"el compañero {self._razon_tipo_cambio_previo(tipo_previo_receptor)}; para incluirlo, ese día debe quedar en su jornada predeterminada")

        return ", ".join(razones) if razones else "no válido"
