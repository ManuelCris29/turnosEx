"""
Servicio para filtrar empleados según reglas específicas de dobladas.

Responsabilidad única: Aplicar filtros de negocio para determinar qué empleados
están disponibles para recibir solicitudes de doblada.
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

from django.db.models import QuerySet

from core.utils.date_utils import DateUtils
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from turnos.models import Turno

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
        tiene una doblada aprobada en esa fecha (evitar triple turno). "Tener doblada"
        es trabajar AM+PM ese día: el RECEPTOR de una doblada aprobada, o quien ya
        tiene ambos turnos materializados. El SOLICITANTE de una doblada no se dobla,
        se libera — ese descansa y sigue disponible.
        
        Args:
            empleados: Lista o QuerySet de empleados a filtrar
            fecha: Fecha a verificar (date o string 'YYYY-MM-DD')
        
        Returns:
            Lista de empleados sin doblada activa
        """
        # Convertir fecha a objeto date si es string
        if isinstance(fecha, str):
            fecha_obj = DateUtils.parse_date(fecha)
        else:
            fecha_obj = fecha
        
        # -------------------------------
        # 1) Empleados que QUEDAN DOBLADOS por una SolicitudCambio aprobada
        # -------------------------------
        # OJO CON EL ROL: en una DOBLADA el `explorador_solicitante` es quien CEDE su jornada y
        # DESCANSA; quien se dobla (AM+PM) es el `explorador_receptor`. Filtrar por solicitante
        # excluía justo a la gente libre ese día —incluida la que descansa porque te cedió a TI—,
        # así que no aparecía en el selector de compañeros pese a estar disponible.
        empleados_con_doblada_receptor = set(
            SolicitudCambio.objects.filter(
                tipo_cambio__nombre='DOBLADA',
                fecha_cambio_turno=fecha_obj,
                estado='aprobada'
            ).values_list('explorador_receptor_id', flat=True)
        )
        
        # Convertir QuerySet a lista si es necesario
        if isinstance(empleados, QuerySet):
            empleados_list = list(empleados)
        else:
            empleados_list = empleados

        if not empleados_list:
            return []

        # -------------------------------
        # 2) Empleados con DOBLADA real en Turno (AM + PM en la misma fecha)
        # -------------------------------
        turnos = (
            Turno.objects
            .filter(explorador__in=empleados_list, fecha=fecha_obj)
            .select_related('jornada', 'explorador')
        )

        jornadas_por_empleado: Dict[int, set] = {}
        for turno in turnos:
            if not turno.jornada:
                continue
            jornadas_por_empleado.setdefault(turno.explorador_id, set()).add(
                turno.jornada.nombre.upper()
            )

        empleados_con_doblada_turno = {
            emp_id
            for emp_id, jornadas in jornadas_por_empleado.items()
            if 'AM' in jornadas and 'PM' in jornadas
        }

        # -------------------------------
        # 3) Unir todas las fuentes de doblada
        # -------------------------------
        empleados_con_doblada = empleados_con_doblada_receptor.union(
            empleados_con_doblada_turno
        )

        # -------------------------------
        # 4) Filtrar empleados sin doblada activa
        # -------------------------------
        empleados_disponibles = [
            emp for emp in empleados_list
            if emp.id not in empleados_con_doblada
        ]

        logger.debug(
            f"Filtrados {len(empleados_list) - len(empleados_disponibles)} empleados "
            f"que quedan doblados en {fecha_obj} "
            f"(receptores={len(empleados_con_doblada_receptor)}, "
            f"turnos={len(empleados_con_doblada_turno)})"
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

    @staticmethod
    def obtener_empleados_en_descanso(fecha: str, excluir_id: int) -> List[Empleado]:
        """
        Obtiene empleados activos que están en descanso en la fecha dada.
        Un empleado descansa si no tiene turnos y su jornada calculada es None/Descanso.
        """
        from turnos.services.turno_service import TurnoService

        fecha_obj = DateUtils.parse_date(fecha) if isinstance(fecha, str) else fecha

        empleados_activos = (
            Empleado.objects.filter(activo=True)
            .exclude(id=excluir_id)
            .select_related('supervisor')
        )

        turnos_fecha = set(
            Turno.objects.filter(explorador__in=empleados_activos, fecha=fecha_obj)
            .values_list('explorador_id', flat=True)
        )

        en_descanso = []
        for emp in empleados_activos:
            if emp.id in turnos_fecha:
                continue
            jornada_display = TurnoService.obtener_jornada_display(emp, fecha_obj)
            if jornada_display is None:
                en_descanso.append(emp)

        return en_descanso







