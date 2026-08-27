"""
Servicio para gestión de deudas entre exploradores.

Responsabilidad única: Crear, consultar y gestionar deudas entre exploradores
generadas por solicitudes de doblada.
"""
import logging
from datetime import date
from typing import Optional

from django.db.models import Q, QuerySet

from empleados.models import Empleado
from solicitudes.models import DeudaExplorador, SolicitudCambio

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
        fecha_pago_pactada: date,
        jornada_cedida: str,
        media_jornada: bool = True,
        fecha_pago_real: Optional[date] = None
    ) -> DeudaExplorador:
        """
        Crear un registro de deuda entre exploradores.

        NO recibe `fecha_generacion` a propósito: ese campo del modelo es `auto_now_add`, o sea
        que Django graba la fecha de HOY al insertar y descarta cualquier valor que se le pase.
        Antes la firma lo aceptaba y varios llamadores le pasaban la fecha de cesión creyendo
        que se guardaba; se tiraba en silencio. Si necesitas la fecha del favor, está en
        `fecha_pago_pactada` o en `solicitud_origen.fecha_cambio_turno`.

        Args:
            deudor: Explorador que debe la jornada
            acreedor: Explorador al que se le debe la jornada
            solicitud: Solicitud que generó la deuda
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
            fecha_pago_pactada=fecha_pago_pactada,
            fecha_pago_real=fecha_pago_real,
            estado=estado,
            media_jornada=media_jornada,
            jornada_cedida=jornada_cedida
        )

        logger.info(f"Deuda creada: {deudor.nombre} debe a {acreedor.nombre} - {jornada_cedida}")
        return deuda
    
    @staticmethod
    def crear_deuda_idempotente(
        deudor: Empleado,
        acreedor: Empleado,
        solicitud: SolicitudCambio,
        fecha_pago_pactada: date,
        jornada_cedida: str,
        media_jornada: bool = True,
        fecha_pago_real: Optional[date] = None
    ) -> Optional[DeudaExplorador]:
        """
        Igual que `crear_deuda`, pero NO crea nada si ya existe una deuda NO cancelada de esta
        solicitud entre ese deudor y ese acreedor con esa misma fecha de pago pactada.

        Motivo: re-aplicar una solicitud ya aplicada (`reaplicar_doblada`,
        `corregir_doblada_cesion_total`, un reintento) volvía a crear la deuda, dejando dos
        registros del mismo favor. La clave incluye deudor+acreedor+fecha_pago_pactada para no
        confundir la deuda principal con la residual del pago en sábado, que va en sentido
        contrario y con otra fecha.

        OJO: la clave NO puede usar `fecha_generacion` — ese campo es `auto_now_add`, así que
        guarda la fecha de HOY. Filtrar por él nunca coincidiría (por eso ya ni se recibe como
        parámetro; ver `crear_deuda`).

        Devuelve None si ya existía. Ver PROTECTION_PATTERNS.md #21.
        """
        if DeudaExplorador.objects.filter(
            solicitud_origen=solicitud,
            deudor=deudor,
            acreedor=acreedor,
            fecha_pago_pactada=fecha_pago_pactada,
        ).exclude(estado='cancelada').exists():
            logger.info(
                "Deuda entre exploradores ya existente (%s → %s, solicitud %s): no se duplica.",
                deudor.nombre, acreedor.nombre, getattr(solicitud, 'id', None),
            )
            return None
        return DeudaService.crear_deuda(
            deudor=deudor,
            acreedor=acreedor,
            solicitud=solicitud,
            fecha_pago_pactada=fecha_pago_pactada,
            jornada_cedida=jornada_cedida,
            media_jornada=media_jornada,
            fecha_pago_real=fecha_pago_real,
        )

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








