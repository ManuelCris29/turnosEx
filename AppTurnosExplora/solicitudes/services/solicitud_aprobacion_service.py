"""
Servicio para aprobación y rechazo de solicitudes.

Responsabilidad única: Procesar aprobaciones y rechazos de solicitudes.
"""
from django.utils import timezone
from solicitudes.models import SolicitudCambio
from .solicitud_factory import SolicitudFactory
from .notificacion_service import NotificacionService
from solicitudes.domain.estado_machine import transicionar, EstadoTransicionError
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers de notificación (usados en on_commit): si fallan, solo se loguea
# ---------------------------------------------------------------------------

def _notificar_supervisor_aprobacion(solicitud, supervisor, comentario):
    try:
        NotificacionService.crear_notificacion_aprobacion_supervisor(solicitud, supervisor, comentario)
    except Exception:
        logger.exception("Error enviando notificación aprobación supervisor — sol %s", getattr(solicitud, 'id', '?'))


def _notificar_receptor_aprobacion(solicitud, receptor, comentario):
    try:
        NotificacionService.crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario)
    except Exception:
        logger.exception("Error enviando notificación aprobación receptor — sol %s", getattr(solicitud, 'id', '?'))


def _notificar_supervisor_rechazo(solicitud, supervisor, comentario):
    try:
        NotificacionService.crear_notificacion_rechazo_supervisor(solicitud, supervisor, comentario)
    except Exception:
        logger.exception("Error enviando notificación rechazo supervisor — sol %s", getattr(solicitud, 'id', '?'))


def _notificar_receptor_rechazo(solicitud, receptor, comentario):
    try:
        NotificacionService.crear_notificacion_rechazo_receptor(solicitud, receptor, comentario)
    except Exception:
        logger.exception("Error enviando notificación rechazo receptor — sol %s", getattr(solicitud, 'id', '?'))


