"""
Servicio para gestión de deudas corporativas.

Responsabilidad única: Crear, consultar y gestionar deudas corporativas
acumuladas por exploradores al realizar dobladas.
"""
from typing import Optional
from django.db.models import Sum, QuerySet
from solicitudes.models import DeudaCorporativa, SolicitudCambio
from empleados.models import Empleado
from datetime import date, timedelta
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

    # Marca para identificar las sanciones generadas automáticamente por deuda vencida
    AUTO_SANCION_PREFIJO = '[AUTO-DEUDA]'

    @staticmethod
    def _deuda_vencida_info(explorador: Empleado):
        """
        Determina si el explorador tiene deuda corporativa VENCIDA: una doblada cuya deuda
        no se pagó DENTRO DE SU MISMO MES (es de un mes anterior al actual y sigue 'activa').
        Las deudas pagadas se marcan estado='pagada', por lo que las 'activa' son exactamente
        las pendientes: basta mirar la más antigua.
        Devuelve {'fecha_doblada'} de la deuda vencida, o None.
        """
        from solicitudes.models import DeudaCorporativa
        d = (
            DeudaCorporativa.objects
            .filter(explorador=explorador, estado='activa')
            .order_by('fecha_doblada', 'id')
            .first()
        )
        if not d:
            return None
        hoy = date.today()
        # Vencida si la más antigua pendiente es de un MES anterior al actual.
        if (d.fecha_doblada.year, d.fecha_doblada.month) < (hoy.year, hoy.month):
            return {'fecha_doblada': d.fecha_doblada}
        return None

    @staticmethod
    def gestionar_sancion_por_deuda(explorador: Empleado):
        """
        Genera o levanta AUTOMÁTICAMENTE la sanción por deuda de doblada que no se pagó
        dentro de su mismo mes:
        - Si hay deuda vencida (de un mes anterior, sin pagar) y no existe ya una sanción
          automática activa → crea la sanción (bloquea cualquier solicitud).
        - Si ya NO hay deuda vencida y existe una sanción automática activa → la levanta.
        """
        from empleados.models import SancionEmpleado
        from django.db.models import Q as _Q
        if not explorador:
            return
        hoy = date.today()
        info = DeudaCorporativaService._deuda_vencida_info(explorador)
        auto = (
            SancionEmpleado.objects
            .filter(explorador=explorador, motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO,
                    fecha_inicio__lte=hoy)
            .filter(_Q(fecha_fin__isnull=True) | _Q(fecha_fin__gte=hoy))
            .order_by('-fecha_inicio')
            .first()
        )
        if info and not auto:
            supervisor = getattr(explorador, 'supervisor', None) or explorador
            mes_nombre = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                          'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][info['fecha_doblada'].month - 1]
            SancionEmpleado.objects.create(
                explorador=explorador,
                supervisor=supervisor,
                fecha_inicio=hoy,
                fecha_fin=None,  # indefinida hasta que pague la deuda
                motivo=(
                    f"{DeudaCorporativaService.AUTO_SANCION_PREFIJO} Sanción automática: tienes una doblada del "
                    f"{info['fecha_doblada'].strftime('%d/%m/%Y')} cuya deuda de horas no se pagó dentro de {mes_nombre}. "
                    f"Paga la deuda (PDH) para levantarla."
                ),
            )
        elif (not info) and auto:
            # Ya no hay deuda vencida: levantar la sanción automática
            auto.fecha_fin = hoy - timedelta(days=1)
            auto.save(update_fields=['fecha_fin', 'actualizado_en'])

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
    
