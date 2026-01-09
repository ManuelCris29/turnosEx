"""
Doblada Strategy - Implementation for "DOBLADA" solicitud type

This strategy implements the specific logic for "DOBLADA" solicitudes,
which are requests where one explorer covers another's shift (cesión),
creating a debt that must be paid back later.
"""

import logging
import json
from typing import Dict, Any, Tuple, Optional
from django.core.exceptions import ValidationError
from django.db import transaction
from datetime import datetime, date
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from ..solicitud_validator import SolicitudValidator
from turnos.services.jornada_service import JornadaService
from core.services import get_empleado_disponibilidad_service, get_turno_service
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)


class DobladaStrategy(SolicitudStrategy):
    """
    Strategy for "DOBLADA" solicitudes.
    
    This implements the specific logic for double shift requests,
    including validation, creation, and application of changes.
    
    IMPORTANT: When a doblada request is approved by BOTH receptor AND supervisor,
    BOTH dobladas (receptor's and deudor's) are applied IMMEDIATELY.
    There are no "pending dobladas".
    """
    
    def __init__(self):
        super().__init__("DOBLADA")
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate doblada specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance (the one who covers)
                - fecha_cambio_turno: Date string (fecha de cesión)
                - fecha_pago: Date string (obligatory)
                - jornada_cedida: 'AM' or 'PM' (optional, if solicitante is in doblada)
                - tipo_cesion: 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm'
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha_cesion = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')
            jornada_cedida = datos.get('jornada_cedida')
            fecha_creacion_solicitud = datos.get('fecha_creacion_solicitud')
            
            # Validaciones básicas de campos requeridos
            if not explorador_solicitante:
                return False, "Explorador solicitante es requerido"
            
            if not explorador_receptor:
                return False, "Explorador receptor es requerido"
            
            if not fecha_cesion:
                return False, "Fecha de cesión es requerida"
            
            if not fecha_pago:
                return False, "Fecha de pago es obligatoria. No existen dobladas abiertas."
            
            # Validar que fecha_cesion no sea en el pasado
            fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)
            fecha_actual = date.today()
            if fecha_cesion_obj < fecha_actual:
                return False, f"La fecha de cesión ({fecha_cesion_obj.strftime('%d/%m/%Y')}) no puede ser en el pasado."
            
            # Validar empleados activos
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            
            # Validar que no sea el mismo empleado
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            
            # Validar acuerdo previo obligatorio
            SolicitudValidator.validar_acuerdo_previo_obligatorio(
                fecha_cesion,
                fecha_pago,
                fecha_creacion_solicitud
            )
            
            # Validar días especiales para fecha de cesión
            SolicitudValidator.validar_dias_especiales_doblada(fecha_cesion)
            
            # Validar días especiales para fecha de pago
            SolicitudValidator.validar_dias_especiales_doblada(fecha_pago)
            
            # Validar jornadas contrarias
            SolicitudValidator.validar_jornadas_contrarias_doblada(
                explorador_solicitante,
                explorador_receptor,
                fecha_cesion,
                jornada_cedida
            )
            
            # Validar que receptor no tenga doblada activa (evitar triple turno)
            SolicitudValidator.validar_no_triple_turno(explorador_receptor, fecha_cesion)
            SolicitudValidator.validar_no_triple_turno(explorador_receptor, fecha_pago)
            
            # IMPORTANTE: NO validar doblada del solicitante en fecha de cesión
            # Porque Cesión Total existe precisamente para ceder una doblada existente
            # Solo validar que NO tenga doblada en fecha de PAGO
            
            # Validar que deudor no tenga doblada activa en fecha de pago
            SolicitudValidator.validar_no_doblada_activa(explorador_solicitante, fecha_pago)
            
            # Validar coincidencia de jornadas en fecha de pago (caso crítico)
            # Esta validación se hace cuando se envía la solicitud, no cuando se aprueba
            coincidencia = SolicitudValidator.validar_coincidencia_jornadas_pago(
                explorador_solicitante,  # deudor
                explorador_receptor,     # acreedor
                fecha_pago
            )
            
            if coincidencia['requiere_cambio_turno']:
                return False, json.dumps({
                    'code': 'requiere_cambio_turno_previo',
                    'message': 'No se puede pagar trabajando dos veces la misma jornada. Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago.',
                    'fecha_pago': fecha_pago,
                    'jornada_comun': coincidencia['jornada_comun']
                })
            
            return True, "Solicitud de doblada válida"
            
        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            logger.error(f"Error validando doblada: {str(e)}", exc_info=True)
            return False, f"Error validando doblada: {str(e)}"
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a doblada solicitud.
        
        IMPORTANT: This is NOT a self-request anymore.
        empleado_receptor is the one who covers (not the same as solicitante).
        
        Args:
            datos: Dictionary containing solicitud data
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance (the one who covers)
                - tipo_cambio: TipoSolicitudCambio instance
                - fecha_cambio_turno: Date string (fecha de cesión)
                - fecha_pago: Date string (obligatory)
                - jornada_cedida: 'AM' or 'PM' (optional)
                - tipo_cesion: 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm'
                - comentario: Optional string
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cambio_turno = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')
            jornada_cedida = datos.get('jornada_cedida')
            tipo_cesion = datos.get('tipo_cesion', 'cesion_completa')
            
            # Create the main solicitud
            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_receptor,  # NOT self-request anymore
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_cambio_turno,
                estado='pendiente'
            )
            
            # Create the doblada detail
            DobladaDetalle.objects.create(
                solicitud=solicitud,
                minutos_deuda=30,  # Default 30 minutes
                fecha_pago=fecha_pago,
                tipo_cesion=tipo_cesion,
                jornada_cedida=jornada_cedida,
                empleado_receptor=explorador_receptor  # Guardar receptor en DobladaDetalle para consultas directas
            )
            
            logger.info(f"Doblada solicitud creada: {solicitud.id} - {explorador_solicitante.nombre} -> {explorador_receptor.nombre}")
            
            # Crear notificaciones y enviar emails
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception as e:
                logger.exception("Error creando notificaciones para DOBLADA")
            
            return solicitud, "Solicitud de doblada creada correctamente"
            
        except Exception as e:
            logger.error(f"Error creando solicitud de doblada: {str(e)}", exc_info=True)
            return None, f"Error creando solicitud de doblada: {str(e)}"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply doblada when solicitud is approved by BOTH receptor AND supervisor.
        
        IMPORTANT: This method applies BOTH dobladas IMMEDIATELY:
        - Receptor's doblada in fecha_cesion
        - Deudor's doblada in fecha_pago
        
        There are no "pending dobladas". Both are applied when both approve.
        
        Args:
            solicitud: The approved solicitud instance
        
        Returns:
            Tuple of (success, message)
        """
        try:
            from ..doblada_aplicacion_service import DobladaAplicacionService
            
            with transaction.atomic():
                detalle = solicitud.doblada
                
                # Aplicar doblada en fecha de cesión
                DobladaAplicacionService.aplicar_doblada_cesion(solicitud, detalle)
                
                # Aplicar doblada en fecha de pago
                DobladaAplicacionService.aplicar_doblada_pago(solicitud, detalle)
                
                # Generar deudas
                DobladaAplicacionService.generar_deudas_doblada(solicitud, detalle)
                
                logger.info(f"Doblada aplicada: Solicitud {solicitud.id}")
                
                return True, "Doblada aplicada correctamente. Ambas dobladas (cesión y pago) fueron aplicadas inmediatamente."
                
        except Exception as e:
            logger.error(f"Error aplicando doblada: {str(e)}", exc_info=True)
            return False, f"Error aplicando doblada: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for doblada according to visibility rules.
        
        Rules:
        - If solicitante works AM → only show PM employees (except those in doblada)
        - If solicitante works PM → only show AM employees (except those in doblada)
        - If solicitante is in doblada:
          - To cede AM → show PM employees (except those in doblada)
          - To cede PM → show AM employees (except those in doblada)
        - Exclude employees who already have doblada active in that date
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            **kwargs: Additional arguments
                - jornada_cedida: 'AM' or 'PM' (optional, if usuario is in doblada)
        
        Returns:
            List of available empleados
        """
        try:
            from ..doblada_filtro_service import DobladaFiltroService
            
            jornada_cedida = kwargs.get('jornada_cedida')
            
            # Determinar jornada a ceder
            jornada_a_ceder = DobladaFiltroService.obtener_jornada_a_ceder(
                usuario_actual, fecha, jornada_cedida
            )
            
            if not jornada_a_ceder:
                logger.warning(
                    f"No se pudo determinar jornada a ceder para {usuario_actual.nombre} en {fecha}"
                )
                return []
            
            # Obtener empleados con jornada contraria usando el servicio optimizado
            servicio = get_empleado_disponibilidad_service()
            
            # Si hay jornada_cedida, necesitamos filtrar manualmente por jornada contraria
            # porque el servicio usa la jornada del usuario_actual
            if jornada_cedida:
                # Caso especial: usuario está en doblada, usar jornada_cedida para determinar contraria
                # Obtener todos los empleados activos y filtrar por jornada contraria manualmente
                from turnos.services.jornada_service import JornadaService
                jornada_contraria = 'PM' if jornada_a_ceder == 'AM' else 'AM'
                
                empleados_activos = Empleado.objects.filter(activo=True).exclude(id=usuario_actual.id)
                empleados_contrarios = []
                
                for empleado in empleados_activos:
                    jornada_empleado = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha)
                    if jornada_empleado and jornada_empleado.nombre.upper() == jornada_contraria:
                        empleados_contrarios.append(empleado)
            else:
                # Caso normal: usar servicio optimizado
                empleados_contrarios = list(servicio.get_empleados_jornada_contraria(fecha, usuario_actual))
            
            # Filtrar empleados con doblada activa
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            empleados_sin_doblada = DobladaFiltroService.filtrar_empleados_sin_doblada_activa(
                empleados_contrarios, fecha_obj
            )
            
            # Convertir a formato de diccionario
            return DobladaFiltroService.convertir_empleados_a_dict(empleados_sin_doblada, fecha)
            
        except Exception as e:
            logger.error(f"Error obteniendo empleados disponibles para doblada: {str(e)}", exc_info=True)
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
