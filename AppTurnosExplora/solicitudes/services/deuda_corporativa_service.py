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
from django.utils import timezone

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
        hoy = timezone.localdate()
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
        from empleados.sancion_utils import vigentes_en
        if not explorador:
            return
        hoy = timezone.localdate()
        info = DeudaCorporativaService._deuda_vencida_info(explorador)

        # Sanción AUTO vigente en este momento (una ya levantada no cuenta)
        auto_activa = (
            SancionEmpleado.objects
            .filter(vigentes_en(hoy),
                    explorador=explorador,
                    motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO)
            .order_by('-fecha_inicio')
            .first()
        )

        if not info:
            # Deuda pagada → levantar la sanción vigente si la hay.
            # Se LEVANTA (queda el registro de por qué terminó antes) en vez de recortarle
            # la fecha_fin: eso perdía la duración original y, si el pago llegaba el mismo
            # día en que nació la sanción, dejaba fecha_fin un día ANTES de fecha_inicio.
            if auto_activa:
                auto_activa.levantar(
                    motivo='Deuda de horas pagada: la sanción automática se levanta sola.',
                    supervisor=None, fecha=hoy)
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

        # Solo cuentan las que EXPIRARON sin pagar. Una levantada se levantó porque el
        # explorador pagó, así que no es reincidencia: agravar por ella castigaría
        # justo la conducta que se quiere premiar. Antes se colaban, porque levantar
        # consistía en dejarles la fecha_fin en el pasado y aquí parecían vencidas.
        vencidas_count = SancionEmpleado.objects.filter(
            explorador=explorador,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO,
            fecha_inicio__gte=deuda_vencio_desde,
            fecha_fin__lt=hoy,
            levantada_en__isnull=True,
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
            hoy = timezone.localdate()
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
        para ese (explorador, fecha_doblada) — venga de la solicitud que venga.

        Un día doblado = 30 min, SIEMPRE. Nadie puede doblar dos veces el mismo día, así que dos
        deudas activas en la misma fecha son necesariamente un cobro doble. La clave es por DÍA a
        propósito: cuando incluía `solicitud_origen`, dos solicitudes DISTINTAS que tocaban el mismo
        día del mismo explorador creaban 30 min cada una (60 min por un solo día doblado) y el guard
        no las veía. El caso real venía por la doblada permanente, que creaba sobre sus ocurrencias
        calculadas sin mirar el estado del día.

        También cubre el motivo original: re-aplicar una solicitud ya aplicada
        (`reaplicar_doblada`, `corregir_doblada_cesion_total`, un reintento o una re-aprobación).
        El cobro doble no produce ningún error visible: aparece en el Consolidado de Horas semanas
        después.

        Solo mira las ACTIVAS: si la deuda del día fue cancelada (solicitud revertida o el día dejó
        de ser doblada) se puede volver a crear, que es justo lo que debe pasar al re-aplicar.

        Úsala SIEMPRE que la deuda nazca de aplicar una solicitud. Devuelve None si ya existía.
        Ver PROTECTION_PATTERNS.md #21.
        """
        existente = DeudaCorporativa.objects.filter(
            explorador=explorador,
            fecha_doblada=fecha_doblada,
            estado='activa',
        ).first()
        if existente:
            logger.info(
                "Deuda corporativa ya existente para %s en %s (deuda %s, solicitud origen %s); "
                "la solicitud %s no crea otra: un día doblado = 30 min.",
                explorador.nombre, fecha_doblada, existente.id,
                existente.solicitud_origen_id, getattr(solicitud, 'id', None),
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
    def cancelar_deudas_de_solicitud(solicitud: SolicitudCambio, motivo: str = '') -> int:
        """
        Cancela las deudas corporativas ACTIVAS de una solicitud al revertirla. Devuelve cuántas.

        Úsala en vez de `DeudaCorporativa.objects.filter(solicitud_origen=...).update(...)`: el
        filtro por `estado='activa'` es la parte que importa y se olvidaba. Sin él, una deuda ya
        PAGADA pasaba a 'cancelada' al revertir, con dos daños: se perdía el registro de que el
        explorador ya compensó esos 30 min, y el PDH que la pagó quedaba apuntando (vía
        `deudas_pagadas`) a una deuda que dice estar cancelada. Si después se re-aplicaba la
        solicitud, el guard idempotente no veía nada activo y volvía a cobrar un día ya pagado.

        Una deuda pagada es historia cerrada: revertir la solicitud no des-paga lo que ya se pagó.

        OJO: esto vale solo para `DeudaCorporativa`. En `DeudaExplorador` el estado 'pagada' es
        otra cosa (el par de favores está completo, y se marca al crearla), así que ahí sí hay que
        cancelarla al revertir — ver `exclude(estado='cancelada')` en signals.py.
        """
        n = (DeudaCorporativa.objects
             .filter(solicitud_origen=solicitud, estado='activa')
             .update(estado='cancelada'))
        if n:
            logger.info(
                "Solicitud %s revertida%s: %s deuda(s) corporativa(s) activa(s) canceladas "
                "(las pagadas se conservan).",
                getattr(solicitud, 'id', None), f' ({motivo})' if motivo else '', n,
            )
        return n

    @staticmethod
    def sincronizar_deuda_corporativa(explorador: Empleado, fecha: date, motivo: str = '') -> int:
        """
        Cancela las deudas corporativas ACTIVAS de `explorador` en `fecha` si ese día YA NO es
        DOBLADA según los turnos reales.

        Los 30 min son de quien REALMENTE dobla. Cuando una solicitud posterior le quita una de
        las dos mitades (p. ej. cede a un tercero la jornada que otro compañero le había cedido),
        deja de doblar y los 30 min pasan a quien ahora dobla — pero la deuda vieja seguía activa
        y sumando en el Consolidado de Horas. Llamar después de aplicar los turnos.

        Devuelve el número de deudas canceladas.
        """
        from turnos.services.turno_service import TurnoService

        if TurnoService.obtener_jornada_display(explorador, fecha) == 'DOBLADA':
            return 0

        activas = list(DeudaCorporativa.objects.filter(
            explorador=explorador, fecha_doblada=fecha, estado='activa',
        ))
        for deuda in activas:
            DeudaCorporativaService.cancelar_deuda(
                deuda,
                comentario=(
                    f"Cancelada automáticamente: el {fecha} ya no es jornada DOBLADA para "
                    f"{explorador.nombre}{f' ({motivo})' if motivo else ''}."
                ),
            )
        if activas:
            logger.info(
                "Deuda corporativa sincronizada: %s deuda(s) canceladas para %s en %s (ya no dobla).",
                len(activas), explorador.nombre, fecha,
            )
        return len(activas)

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
    
