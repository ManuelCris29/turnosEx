"""
Cambio Turno Strategy - Implementation for "Cambio Turno" solicitud type

This strategy implements the specific logic for "Cambio Turno" solicitudes,
migrating the current SolicitudService functionality to the new architecture.
"""

import logging
from typing import Dict, Any, Tuple, Optional
from django.db.models import Q
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from core.services import get_empleado_disponibilidad_service, get_turno_service

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
            from django.core.exceptions import ValidationError
            from ..solicitud_validator import SolicitudValidator
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha = datos.get('fecha_cambio_turno')
            comentario = datos.get('comentario') or ''
            
            if not all([explorador_solicitante, explorador_receptor, fecha]):
                return False, "Faltan datos requeridos para la validación"

            # Caso A: Validar que la fecha no sea pasada
            from datetime import date as _date, datetime as _datetime
            _fecha_obj = _datetime.strptime(fecha, '%Y-%m-%d').date() if isinstance(fecha, str) else fecha
            if _fecha_obj < _date.today():
                return False, "No se puede solicitar un cambio de turno para una fecha pasada."

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

            # Caso B: Verificar límite de cambios aprobados al CREAR (no solo al aprobar).
            # Evita que se creen solicitudes que el supervisor no podrá aprobar por límite alcanzado.
            LIMITE_CAMBIOS_POR_FECHA = 3
            from ..solicitud_consulta_service import SolicitudConsultaService
            from datetime import datetime as _dt_b
            _fecha_b = _dt_b.strptime(fecha, '%Y-%m-%d').date() if isinstance(fecha, str) else fecha

            cambios_solicitante = SolicitudConsultaService.contar_cambios_explorador_fecha(
                explorador_solicitante.id, _fecha_b
            )
            if cambios_solicitante >= LIMITE_CAMBIOS_POR_FECHA:
                return False, (
                    f'No puedes crear esta solicitud. Ya tienes {cambios_solicitante} cambio(s) de turno '
                    f'aprobado(s) para el {_fecha_b.strftime("%d/%m/%Y")}. '
                    f'El límite máximo es {LIMITE_CAMBIOS_POR_FECHA} cambio(s) por fecha.'
                )

            cambios_receptor = SolicitudConsultaService.contar_cambios_explorador_fecha(
                explorador_receptor.id, _fecha_b
            )
            if cambios_receptor >= LIMITE_CAMBIOS_POR_FECHA:
                return False, (
                    f'No se puede crear esta solicitud. El compañero seleccionado ya tiene '
                    f'{cambios_receptor} cambio(s) de turno aprobado(s) para el {_fecha_b.strftime("%d/%m/%Y")}. '
                    f'El límite máximo es {LIMITE_CAMBIOS_POR_FECHA} cambio(s) por fecha.'
                )

            return True, "Solicitud válida"
            
        except Exception as e:
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
        else:
            # CT antiguos (sin snapshot): elimina los turnos CT de esa fecha.
            Turno.objects.filter(
                explorador__in=[solicitud.explorador_solicitante, solicitud.explorador_receptor],
                fecha=solicitud.fecha_cambio_turno, tipo_cambio='CT',
            ).delete()

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
        from ..solicitud_service import SolicitudService
        
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
                    _snap = {}
                    for _emp in (solicitud.explorador_solicitante, solicitud.explorador_receptor):
                        _snap[f"{_emp.id}:{fecha_cambio.isoformat()}"] = [
                            {'jornada_nombre': _t.jornada.nombre.upper(), 'sala_id': _t.sala_id,
                             'tipo_cambio': _t.tipo_cambio}
                            for _t in Turno.objects.filter(explorador=_emp, fecha=fecha_cambio)
                                                   .select_related('jornada').order_by('jornada_id')
                        ]
                    solicitud.snapshot_turnos_previos = _snap
                    solicitud.save(update_fields=['snapshot_turnos_previos'])

                # FASE 2.3: VALIDACIÓN DE LÍMITE DE CAMBIOS - Verificar límite antes de aplicar cambios
                # Límite máximo de cambios por explorador/fecha (configurable, por defecto 2)
                LIMITE_CAMBIOS_POR_FECHA = 3
                
                # Verificar límite para el solicitante
                from ..solicitud_consulta_service import SolicitudConsultaService
                cambios_solicitante = SolicitudConsultaService.contar_cambios_explorador_fecha(
                    solicitud.explorador_solicitante.id,
                    fecha_cambio
                )
                
                if cambios_solicitante >= LIMITE_CAMBIOS_POR_FECHA:
                    error_msg = (
                        f"Se ha alcanzado el límite de cambios para esta fecha. "
                        f"El explorador {solicitud.explorador_solicitante.nombre} ya tiene "
                        f"{cambios_solicitante} cambio(s) aprobado(s) para el {fecha_cambio.strftime('%d/%m/%Y')}. "
                        f"Límite máximo: {LIMITE_CAMBIOS_POR_FECHA} cambio(s) por fecha."
                    )
                    logger.warning(
                        "FASE 2.3: Límite de cambios excedido - Solicitante ID: %d, Fecha: %s, Cambios: %d",
                        solicitud.explorador_solicitante.id,
                        fecha_cambio,
                        cambios_solicitante
                    )
                    return False, error_msg
                
                # Verificar límite para el receptor
                cambios_receptor = SolicitudConsultaService.contar_cambios_explorador_fecha(
                    solicitud.explorador_receptor.id,
                    fecha_cambio
                )
                
                if cambios_receptor >= LIMITE_CAMBIOS_POR_FECHA:
                    error_msg = (
                        f"Se ha alcanzado el límite de cambios para esta fecha. "
                        f"El explorador {solicitud.explorador_receptor.nombre} ya tiene "
                        f"{cambios_receptor} cambio(s) aprobado(s) para el {fecha_cambio.strftime('%d/%m/%Y')}. "
                        f"Límite máximo: {LIMITE_CAMBIOS_POR_FECHA} cambio(s) por fecha."
                    )
                    logger.warning(
                        "FASE 2.3: Límite de cambios excedido - Receptor ID: %d, Fecha: %s, Cambios: %d",
                        solicitud.explorador_receptor.id,
                        fecha_cambio,
                        cambios_receptor
                    )
                    return False, error_msg
                
                logger.info(
                    "FASE 2.3: Validación de límite exitosa - Solicitante: %d cambios, Receptor: %d cambios, Fecha: %s",
                    cambios_solicitante,
                    cambios_receptor,
                    fecha_cambio
                )
                
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
                
                # 2. Obtener salas de ambos empleados
                turno_service = get_turno_service()
                salas_solicitante = turno_service.get_salas_explorador(solicitud.explorador_solicitante.id)
                salas_receptor = turno_service.get_salas_explorador(solicitud.explorador_receptor.id)
                
                if not salas_solicitante.exists() or not salas_receptor.exists():
                    return False, "No se pudieron obtener las salas de los empleados"
                
                # FASE 2.1: CAMBIO SOBRE CAMBIO - Actualizar Turno existente o crear nuevo
                # 3. Buscar o crear/actualizar turno para el solicitante (con jornada del receptor)
                turno_solicitante_existente = Turno.objects.filter(
                    explorador=solicitud.explorador_solicitante,
                    fecha=fecha_cambio
                ).first()
                
                # FASE 2.4: Inicializar variable para trazabilidad
                solicitud_anterior_solicitante = None
                
                if turno_solicitante_existente:
                    # FASE 2.1: Actualizar turno existente
                    logger.info(
                        "FASE 2.1: Actualizando turno existente para solicitante ID: %d, Fecha: %s, Turno ID: %d",
                        solicitud.explorador_solicitante.id,
                        fecha_cambio,
                        turno_solicitante_existente.id
                    )
                    
                    # FASE 2.4: TRAZABILIDAD - Buscar solicitud anterior que creó este turno
                    solicitud_anterior_solicitante = SolicitudCambio.objects.filter(
                        Q(turno_origen=turno_solicitante_existente) | Q(turno_destino=turno_solicitante_existente),
                        estado='aprobada'
                    ).order_by('-fecha_resolucion').first()
                    
                    # FASE 2.4: Agregar comentario de trazabilidad en la solicitud actual
                    comentario_trazabilidad = []
                    if solicitud_anterior_solicitante:
                        comentario_trazabilidad.append(
                            f"Actualización: cambio previo reemplazado. "
                            f"Solicitud anterior ID: {solicitud_anterior_solicitante.id} "
                            f"(aprobada el {solicitud_anterior_solicitante.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud_anterior_solicitante.fecha_resolucion else 'N/A'})"
                        )
                        # Relacionar solicitudes para trazabilidad
                        solicitud.solicitud_origen = solicitud_anterior_solicitante
                        logger.info(
                            "FASE 2.4: Solicitud anterior encontrada para solicitante - Solicitud anterior ID: %d, Nueva solicitud ID: %d",
                            solicitud_anterior_solicitante.id,
                            solicitud.id
                        )
                    else:
                        comentario_trazabilidad.append(
                            "Actualización: cambio previo reemplazado (solicitud anterior no encontrada en el sistema)"
                        )
                    
                    # Agregar comentario de trazabilidad al comentario existente
                    if comentario_trazabilidad:
                        comentario_actual = solicitud.comentario or ""
                        nuevo_comentario = "\n\n".join([comentario_actual] + comentario_trazabilidad) if comentario_actual else "\n\n".join(comentario_trazabilidad)
                        solicitud.comentario = nuevo_comentario
                    
                    turno_solicitante_existente.jornada = jornada_receptor  # Jornada del receptor
                    turno_solicitante_existente.sala = salas_receptor.first().sala  # Sala del receptor
                    turno_solicitante_existente.tipo_cambio = 'CT'
                    turno_solicitante_existente.save()
                    turno_solicitante = turno_solicitante_existente
                    logger.info("FASE 2.1-2.4: Turno solicitante actualizado ID: %d con trazabilidad", turno_solicitante.id)
                else:
                    # Crear nuevo turno si no existe
                    logger.info(
                        "CambioTurnoStrategy.aplicar_cambios - Creando turno para solicitante ID: %d, Fecha: %s, Jornada: %s",
                        solicitud.explorador_solicitante.id,
                        fecha_cambio,
                        jornada_receptor.nombre if jornada_receptor else 'N/A'
                    )
                    turno_solicitante = Turno.objects.create(
                        explorador=solicitud.explorador_solicitante,
                        fecha=fecha_cambio,
                        jornada=jornada_receptor,  # Jornada del receptor
                        sala=salas_receptor.first().sala,  # Sala del receptor
                        tipo_cambio='CT'
                    )
                    logger.info("CambioTurnoStrategy.aplicar_cambios - Turno solicitante creado ID: %d", turno_solicitante.id)
                
                # FASE 2.1: CAMBIO SOBRE CAMBIO - Actualizar Turno existente o crear nuevo
                # 4. Buscar o crear/actualizar turno para el receptor (con jornada del solicitante)
                turno_receptor_existente = Turno.objects.filter(
                    explorador=solicitud.explorador_receptor,
                    fecha=fecha_cambio
                ).first()
                
                if turno_receptor_existente:
                    # FASE 2.1: Actualizar turno existente
                    logger.info(
                        "FASE 2.1: Actualizando turno existente para receptor ID: %d, Fecha: %s, Turno ID: %d",
                        solicitud.explorador_receptor.id,
                        fecha_cambio,
                        turno_receptor_existente.id
                    )
                    
                    # FASE 2.4: TRAZABILIDAD - Buscar solicitud anterior que creó este turno
                    solicitud_anterior_receptor = SolicitudCambio.objects.filter(
                        Q(turno_origen=turno_receptor_existente) | Q(turno_destino=turno_receptor_existente),
                        estado='aprobada'
                    ).order_by('-fecha_resolucion').first()
                    
                    # FASE 2.4: Agregar comentario de trazabilidad en la solicitud actual (solo si no se agregó ya)
                    # Solo agregar comentario si la solicitud anterior del receptor es diferente a la del solicitante
                    if solicitud_anterior_receptor and (not solicitud_anterior_solicitante or solicitud_anterior_receptor.id != solicitud_anterior_solicitante.id):
                        comentario_trazabilidad_receptor = (
                            f"Actualización (receptor): cambio previo reemplazado. "
                            f"Solicitud anterior ID: {solicitud_anterior_receptor.id} "
                            f"(aprobada el {solicitud_anterior_receptor.fecha_resolucion.strftime('%d/%m/%Y %H:%M') if solicitud_anterior_receptor.fecha_resolucion else 'N/A'})"
                        )
                        comentario_actual = solicitud.comentario or ""
                        nuevo_comentario = "\n\n".join([comentario_actual, comentario_trazabilidad_receptor]) if comentario_actual else comentario_trazabilidad_receptor
                        solicitud.comentario = nuevo_comentario
                        logger.info(
                            "FASE 2.4: Solicitud anterior encontrada para receptor - Solicitud anterior ID: %d, Nueva solicitud ID: %d",
                            solicitud_anterior_receptor.id,
                            solicitud.id
                        )
                    elif not solicitud_anterior_solicitante:
                        # Solo agregar si no se encontró solicitud anterior para el solicitante
                        comentario_trazabilidad_receptor = "Actualización (receptor): cambio previo reemplazado (solicitud anterior no encontrada en el sistema)"
                        comentario_actual = solicitud.comentario or ""
                        nuevo_comentario = "\n\n".join([comentario_actual, comentario_trazabilidad_receptor]) if comentario_actual else comentario_trazabilidad_receptor
                        solicitud.comentario = nuevo_comentario
                    
                    turno_receptor_existente.jornada = jornada_solicitante  # Jornada del solicitante
                    turno_receptor_existente.sala = salas_solicitante.first().sala  # Sala del solicitante
                    turno_receptor_existente.tipo_cambio = 'CT'
                    turno_receptor_existente.save()
                    turno_receptor = turno_receptor_existente
                    logger.info("FASE 2.1-2.4: Turno receptor actualizado ID: %d con trazabilidad", turno_receptor.id)
                else:
                    # Crear nuevo turno si no existe
                    logger.info(
                        "CambioTurnoStrategy.aplicar_cambios - Creando turno para receptor ID: %d, Fecha: %s, Jornada: %s",
                        solicitud.explorador_receptor.id,
                        fecha_cambio,
                        jornada_solicitante.nombre if jornada_solicitante else 'N/A'
                    )
                    turno_receptor = Turno.objects.create(
                        explorador=solicitud.explorador_receptor,
                        fecha=fecha_cambio,
                        jornada=jornada_solicitante,  # Jornada del solicitante
                        sala=salas_solicitante.first().sala,  # Sala del solicitante
                        tipo_cambio='CT'
                    )
                    logger.info("CambioTurnoStrategy.aplicar_cambios - Turno receptor creado ID: %d", turno_receptor.id)
                
                # 5. Actualizar la solicitud con las referencias a los turnos creados
                solicitud.turno_origen = turno_solicitante  # Turno original del solicitante
                solicitud.turno_destino = turno_receptor    # Turno resultante del receptor
                solicitud.save()
                
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
