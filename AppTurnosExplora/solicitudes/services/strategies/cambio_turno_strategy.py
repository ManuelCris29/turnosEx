"""
Cambio Turno Strategy - Implementation for "Cambio Turno" solicitud type

This strategy implements the specific logic for "Cambio Turno" solicitudes,
migrating the current SolicitudService functionality to the new architecture.
"""

import logging
from typing import Dict, Any, Tuple, Optional
from django.core.exceptions import ValidationError
from django.db.models import Q
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from core.services import get_empleado_disponibilidad_service, get_turno_service
from core.utils.date_utils import DateUtils
from core.constants import TipoCambioTurno
from django.utils import timezone

logger = logging.getLogger(__name__)


class CambioTurnoStrategy(SolicitudStrategy):
    """
    Strategy for "Cambio Turno" solicitudes.
    
    This implements the specific logic for turn change requests,
    including validation, creation, and application of changes.
    """
    
    def __init__(self):
        super().__init__("CT")

    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base)."""
        f = solicitud.fecha_cambio_turno
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_cambio_turno': f.strftime('%Y-%m-%d') if f else None,
        }

    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate cambio turno specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance  
                - fecha_cambio_turno: Date string
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_validator import SolicitudValidator

            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha = datos.get('fecha_cambio_turno')
            comentario = datos.get('comentario') or ''
            
            if not all([explorador_solicitante, explorador_receptor, fecha]):
                return False, "Faltan datos requeridos para la validación"

            # Caso A: el cambio se pide a partir de MAÑANA. El día en curso ya se está
            # trabajando (la jornada AM puede haber empezado), así que no hay nada que
            # intercambiar sin reescribir un turno que la persona ya está cubriendo.
            # Al RE-VALIDAR para aprobar solo se exige que no sea pasada: una solicitud
            # enviada ayer para hoy sigue siendo aprobable — el supervisor decide.
            _fecha_obj = DateUtils.parse_date(fecha) if isinstance(fecha, str) else fecha
            _hoy = timezone.localdate()
            if _fecha_obj < _hoy:
                return False, "No se puede solicitar un cambio de turno para una fecha pasada."
            if _fecha_obj == _hoy and not datos.get('es_revalidacion'):
                return False, (
                    "No se puede solicitar un cambio de turno para hoy: el día ya está en curso. "
                    "Elige a partir de mañana."
                )

            # Validaciones básicas
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            # Comentario obligatorio
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de cambio de turno')
            
            # OPTIMIZACIÓN: Obtener jornadas una sola vez y reutilizarlas
            from turnos.services.jornada_service import JornadaService
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(explorador_solicitante.id, fecha)
            jornada_receptor = JornadaService.get_jornada_explorador_fecha(explorador_receptor.id, fecha)
            
            # Validar que ambos tengan jornada (validación centralizada)
            if not jornada_solicitante:
                return False, 'El solicitante no tiene jornada asignada para esa fecha'
            if not jornada_receptor:
                return False, 'El receptor no tiene jornada asignada para esa fecha'

            # Validar que AMBOS realmente TRABAJEN esa fecha (estado real, no solo la jornada
            # predeterminada): un descanso de semana manual o mantenimiento significa que no hay
            # jornada que intercambiar, aunque la predeterminada exista.
            if not SolicitudValidator._explorador_trabaja(explorador_solicitante, _fecha_obj):
                return False, 'No trabajas esa fecha (ese día descansas): no hay jornada para intercambiar. Elige otra fecha.'
            if not SolicitudValidator._explorador_trabaja(explorador_receptor, _fecha_obj):
                return False, (
                    f'El compañero ({explorador_receptor.nombre} {explorador_receptor.apellido}) descansa esa fecha: '
                    f'no tiene jornada para intercambiar. Elige otra fecha o compañero.'
                )

            # El cambio de turno SOLO intercambia AM↔PM (jornadas single). Si alguno ya tiene
            # DOBLADA (AM+PM) ese día, no hay una sola jornada que intercambiar → bloquear con
            # un mensaje claro (fuente de verdad: estado_dia).
            from turnos.services.turno_service import TurnoService as _TSv
            if _TSv.estado_dia(explorador_solicitante, _fecha_obj).get('jornada') == 'DOBLADA':
                return False, (
                    f"Tienes una jornada doblada (AM+PM) el {_fecha_obj.strftime('%d/%m/%Y')}. "
                    f"El cambio de turno solo intercambia AM por PM; no aplica sobre una doblada."
                )
            if _TSv.estado_dia(explorador_receptor, _fecha_obj).get('jornada') == 'DOBLADA':
                return False, (
                    f"{explorador_receptor.nombre} {explorador_receptor.apellido} tiene una jornada "
                    f"doblada (AM+PM) el {_fecha_obj.strftime('%d/%m/%Y')}. El cambio de turno solo "
                    f"intercambia AM por PM; elige otra fecha o compañero."
                )

            # L2 (fuente de verdad): el día no puede estar YA comprometido (descanso) por otra
            # solicitud APROBADA (cambio descanso / d_fds / doblada / doblada permanente).
            _c1 = _TSv.dia_comprometido_por_solicitud(explorador_solicitante, _fecha_obj)
            if _c1:
                return False, (
                    f"Tienes el {_fecha_obj.strftime('%d/%m/%Y')} comprometido en otra solicitud "
                    f"aprobada ({_c1['motivo']}); no puedes cambiar ese turno."
                )
            _c2 = _TSv.dia_comprometido_por_solicitud(explorador_receptor, _fecha_obj)
            if _c2:
                return False, (
                    f"Tu compañero tiene el {_fecha_obj.strftime('%d/%m/%Y')} comprometido en otra "
                    f"solicitud aprobada ({_c2['motivo']}); elige otra fecha o compañero."
                )

            # Duplicados/pendientes: reglas de CREACIÓN; se OMITEN al re-validar para aprobar
            # (la solicitud ya existe y no se está creando otra).
            if not datos.get('es_revalidacion'):
                SolicitudValidator.validar_duplicada_misma_fecha(explorador_solicitante, explorador_receptor, fecha)

                # Caso C: una solicitud pendiente a la vez — bloquear si el receptor ya tiene
                # cualquier solicitud pendiente para esta fecha (como solicitante o receptor).
                # Solo puede enviarse una nueva cuando la pendiente sea aprobada o cancelada.
                SolicitudValidator.validar_receptor_sin_solicitud_pendiente_en_fecha(
                    explorador_receptor, fecha
                )
                # Mismo principio para el solicitante: no puede tener otra solicitud pendiente
                # para la misma fecha (ni como solicitante ni como receptor).
                SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fecha(
                    explorador_solicitante, fecha
                )

            # Validaciones específicas de Cambio Turno (CT)
            # 1. Validar jornada contraria (AM ↔ PM) - Reutilizando jornadas ya obtenidas
            SolicitudValidator.validar_jornada_contraria(
                explorador_solicitante, 
                explorador_receptor, 
                fecha,
                jornada_solicitante=jornada_solicitante,
                jornada_receptor=jornada_receptor
            )
            
            # 2. Validar que no sea día de mantenimiento
            SolicitudValidator.validar_no_dia_mantenimiento(fecha)
            
            # 3. Validar que no sea domingo (no se puede cambiar domingo por día de semana)
            SolicitudValidator.validar_no_domingo_por_semana(fecha, es_cambio_permanente=False)
            
            # 3.1. Validar que no sea sábado (no se puede cambiar sábado por día de semana)
            SolicitudValidator.validar_no_sabado_ct_sencillo(fecha)

            # 3.2. FESTIVO: no se permite cambio de turno en día festivo.
            # En festivo, una jornada trabaja el día completo (AM+PM) por rotación y la otra
            # DESCANSA, así que no hay dos jornadas single que intercambiar. El único cambio
            # válido en festivo es FESTIVO POR FESTIVO, que se hace con una DOBLADA.
            if SolicitudValidator.es_festivo_semana(fecha):
                return False, (
                    "No se puede hacer un cambio de turno en un día festivo. En festivo una "
                    "jornada trabaja completa (AM+PM) y la otra descansa. Si necesitas "
                    "intercambiar un festivo, hazlo con una Doblada (festivo por festivo)."
                )

            # 4. Validar que ni solicitante ni receptor tengan doblada activa para esa fecha
            error_doblada_solicitante = None
            error_doblada_receptor = None

            try:
                SolicitudValidator.validar_no_doblada_activa(explorador_solicitante, fecha)
            except ValidationError as e:
                error_doblada_solicitante = str(e)

            try:
                SolicitudValidator.validar_no_doblada_activa(explorador_receptor, fecha)
            except ValidationError as e:
                error_doblada_receptor = str(e)

            if error_doblada_solicitante or error_doblada_receptor:
                # Construir mensajes claros según quién tiene la doblada
                if error_doblada_solicitante and error_doblada_receptor:
                    return False, (
                        'Tanto tú como el compañero seleccionado tienen jornada doblada en esta fecha. '
                        'Los casos donde ambos tienen doblada deben gestionarse únicamente desde la '
                        'Solicitud de Dobladas.'
                    )
                if error_doblada_solicitante:
                    return False, (
                        'Tienes jornada doblada (AM + PM) en esta fecha. '
                        'Este tipo de cambio no se puede realizar como Cambio de Turno Sencillo; '
                        'debes usar la Solicitud de Dobladas.'
                    )
                if error_doblada_receptor:
                    return False, (
                        'El compañero seleccionado tiene jornada doblada (AM + PM) en esta fecha. '
                        'Este cambio no se puede hacer como Cambio de Turno Sencillo; '
                        'debe gestionarse mediante la Solicitud de Dobladas.'
                    )
            
            # NOTA: Para festivos, el sistema ya filtra correctamente en get_empleados_jornada_contraria
            # para mostrar solo exploradores que tienen jornada en esa fecha (incluyendo festivos).
            # La validación de existencia de jornada se realiza centralizadamente en las líneas 64-67.

            # NOTA: no hay tope de cambios de turno por fecha. Lo que un explorador puede o no
            # hacer ese día ya lo gobiernan las reglas de estado real (trabaja, no está doblado,
            # el día no está comprometido por otra solicitud aprobada) y la última aprobada gana.
            # Un contador adicional solo bloqueaba cambios legítimos.

            return True, "Solicitud válida"

        except ValidationError as e:
            # Rechazo de negocio: el mensaje es para el explorador.
            return False, str(e)
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a cambio turno solicitud.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_service import SolicitudService
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario')
            fecha_cambio_turno = datos.get('fecha_cambio_turno')
            
            # Use existing service logic
            return SolicitudService.crear_solicitud_cambio(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_cambio_turno
            )
            
        except Exception as e:
            return None, f"Error creando solicitud de cambio de turno: {str(e)}"

    @staticmethod
    def revertir(solicitud: SolicitudCambio) -> None:
        """
        Revierte un CT (sencillo) aprobado dentro de la ventana de cancelación de 30 min:
        restaura los turnos previos de solicitante y receptor desde el snapshot. CT no genera
        deudas, así que no hay nada más que deshacer.
        """
        from turnos.models import Turno
        from ..doblada_aplicacion_service import DobladaAplicacionService
        snap = getattr(solicitud, 'snapshot_turnos_previos', None)
        if snap:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snap)
            # Patrón #22: el restore arrasa el día entero; reconstruir lo que siga vigente ahí.
            DobladaAplicacionService.reconciliar_dobladas_aprobadas(
                DobladaAplicacionService._fechas_explorador_afectados(snap), solicitud.id)
        else:
            # CT antiguos (sin snapshot): elimina los turnos CT de esa fecha.
            Turno.objects.filter(
                explorador__in=[solicitud.explorador_solicitante, solicitud.explorador_receptor],
                fecha=solicitud.fecha_cambio_turno, tipo_cambio=TipoCambioTurno.CT,
            ).delete()

    @staticmethod
    def reaplicar_fechas(solicitud: SolicitudCambio, fechas) -> int:
        """
        Re-materializa el efecto de un CT (sencillo) APROBADO sobre `fechas` (patrón #22).

        Se llama desde la reconciliación: cuando se restaura el snapshot de otra solicitud,
        ese `delete()` arrasa el día entero y se lleva por delante el CT que seguía vigente.
        Sin esto el CT desaparecía en silencio y la persona volvía a su jornada base.

        El efecto de un CT es un intercambio de jornadas base en `fecha_cambio_turno`, así que
        se puede reconstruir sin snapshot (el estado previo era virtual). Devuelve nº de días.
        """
        from turnos.models import Turno
        from turnos.services.doblada_turno_service import DobladaTurnoService
        from core.utils.jornada_utils import obtener_jornada_base

        fecha = solicitud.fecha_cambio_turno
        if not fecha or fecha not in set(fechas):
            return 0

        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        j_sol = obtener_jornada_base(solicitante, fecha)
        j_rec = obtener_jornada_base(receptor, fecha)
        if not j_sol or not j_rec:
            logger.warning(
                "CT %s no re-materializado en %s: falta la jornada base de alguno de los dos.",
                solicitud.id, fecha,
            )
            return 0

        # El intercambio: cada uno queda con la jornada del otro.
        for empleado, jornada in ((solicitante, j_rec), (receptor, j_sol)):
            Turno.objects.filter(explorador=empleado, fecha=fecha).delete()
            Turno.objects.create(
                explorador=empleado, fecha=fecha, jornada=jornada,
                sala=DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha),
                tipo_cambio=TipoCambioTurno.CT,
            )
        return 1

    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply turn change when solicitud is approved.
        Creates records in Turno table for both employees.

        FASE 1.6: Protegido con transacción atómica para garantizar integridad de datos.
        Todas las operaciones se ejecutan o ninguna (rollback automático en caso de error).
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        from django.db import transaction
        from django.utils import timezone
        from turnos.models import Turno
        
        try:
            logger.info(
                "CambioTurnoStrategy.aplicar_cambios - Iniciando para solicitud ID: %d, Estado: %s",
                solicitud.id,
                solicitud.estado
            )
            
            # FASE 1.6: TRANSACCIÓN ATÓMICA - Garantiza que todas las operaciones se ejecuten o ninguna
            with transaction.atomic():
                # FASE 1.7: BLOQUEO DE SOLICITUD - Prevenir procesamiento concurrente
                # Recargar la solicitud con bloqueo para evitar race conditions
                solicitud = SolicitudCambio.objects.select_for_update().get(id=solicitud.id)
                logger.info(
                    "CambioTurnoStrategy.aplicar_cambios - Solicitud recargada, Estado: %s",
                    solicitud.estado
                )
                
                # Verificar que la solicitud sigue en estado aprobada (puede haber cambiado)
                if solicitud.estado != 'aprobada':
                    error_msg = f"La solicitud no está en estado aprobada (estado actual: {solicitud.estado})"
                    logger.error("CambioTurnoStrategy.aplicar_cambios - %s", error_msg)
                    return False, error_msg
                
                # Verificar que no tiene turnos ya creados (puede haber sido procesada)
                if solicitud.turno_origen or solicitud.turno_destino:
                    return False, "Los turnos ya fueron creados para esta solicitud"
                
                # Convertir fecha a objeto date
                fecha_cambio = solicitud.fecha_cambio_turno
                
                # Validar que fecha_cambio no sea None
                if not fecha_cambio:
                    return False, "La solicitud no tiene fecha de cambio de turno definida"

                # Snapshot de turnos previos (solicitante + receptor en la fecha) ANTES de mutar,
                # para poder revertir al cancelar dentro de los 30 min. Idempotente: solo la 1ª vez.
                if not solicitud.snapshot_turnos_previos:
                    from ..doblada_snapshot_service import DobladaSnapshotService
                    solicitud.snapshot_turnos_previos = DobladaSnapshotService.serializar_pares(
                        f"{_emp.id}:{fecha_cambio.isoformat()}"
                        for _emp in (solicitud.explorador_solicitante, solicitud.explorador_receptor)
                    )
                    solicitud.save(update_fields=['snapshot_turnos_previos'])

                # 1. Obtener jornadas actuales de ambos empleados para esa fecha
                from turnos.services.jornada_service import JornadaService
                jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                    solicitud.explorador_solicitante.id, 
                    fecha_cambio.strftime('%Y-%m-%d')
                )
                jornada_receptor = JornadaService.get_jornada_explorador_fecha(
                    solicitud.explorador_receptor.id, 
                    fecha_cambio.strftime('%Y-%m-%d')
                )
                
                if not jornada_solicitante or not jornada_receptor:
                    return False, "No se pudieron obtener las jornadas de los empleados"
                
                # 2. Sala de cada uno. El CT intercambia la JORNADA, no la sala: la sala es
                # informativa (dice en qué es experto el explorador) y no cambia porque se
                # intercambie un turno. Cada uno conserva la suya, igual que en las dobladas.
                # Se calcula ANTES de borrar los turnos, porque `obtener_sala_explorador_fecha`
                # prioriza la sala del turno que ya existe ese día.
                from turnos.services.doblada_turno_service import DobladaTurnoService
                sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(
                    solicitud.explorador_solicitante, fecha_cambio)
                sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(
                    solicitud.explorador_receptor, fecha_cambio)

                # FASE 2.1: CAMBIO SOBRE CAMBIO
                # 3. Capturar trazabilidad ANTES de borrar, luego delete+create limpio
                turno_solicitante_existente = Turno.objects.filter(
                    explorador=solicitud.explorador_solicitante,
                    fecha=fecha_cambio
                ).first()

                # FASE 2.4: Inicializar variable para trazabilidad
                solicitud_anterior_solicitante = None

                if turno_solicitante_existente:
                    # FASE 2.4: TRAZABILIDAD - Buscar solicitud anterior antes de borrar
                    solicitud_anterior_solicitante = SolicitudCambio.objects.filter(
                        Q(turno_origen=turno_solicitante_existente) | Q(turno_destino=turno_solicitante_existente),
                        estado='aprobada'
                    ).order_by('-fecha_resolucion').first()

                    comentario_trazabilidad = []
                    if solicitud_anterior_solicitante:
                        comentario_trazabilidad.append(
                            f"Actualización: cambio previo reemplazado. "
                            f"Solicitud anterior ID: {solicitud_anterior_solicitante.id} "
                            f"(aprobada el {DateUtils.format_datetime_display(solicitud_anterior_solicitante.fecha_resolucion) or 'N/A'})"
                        )
                        solicitud.solicitud_origen = solicitud_anterior_solicitante
                        logger.info(
                            "FASE 2.4: Solicitud anterior encontrada para solicitante - ID: %d -> nueva ID: %d",
                            solicitud_anterior_solicitante.id, solicitud.id
                        )
                    else:
                        comentario_trazabilidad.append(
                            "Actualización: cambio previo reemplazado (solicitud anterior no encontrada en el sistema)"
                        )
                    if comentario_trazabilidad:
                        comentario_actual = solicitud.comentario or ""
                        solicitud.comentario = "\n\n".join([comentario_actual] + comentario_trazabilidad) if comentario_actual else "\n\n".join(comentario_trazabilidad)

                # Borrar TODOS los turnos del solicitante en esa fecha (evita huérfanos si tenía doblada)
                Turno.objects.filter(explorador=solicitud.explorador_solicitante, fecha=fecha_cambio).delete()
                turno_solicitante = Turno.objects.create(
                    explorador=solicitud.explorador_solicitante,
                    fecha=fecha_cambio,
                    jornada=jornada_receptor,
                    sala=sala_solicitante,
                    tipo_cambio=TipoCambioTurno.CT
                )
                logger.info(
                    "FASE 2.1: Turno solicitante (re)creado ID: %d | Fecha: %s | Jornada: %s",
                    turno_solicitante.id, fecha_cambio, jornada_receptor.nombre if jornada_receptor else 'N/A'
                )

                # FASE 2.1: CAMBIO SOBRE CAMBIO
                # 4. Mismo patrón para el receptor
                turno_receptor_existente = Turno.objects.filter(
                    explorador=solicitud.explorador_receptor,
                    fecha=fecha_cambio
                ).first()

                if turno_receptor_existente:
                    # FASE 2.4: TRAZABILIDAD - Capturar antes de borrar
                    solicitud_anterior_receptor = SolicitudCambio.objects.filter(
                        Q(turno_origen=turno_receptor_existente) | Q(turno_destino=turno_receptor_existente),
                        estado='aprobada'
                    ).order_by('-fecha_resolucion').first()

                    if solicitud_anterior_receptor and (not solicitud_anterior_solicitante or solicitud_anterior_receptor.id != solicitud_anterior_solicitante.id):
                        comentario_trazabilidad_receptor = (
                            f"Actualización (receptor): cambio previo reemplazado. "
                            f"Solicitud anterior ID: {solicitud_anterior_receptor.id} "
                            f"(aprobada el {DateUtils.format_datetime_display(solicitud_anterior_receptor.fecha_resolucion) or 'N/A'})"
                        )
                        comentario_actual = solicitud.comentario or ""
                        solicitud.comentario = "\n\n".join([comentario_actual, comentario_trazabilidad_receptor]) if comentario_actual else comentario_trazabilidad_receptor
                        logger.info(
                            "FASE 2.4: Solicitud anterior receptor ID: %d -> nueva ID: %d",
                            solicitud_anterior_receptor.id, solicitud.id
                        )
                    elif not solicitud_anterior_solicitante:
                        comentario_trazabilidad_receptor = "Actualización (receptor): cambio previo reemplazado (solicitud anterior no encontrada en el sistema)"
                        comentario_actual = solicitud.comentario or ""
                        solicitud.comentario = "\n\n".join([comentario_actual, comentario_trazabilidad_receptor]) if comentario_actual else comentario_trazabilidad_receptor

                # Borrar TODOS los turnos del receptor en esa fecha (evita huérfanos si tenía doblada)
                Turno.objects.filter(explorador=solicitud.explorador_receptor, fecha=fecha_cambio).delete()
                turno_receptor = Turno.objects.create(
                    explorador=solicitud.explorador_receptor,
                    fecha=fecha_cambio,
                    jornada=jornada_solicitante,
                    sala=sala_receptor,
                    tipo_cambio=TipoCambioTurno.CT
                )
                logger.info(
                    "FASE 2.1: Turno receptor (re)creado ID: %d | Fecha: %s | Jornada: %s",
                    turno_receptor.id, fecha_cambio, jornada_solicitante.nombre if jornada_solicitante else 'N/A'
                )
                
                # 5. Actualizar la solicitud con las referencias a los turnos creados
                solicitud.turno_origen = turno_solicitante  # Turno original del solicitante
                solicitud.turno_destino = turno_receptor    # Turno resultante del receptor
                solicitud.save()

                # Estado RESULTANTE: lo que este cambio deja en esas fechas. Al cancelar se
                # compara contra los turnos actuales para no pisar un cambio ajeno posterior.
                from ..doblada_snapshot_service import DobladaSnapshotService
                DobladaSnapshotService.capturar_snapshot_resultante(solicitud)


                # FASE 3.5: Invalidar caché de turnos para ambos exploradores usando helper centralizado
                from core.services.cache_service import CacheService
                if fecha_cambio:
                    anio = fecha_cambio.year
                    mes = fecha_cambio.month
                    # Invalidar caché para el solicitante y receptor usando helper que normaliza formato
                    CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, mes, anio)
                    CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, mes, anio)
                    logger.info(
                        "FASE 3.5: Caché invalidado para solicitante (ID: %d) y receptor (ID: %d) en %d/%d",
                        solicitud.explorador_solicitante.id,
                        solicitud.explorador_receptor.id,
                        mes,
                        anio
                    )
                
                # FASE 1.14: FIRST-COME, FIRST-SERVED - Rechazar automáticamente otras solicitudes pendientes
                # Buscar otras solicitudes pendientes para el mismo receptor y fecha
                
                # Log para debugging - verificar valores
                logger.info(
                    "FASE 1.14: Buscando otras solicitudes pendientes - Receptor ID: %d, Fecha: %s, Solicitud actual ID: %d",
                    solicitud.explorador_receptor.id,
                    fecha_cambio,
                    solicitud.id
                )
                
                otras_solicitudes = SolicitudCambio.objects.filter(
                    explorador_receptor=solicitud.explorador_receptor,
                    fecha_cambio_turno=fecha_cambio,
                    estado='pendiente'
                ).exclude(id=solicitud.id).select_related(
                    'explorador_solicitante__supervisor',
                    'tipo_cambio'
                )
                
                # Rechazar automáticamente las otras solicitudes
                if otras_solicitudes.exists():
                    # Obtener la lista de IDs para logging ANTES de actualizar
                    ids_encontradas = list(otras_solicitudes.values_list('id', flat=True))
                    count_rechazadas = len(ids_encontradas)
                    
                    logger.info(
                        "FASE 1.14: Encontradas %d solicitudes pendientes para rechazar automáticamente. IDs: %s",
                        count_rechazadas,
                        ids_encontradas
                    )
                    
                    fecha_ahora = timezone.now()
                    comentario_rechazo = "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)"
                    
                    # FASE 1.15: Obtener las solicitudes antes de actualizarlas para crear notificaciones
                    solicitudes_para_notificar = list(otras_solicitudes)
                    
                    # Actualizar todas las solicitudes en una sola operación
                    otras_solicitudes.update(
                        estado='rechazada',
                        fecha_resolucion=fecha_ahora,
                        comentario=comentario_rechazo
                    )
                    
                    # FASE 1.15: Crear notificaciones para cada solicitante afectado
                    from ..notificacion_service import NotificacionService
                    for solicitud_rechazada in solicitudes_para_notificar:
                        try:
                            # Recargar la solicitud para obtener el estado actualizado
                            solicitud_rechazada.refresh_from_db()
                            NotificacionService.crear_notificacion_rechazo_automatico(solicitud_rechazada)
                        except Exception as e:
                            # Log error pero no fallar la transacción
                            logger.error(
                                "FASE 1.15: Error creando notificación para solicitud %d: %s",
                                solicitud_rechazada.id,
                                str(e)
                            )
                    
                    # Log para debugging
                    logger.info(
                        "FASE 1.14-1.15: Rechazadas %d solicitudes pendientes para receptor %d en fecha %s. Notificaciones creadas.",
                        count_rechazadas,
                        solicitud.explorador_receptor.id,
                        fecha_cambio
                    )
                else:
                    # Log cuando NO se encuentran solicitudes para rechazar
                    logger.info(
                        "FASE 1.14: No se encontraron otras solicitudes pendientes para rechazar - Receptor ID: %d, Fecha: %s",
                        solicitud.explorador_receptor.id,
                        fecha_cambio
                    )
                
                # La transacción se confirma automáticamente al salir del bloque 'with'
                logger.info(
                    "FASE 1.14: aplicar_cambios completado exitosamente para solicitud ID: %d",
                    solicitud.id
                )
                return True, "Cambio de turno aplicado correctamente"
            
        except Exception as e:
            # En caso de error, la transacción se revierte automáticamente
            return False, f"Error aplicando cambio de turno: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for cambio turno (jornada contraria).
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            **kwargs: Additional arguments (ignored for CT, used for CT PERMANENTE)
            
        Returns:
            List of available empleados
        """
        try:
            logger.info("CambioTurnoStrategy.get_empleados_disponibles - Iniciando", extra={
                'fecha': fecha,
                'usuario_id': usuario_actual.id if usuario_actual else None,
                'solo_jornada_contraria': True,
                'kwargs_keys': list(kwargs.keys()) if kwargs else []
            })
            
            servicio = get_empleado_disponibilidad_service()
            empleados = servicio.get_empleados_disponibles(
                fecha, 
                usuario_actual, 
                solo_jornada_contraria=True
            )
            
            logger.info("CambioTurnoStrategy.get_empleados_disponibles - Completado", extra={
                'fecha': fecha,
                'usuario_id': usuario_actual.id if usuario_actual else None,
                'empleados_encontrados': len(empleados) if empleados else 0
            })
            
            return empleados if empleados else []
            
        except Exception as e:
            logger.error("CambioTurnoStrategy.get_empleados_disponibles - Error", extra={
                'fecha': fecha,
                'usuario_id': usuario_actual.id if usuario_actual else None,
                'error': str(e)
            }, exc_info=True)
            return []
    
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer.
        
        Args:
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with turn information
        """
        try:
            turno_service = get_turno_service()
            return turno_service.get_turno_explorador(explorador_id, fecha)
            
        except Exception:
            return {}

    def detalle(self, solicitud, datos):
        """
        Detalle propio de CAMBIO TURNO para la pantalla de consulta.

        Movido desde `views/detalle.py` en la Fase 2 (cerrar el OCP): la vista
        elegía con una cadena `if tipo_nombre == ...`, así que cada tipo nuevo
        obligaba a editarla. El cuerpo se trasladó SIN cambios de lógica; solo
        los imports relativos pasaron a absolutos al cambiar de paquete.
        """
        if solicitud.fecha_cambio_turno:
            datos['fechas']['fecha_cambio'] = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')
            
            # Jornada de cada uno en la fecha del cambio. Si la solicitud ya fue aplicada,
            # turno_origen/turno_destino reflejan el turno YA intercambiado (jornada final).
            # Si sigue pendiente, esos turnos aún no existen: se calcula la jornada ACTUAL
            # (antes del intercambio) para que el revisor sepa qué se va a intercambiar.
            if solicitud.turno_origen and solicitud.turno_origen.jornada:
                datos['informacion_adicional']['jornada_solicitante'] = solicitud.turno_origen.jornada.nombre
            else:
                from turnos.services.jornada_service import JornadaService
                j_sol = JornadaService.get_jornada_explorador_fecha(
                    solicitud.explorador_solicitante.id, solicitud.fecha_cambio_turno
                )
                datos['informacion_adicional']['jornada_solicitante'] = j_sol.nombre if j_sol else None

            if solicitud.turno_destino and solicitud.turno_destino.jornada:
                datos['informacion_adicional']['jornada_receptor'] = solicitud.turno_destino.jornada.nombre
            else:
                from turnos.services.jornada_service import JornadaService
                j_rec = JornadaService.get_jornada_explorador_fecha(
                    solicitud.explorador_receptor.id, solicitud.fecha_cambio_turno
                )
                datos['informacion_adicional']['jornada_receptor'] = j_rec.nombre if j_rec else None

            if solicitud.estado == 'pendiente':
                datos['informacion_adicional']['nota_jornadas'] = (
                    'Jornadas actuales (antes del intercambio): al aprobarse, el solicitante '
                    'pasa a la jornada del receptor y viceversa.'
                )
            
            # Analizar fecha para mostrar información detallada
            from solicitudes.services.fechas_helper import obtener_informacion_fecha_para_detalle
            info_fecha = obtener_informacion_fecha_para_detalle(
                solicitud.fecha_cambio_turno,
                solicitante=solicitud.explorador_solicitante,
                receptor=solicitud.explorador_receptor,
                tipo_solicitud='CT'
            )
            datos['fechas']['analisis'] = info_fecha
            
            # Si hay razones de exclusión, agregarlas
            if info_fecha['razones_exclusion']:
                datos['fechas']['excluidas'] = [{
                    'fecha': info_fecha['fecha'],
                    'razon': ', '.join(info_fecha['razones_exclusion'])
                }]
            else:
                # Si es válida, agregarla a aplicables
                datos['fechas']['aplicables'] = [info_fecha['fecha']]
            
            datos['informacion_adicional']['nota'] = 'Se excluyen días de mantenimiento, domingos y dobladas activas. Los festivos se permiten si ambos empleados tienen jornada.'

    def reaplicar(self, solicitud, fechas):
        n = CambioTurnoStrategy.reaplicar_fechas(solicitud, fechas)
        if n:
            logger.info(
                "Reconciliacion post-revert: re-materializado CAMBIO TURNO %s en %d dia(s).",
                solicitud.id, n,
            )

    def pares_que_reescribe(self, solicitud, fechas):
        """
        Un unico dia, pero escrito a AMBAS partes: lo que este tipo aporta al
        conjunto no es una fecha nueva -ya esta en `fechas`- sino la OTRA PERSONA.

        Ese matiz se perdia por un generador que se agotaba en la primera persona
        (corregido el 2026-08-20). Por eso `_pares` materializa su argumento.
        """
        return self._pares(solicitud, [solicitud.fecha_cambio_turno], fechas)
