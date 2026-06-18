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
    def aplica_deuda_doblada(fecha: date) -> bool:
        """
        Regla de negocio: los 30 minutos de deuda corporativa por doblada solo
        aplican de LUNES A VIERNES. Los sábados, domingos y festivos NO generan
        deuda, porque ese día se trabaja una jornada completa de todos modos.
        """
        if fecha.weekday() >= 5:  # 5=sábado, 6=domingo
            return False
        try:
            from solicitudes.services.ct_permanente_helper import _es_festivo
            if _es_festivo(fecha):
                return False
        except Exception:
            pass
        return True

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

        # Nota: la ACUMULACIÓN de horas vive en DeudaCorporativa y se muestra en el
        # Consolidado de Horas. El modelo PDH se reserva para los PAGOS de horas
        # (descuentos autorizados por un supervisor), que son un ledger aparte.
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
    
