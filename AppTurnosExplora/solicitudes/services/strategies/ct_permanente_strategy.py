"""
CT Permanente Strategy - Implementation for "CT PERMANENTE" solicitud type

This strategy implements the specific logic for "CT PERMANENTE" solicitudes,
which are requests for permanent shift changes.
"""

from typing import Dict, Any, Tuple, Optional, List, Set
from datetime import date, timedelta
from solicitudes.models import SolicitudCambio, CambioPermanenteDetalle, CambioPermanenteDia
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from core.services import get_empleado_disponibilidad_service, get_turno_service


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
            
            # Validar datos básicos
            if not all([explorador_solicitante, explorador_receptor, fecha_inicio, fecha_fin]):
                return False, "Faltan datos requeridos para la validación (fecha_fin es obligatoria)"
            
            # Validaciones básicas (empleados activos, no mismo empleado)
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            
            # Validaciones específicas de CT PERMANENTE
            SolicitudValidator.validar_fechas_cambio_permanente(fecha_inicio, fecha_fin)
            SolicitudValidator.validar_jornada_contraria(explorador_solicitante, explorador_receptor, fecha_inicio)
            
            # Validar días seleccionados si existen
            if dias_seleccionados:
                SolicitudValidator.validar_dias_seleccionados_permanente(fecha_inicio, fecha_fin, dias_seleccionados)
            
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
                # Guardar fechas específicas
                fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
                for fecha_str in fechas_especificas:
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    CambioPermanenteDia.objects.create(
                        cambio_permanente=detalle,
                        fecha_especifica=fecha_obj,
                        tipo='fecha_especifica'
                    )
                
                # Guardar días de semana
                dias_semana = dias_seleccionados.get('dias_semana', [])
                for dia_semana in dias_semana:
                    CambioPermanenteDia.objects.create(
                        cambio_permanente=detalle,
                        dia_semana=int(dia_semana),
                        tipo='dia_semana'
                    )
            
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
            
            # Obtener las salas de cada empleado
            from turnos.models import AsignarSalaExplorador
            # Las salas son indefinidas por defecto (sin fecha_fin)
            sala_solicitante = AsignarSalaExplorador.objects.filter(
                explorador=solicitud.explorador_solicitante,
                fecha_inicio__lte=detalle.fecha_inicio
            ).order_by('-fecha_inicio').first()
            
            sala_receptor = AsignarSalaExplorador.objects.filter(
                explorador=solicitud.explorador_receptor,
                fecha_inicio__lte=detalle.fecha_inicio
            ).order_by('-fecha_inicio').first()
            
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
                # Verificar si es día válido (no domingo, no festivo, no mantenimiento, no descanso)
                # Nota: Los días de descanso ya deberían estar excluidos en la validación,
                # pero verificamos aquí como medida de seguridad
                es_domingo = fecha_actual.weekday() == 6
                es_festivo = self._es_festivo(fecha_actual)
                es_mantenimiento = self._es_mantenimiento(fecha_actual)
                es_descanso_solicitante = self._es_dia_descanso(solicitud.explorador_solicitante, fecha_actual)
                es_descanso_receptor = self._es_dia_descanso(solicitud.explorador_receptor, fecha_actual)
                
                # Determinar si el día es válido
                es_valido = (not es_domingo and 
                            not es_festivo and 
                            not es_mantenimiento and
                            not es_descanso_solicitante and
                            not es_descanso_receptor)
                
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
                        es_domingo, 
                        es_festivo, 
                        es_mantenimiento,
                        es_descanso_solicitante,
                        es_descanso_receptor
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
            
            # Construir mensaje informativo
            mensaje = f"Cambio permanente aplicado para {dias_procesados} días"
            if dias_omitidos:
                mensaje += f". Días omitidos: {', '.join(dias_omitidos)}"
            
            return True, mensaje
            
        except Exception as e:
            return False, f"Error aplicando cambio permanente: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado) -> list:
        """
        Get available employees for CT permanente (only employees with opposite schedule).
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            
        Returns:
            List of available empleados with opposite schedule
        """
        try:
            # Crear un objeto mock que tenga el atributo empleado
            class MockUser:
                def __init__(self, empleado):
                    self.empleado = empleado
            
            mock_user = MockUser(usuario_actual)
            servicio = get_empleado_disponibilidad_service()
            return servicio.get_empleados_disponibles(
                fecha,
                mock_user,
                solo_jornada_contraria=True  # Solo jornada contraria para CT PERMANENTE
            )
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error en get_empleados_disponibles CT PERMANENTE")
            return []
    
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer.
        
        Args:
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with turn information
        """
        try:
            turno_service = get_turno_service()
            return turno_service.get_turno_explorador(explorador_id, fecha)
        except Exception:
            return {}
    
    def _generar_fechas_validas(self, detalle: CambioPermanenteDetalle, fecha_fin: date) -> List[date]:
        """
        Genera lista de fechas válidas para el cambio permanente.
        
        Si hay días seleccionados en CambioPermanenteDia, usa esos.
        Si no hay días seleccionados, usa el rango completo (retrocompatibilidad).
        
        Args:
            detalle: Instancia de CambioPermanenteDetalle
            fecha_fin: Fecha fin del cambio permanente
            
        Returns:
            Lista de fechas válidas (dentro del rango, sin duplicados, ordenadas)
        """
        fechas_validas: Set[date] = set()
        
        # Obtener días seleccionados
        dias_seleccionados = detalle.dias.all()
        
        if dias_seleccionados.exists():
            # Hay días seleccionados: usar solo esos
            fecha_inicio = detalle.fecha_inicio
            
            for dia_seleccionado in dias_seleccionados:
                if dia_seleccionado.tipo == 'fecha_especifica' and dia_seleccionado.fecha_especifica:
                    # Fecha específica: agregar si está dentro del rango
                    fecha_esp = dia_seleccionado.fecha_especifica
                    if fecha_inicio <= fecha_esp <= fecha_fin:
                        fechas_validas.add(fecha_esp)
                
                elif dia_seleccionado.tipo == 'dia_semana' and dia_seleccionado.dia_semana is not None:
                    # Día de semana: generar todas las ocurrencias dentro del rango
                    fecha_actual = fecha_inicio
                    dia_semana_buscado = dia_seleccionado.dia_semana
                    
                    # Avanzar hasta el primer día de la semana buscado
                    dias_hasta_proximo = (dia_semana_buscado - fecha_actual.weekday()) % 7
                    if dias_hasta_proximo > 0:
                        fecha_actual += timedelta(days=dias_hasta_proximo)
                    
                    # Agregar todas las ocurrencias del día de semana dentro del rango
                    while fecha_actual <= fecha_fin:
                        fechas_validas.add(fecha_actual)
                        fecha_actual += timedelta(days=7)  # Siguiente semana
        else:
            # No hay días seleccionados: usar rango completo (retrocompatibilidad)
            fecha_actual = detalle.fecha_inicio
            while fecha_actual <= fecha_fin:
                fechas_validas.add(fecha_actual)
                fecha_actual += timedelta(days=1)
        
        # Ordenar y retornar
        return sorted(list(fechas_validas))
    
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
            
            # Calcular jornada del día
            jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
            
            # Si la jornada del día es "Descanso", el explorador está descansando
            return jornada_dia == "Descanso"
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
        """Verificar si es día de mantenimiento"""
        try:
            from turnos.models import DiaEspecial
            return DiaEspecial.objects.filter(fecha=fecha, tipo='mantenimiento', activo=True).exists()
        except:
            return False
    
    def _obtener_razon_dia_invalido(self, fecha):
        """Obtener la razón por la cual un día es inválido"""
        if fecha.weekday() == 6:
            return "domingo"
        elif self._es_festivo(fecha):
            return "festivo"
        elif self._es_mantenimiento(fecha):
            return "mantenimiento"
        else:
            return "no válido"
    
    def _obtener_razon_dia_invalido_detallada(self, fecha, es_domingo, es_festivo, es_mantenimiento, es_descanso_solicitante, es_descanso_receptor):
        """Obtener la razón detallada por la cual un día es inválido"""
        razones = []
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
        
        return ", ".join(razones) if razones else "no válido"
