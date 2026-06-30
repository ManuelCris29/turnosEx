"""
SolicitudRepository

Centraliza las queries a SolicitudCambio. Ninguna vista ni servicio debería
hacer SolicitudCambio.objects.filter(...) directamente para los casos cubiertos aquí.

Beneficio principal: cuando hay que añadir un índice, select_related o caché,
hay un único lugar donde hacerlo.
"""
from django.db.models import Q, QuerySet
from solicitudes.models import SolicitudCambio


class SolicitudRepository:

    # ------------------------------------------------------------------
    # Lecturas básicas
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_id(solicitud_id: int, select_related: list | None = None) -> SolicitudCambio | None:
        qs = SolicitudCambio.objects
        if select_related:
            qs = qs.select_related(*select_related)
        try:
            return qs.get(id=solicitud_id)
        except SolicitudCambio.DoesNotExist:
            return None

    @staticmethod
    def get_by_id_con_relaciones(solicitud_id: int) -> SolicitudCambio | None:
        try:
            return SolicitudCambio.objects.select_related(
                'explorador_solicitante', 'explorador_receptor', 'explorador_solicitante__supervisor'
            ).get(id=solicitud_id)
        except SolicitudCambio.DoesNotExist:
            return None

    @staticmethod
    def get_by_id_with_lock(solicitud_id: int, select_related: list | None = None) -> SolicitudCambio | None:
        """Versión con select_for_update() para uso dentro de transaction.atomic()."""
        qs = SolicitudCambio.objects.select_for_update()
        if select_related:
            qs = qs.select_related(*select_related)
        try:
            return qs.get(id=solicitud_id)
        except SolicitudCambio.DoesNotExist:
            return None

    # ------------------------------------------------------------------
    # Por explorador y estado
    # ------------------------------------------------------------------

    @staticmethod
    def pendientes_de_explorador(explorador) -> QuerySet:
        """Solicitudes pendientes donde el explorador es solicitante o receptor."""
        return (SolicitudCambio.objects
                .filter(estado='pendiente')
                .filter(Q(explorador_solicitante=explorador) | Q(explorador_receptor=explorador))
                .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor')
                .order_by('-fecha_solicitud'))

    @staticmethod
    def aprobadas_de_explorador(explorador) -> QuerySet:
        """Solicitudes aprobadas donde el explorador participa."""
        return (SolicitudCambio.objects
                .filter(estado='aprobada')
                .filter(Q(explorador_solicitante=explorador) | Q(explorador_receptor=explorador))
                .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada')
                .order_by('-fecha_resolucion'))

    @staticmethod
    def historial_explorador(explorador, limit: int = 50) -> QuerySet:
        """Historial completo de solicitudes de un explorador (cualquier estado)."""
        return (SolicitudCambio.objects
                .filter(Q(explorador_solicitante=explorador) | Q(explorador_receptor=explorador))
                .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor')
                .order_by('-fecha_solicitud')[:limit])

    # ------------------------------------------------------------------
    # Pendientes para aprobación (supervisor)
    # ------------------------------------------------------------------

    @staticmethod
    def pendientes_para_supervisor(supervisor) -> QuerySet:
        """Solicitudes pendientes cuyo solicitante tiene al supervisor dado."""
        return (SolicitudCambio.objects
                .filter(estado='pendiente', explorador_solicitante__supervisor=supervisor)
                .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor')
                .order_by('-fecha_solicitud'))

    # ------------------------------------------------------------------
    # Por tipo y fecha (para validaciones)
    # ------------------------------------------------------------------

    @staticmethod
    def aprobadas_por_tipo_y_explorador(tipo_nombre: str, explorador) -> QuerySet:
        """Solicitudes aprobadas de un tipo específico donde el explorador participa."""
        return (SolicitudCambio.objects
                .filter(
                    estado='aprobada',
                    tipo_cambio__nombre=tipo_nombre,
                )
                .filter(Q(explorador_solicitante=explorador) | Q(explorador_receptor=explorador))
                .select_related('doblada'))

    @staticmethod
    def aprobadas_cambio_descanso_recientes(explorador, desde) -> QuerySet:
        """Solicitudes de CAMBIO DESCANSO aprobadas desde una fecha/hora (para ventana cancelación)."""
        return (SolicitudCambio.objects
                .filter(
                    tipo_cambio__nombre='CAMBIO DESCANSO',
                    estado='aprobada',
                    fecha_resolucion__gte=desde,
                )
                .filter(Q(explorador_solicitante=explorador) | Q(explorador_receptor=explorador))
                .select_related('doblada'))

    @staticmethod
    def existe_solicitud_activa_entre(solicitante, receptor, tipo_nombre: str, fecha) -> bool:
        """Verifica si ya hay una solicitud pendiente o aprobada del tipo dado entre los dos exploradores para esa fecha."""
        return SolicitudCambio.objects.filter(
            tipo_cambio__nombre=tipo_nombre,
            estado__in=['pendiente', 'aprobada'],
            fecha_cambio_turno=fecha,
        ).filter(
            Q(explorador_solicitante=solicitante, explorador_receptor=receptor) |
            Q(explorador_solicitante=receptor, explorador_receptor=solicitante)
        ).exists()
