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
    
    @staticmethod
    def generar_deuda_fin_semana_predeterminado(explorador: Empleado, fecha: date) -> Optional[DeudaCorporativa]:
        """
        Genera deuda corporativa para una doblada predeterminada de sábado o domingo.
        
        IMPORTANTE: Solo genera si el explorador REALMENTE trabaja la doblada completa (AM+PM).
        Si por algún cambio de turno queda con media jornada, NO genera deuda.
        
        Solo genera si:
        1. Es sábado o domingo
        2. Le corresponde trabajar según alternancia
        3. Tiene AM+PM en BD (doblada completa) - Si solo tiene AM o PM, NO genera
        4. No existe ya una deuda para esa fecha
        
        Args:
            explorador: Explorador que trabaja el fin de semana
            fecha: Fecha del sábado o domingo
        
        Returns:
            DeudaCorporativa creada o None si ya existe o no aplica
        """
        # Verificar que es sábado o domingo
        if fecha.weekday() not in [5, 6]:  # 5 = Sábado, 6 = Domingo
            return None
        
        # Verificar que le corresponde trabajar según alternancia
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        if fecha.weekday() == 5:  # Sábado
            jornada_trabaja = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha)
        else:  # Domingo
            jornada_trabaja = AlternanciaFinesSemanaService.jornada_trabaja_domingo(fecha)
        
        if not jornada_trabaja:
            return None
        
        # Verificar jornada del explorador
        from turnos.services.jornada_service import JornadaService
        jornada_explorador = JornadaService.get_jornada_explorador_fecha(
            explorador.id, fecha.strftime('%Y-%m-%d')
        )
        if not jornada_explorador or jornada_explorador.nombre.upper() != jornada_trabaja.upper():
            return None
        
        # ✅ REGLA CRÍTICA: Verificar que tiene AM+PM en BD (doblada completa)
        # Si solo tiene AM o solo PM, NO generar deuda (alguien más trabajó media jornada)
        from turnos.models import Turno
        turnos_sabado = Turno.objects.filter(
            explorador=explorador,
            fecha=fecha
        ).select_related('jornada')
        
        jornadas_turnos = [t.jornada.nombre.upper() for t in turnos_sabado if t.jornada]
        tiene_am = 'AM' in jornadas_turnos
        tiene_pm = 'PM' in jornadas_turnos
        tiene_doblada_completa = tiene_am and tiene_pm
        
        # Si NO tiene doblada completa, NO generar deuda
        if not tiene_doblada_completa:
            logger.info(
                f"No se genera deuda para {explorador.nombre} en {fecha}: "
                f"tiene jornadas {jornadas_turnos} (no es doblada completa AM+PM)"
            )
            return None
        
        # Verificar si ya existe deuda para esta fecha
        deuda_existente = DeudaCorporativa.objects.filter(
            explorador=explorador,
            fecha_doblada=fecha,
            estado='activa',
            solicitud_origen__isnull=True  # Solo deudas de sábados predeterminados
        ).first()
        
        if deuda_existente:
            return deuda_existente  # Ya existe, retornar la existente
        
        # Crear nueva deuda corporativa (solo si tiene doblada completa)
        dia_semana = 'sábado' if fecha.weekday() == 5 else 'domingo'
        return DeudaCorporativaService.crear_deuda_corporativa(
            explorador=explorador,
            minutos=30,
            fecha_generacion=fecha,
            fecha_doblada=fecha,
            solicitud=None,  # No hay solicitud para dobladas predeterminadas
            comentario=f'Doblada predeterminada de {dia_semana} (alternancia) - {fecha.strftime("%d/%m/%Y")}'
        )