class _AplicacionFallida(Exception):
    """Sentinel interno: aplicar_cambios devolvió success=False.

    Se usa para forzar el rollback de la transacción que marca la solicitud como
    'aprobada', evitando dejarla aprobada sin turnos/deudas aplicados.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(message)


class SolicitudAprobacionService:
    """
    Servicio para procesar aprobaciones y rechazos de solicitudes.

    Responsabilidad única: Gestionar el flujo de aprobación/rechazo.
    """

    @staticmethod
    def _verificar_sancion_partes(solicitud):
        """
        Verifica que ni el solicitante ni el receptor estén sancionados. Refresca la
        auto-sanción por deuda de cada uno antes de comprobar. Devuelve (ok, mensaje).

        Un sancionado no puede participar en ninguna solicitud en ningún rol; este
        chequeo es el backstop común a las dos vías de aprobación (receptor y supervisor).
        """
        from empleados.sancion_utils import sancion_activa
        partes = [
            (solicitud.explorador_solicitante, 'El solicitante'),
            (solicitud.explorador_receptor, 'El compañero'),
        ]
        for emp, etiqueta in partes:
            if emp is None:
                continue
            try:
                from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
                DeudaCorporativaService.gestionar_sancion_por_deuda(emp)
            except Exception:
                logger.exception('Error gestionando sanción automática por deuda de %s', getattr(emp, 'id', '?'))
            if sancion_activa(emp):
                nombre = getattr(emp, 'nombre', None) or str(emp)
                return False, f"No se puede aprobar: {etiqueta} ({nombre}) está sancionado y no puede participar en la solicitud."
        return True, ""

    @staticmethod
    def _confirmar_aprobacion_y_aplicar(solicitud):
        """
        Marca la solicitud como 'aprobada' y aplica sus cambios de forma ATÓMICA.

        El estado 'aprobada', las fechas de resolución y los turnos/deudas generados
        por ``aplicar_cambios`` se confirman juntos o no se confirman: si la aplicación
        falla, se revierte TODO (incluido el estado), dejando la solicitud en su estado
        previo para poder reintentar. Antes, el estado se guardaba por separado y un
        fallo en la aplicación dejaba la solicitud "aprobada" sin turnos ni deudas.

        Returns:
            Tupla (success: bool, message: str)
        """
        from django.db import transaction
        from solicitudes.domain.bloqueo_partes import bloquear_partes

        # Lock de los EXPLORADORES implicados, antes de re-validar. El `select_for_update()` de
        # los llamadores bloquea la fila de ESTA solicitud (doble clic), pero no impide que otra
        # solicitud distinta que comparta explorador se apruebe a la vez: cada una bloquearía su
        # propia fila y, bajo REPEATABLE READ, ninguna vería los turnos aún sin confirmar de la
        # otra, así que ambas re-validarían contra un mundo desactualizado y escribirían encima.
        bloquear_partes(solicitud)

        # Re-validación con el estado ACTUAL (#7): atrapa solicitudes que quedaron inválidas
        # entre el envío y la aprobación (festivo nuevo, día ya comprometido, fecha pasada…).
        # Si ya no es válida, NO se aprueba ni se aplica.
        ok_reval, msg_reval = SolicitudFactory.revalidar_para_aprobar(solicitud)
        if not ok_reval:
            logger.warning("Re-validación falló para solicitud ID %d: %s", solicitud.id, msg_reval)
            return False, f"No se puede aprobar: {msg_reval}"

        # Backstop de sanción: si CUALQUIER parte (solicitante o receptor) está sancionada en el
        # momento de materializar el cambio, no se aplica. La sanción es automática por deuda y
        # puede caer ENTRE el envío y la aprobación; sin esta guardia, un sancionado podría
        # participar pidiéndole a un compañero que enviara la solicitud (o aprobándola él mismo).
        ok_sancion, msg_sancion = SolicitudAprobacionService._verificar_sancion_partes(solicitud)
        if not ok_sancion:
            logger.warning("Aprobación bloqueada por sanción — solicitud ID %d: %s", solicitud.id, msg_sancion)
            return False, msg_sancion

        transicionar(solicitud, 'aprobada', save=False)
        solicitud.fecha_resolucion = timezone.now()
        try:
            with transaction.atomic():
                # Guardar dentro de la transacción: aplicar_cambios recarga la solicitud
                # y, al compartir conexión, ve el estado 'aprobada'.
                solicitud.save()
                logger.info("Solicitud guardada con estado 'aprobada' - ID: %d", solicitud.id)
                logger.info("Llamando a aplicar_cambios para solicitud ID: %d", solicitud.id)
                success, message = SolicitudFactory.aplicar_cambios(solicitud)
                if not success:
                    # Forzar rollback del estado 'aprobada' junto con cualquier cambio parcial.
                    raise _AplicacionFallida(message)
            logger.info("Cambios aplicados exitosamente para solicitud ID: %d - Mensaje: %s", solicitud.id, message)
            return True, message
        except _AplicacionFallida as e:
            logger.error(
                "ERROR aplicando cambios para solicitud ID: %d - Mensaje: %s. Estado revertido.",
                solicitud.id, e.message
            )
            return False, f"Error aplicando cambios: {e.message}"

    @staticmethod
    def aprobar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del supervisor.
        
        Args:
            solicitud_id: ID de la solicitud
            supervisor: Objeto Empleado supervisor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            from django.db import transaction
            # Lock de fila + re-chequeo de estado bajo el lock (igual que en la aprobación del
            # receptor): serializa concurrencia y evita doble aplicación por doble clic/reintento.
            with transaction.atomic():
                solicitud = (
                    SolicitudCambio.objects
                    .select_for_update()
                    .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                    .get(id=solicitud_id)
                )

                # Verificar que el aprobador sea el supervisor del solicitante
                # Permitir auto-supervisión para desarrollo
                if solicitud.explorador_solicitante.supervisor != supervisor:
                    return False, "No tienes permisos para aprobar esta solicitud"

                # Verificar que la solicitud esté pendiente
                if solicitud.estado != 'pendiente':
                    if solicitud.estado == 'cancelada':
                        return False, "Esta solicitud fue cancelada y ya no puede ser aprobada"
                    elif solicitud.estado == 'aprobada':
                        return False, "Esta solicitud ya fue aprobada"
                    elif solicitud.estado == 'rechazada':
                        return False, "Esta solicitud ya fue rechazada"
                    else:
                        return False, "La solicitud no está pendiente de aprobación"

                # Idempotencia: si el supervisor ya aprobó (aunque el estado siga 'pendiente'
                # por faltar el receptor), no re-procesar ni volver a notificar.
                if solicitud.aprobado_supervisor:
                    return False, "Ya habías aprobado esta solicitud como supervisor."

                # Marcar como aprobada por supervisor
                solicitud.aprobado_supervisor = True
                solicitud.fecha_aprobacion_supervisor = timezone.now()

                # Si ya fue aprobada por el receptor, cambiar estado a aprobada
                if solicitud.aprobado_receptor:
                    logger.info(
                        "Aprobando solicitud completamente - ID: %d, Tipo: %s, Receptor: %d, Solicitante: %d",
                        solicitud.id,
                        solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A',
                        solicitud.explorador_receptor.id,
                        solicitud.explorador_solicitante.id
                    )

                    # Confirmar estado y aplicar cambios atómicamente (revierte si falla)
                    success, message = SolicitudAprobacionService._confirmar_aprobacion_y_aplicar(solicitud)
                    if not success:
                        return False, message
                else:
                    # Si no está completamente aprobada, solo guardar
                    solicitud.save()

                # Notificación garantizada después del commit: si falla no revierte la aprobación
                _sol, _sup, _com = solicitud, supervisor, comentario_respuesta
                transaction.on_commit(lambda: _notificar_supervisor_aprobacion(_sol, _sup, _com))

            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
                f"solicitudes_count_pend_{supervisor.id}",
            ]
            CacheService.delete_many(cache_keys)

            return True, "Solicitud aprobada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al aprobar solicitud supervisor")
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def aprobar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del compañero receptor.
        
        Args:
            solicitud_id: ID de la solicitud
            receptor: Objeto Empleado receptor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            from django.db import transaction
            # Lock de fila (select_for_update) + re-chequeo de estado bajo el lock: serializa
            # peticiones concurrentes (doble clic / reintento). La segunda espera a la primera
            # y al leer estado != 'pendiente' se rechaza, evitando una doble aplicación.
            with transaction.atomic():
                solicitud = (
                    SolicitudCambio.objects
                    .select_for_update()
                    .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                    .get(id=solicitud_id)
                )

                # Verificar que el aprobador sea el receptor de la solicitud
                if solicitud.explorador_receptor != receptor:
                    return False, "No tienes permisos para aprobar esta solicitud"

                # Verificar que la solicitud esté pendiente
                if solicitud.estado != 'pendiente':
                    if solicitud.estado == 'cancelada':
                        return False, "Esta solicitud fue cancelada y ya no puede ser aprobada"
                    elif solicitud.estado == 'aprobada':
                        return False, "Esta solicitud ya fue aprobada"
                    elif solicitud.estado == 'rechazada':
                        return False, "Esta solicitud ya fue rechazada"
                    else:
                        return False, "La solicitud no está pendiente de aprobación"

                # Idempotencia: si el receptor ya aprobó (aunque el estado siga 'pendiente'
                # por faltar el supervisor), no re-procesar ni volver a notificar.
                if solicitud.aprobado_receptor:
                    return False, "Ya habías aprobado esta solicitud como compañero."

                # Sanción: un receptor sancionado no puede aceptar/participar (aunque otro haya
                # enviado la solicitud en su nombre). Mensaje claro al intentar aceptar.
                from empleados.sancion_utils import sancion_activa
                if sancion_activa(receptor):
                    return False, "Estás sancionado y no puedes aceptar ni participar en solicitudes de cambio de turno."

                # Marcar como aprobada por receptor
                solicitud.aprobado_receptor = True
                solicitud.fecha_aprobacion_receptor = timezone.now()

                # Si ya fue aprobada por el supervisor, cambiar estado a aprobada
                if solicitud.aprobado_supervisor:
                    logger.info(
                        "Aprobando solicitud completamente - ID: %d, Tipo: %s, Receptor: %d, Solicitante: %d",
                        solicitud.id,
                        solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A',
                        solicitud.explorador_receptor.id,
                        solicitud.explorador_solicitante.id
                    )

                    # Confirmar estado y aplicar cambios atómicamente (revierte si falla)
                    success, message = SolicitudAprobacionService._confirmar_aprobacion_y_aplicar(solicitud)
                    if not success:
                        return False, message
                else:
                    # Si no está completamente aprobada, solo guardar
                    solicitud.save()

                # Notificación garantizada después del commit
                _sol, _rec, _com = solicitud, receptor, comentario_respuesta
                transaction.on_commit(lambda: _notificar_receptor_aprobacion(_sol, _rec, _com))

            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{receptor.id}",
            ]
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)

            return True, "Solicitud aprobada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al aprobar solicitud receptor")
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del supervisor.
        
        Args:
            solicitud_id: ID de la solicitud
            supervisor: Objeto Empleado supervisor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            solicitud = (
                SolicitudCambio.objects
                .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                .get(id=solicitud_id)
            )
            
            # Verificar que el rechazador sea el supervisor del solicitante
            if solicitud.explorador_solicitante.supervisor != supervisor:
                return False, "No tienes permisos para rechazar esta solicitud"
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                if solicitud.estado == 'cancelada':
                    return False, "Esta solicitud fue cancelada y ya no puede ser rechazada"
                elif solicitud.estado == 'aprobada':
                    return False, "Esta solicitud ya fue aprobada"
                elif solicitud.estado == 'rechazada':
                    return False, "Esta solicitud ya fue rechazada"
                else:
                    return False, "La solicitud no está pendiente de aprobación"
            
            # Rechazar la solicitud
            from django.db import transaction
            with transaction.atomic():
                transicionar(solicitud, 'rechazada', save=False)
                solicitud.aprobado_supervisor = False
                solicitud.fecha_aprobacion_supervisor = timezone.now()
                solicitud.fecha_resolucion = timezone.now()
                solicitud.save()
                _sol, _sup, _com = solicitud, supervisor, comentario_respuesta
                transaction.on_commit(lambda: _notificar_supervisor_rechazo(_sol, _sup, _com))

            from core.services.cache_service import CacheService
            CacheService.delete_many([
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
                f"solicitudes_count_pend_{supervisor.id}",
            ])
            return True, "Solicitud rechazada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al rechazar solicitud supervisor")
            return False, f"Error al rechazar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del compañero receptor.
        
        Args:
            solicitud_id: ID de la solicitud
            receptor: Objeto Empleado receptor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            solicitud = (
                SolicitudCambio.objects
                .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                .get(id=solicitud_id)
            )
            
            # Verificar que el rechazador sea el receptor de la solicitud
            if solicitud.explorador_receptor != receptor:
                return False, "No tienes permisos para rechazar esta solicitud"
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                if solicitud.estado == 'cancelada':
                    return False, "Esta solicitud fue cancelada y ya no puede ser rechazada"
                elif solicitud.estado == 'aprobada':
                    return False, "Esta solicitud ya fue aprobada"
                elif solicitud.estado == 'rechazada':
                    return False, "Esta solicitud ya fue rechazada"
                else:
                    return False, "La solicitud no está pendiente de aprobación"
            
            # Rechazar la solicitud
            from django.db import transaction
            with transaction.atomic():
                transicionar(solicitud, 'rechazada', save=False)
                solicitud.aprobado_receptor = False
                solicitud.fecha_aprobacion_receptor = timezone.now()
                solicitud.fecha_resolucion = timezone.now()
                solicitud.save()
                _sol, _rec, _com = solicitud, receptor, comentario_respuesta
                transaction.on_commit(lambda: _notificar_receptor_rechazo(_sol, _rec, _com))

            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{receptor.id}",
            ]
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)
            
            return True, "Solicitud rechazada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al rechazar solicitud receptor")
            return False, f"Error al rechazar la solicitud: {str(e)}"


