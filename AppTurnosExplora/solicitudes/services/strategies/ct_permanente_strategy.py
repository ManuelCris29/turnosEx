"""
CT Permanente Strategy - Implementation for "CT PERMANENTE" solicitud type

This strategy implements the specific logic for "CT PERMANENTE" solicitudes,
which are requests for permanent shift changes.
"""

from typing import Dict, Any, Tuple, Optional
from solicitudes.models import SolicitudCambio, CambioPermanenteDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy


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
            
            # Validar datos básicos
            if not all([explorador_solicitante, explorador_receptor, fecha_inicio]):
                return False, "Faltan datos requeridos para la validación"
            
            # Validaciones básicas (empleados activos, no mismo empleado)
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            
            # Validaciones específicas de CT PERMANENTE
            SolicitudValidator.validar_fechas_cambio_permanente(fecha_inicio, fecha_fin)
            SolicitudValidator.validar_jornada_contraria(explorador_solicitante, explorador_receptor, fecha_inicio)
            SolicitudValidator.validar_no_dia_mantenimiento(fecha_inicio)
            SolicitudValidator.validar_no_domingo_por_semana(fecha_inicio, es_cambio_permanente=True)
            SolicitudValidator.validar_no_festivo_por_semana(fecha_inicio, es_cambio_permanente=True)
            SolicitudValidator.validar_no_cambio_permanente_superpuesto(
                explorador_solicitante, explorador_receptor, fecha_inicio, fecha_fin
            )
            
            # Si hay fecha fin, validar también esa fecha
            if fecha_fin:
                SolicitudValidator.validar_no_dia_mantenimiento(fecha_fin)
                SolicitudValidator.validar_no_domingo_por_semana(fecha_fin, es_cambio_permanente=True)
                SolicitudValidator.validar_no_festivo_por_semana(fecha_fin, es_cambio_permanente=True)
            
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
            
            CambioPermanenteDetalle.objects.create(
                solicitud=solicitud,
                fecha_inicio=fecha_inicio_obj,
                fecha_fin=fecha_fin_obj
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
            jornada_solicitante = AsignarJornadaExplorador.objects.filter(
                explorador=solicitud.explorador_solicitante,
                fecha_inicio__lte=detalle.fecha_inicio,
                fecha_fin__gte=detalle.fecha_inicio
            ).first()
            
            jornada_receptor = AsignarJornadaExplorador.objects.filter(
                explorador=solicitud.explorador_receptor,
                fecha_inicio__lte=detalle.fecha_inicio,
                fecha_fin__gte=detalle.fecha_inicio
            ).first()
            
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
            
            # 1. Finalizar las jornadas actuales antes de la fecha de inicio
            if jornada_solicitante.fecha_fin >= detalle.fecha_inicio:
                jornada_solicitante.fecha_fin = detalle.fecha_inicio - timedelta(days=1)
                jornada_solicitante.save()
            
            if jornada_receptor.fecha_fin >= detalle.fecha_inicio:
                jornada_receptor.fecha_fin = detalle.fecha_inicio - timedelta(days=1)
                jornada_receptor.save()
            
            # 2. Crear registros en Turno para el período de cambio permanente
            from turnos.models import Turno
            
            # Crear registros diarios en Turno para el período
            fecha_actual = detalle.fecha_inicio
            turnos_creados = []
            dias_omitidos = []
            dias_procesados = 0
            
            # Obtener las salas de cada empleado
            from turnos.models import AsignarSalaExplorador
            sala_solicitante = AsignarSalaExplorador.objects.filter(
                explorador=solicitud.explorador_solicitante,
                fecha_inicio__lte=detalle.fecha_inicio,
                fecha_fin__gte=detalle.fecha_inicio
            ).first()
            
            sala_receptor = AsignarSalaExplorador.objects.filter(
                explorador=solicitud.explorador_receptor,
                fecha_inicio__lte=detalle.fecha_inicio,
                fecha_fin__gte=detalle.fecha_inicio
            ).first()
            
            if not sala_solicitante or not sala_receptor:
                return False, "No se encontraron las salas de los empleados"
            
            while fecha_actual <= fecha_fin_cambio:
                # Verificar si es día válido (no domingo, no festivo, no mantenimiento)
                if (fecha_actual.weekday() != 6 and 
                    not self._es_festivo(fecha_actual) and 
                    not self._es_mantenimiento(fecha_actual)):
                    
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
                    # Registrar día omitido
                    razon = self._obtener_razon_dia_invalido(fecha_actual)
                    dias_omitidos.append(f"{fecha_actual.strftime('%d/%m/%Y')} ({razon})")
                
                fecha_actual += timedelta(days=1)
            
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
            # For CT permanente, only show employees with opposite schedule
            from ..solicitud_service import SolicitudService
            
            # Crear un objeto mock que tenga el atributo empleado
            class MockUser:
                def __init__(self, empleado):
                    self.empleado = empleado
            
            mock_user = MockUser(usuario_actual)
            
            return SolicitudService.get_empleados_disponibles(
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
            # Import here to avoid circular imports
            from ..solicitud_service import SolicitudService
            
            return SolicitudService.get_turno_explorador(explorador_id, fecha)
            
        except Exception:
            return {}
    
    def _es_festivo(self, fecha):
        """Verificar si es festivo"""
        try:
            from turnos.models import DiaEspecial
            return DiaEspecial.objects.filter(fecha=fecha, tipo='festivo').exists()
        except:
            return False

    def _es_mantenimiento(self, fecha):
        """Verificar si es día de mantenimiento"""
        try:
            from turnos.models import DiaEspecial
            return DiaEspecial.objects.filter(fecha=fecha, tipo='mantenimiento').exists()
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
