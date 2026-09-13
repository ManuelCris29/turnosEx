"""Persistencia de `DeudaCorporativa`: crear, cancelar, sincronizar y sumar.

Extraído de `DeudaCorporativaService`, que había crecido a 1130 líneas y 21 métodos
mezclando cuatro cosas distintas: la POLÍTICA de sanción por deuda (a quién se sanciona y
por cuánto), la persistencia de las deudas, las notificaciones y la auditoría de morosos.
Cambiar cualquiera de ellas obligaba a abrir el mismo archivo — el caso de libro de
Divergent Change.

Aquí vive solo el acceso a datos: ninguna regla de negocio decide nada en este módulo, y
por eso puede usarse desde las estrategias al aplicar una solicitud sin arrastrar consigo
la máquina de sanciones.
"""
import logging
from datetime import date
from typing import Optional

from django.db.models import Sum

from core.constants import JornadaDisplay
from empleados.models import Empleado
from solicitudes.models import DeudaCorporativa, SolicitudCambio

logger = logging.getLogger(__name__)


class DeudaCorporativaRepository:
    """Operaciones de lectura y escritura sobre `DeudaCorporativa`."""

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
        return DeudaCorporativaRepository.crear_deuda_corporativa(
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

        if TurnoService.obtener_jornada_display(explorador, fecha) == JornadaDisplay.DOBLADA:
            return 0

        activas = list(DeudaCorporativa.objects.filter(
            explorador=explorador, fecha_doblada=fecha, estado='activa',
        ))
        for deuda in activas:
            DeudaCorporativaRepository.cancelar_deuda(
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
