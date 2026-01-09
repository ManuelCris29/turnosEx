"""
Servicio para gestión de deudas corporativas.

Responsabilidad única: Crear, consultar y gestionar deudas corporativas
acumuladas por exploradores al realizar dobladas.
"""
from typing import Optional
from django.db.models import Sum, QuerySet
from solicitudes.models import DeudaCorporativa, SolicitudCambio
from empleados.models import Empleado
from datetime import date
import logging

logger = logging.getLogger(__name__)


class DeudaCorporativaService:
    """
    Servicio para gestión de deudas corporativas.
    
    Responsabilidad única: Operaciones sobre deudas corporativas acumuladas.
    """
    
    @staticmethod
    def crear_deuda_corporativa(
        explorador: Empleado,
        minutos: int,
        fecha_generacion: date,
        fecha_doblada: date,
        solicitud: Optional[SolicitudCambio] = None,
        comentario: Optional[str] = None
    ) -> DeudaCorporativa:
        """
        Crear un registro de deuda corporativa.
        
        Args:
            explorador: Explorador que acumula la deuda
            minutos: Minutos de deuda (típicamente 30 por doblada)
            fecha_generacion: Fecha en que se generó la deuda
            fecha_doblada: Fecha en que se realizó la doblada
            solicitud: Solicitud que generó la deuda (opcional)
            comentario: Comentario opcional
        
        Returns:
            Instancia de DeudaCorporativa creada
        """
        deuda = DeudaCorporativa.objects.create(
            explorador=explorador,
            solicitud_origen=solicitud,
            minutos=minutos,
            fecha_generacion=fecha_generacion,
            fecha_doblada=fecha_doblada,
            estado='activa',
            comentario=comentario
        )
        
        logger.info(f"Deuda corporativa creada: {explorador.nombre} - {minutos} min - {fecha_doblada}")
        
        # CORRECCIÓN: También crear registro en PDH para visibilidad de supervisores
        try:
            from permisos.models import PDH
            
            # Determinar supervisor
            supervisor = None
            if solicitud:
                # Intentar obtener supervisor que aprobó la solicitud
                if hasattr(solicitud, 'aprobado_supervisor') and solicitud.aprobado_supervisor:
                    supervisor = solicitud.aprobado_supervisor
                # Si no, usar supervisor del solicitante
                elif solicitud.explorador_solicitante:
                    supervisor = getattr(solicitud.explorador_solicitante, 'supervisor', None)
            
            # Si aún no hay supervisor, usar supervisor del explorador
            if not supervisor:
                supervisor = getattr(explorador, 'supervisor', None)
            
            # Crear registro en PDH (convertir minutos a horas)
            PDH.objects.create(
                explorador=explorador,
                solicitud=solicitud,
                fecha=fecha_doblada,
                horas=round(minutos / 60, 2),  # 30 min = 0.5 horas
                supervisor=supervisor,
                tipo_registro='deuda_corporativa',
                comentario=comentario or f'Deuda corporativa acumulada: {minutos} minutos por doblada en {fecha_doblada}'
            )
            logger.info(
                f"Registro PDH creado para deuda corporativa: {explorador.nombre} - "
                f"{minutos} min ({round(minutos / 60, 2)} hrs) - Supervisor: {supervisor.nombre if supervisor else 'N/A'}"
            )
        except Exception as e:
            logger.warning(
                f"No se pudo crear registro en PDH para {explorador.nombre}: {str(e)}. "
                f"DeudaCorporativa se creó correctamente (principal)."
            )
            # No fallar si PDH falla, DeudaCorporativa es la tabla principal
        
        return deuda
    
    @staticmethod
    def obtener_deuda_total(explorador: Empleado) -> int:
        """
        Obtener la deuda corporativa total acumulada de un explorador.
        Suma todas las deudas con estado 'activa'.
        
        Args:
            explorador: Explorador para el cual calcular la deuda total
        
        Returns:
            Total de minutos de deuda corporativa acumulada
        """
        total = DeudaCorporativa.objects.filter(
            explorador=explorador,
            estado='activa'
        ).aggregate(total=Sum('minutos'))['total']
        
        return total or 0
    
    @staticmethod
    def obtener_deudas_activas(explorador: Empleado) -> QuerySet[DeudaCorporativa]:
        """
        Obtener todas las deudas corporativas activas de un explorador.
        
        Args:
            explorador: Explorador para el cual obtener las deudas
        
        Returns:
            QuerySet de deudas activas ordenadas por fecha de generación
        """
        return DeudaCorporativa.objects.filter(
            explorador=explorador,
            estado='activa'
        ).select_related('solicitud_origen').order_by('-fecha_generacion')
    
    @staticmethod
    def cancelar_deuda(deuda: DeudaCorporativa, comentario: Optional[str] = None) -> DeudaCorporativa:
        """
        Cancelar una deuda corporativa (marcar como cancelada).
        Útil para correcciones administrativas.
        
        Args:
            deuda: Instancia de DeudaCorporativa a cancelar
            comentario: Comentario opcional sobre la cancelación
        
        Returns:
            Instancia de DeudaCorporativa actualizada
        """
        deuda.estado = 'cancelada'
        if comentario:
            deuda.comentario = comentario
        deuda.save()
        
        logger.info(f"Deuda corporativa cancelada: {deuda.explorador.nombre} - {deuda.minutos} min")
        return deuda
    
    @staticmethod
    def obtener_deudas_por_solicitud(solicitud: SolicitudCambio) -> QuerySet[DeudaCorporativa]:
        """
        Obtener todas las deudas corporativas generadas por una solicitud.
        
        Args:
            solicitud: Solicitud de doblada
        
        Returns:
            QuerySet de deudas corporativas
        """
        return DeudaCorporativa.objects.filter(
            solicitud_origen=solicitud
        ).select_related('explorador')


