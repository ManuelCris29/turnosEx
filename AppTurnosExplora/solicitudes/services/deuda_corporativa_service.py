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
            logger.warning("Error verificando festivo para deuda (fecha=%s)", fecha, exc_info=True)
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

    DURACION_BASE_DIAS = 15  # primera sanción: 15 días; cada reincidencia suma 15

    @staticmethod
    def gestionar_sancion_por_deuda(explorador: Empleado):
        """
        Sanciones progresivas por deuda vencida (no pagada dentro del mismo mes):
        - 1ª vez: 15 días. Si vence y sigue sin pagar → 30 días. Luego 45, 60…
        - Mientras haya una sanción activa no se crea otra (se espera a que venza).
        - Cuando el explorador paga, la sanción activa se levanta inmediatamente.
        - Cada nueva sanción genera una notificación in-app al explorador.
        """
        from empleados.models import SancionEmpleado
        from django.db.models import Q as _Q
        if not explorador:
            return
        hoy = date.today()
        info = DeudaCorporativaService._deuda_vencida_info(explorador)

        # Sanción AUTO activa en este momento
        auto_activa = (
            SancionEmpleado.objects
            .filter(explorador=explorador,
                    motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO,
                    fecha_inicio__lte=hoy,
                    fecha_fin__gte=hoy)
            .order_by('-fecha_inicio')
            .first()
        )

        if not info:
            # Deuda pagada → levantar sanción activa si la hay
            if auto_activa:
                auto_activa.fecha_fin = hoy - timedelta(days=1)
                auto_activa.save(update_fields=['fecha_fin', 'actualizado_en'])
                DeudaCorporativaService._invalidar_cache_mis_turnos_sancion(auto_activa)
            return

        # Hay deuda vencida → si ya hay sanción activa, esperar a que venza
        if auto_activa:
            return

        # Calcular cuántas sanciones AUTO ya expiraron desde que la deuda venció
        # para determinar la duración progresiva de la nueva.
        fecha_doblada = info['fecha_doblada']
        if fecha_doblada.month == 12:
            deuda_vencio_desde = date(fecha_doblada.year + 1, 1, 1)
        else:
            deuda_vencio_desde = date(fecha_doblada.year, fecha_doblada.month + 1, 1)

        vencidas_count = SancionEmpleado.objects.filter(
            explorador=explorador,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO,
            fecha_inicio__gte=deuda_vencio_desde,
            fecha_fin__lt=hoy,
        ).count()

        duracion = DeudaCorporativaService.DURACION_BASE_DIAS * (vencidas_count + 1)
        fecha_fin_nueva = hoy + timedelta(days=duracion)

        supervisor = getattr(explorador, 'supervisor', None) or explorador
        mes_nombre = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
                      'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'][fecha_doblada.month - 1]

        reincidencia = f" (reincidencia #{vencidas_count})" if vencidas_count else ""
        nueva = SancionEmpleado.objects.create(
            explorador=explorador,
            supervisor=supervisor,
            fecha_inicio=hoy,
            fecha_fin=fecha_fin_nueva,
            motivo=(
                f"{DeudaCorporativaService.AUTO_SANCION_PREFIJO} Sanción automática{reincidencia}: "
                f"tienes una doblada del {fecha_doblada.strftime('%d/%m/%Y')} cuya deuda de horas "
                f"no se pagó dentro de {mes_nombre}. Tienes {duracion} días para pagar la deuda (PDH). "
                f"Si no pagas antes del {fecha_fin_nueva.strftime('%d/%m/%Y')}, la siguiente sanción "
                f"será de {duracion + DeudaCorporativaService.DURACION_BASE_DIAS} días."
            ),
        )

        # Notificación in-app al explorador
        DeudaCorporativaService._notificar_sancion(explorador, nueva, duracion, fecha_fin_nueva, vencidas_count)
        DeudaCorporativaService._invalidar_cache_mis_turnos_sancion(nueva)

    @staticmethod
    def _notificar_sancion(explorador, sancion, duracion, fecha_fin, reincidencia_num) -> None:
        """Crea una notificación in-app informando al explorador de la nueva sanción."""
        try:
            from solicitudes.models import Notificacion
            if reincidencia_num == 0:
                titulo = f"⚠️ Sanción automática: {duracion} días bloqueado"
                intro = "Tienes una deuda de horas (doblada) que no pagaste dentro del mes correspondiente."
            else:
                titulo = f"⚠️ Sanción ampliada: {duracion} días bloqueados (reincidencia #{reincidencia_num})"
                intro = (
                    f"La sanción anterior venció y tu deuda sigue sin pagar. "
                    f"Esta es la reincidencia #{reincidencia_num}."
                )
            Notificacion.objects.create(
                destinatario=explorador,
                tipo='sancion',
                titulo=titulo,
                mensaje=(
                    f"{intro}\n\n"
                    f"Desde: {sancion.fecha_inicio.strftime('%d/%m/%Y')} "
                    f"hasta: {fecha_fin.strftime('%d/%m/%Y')} ({duracion} días).\n\n"
                    f"Durante este período NO puedes realizar solicitudes de cambio de turno ni permisos. "
                    f"Para levantar la sanción, paga tu deuda de horas (PDH) con tu supervisor."
                ),
                solicitud=None,
            )
        except Exception:
            logger.warning("Error creando notificación de sanción por deuda", exc_info=True)

    @staticmethod
    def _invalidar_cache_mis_turnos_sancion(sancion) -> None:
        """
        Invalida la caché de Mis Turnos del explorador en TODOS los meses que la sanción
        pudo afectar. Para sanciones indefinidas (o recién levantadas que antes lo eran),
        se cubre además un año hacia adelante, porque una sanción indefinida se muestra en
        todos los meses futuros y, al levantarla, esos meses cacheados deben refrescarse.
        """
        try:
            from core.services.cache_service import CacheService
            hoy = date.today()
            desde = sancion.fecha_inicio
            # Cubrir hasta el mayor entre su fecha_fin y un año adelante (para indefinidas/levantadas).
            hasta = max(sancion.fecha_fin or hoy, hoy + timedelta(days=365))
            meses = set()
            d = date(desde.year, desde.month, 1)
            while d <= hasta:
                meses.add((d.month, d.year))
                # avanzar al primer día del mes siguiente
                if d.month == 12:
                    d = date(d.year + 1, 1, 1)
                else:
                    d = date(d.year, d.month + 1, 1)
            for m, y in meses:
                CacheService.invalidar_cache_turnos_empleado(sancion.explorador_id, m, y)
        except Exception:
            # La invalidación de caché nunca debe romper el flujo principal.
            logger.warning("Error invalidando caché de turnos por sanción (explorador=%s)", sancion.explorador_id, exc_info=True)

    @staticmethod
    def crear_deuda_corporativa(
        explorador: Empleado,
        minutos: int,
        fecha_doblada: date,
        solicitud: Optional[SolicitudCambio] = None,
        comentario: Optional[str] = None
    ) -> DeudaCorporativa:
        """
        Crear un registro de deuda corporativa.

        NO recibe `fecha_generacion`: ese campo es `auto_now_add`, o sea que Django graba la
        fecha de HOY al insertar y descarta lo que se le pase. Aceptarlo como parámetro solo
        invita a creer que se puede fijar. La fecha que importa para el negocio es
        `fecha_doblada` (el día que la persona realmente dobló), y esa sí se guarda.

        Args:
            explorador: Explorador que acumula la deuda
            minutos: Minutos de deuda (típicamente 30 por doblada)
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
    def crear_deuda_corporativa_idempotente(
        explorador: Empleado,
        minutos: int,
        fecha_doblada: date,
        solicitud: Optional[SolicitudCambio] = None,
        comentario: Optional[str] = None
    ) -> Optional[DeudaCorporativa]:
        """
        Igual que `crear_deuda_corporativa`, pero NO crea nada si ya existe una deuda ACTIVA
        para la misma combinación (explorador, fecha_doblada, solicitud_origen).

        Un día doblado = 30 min, SIEMPRE. Los turnos toleran una re-aplicación (se borran y se
        recrean), pero la deuda no: se sumaba encima. Esto pasa de verdad al re-aplicar una
        solicitud ya aplicada (`reaplicar_doblada`, `corregir_doblada_cesion_total`, un reintento
        o una re-aprobación), y el cobro doble no produce ningún error visible: aparece en el
        Consolidado de Horas semanas después.

        Úsala SIEMPRE que la deuda nazca de aplicar una solicitud. Devuelve None si ya existía.
        Ver PROTECTION_PATTERNS.md #21.
        """
        if DeudaCorporativa.objects.filter(
            explorador=explorador,
            fecha_doblada=fecha_doblada,
            solicitud_origen=solicitud,
            estado='activa',
        ).exists():
            logger.info(
                "Deuda corporativa ya existente para %s en %s (solicitud %s): no se duplica.",
                explorador.nombre, fecha_doblada, getattr(solicitud, 'id', None),
            )
            return None
        return DeudaCorporativaService.crear_deuda_corporativa(
            explorador=explorador,
            minutos=minutos,
            fecha_doblada=fecha_doblada,
            solicitud=solicitud,
            comentario=comentario,
        )

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
    
