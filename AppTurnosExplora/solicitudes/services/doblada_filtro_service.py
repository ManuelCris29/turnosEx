"""
Servicio para filtrar empleados según reglas específicas de dobladas.

Responsabilidad única: Aplicar filtros de negocio para determinar qué empleados
están disponibles para recibir solicitudes de doblada.
"""
from typing import List, Dict, Any, Optional
from django.db.models import QuerySet
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)


class DobladaFiltroService:
    """
    Servicio para filtrar empleados según reglas de doblada.
    
    Responsabilidad única: Aplicar filtros de negocio para dobladas.
    """
    
    @staticmethod
    def filtrar_empleados_sin_doblada_activa(
        empleados: List[Empleado] | QuerySet[Empleado],
        fecha: date | str
    ) -> List[Empleado]:
        """
        Filtra empleados excluyendo aquellos que tienen doblada activa en la fecha.
        
        Regla de negocio: No se puede solicitar doblada a un explorador que ya
        tiene una doblada aprobada en esa fecha (evitar triple turno).
        
        Args:
            empleados: Lista o QuerySet de empleados a filtrar
            fecha: Fecha a verificar (date o string 'YYYY-MM-DD')
        
        Returns:
            Lista de empleados sin doblada activa
        """
        # Convertir fecha a objeto date si es string
        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        else:
            fecha_obj = fecha
        
        # Obtener IDs de empleados con doblada activa
        empleados_con_doblada = SolicitudCambio.objects.filter(
            tipo_cambio__nombre='DOBLADA',
            fecha_cambio_turno=fecha_obj,
            estado='aprobada'
        ).values_list('explorador_solicitante_id', flat=True)
        
        # Convertir QuerySet a lista si es necesario
        if isinstance(empleados, QuerySet):
            empleados_list = list(empleados)
        else:
            empleados_list = empleados
        
        # Filtrar empleados sin doblada activa
        empleados_disponibles = [
            emp for emp in empleados_list
            if emp.id not in empleados_con_doblada
        ]
        
        logger.debug(
            f"Filtrados {len(empleados_list) - len(empleados_disponibles)} empleados "
            f"con doblada activa en {fecha_obj}"
        )
        
        return empleados_disponibles
    
    @staticmethod
    def obtener_jornada_a_ceder(
        usuario_actual: Empleado,
        fecha: str,
        jornada_cedida: Optional[str] = None
    ) -> Optional[str]:
        """
        Determina la jornada que se va a ceder en una solicitud de doblada.
        
        Reglas:
        - Si jornada_cedida está presente, usarla (caso: solicitante está en doblada)
        - Si no, usar la jornada predeterminada del solicitante
        
        Args:
            usuario_actual: Explorador solicitante
            fecha: Fecha de la doblada (string 'YYYY-MM-DD')
            jornada_cedida: Jornada específica a ceder ('AM' o 'PM'), opcional
        
        Returns:
            Nombre de la jornada a ceder ('AM' o 'PM') o None si no se puede determinar
        """
        from turnos.services.jornada_service import JornadaService
        
        # Si hay jornada_cedida explícita, usarla
        if jornada_cedida:
            return jornada_cedida.upper()
        
        # Obtener jornada predeterminada del solicitante
        jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
            usuario_actual.id, fecha
        )
        
        if not jornada_solicitante:
            return None
        
        return jornada_solicitante.nombre.upper()
    
    @staticmethod
    def convertir_empleados_a_dict(empleados: List[Empleado], fecha: str) -> List[Dict[str, Any]]:
        """
        Convierte una lista de empleados a formato de diccionario para respuestas JSON.
        
        Args:
            empleados: Lista de instancias de Empleado
            fecha: Fecha para obtener jornada (string 'YYYY-MM-DD')
        
        Returns:
            Lista de diccionarios con información de empleados
        """
        from turnos.services.jornada_service import JornadaService
        
        resultado = []
        
        for empleado in empleados:
            jornada = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha)
            
            resultado.append({
                'id': empleado.id,
                'nombre': empleado.nombre,
                'apellido': empleado.apellido,
                'jornada': jornada.nombre if jornada else None
            })
        
        return resultado





