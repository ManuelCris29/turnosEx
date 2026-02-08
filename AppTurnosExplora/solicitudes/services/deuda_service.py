"""
Servicio para gestión de deudas entre exploradores.

Responsabilidad única: Crear, consultar y gestionar deudas entre exploradores
generadas por solicitudes de doblada.
"""
from typing import Optional
from django.db.models import Q, QuerySet
from solicitudes.models import DeudaExplorador, SolicitudCambio
from empleados.models import Empleado
from datetime import date
import logging

logger = logging.getLogger(__name__)


class DeudaService:
    """
    Servicio para gestión de deudas entre exploradores.
    
    Responsabilidad única: Operaciones CRUD sobre deudas entre exploradores.
    """
    
    @staticmethod
    def crear_deuda(
        deudor: Empleado,
        acreedor: Empleado,
        solicitud: SolicitudCambio,
        fecha_generacion: date,
        fecha_pago_pactada: date,
        jornada_cedida: str,
        media_jornada: bool = True,
        fecha_pago_real: Optional[date] = None
    ) -> DeudaExplorador:
        """
        Crear un registro de deuda entre exploradores.
        
        Args:
            deudor: Explorador que debe la jornada
            acreedor: Explorador al que se le debe la jornada
            solicitud: Solicitud que generó la deuda
            fecha_generacion: Fecha en que se generó la deuda
            fecha_pago_pactada: Fecha acordada para pagar
            jornada_cedida: 'AM' o 'PM' (jornada que se cedió)
            media_jornada: True si es media jornada, False si es completa
            fecha_pago_real: Fecha en que se pagó realmente (opcional)
        
        Returns:
            Instancia de DeudaExplorador creada
        """
        estado = 'pagada' if fecha_pago_real else 'pendiente'
        
        deuda = DeudaExplorador.objects.create(
            deudor=deudor,
            acreedor=acreedor,
            solicitud_origen=solicitud,
            fecha_generacion=fecha_generacion,
            fecha_pago_pactada=fecha_pago_pactada,
            fecha_pago_real=fecha_pago_real,
            estado=estado,
            media_jornada=media_jornada,
            jornada_cedida=jornada_cedida
        )
        
        logger.info(f"Deuda creada: {deudor.nombre} debe a {acreedor.nombre} - {jornada_cedida}")
        return deuda
    
    @staticmethod
    def obtener_deudas_pendientes(explorador: Empleado) -> QuerySet[DeudaExplorador]:
        """
        Obtener todas las deudas pendientes donde el explorador es deudor o acreedor.
        
        Args:
            explorador: Explorador para el cual obtener las deudas
        
        Returns:
            QuerySet de deudas pendientes
        """
        return DeudaExplorador.objects.filter(
            Q(deudor=explorador) | Q(acreedor=explorador),
            estado='pendiente'
        ).select_related('deudor', 'acreedor', 'solicitud_origen').order_by('fecha_pago_pactada')
    
    @staticmethod
    def obtener_deudas_por_pagar(explorador: Empleado) -> QuerySet[DeudaExplorador]:
        """
        Obtener deudas donde el explorador es deudor y están pendientes.
        
        Args:
            explorador: Explorador deudor
        
        Returns:
            QuerySet de deudas ordenadas por fecha de pago pactada
        """
        return DeudaExplorador.objects.filter(
            deudor=explorador,
            estado='pendiente'
        ).select_related('acreedor', 'solicitud_origen').order_by('fecha_pago_pactada')
    
    @staticmethod
    def obtener_deudas_por_cobrar(explorador: Empleado) -> QuerySet[DeudaExplorador]:
        """
        Obtener deudas donde el explorador es acreedor y están pendientes.
        
        Args:
            explorador: Explorador acreedor
        
        Returns:
            QuerySet de deudas ordenadas por fecha de pago pactada
        """
        return DeudaExplorador.objects.filter(
            acreedor=explorador,
            estado='pendiente'
        ).select_related('deudor', 'solicitud_origen').order_by('fecha_pago_pactada')
    
    @staticmethod
    def pagar_deuda(deuda: DeudaExplorador, fecha_pago_real: date) -> DeudaExplorador:
        """
        Marcar una deuda como pagada.
        
        Args:
            deuda: Instancia de DeudaExplorador a pagar
            fecha_pago_real: Fecha en que se pagó realmente
        
        Returns:
            Instancia de DeudaExplorador actualizada
        """
        deuda.estado = 'pagada'
        deuda.fecha_pago_real = fecha_pago_real
        deuda.save()
        
        logger.info(f"Deuda pagada: {deuda.deudor.nombre} pagó a {deuda.acreedor.nombre}")
        return deuda
    
    @staticmethod
    def cancelar_deuda(deuda: DeudaExplorador) -> DeudaExplorador:
        """
        Cancelar una deuda (marcar como cancelada).
        
        Args:
            deuda: Instancia de DeudaExplorador a cancelar
        
        Returns:
            Instancia de DeudaExplorador actualizada
        """
        deuda.estado = 'cancelada'
        deuda.save()
        
        logger.info(f"Deuda cancelada: {deuda.deudor.nombre} - {deuda.acreedor.nombre}")
        return deuda
    
    @staticmethod
    def obtener_deuda_por_solicitud(solicitud: SolicitudCambio) -> Optional[DeudaExplorador]:
        """
        Obtener la deuda generada por una solicitud específica.
        
        Args:
            solicitud: Solicitud de doblada
        
        Returns:
            Instancia de DeudaExplorador o None si no existe
        """
        return DeudaExplorador.objects.filter(solicitud_origen=solicitud).first()





