"""
Servicio para aplicar cambios de doblada.

Responsabilidad única: Aplicar los cambios de turnos y generar deudas cuando
una solicitud de doblada es aprobada.
"""
from typing import Tuple
from django.core.exceptions import ValidationError
from django.db import transaction
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from turnos.models import Turno
from turnos.services.jornada_service import JornadaService
from turnos.services.doblada_turno_service import DobladaTurnoService
from .doblada_snapshot_service import DobladaSnapshotService
from .doblada_deuda_service import DobladaDeudaService
from core.utils.jornada_utils import obtener_jornadas_am_pm as _obtener_jornadas_cache
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


def _fecha_limite_pago_semana(fecha_sabado: date) -> date:
    """
    Calcula la fecha límite para pagar la deuda residual de un pago en sábado AMBAS:
    un día de la semana (lunes a viernes) DENTRO DEL MISMO MES del sábado, que no sea
    festivo ni día de mantenimiento efectivo (la temporada manda sobre el mantenimiento).

    Estrategia: primer día hábil válido DESPUÉS del sábado dentro del mes; si no hay
    (sábado al final del mes), el último día hábil válido ANTES del sábado en el mes.
    """
    from turnos.models import DiaEspecial
    from solicitudes.services.ct_permanente_helper import _es_festivo

    def _es_habil(d):
        return d.weekday() < 5 and not _es_festivo(d) and not DiaEspecial.es_mantenimiento_efectivo(d)

    # Hacia adelante, mismo mes
    d = fecha_sabado + timedelta(days=1)
    while d.month == fecha_sabado.month:
        if _es_habil(d):
            return d
        d += timedelta(days=1)

    # Hacia atrás, mismo mes (caso borde: sábado al final del mes)
    d = fecha_sabado - timedelta(days=1)
    while d.month == fecha_sabado.month and d.day >= 1:
        if _es_habil(d):
            return d
        d -= timedelta(days=1)

    # Fallback improbable: el propio sábado
    return fecha_sabado


class DobladaAplicacionService:
    """
    Servicio para aplicar cambios de doblada.
    
    Responsabilidad única: Aplicar cambios de turnos y generar deudas.
    Incluye validación post-aplicación para garantizar integridad de datos.
    """

    @staticmethod
    def capturar_snapshot_turnos_previos(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> dict:
        return DobladaSnapshotService.capturar_snapshot_turnos_previos(solicitud, detalle)

    @staticmethod
    def restaurar_turnos_desde_snapshot(snapshot: dict) -> None:
        DobladaSnapshotService.restaurar_turnos_desde_snapshot(snapshot)

    @staticmethod
    def _fechas_explorador_afectados(snapshot: dict):
        return DobladaSnapshotService.fechas_explorador_afectados(snapshot)

    @staticmethod
    def reconciliar_dobladas_aprobadas(afectados, excluir_solicitud_id) -> None:
        DobladaSnapshotService.reconciliar_dobladas_aprobadas(afectados, excluir_solicitud_id)

    @staticmethod
    def validar_turnos_doblada_cesion(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> dict:
        """
        Valida que los turnos se hayan creado correctamente después de aplicar la doblada de cesión.
        
        Returns:
            dict con 'valido' (bool), 'errores' (list), 'advertencias' (list)
        """
        resultado = {
            'valido': True,
            'errores': [],
            'advertencias': []
        }
        
        fecha_cesion = solicitud.fecha_cambio_turno
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        # Verificar turnos del receptor
        turnos_receptor = Turno.objects.filter(
            explorador=receptor,
            fecha=fecha_cesion
        ).select_related('jornada')
        
        if not turnos_receptor.exists():
            resultado['valido'] = False
            resultado['errores'].append(
                f"CRÍTICO: Receptor {receptor.nombre} no tiene turnos para {fecha_cesion}. "
                f"Debería tener al menos 1 turno."
            )
        else:
            jornadas_receptor = [t.jornada.nombre.upper() for t in turnos_receptor]
            
            # Para cesión completa, el receptor debe tener al menos 1 jornada
            # Para cesión parcial, debe tener la jornada cedida
            if detalle.tipo_cesion in ['cesion_parcial_am', 'cesion_parcial_pm']:
                jornada_esperada = detalle.jornada_cedida.upper() if detalle.jornada_cedida else None
                if jornada_esperada and jornada_esperada not in jornadas_receptor:
                    resultado['valido'] = False
                    resultado['errores'].append(
                        f"ERROR: Receptor {receptor.nombre} no tiene la jornada {jornada_esperada} "
                        f"en {fecha_cesion}. Jornadas encontradas: {', '.join(jornadas_receptor)}"
                    )
            
            logger.info(f"✅ Validación receptor: {receptor.nombre} tiene {len(jornadas_receptor)} jornada(s): {', '.join(jornadas_receptor)}")
        
        # Verificar turnos del solicitante (debe estar descansando o con cesión parcial)
        turnos_solicitante = Turno.objects.filter(
            explorador=solicitante,
            fecha=fecha_cesion
        ).count()
        
        if detalle.tipo_cesion == 'cesion_completa':
            if turnos_solicitante > 0:
                resultado['advertencias'].append(
                    f"ADVERTENCIA: Solicitante {solicitante.nombre} tiene {turnos_solicitante} turno(s) "
                    f"en {fecha_cesion}, pero debería estar descansando (cesión completa)."
                )
        
        return resultado
    
    @staticmethod
    def _explorador_descansa(explorador, fecha, base_nombre, excluir_id=None) -> bool:
        """
        True si el explorador NO trabaja ninguna jornada ese día (está LIBRE), considerando:
        - Liberado por CUALQUIER solicitud aprobada previa (fuente de verdad L2): doblada/D FDS
          cedida, pago de doblada recibido como acreedor, cambio de descanso, doblada permanente.
        - Fin de semana: su grupo descansa por alternancia.
        - Entre semana: descanso de semana (manual) o lunes de mantenimiento efectivo.
        Sirve para que, cuando el receptor está libre, cubra SOLO la jornada cedida (no se
        doble con una jornada base que en realidad no trabaja).

        Respeta el principio "manda la última aprobada": si otra aprobación ya liberó este día,
        no se reconstruye una doblada sobre una base inexistente. Por eso la capa de solicitudes
        se consulta con la fuente de verdad (dia_comprometido_por_solicitud), NO una consulta
        parcial que solo veía "cedió como solicitante".

        `excluir_id`: ignora la solicitud PROPIA (que se está aplicando) para no auto-detectarse.
        """
        try:
            from turnos.services.turno_service import TurnoService as _TS
            if _TS.dia_comprometido_por_solicitud(explorador, fecha, excluir_id=excluir_id) is not None:
                return True

            if fecha.weekday() in (5, 6):
                from turnos.services.asignacion_especial_service import AsignacionEspecialService
                trabaja = AsignacionEspecialService.grupo_trabaja_efectivo(fecha)
                return bool(base_nombre) and trabaja is not None and base_nombre != trabaja

            from turnos.services.descanso_semana_service import DescansoSemanaService
            from turnos.models import DiaEspecial
            if DescansoSemanaService.es_descanso_semana_manual(base_nombre, fecha):
                return True
            if DiaEspecial.es_mantenimiento_efectivo(fecha):
                return True
            return False
        except Exception:
            return False

    @staticmethod
    @transaction.atomic
    def aplicar_doblada_cesion(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la doblada en la fecha de cesión.
        
        Reglas:
        - Receptor dobla (trabaja su jornada + jornada del solicitante)
        - Solicitante descansa (no tiene turno)
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        
        Raises:
            ValidationError: Si hay errores al aplicar los cambios
        """
        fecha_cesion = solicitud.fecha_cambio_turno
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor

        # ¿El solicitante tenía una DOBLADA (AM+PM) en la cesión ANTES de aplicar? Solo entonces, al
        # ceder una media jornada (cesión parcial), CONSERVA la otra media. Si tenía UNA sola jornada,
        # ceder = día libre: NO se debe materializar la contraria (esa "media jornada fantasma" dejaba
        # el día con una jornada errónea, p. ej. aparecer con PM tras ceder tu única AM).
        from turnos.services.turno_service import TurnoService as _TS_ces_prev
        _sol_tenia_doblada = _TS_ces_prev.estado_dia(solicitante, fecha_cesion).get('jornada') == 'DOBLADA'

        fecha_cesion_str = fecha_cesion.strftime('%Y-%m-%d')
        
        # Obtener jornadas
        jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
            solicitante.id, fecha_cesion_str
        )
        
        # Determinar jornada a ceder
        if detalle.jornada_cedida:
            jornada_cedida_nombre = detalle.jornada_cedida.upper()
        else:
            jornada_cedida_nombre = jornada_solicitante.nombre.upper()
        
        # Obtener jornadas con cache
        jornadas_cache = _obtener_jornadas_cache()
        jornada_cedida_obj = jornadas_cache[jornada_cedida_nombre]
        
        # Obtener jornada del receptor
        jornada_receptor = JornadaService.get_jornada_explorador_fecha(
            receptor.id, fecha_cesion_str
        )
        
        # Receptor: cubre la jornada cedida. Si ese día YA trabaja su jornada (la contraria a la
        # cedida), la CONSERVA y se DOBLA (su jornada + la cedida); si está libre/festivo, cubre
        # SOLO la cedida. Mismo criterio para cesión PARCIAL y COMPLETA. (Antes, la cesión parcial
        # le borraba su jornada y lo dejaba en media jornada, perdiendo su turno propio y sus 30 min.)
        turno_receptor_existente = DobladaTurnoService.tiene_jornada_en_fecha(
            receptor, fecha_cesion, jornada_receptor
        )
        if turno_receptor_existente:
            jornadas_receptor = DobladaTurnoService.obtener_jornadas_en_fecha(receptor, fecha_cesion)
            if jornada_cedida_nombre not in jornadas_receptor:
                DobladaTurnoService.agregar_jornada_a_doblada(
                    receptor, fecha_cesion, jornada_cedida_obj, 'DOBLADA'
                )
        else:
            # El receptor no tiene turno con su jornada base en esta fecha.
            # Si está LIBRE (festivo donde descansa, descanso de semana, fin de semana de
            # descanso, o día libre por una doblada previa), su base no es trabajo real:
            # cubre SOLO la jornada cedida (no se crea una doblada con una base inexistente).
            # Si en cambio sí trabaja su base (virtual), se dobla (base + cedida).
            from solicitudes.services.solicitud_validator import SolicitudValidator as _SV
            _es_cesion_festivo = _SV.es_festivo_semana(fecha_cesion)
            _base_rec = jornada_receptor.nombre.upper() if jornada_receptor else None
            _receptor_libre = DobladaAplicacionService._explorador_descansa(
                receptor, fecha_cesion, _base_rec, excluir_id=solicitud.id
            )
            # Si el receptor NO tiene jornada base (no hay AsignarJornadaExplorador vigente), no hay
            # con qué doblarlo: cubre solo la cedida. Evita crear un Turno con jornada nula (crash).
            if _es_cesion_festivo or _receptor_libre or jornada_receptor is None:
                sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_cesion)
                Turno.objects.create(
                    explorador=receptor,
                    fecha=fecha_cesion,
                    jornada=jornada_cedida_obj,
                    sala=sala_receptor,
                    tipo_cambio='DOBLADA'
                )
                logger.info(
                    f"Doblada cesión: receptor {receptor.nombre} estaba LIBRE; cubre solo "
                    f"{jornada_cedida_nombre} en {fecha_cesion} (sin doblarse)."
                )
            else:
                DobladaTurnoService.crear_doblada_completa(
                    receptor, fecha_cesion, jornada_receptor, jornada_cedida_obj, 'DOBLADA'
                )
        
        # Solicitante: Eliminar turnos según tipo de cesión
        # Si es cesión parcial, eliminar solo la jornada cedida y asegurar que tenga la otra
        if detalle.tipo_cesion == 'cesion_parcial_am':
            # Cesión parcial AM: Eliminar solo turno AM, dejar/crear PM
            Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj
            ).delete()
            jornada_otra_nombre = 'PM'
            jornada_otra_obj = jornadas_cache[jornada_otra_nombre]
            # Solo conservar/crear la PM si el solicitante REALMENTE tenía una doblada (AM+PM). Si tenía
            # una sola jornada (AM), ceder la AM lo deja en día libre — no se crea una PM fantasma.
            if _sol_tenia_doblada and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_cesion, jornada_otra_obj):
                sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_cesion)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_cesion,
                    jornada=jornada_otra_obj,
                    sala=sala_sol,
                    tipo_cambio="DOBLADA"
                )
            logger.info(
                f"Doblada cesión parcial AM aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} {'mantiene PM' if _sol_tenia_doblada else 'queda LIBRE (tenía una sola jornada)'}"
            )
        elif detalle.tipo_cesion == 'cesion_parcial_pm':
            # Cesión parcial PM: Eliminar solo turno PM, dejar/crear AM
            Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj
            ).delete()
            jornada_otra_nombre = 'AM'
            jornada_otra_obj = jornadas_cache[jornada_otra_nombre]
            # Solo conservar/crear la AM si REALMENTE tenía doblada (AM+PM). Con una sola jornada (PM),
            # ceder la PM lo deja en día libre — no se crea una AM fantasma.
            if _sol_tenia_doblada and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_cesion, jornada_otra_obj):
                sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_cesion)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_cesion,
                    jornada=jornada_otra_obj,
                    sala=sala_sol,
                    tipo_cambio="DOBLADA"
                )
            logger.info(
                f"Doblada cesión parcial PM aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} {'mantiene AM' if _sol_tenia_doblada else 'queda LIBRE (tenía una sola jornada)'}"
            )
        else:
            # Cesión completa: Eliminar todos los turnos
            DobladaTurnoService.eliminar_turnos_explorador(solicitante, fecha_cesion)
            logger.info(
                f"Doblada cesión aplicada: Receptor {receptor.nombre} dobla en {fecha_cesion}, "
                f"Solicitante {solicitante.nombre} descansa"
            )
        
        # VALIDACIÓN POST-APLICACIÓN (Integridad de datos)
        try:
            from django.core.exceptions import ValidationError as DjangoValidationError
            
            # Validar que los turnos se hayan creado correctamente
            # (La transacción atómica garantiza que los cambios sean visibles dentro del bloque)
            validacion = DobladaAplicacionService.validar_turnos_doblada_cesion(solicitud, detalle)
            
            if not validacion['valido']:
                errores_str = '; '.join(validacion['errores'])
                logger.error(f"❌ VALIDACIÓN FALLIDA para solicitud {solicitud.id}: {errores_str}")
                raise DjangoValidationError(
                    f"Error de integridad de datos al aplicar doblada: {errores_str}. "
                    f"La transacción será revertida."
                )
            
            if validacion['advertencias']:
                for adv in validacion['advertencias']:
                    logger.warning(f"⚠️ {adv}")
            
            logger.info(f"✅ Validación exitosa para solicitud {solicitud.id}")
            
        except Exception as e:
            logger.error(f"❌ Error en validación post-aplicación: {e}", exc_info=True)
            # Re-lanzar para que la transacción se revierta
            raise
    
    @staticmethod
    @transaction.atomic
    def aplicar_doblada_pago(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la doblada en la fecha de pago.
        
        Orden de prioridad:
        1. Sábado con jornada_pago_sabado → reparto sábado.
        2. jornada_cubre_en_pago AM/PM → deudor SOLO esa media jornada, acreedor la otra.
        3. jornada_cubre_en_pago AMBAS  → deudor AM+PM, acreedor sin turnos.
        4. Cesión parcial sin jcp        → deudor la jornada cedida, acreedor la otra.
        5. jornada_cedida (quirúrgico)   → doblada completa en deudor.
        6. Fallback (legacy)             → doblada completa en deudor.
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        
        Raises:
            ValidationError: Si hay errores al aplicar los cambios
        """
        fecha_pago = detalle.fecha_pago
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        fecha_pago_str = fecha_pago.strftime('%Y-%m-%d')
        
        # ===========================
        # Caso especial: Pago en Sábado
        # ===========================
        # Regla de negocio:
        # - En un sábado (fin de semana), el explorador que "tiene el fin de semana"
        #   normalmente tiene AM+PM (doblada completa) en BD o por asignación.
        # - Al pagar en sábado, el solicitante elige qué jornada trabajará (AM o PM)
        # - El receptor trabaja la jornada contraria (la que queda disponible).
        #
        # Implementación:
        # - Asegurar que el solicitante tenga SOLO la jornada seleccionada.
        # - Asegurar que el receptor tenga SOLO la jornada contraria.
        #
        if fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado:
            jornada_sel = detalle.jornada_pago_sabado.upper()

            # ===========================
            # AMBAS: el solicitante cubre el día completo (AM+PM) y el receptor descansa.
            # Como el solicitante trabaja de más, el receptor le queda debiendo media jornada
            # (se registra en generar_deudas_doblada y se paga en semana).
            # ===========================
            if jornada_sel == "AMBAS":
                jornadas_cache = _obtener_jornadas_cache()
                # Receptor descansa ese sábado: se eliminan sus turnos
                Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
                # Solicitante: dejar AM + PM
                Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
                sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                for jn in ("AM", "PM"):
                    Turno.objects.create(
                        explorador=solicitante,
                        fecha=fecha_pago,
                        jornada=jornadas_cache[jn],
                        sala=sala_solicitante,
                        tipo_cambio="DOBLADA",
                    )
                logger.info(
                    f"Pago en sábado (AMBAS): {solicitante.nombre} cubre AM+PM en {fecha_pago}, "
                    f"{receptor.nombre} descansa (queda media jornada a favor del solicitante)."
                )
                return

            if jornada_sel not in ("AM", "PM"):
                raise ValidationError("jornada_pago_sabado inválida. Debe ser 'AM', 'PM' o 'AMBAS'")

            jornada_contraria = "PM" if jornada_sel == "AM" else "AM"

            jornadas_cache = _obtener_jornadas_cache()
            jornada_sel_obj = jornadas_cache[jornada_sel]
            jornada_contraria_obj = jornadas_cache[jornada_contraria]

            # 1) Solicitante: dejar la jornada seleccionada. Normalmente el sábado se reparte en dos
            # (el deudor trabaja una mitad), así que se limpia el día y se deja SOLO la seleccionada.
            # EXCEPCIÓN: si la mitad CONTRARIA ya la trabaja como pago de OTRA doblada aprobada ese
            # mismo sábado (cediste ambas jornadas a dos personas distintas), se ACUMULA — el deudor
            # termina doblado AM+PM, cada mitad pagando a una persona. En ese caso no se borra la
            # contraria, solo se recrea la seleccionada.
            _otra_mitad_pagada = SolicitudCambio.objects.filter(
                explorador_solicitante=solicitante,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                estado='aprobada',
                doblada__fecha_pago=fecha_pago,
                doblada__jornada_pago_sabado__iexact=jornada_contraria,
            ).exclude(id=solicitud.id).exists()
            if _otra_mitad_pagada:
                # Conservar la mitad contraria (otra doblada); rehacer solo la seleccionada.
                Turno.objects.filter(explorador=solicitante, fecha=fecha_pago, jornada=jornada_sel_obj).delete()
            else:
                Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
            sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
            Turno.objects.create(
                explorador=solicitante,
                fecha=fecha_pago,
                jornada=jornada_sel_obj,
                sala=sala_solicitante,
                tipo_cambio="DOBLADA"
            )

            # 2) Receptor: se le quita la jornada que ahora cubre el deudor (jornada_sel). Normalmente
            # CONSERVA la contraria (reparto del sábado). EXCEPCIÓN: si esa contraria también se la
            # cubre el MISMO deudor con OTRA doblada suya ese mismo sábado (le pagas las DOS mitades al
            # mismo compañero), entonces el receptor NO trabaja ninguna → DESCANSA el día completo.
            _contraria_tambien_cubierta = SolicitudCambio.objects.filter(
                explorador_solicitante=solicitante,
                explorador_receptor=receptor,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                estado='aprobada',
                doblada__fecha_pago=fecha_pago,
                doblada__jornada_pago_sabado__iexact=jornada_contraria,
            ).exclude(id=solicitud.id).exists()

            if _contraria_tambien_cubierta:
                # Le pagas AM y PM al mismo compañero ese sábado → descansa completo (tú doblas).
                Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
                logger.info(
                    f"Pago en sábado aplicado: {solicitante.nombre} cubre {jornada_sel} en {fecha_pago}; "
                    f"{receptor.nombre} DESCANSA el día completo (le cubres ambas mitades)."
                )
            else:
                # Reparto normal: el receptor conserva la jornada contraria.
                Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_sel_obj).delete()
                if not Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_contraria_obj).exists():
                    sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
                    Turno.objects.create(
                        explorador=receptor,
                        fecha=fecha_pago,
                        jornada=jornada_contraria_obj,
                        sala=sala_receptor,
                        tipo_cambio="DOBLADA"
                    )
                logger.info(
                    f"Pago en sábado aplicado: {solicitante.nombre} trabaja {jornada_sel} en {fecha_pago}, "
                    f"{receptor.nombre} trabaja {jornada_contraria} (jornada restante)"
                )
            return

        # ===========================
        # jornada_cubre_en_pago: elección explícita del deudor (AM / PM / AMBAS)
        # ===========================
        # TIENE PRIORIDAD sobre tipo_cesion, jornada_cedida y fallback.
        # Si el deudor eligió "solo AM", queda solo AM; si eligió "AMBAS", queda AM+PM.
        jcp = (getattr(detalle, 'jornada_cubre_en_pago', None) or '').strip().upper()

        if jcp == 'AMBAS':
            jornadas_cache = _obtener_jornadas_cache()
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
            for jn in ('AM', 'PM'):
                j_obj = jornadas_cache[jn]
                if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, j_obj):
                    sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(
                        solicitante, fecha_pago
                    )
                    Turno.objects.create(
                        explorador=solicitante,
                        fecha=fecha_pago,
                        jornada=j_obj,
                        sala=sala_solicitante,
                        tipo_cambio="DOBLADA",
                    )
            logger.info(
                f"Doblada pago (jcp=AMBAS): {solicitante.nombre} AM+PM en {fecha_pago}, "
                f"{receptor.nombre} descansa"
            )
            return

        if jcp in ('AM', 'PM'):
            # jcp = jornada del ACREEDOR (que tiene doblada) que el deudor CUBRE al pagar.
            # El acreedor pierde la jornada cubierta y conserva la otra. Del lado del deudor:
            #   - si ESE día TRABAJA su propia jornada (la contraria a jcp) → DOBLA (su jornada + jcp).
            #   - si ese día está LIBRE (cedió, temporada, fin de semana...) → cubre SOLO jcp, quedando
            #     con UNA jornada (no tiene jornada propia que sumar).
            j_cubre = jcp                                   # ej. AM (la del acreedor que cubro)
            j_propia = 'PM' if j_cubre == 'AM' else 'AM'    # mi propia jornada ese día (contraria)
            jornadas_cache = _obtener_jornadas_cache()
            j_cubre_obj = jornadas_cache[j_cubre]
            j_propia_obj = jornadas_cache[j_propia]

            from turnos.services.turno_service import TurnoService as _TS_jcp
            deudor_trabaja_jcp = bool(_TS_jcp.estado_dia(solicitante, fecha_pago).get('trabaja'))
            # Si trabaja, suma su jornada propia (queda doblado); si está libre, solo cubre jcp.
            jornadas_deudor_crear = (j_propia_obj, j_cubre_obj) if deudor_trabaja_jcp else (j_cubre_obj,)
            for j_obj in jornadas_deudor_crear:
                if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, j_obj):
                    sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                    Turno.objects.create(
                        explorador=solicitante,
                        fecha=fecha_pago,
                        jornada=j_obj,
                        sala=sala_solicitante,
                        tipo_cambio="DOBLADA",
                    )

            # Acreedor: pierde la jornada que cubre el deudor (jcp) y conserva la otra.
            Turno.objects.filter(
                explorador=receptor, fecha=fecha_pago, jornada=j_cubre_obj
            ).delete()
            if not DobladaTurnoService.tiene_jornada_en_fecha(receptor, fecha_pago, j_propia_obj):
                sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
                Turno.objects.create(
                    explorador=receptor,
                    fecha=fecha_pago,
                    jornada=j_propia_obj,
                    sala=sala_receptor,
                    tipo_cambio="DOBLADA",
                )

            logger.info(
                f"Doblada pago (jcp={j_cubre}): {solicitante.nombre} dobla (su {j_propia} + cubre {j_cubre}); "
                f"{receptor.nombre} conserva {j_propia} en {fecha_pago}"
            )
            return

        # ===========================
        # Cesión parcial SIN jornada_cubre_en_pago
        # ===========================
        # Regla de negocio: en la fecha de pago el DEUDOR cubre la jornada que trabaja el
        # ACREEDOR ese día (el favor que devuelve) y el ACREEDOR DESCANSA. El deudor conserva
        # lo que ya tenía, así que:
        #   - si el deudor ya trabajaba la otra jornada → queda con AM+PM (dobla).
        #   - si el deudor NO tenía turno ese día → trabaja SOLO la jornada del acreedor.
        if detalle.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
            # Jornadas que el acreedor trabaja ese día = lo que el deudor va a cubrir.
            jornadas_acreedor = list(
                Turno.objects.filter(explorador=receptor, fecha=fecha_pago)
                .select_related('jornada')
            )
            if jornadas_acreedor:
                jornadas_a_cubrir = [t.jornada for t in jornadas_acreedor]
            else:
                # Sin turno explícito: usar la jornada base (predeterminada) del acreedor.
                jb = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha_pago_str)
                jornadas_cache = _obtener_jornadas_cache()
                jornadas_a_cubrir = [jornadas_cache.get((jb.nombre.upper() if jb else 'AM'))]

            # IMPORTANTE: materializar la jornada BASE (virtual) del deudor como Turno explícito.
            # En un día de semana la jornada propia del deudor no tiene fila en BD (es virtual,
            # viene de la jornada predeterminada). Si no la materializamos y el deudor además
            # cubre la jornada del acreedor, queda UNA sola fila explícita y
            # TurnoService.obtener_jornada_display() NO lo reconoce como DOBLADA → se pierden
            # los 30 min de deuda corporativa aunque físicamente trabaje AM+PM.
            # OJO: solo se materializa si el deudor TRABAJA ese día. Si está LIBRE (descansa por
            # otra solicitud, fin de semana, temporada, etc.) NO tiene jornada propia que sumar:
            # solo cubre la del acreedor → queda con UNA jornada, no doblada.
            from turnos.services.turno_service import TurnoService as _TS_deudor_pago
            deudor_trabaja = bool(_TS_deudor_pago.estado_dia(solicitante, fecha_pago).get('trabaja'))
            deudor_sin_turnos = not Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).exists()
            if deudor_sin_turnos and deudor_trabaja:
                jb_deudor = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha_pago_str)
                if jb_deudor and jb_deudor.nombre.upper() in ('AM', 'PM'):
                    jbd_obj = _obtener_jornadas_cache().get(jb_deudor.nombre.upper())
                    if jbd_obj and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, jbd_obj):
                        sala_base = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                        Turno.objects.create(
                            explorador=solicitante,
                            fecha=fecha_pago,
                            jornada=jbd_obj,
                            sala=sala_base,
                            tipo_cambio="DOBLADA",
                        )

            # El acreedor descansa.
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()
            # El deudor cubre esas jornadas (además de las suyas).
            for j_obj in jornadas_a_cubrir:
                if j_obj and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, j_obj):
                    sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                    Turno.objects.create(
                        explorador=solicitante,
                        fecha=fecha_pago,
                        jornada=j_obj,
                        sala=sala_solicitante,
                        tipo_cambio="DOBLADA",
                    )
            cubiertas = ', '.join(sorted({j.nombre for j in jornadas_a_cubrir if j}))
            logger.info(
                f"Doblada pago (cesión parcial): {solicitante.nombre} cubre {cubiertas} de "
                f"{receptor.nombre} (que descansa) en {fecha_pago}"
            )
            return

        # ===========================
        # Pago con jornada_cedida conocida (quirúrgico: unión de jornadas del deudor)
        # ===========================
        # Cuando jornada_cedida está definida y no es sábado ni festivo especial,
        # el deudor (solicitante) debe terminar trabajando su jornada natural del día
        # MÁS la jornada cedida (doblada completa), y el acreedor descansa o pierde
        # solo la jornada cedida según su configuración.
        if detalle.jornada_cedida:
            _jc_nombre = detalle.jornada_cedida.upper()
            _jcache = _obtener_jornadas_cache()
            _jc_obj = _jcache[_jc_nombre]

            turnos_deudor_antes = list(
                Turno.objects.filter(explorador=solicitante, fecha=fecha_pago)
                .select_related('jornada')
                .values('id', 'jornada__nombre', 'tipo_cambio')
            )

            # Materializar la base del deudor SOLO si ese día trabaja (no si descansa): un deudor
            # libre no suma su jornada propia, solo cubre la que devuelve.
            from turnos.services.turno_service import TurnoService as _TS_deudor_pago2
            _deudor_trabaja_cc = bool(_TS_deudor_pago2.estado_dia(solicitante, fecha_pago).get('trabaja'))
            if not turnos_deudor_antes and _deudor_trabaja_cc:
                jornada_base_deudor = JornadaService.get_jornada_explorador_fecha(
                    solicitante.id, fecha_pago_str
                )
                if jornada_base_deudor:
                    _jb_nombre = jornada_base_deudor.nombre.upper()
                    if _jb_nombre != _jc_nombre:
                        _jb_obj = _jcache.get(_jb_nombre)
                        if _jb_obj and not DobladaTurnoService.tiene_jornada_en_fecha(
                            solicitante, fecha_pago, _jb_obj
                        ):
                            sala_sol_base = DobladaTurnoService.obtener_sala_explorador_fecha(
                                solicitante, fecha_pago
                            )
                            Turno.objects.create(
                                explorador=solicitante,
                                fecha=fecha_pago,
                                jornada=_jb_obj,
                                sala=sala_sol_base,
                                tipo_cambio="DOBLADA",
                            )

            # La jornada cedida es la parte PROPIA del deudor en la doblada de pago: solo se suma
            # si ese día TRABAJA. Si está LIBRE no dobla — únicamente cubre la del acreedor (abajo),
            # quedando con UNA sola jornada.
            if _deudor_trabaja_cc and not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, _jc_obj):
                sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=_jc_obj,
                    sala=sala_sol,
                    tipo_cambio="DOBLADA",
                )

            # El deudor SIEMPRE cubre la jornada del acreedor (es el pago). Se garantiza aunque
            # coincida con la cedida (tiene_jornada evita duplicados): así el deudor libre queda
            # con esa jornada aunque el bloque de arriba se haya omitido.
            jornada_acreedor = JornadaService.get_jornada_explorador_fecha(
                receptor.id, fecha_pago_str
            )
            if jornada_acreedor:
                _ja_nombre = jornada_acreedor.nombre.upper()
                _ja_obj = _jcache.get(_ja_nombre)
                if _ja_obj and not DobladaTurnoService.tiene_jornada_en_fecha(
                    solicitante, fecha_pago, _ja_obj
                ):
                    sala_sol_acre = DobladaTurnoService.obtener_sala_explorador_fecha(
                        solicitante, fecha_pago
                    )
                    Turno.objects.create(
                        explorador=solicitante,
                        fecha=fecha_pago,
                        jornada=_ja_obj,
                        sala=sala_sol_acre,
                        tipo_cambio="DOBLADA",
                    )

            if getattr(detalle, 'tipo_cesion', None) == 'cesion_completa':
                DobladaTurnoService.eliminar_turnos_explorador(receptor, fecha_pago)
            else:
                Turno.objects.filter(
                    explorador=receptor,
                    fecha=fecha_pago,
                    jornada=_jc_obj,
                ).delete()
                _jo_nombre = 'PM' if _jc_nombre == 'AM' else 'AM'
                _jo_obj = _jcache.get(_jo_nombre)
                if _jo_obj and not DobladaTurnoService.tiene_jornada_en_fecha(
                    receptor, fecha_pago, _jo_obj
                ):
                    sala_rec = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_pago)
                    Turno.objects.create(
                        explorador=receptor,
                        fecha=fecha_pago,
                        jornada=_jo_obj,
                        sala=sala_rec,
                        tipo_cambio="DOBLADA",
                    )

            _jornadas_deudor_final = sorted(
                Turno.objects.filter(explorador=solicitante, fecha=fecha_pago)
                .values_list('jornada__nombre', flat=True)
            )
            logger.info(
                f"Doblada pago (quirúrgico) aplicada: {solicitante.nombre} queda con "
                f"{_jornadas_deudor_final or 'sin turnos'}, {receptor.nombre} cede su jornada en {fecha_pago}"
            )
            return
        
        # ===========================
        # Caso fallback: Pago sin jornada_cedida (legacy)
        # ===========================
        jornada_deudor = JornadaService.get_jornada_explorador_fecha(
            solicitante.id, fecha_pago_str
        )
        jornada_acreedor = JornadaService.get_jornada_explorador_fecha(
            receptor.id, fecha_pago_str
        )
        
        jornadas_cache = _obtener_jornadas_cache()
        jornada_acreedor_obj = jornadas_cache[jornada_acreedor.nombre.upper()]

        # El deudor solo DOBLA (suma su jornada propia) si ESE día trabaja. Si está LIBRE —descansa
        # por otra solicitud (cedió), temporada o fin de semana— únicamente cubre la jornada del
        # acreedor y queda con UNA sola jornada. Sin esta comprobación, un deudor libre cuya jornada
        # base coincide con la del acreedor terminaba con la jornada DUPLICADA (dos filas AM/PM).
        from turnos.services.turno_service import TurnoService as _TS_fb
        deudor_trabaja_fb = bool(_TS_fb.estado_dia(solicitante, fecha_pago).get('trabaja'))

        if not deudor_trabaja_fb:
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, jornada_acreedor_obj):
                sala_fb = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                Turno.objects.create(
                    explorador=solicitante, fecha=fecha_pago,
                    jornada=jornada_acreedor_obj, sala=sala_fb, tipo_cambio='DOBLADA',
                )
        else:
            turno_deudor_existente = DobladaTurnoService.tiene_jornada_en_fecha(
                solicitante, fecha_pago, jornada_deudor
            )
            if turno_deudor_existente:
                jornadas_deudor = DobladaTurnoService.obtener_jornadas_en_fecha(solicitante, fecha_pago)
                jornada_acreedor_nombre = jornada_acreedor.nombre.upper()

                if jornada_acreedor_nombre not in jornadas_deudor:
                    DobladaTurnoService.agregar_jornada_a_doblada(
                        solicitante, fecha_pago, jornada_acreedor_obj, 'DOBLADA'
                    )
            else:
                DobladaTurnoService.crear_doblada_completa(
                    solicitante, fecha_pago, jornada_deudor, jornada_acreedor_obj, 'DOBLADA'
                )

        DobladaTurnoService.eliminar_turnos_explorador(receptor, fecha_pago)

        logger.info(
            f"Doblada pago (legacy) aplicada: {solicitante.nombre} "
            f"{'cubre la jornada del acreedor (libre)' if not deudor_trabaja_fb else 'dobla'} en "
            f"{fecha_pago}, Acreedor {receptor.nombre} descansa"
        )

    @staticmethod
    @transaction.atomic
    def aplicar_intercambio(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        INTERCAMBIO DE DOBLADAS: swap de días doblados (sin deuda). Ambos tenían doblada:
        - Día A (fecha de cesión) = tu doblada → el RECEPTOR la asume (AM+PM) y TÚ descansas.
        - Día B (fecha de pago) = la doblada del compañero → TÚ la asumes (AM+PM) y ÉL descansa.
        No genera ni altera deudas (es un cambio de turno, pero de días doblados).
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        dia_a = solicitud.fecha_cambio_turno
        dia_b = detalle.fecha_pago
        jornadas_cache = _obtener_jornadas_cache()

        def _sala_de(empleado, fecha):
            # Quien asume la doblada trabaja en la SALA de la doblada que cubre (la del dueño
            # de ese día), no la suya (no tiene turno ese día). Fallback: su sala por competencia.
            t = (Turno.objects.filter(explorador=empleado, fecha=fecha)
                 .select_related('sala').first())
            if t and t.sala:
                return t.sala
            return DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)

        # Salas de las dobladas que se asumen (capturar ANTES de mutar).
        sala_a = _sala_de(solicitante, dia_a)   # tu doblada en el día A
        sala_b = _sala_de(receptor, dia_b)       # la doblada del compañero en el día B

        def _doblar(empleado, fecha, sala):
            Turno.objects.filter(explorador=empleado, fecha=fecha).delete()
            for jn in ('AM', 'PM'):
                Turno.objects.create(
                    explorador=empleado, fecha=fecha,
                    jornada=jornadas_cache[jn], sala=sala, tipo_cambio='DOBLADA',
                )

        # Día A: el receptor asume tu doblada (misma sala); tú descansas.
        _doblar(receptor, dia_a, sala_a)
        Turno.objects.filter(explorador=solicitante, fecha=dia_a).delete()
        # Día B: tú asumes la doblada del compañero (misma sala); él descansa.
        _doblar(solicitante, dia_b, sala_b)
        Turno.objects.filter(explorador=receptor, fecha=dia_b).delete()

        logger.info(
            "Intercambio de dobladas aplicado: solicitud %s — %s y %s intercambian sus dobladas "
            "(A=%s, B=%s); sin deudas.",
            solicitud.id, solicitante.nombre, receptor.nombre, dia_a, dia_b,
        )
    
    @staticmethod
    @transaction.atomic
    def aplicar_pago_residual_semana(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica la devolución en semana de la deuda residual generada por un pago en sábado AMBAS.

        Ese día (detalle.fecha_pago_semana) el RECEPTOR dobla para cubrir al SOLICITANTE:
        - El solicitante DESCANSA su jornada (la que el receptor le devuelve).
        - El receptor trabaja DOBLE: su propia jornada + la del solicitante.

        Requiere jornadas contrarias ese día (ya validado en la estrategia).
        """
        fecha = detalle.fecha_pago_semana
        if not fecha:
            return

        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fstr = fecha.strftime('%Y-%m-%d')

        j_sol = JornadaService.get_jornada_explorador_fecha(solicitante.id, fstr)
        j_rec = JornadaService.get_jornada_explorador_fecha(receptor.id, fstr)
        if not j_sol or not j_rec:
            raise ValidationError("No se pudo determinar la jornada para el pago en semana.")

        jornadas_cache = _obtener_jornadas_cache()
        j_sol_obj = jornadas_cache[j_sol.nombre.upper()]
        j_rec_obj = jornadas_cache[j_rec.nombre.upper()]

        # Solicitante descansa su jornada (el receptor se la devuelve)
        Turno.objects.filter(explorador=solicitante, fecha=fecha, jornada=j_sol_obj).delete()

        # Receptor dobla: su jornada + la del solicitante
        if DobladaTurnoService.tiene_jornada_en_fecha(receptor, fecha, j_rec_obj):
            jornadas_receptor = DobladaTurnoService.obtener_jornadas_en_fecha(receptor, fecha)
            if j_sol.nombre.upper() not in jornadas_receptor:
                DobladaTurnoService.agregar_jornada_a_doblada(receptor, fecha, j_sol_obj, 'DOBLADA')
        else:
            DobladaTurnoService.crear_doblada_completa(receptor, fecha, j_rec_obj, j_sol_obj, 'DOBLADA')

        logger.info(
            f"Pago en semana aplicado: {receptor.nombre} dobla cubriendo a {solicitante.nombre} "
            f"en {fecha} (el solicitante descansa su jornada {j_sol.nombre.upper()})."
        )

    @staticmethod
    @transaction.atomic
    def generar_deudas_doblada(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        DobladaDeudaService.generar_deudas_doblada(solicitud, detalle)

    @staticmethod
    @transaction.atomic
    def anular_doblada_de_un_dia(solicitud: SolicitudCambio, explorador, fecha, motivo: str) -> int:
        """
        Revert PARCIAL y AUDITABLE del día de doblada de UN solo explorador (el que no cumplió):
        - SOFT-DELETE de sus turnos DOBLADA de esa fecha (marca ``anulado=True`` + motivo; NO borra,
          para que la auditoría vea "anulado por reprogramación" y no una falta).
        - Cancela SOLO su ``DeudaCorporativa`` de esa fecha/solicitud (los 30 min de ese día), dejando
          el historial intacto.
        NO toca al otro explorador ni las demás deudas/turnos de la doblada. Es el "anti-veneno":
        revierte el efecto económico y de asistencia de una persona en un día, sin efecto mariposa.

        Devuelve la cantidad de turnos anulados.
        """
        from solicitudes.models import DeudaCorporativa
        from core.services.cache_service import CacheService

        turnos = list(Turno.objects.filter(
            explorador=explorador, fecha=fecha, tipo_cambio__in=['DOBLADA', 'D FDS', 'DOBLADA PERM']
        ))
        for t in turnos:
            t.anulado = True
            t.motivo_anulacion = (motivo or 'Anulado por reprogramación')[:200]
            t.save(update_fields=['anulado', 'motivo_anulacion'])

        DeudaCorporativa.objects.filter(
            explorador=explorador, fecha_doblada=fecha, solicitud_origen=solicitud, estado='activa'
        ).update(estado='cancelada')

        CacheService.invalidar_cache_turnos_empleado(explorador.id, fecha.month, fecha.year)
        logger.info(
            "Doblada de un día ANULADA (reprogramación): solicitud %s, %s, %s — %d turno(s) soft-deleted.",
            solicitud.id, getattr(explorador, 'nombre', explorador), fecha, len(turnos),
        )
        return len(turnos)

    @staticmethod
    @transaction.atomic
    def revertir_doblada_aplicada(solicitud: SolicitudCambio) -> None:
        """
        Revierte los cambios de una doblada ya aprobada.

        Utilizado dentro de la ventana de cancelación de 30 minutos.
        Si existe ``snapshot_turnos_previos`` (guardado al aprobar), restaura exactamente
        los turnos que había en cesión y pago para ambos exploradores (incl. cambios de
        turno sencillo previos). Si no hay snapshot (dobladas antiguas), elimina turnos
        con tipo_cambio DOBLADA y reconstruye según jornada predeterminada (comportamiento
        anterior, limitado).
        Cancela las deudas asociadas a esta solicitud.

        Args:
            solicitud: Solicitud de doblada aprobada a revertir

        Raises:
            Exception: Si ocurre un error durante la reversión
        """
        from solicitudes.models import DeudaExplorador, DeudaCorporativa
        from core.utils.jornada_utils import JornadaUtils

        detalle = solicitud.doblada
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago

        snapshot = getattr(detalle, 'snapshot_turnos_previos', None)
        if snapshot:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)
            # Cancelar primero las deudas de ESTA solicitud (para que la reconciliación no las
            # cuente como vigentes) y luego reconstruir el estado con las dobladas que siguen
            # aprobadas sobre las fechas afectadas (corrige la cesión total cancelada).
            DeudaExplorador.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
            DeudaCorporativa.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
            afectados = DobladaAplicacionService._fechas_explorador_afectados(snapshot)
            DobladaAplicacionService.reconciliar_dobladas_aprobadas(afectados, solicitud.id)
            from core.services.cache_service import CacheService
            for emp_id, f in afectados:
                CacheService.invalidar_cache_turnos_empleado(emp_id, f.month, f.year)
            logger.info(
                f"Doblada revertida (desde snapshot + reconciliación): Solicitud {solicitud.id} - "
                f"{solicitante.nombre} <-> {receptor.nombre}"
            )
            return

        jornadas_cache = _obtener_jornadas_cache()

        def _restaurar_turno_base(empleado, fecha):
            """
            Elimina turnos DOBLADA del empleado en la fecha y recrea su turno normal
            basándose en la jornada asignada si corresponde trabajar ese día.

            En un festivo entre semana la jornada (doblada AM+PM o descanso) la determina la
            ROTACIÓN del festivo, no la jornada base + día; el estado se computa en
            `TurnoService.estado_dia` sin necesidad de filas Turno. Por eso aquí, tras borrar
            los turnos DOBLADA, NO se recrea ningún turno base: crear un turno suelto dejaría
            media jornada donde por rotación corresponde doblada o descanso.
            """
            Turno.objects.filter(explorador=empleado, fecha=fecha, tipo_cambio='DOBLADA').delete()

            from solicitudes.services.solicitud_validator import SolicitudValidator as _SVfv
            if _SVfv.es_festivo_semana(fecha):
                return

            # Obtener jornada asignada y calcular si trabaja ese día
            jornada_base = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha.strftime('%Y-%m-%d'))
            if not jornada_base:
                return

            jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
            if jornada_dia == 'Descanso':
                return

            jornada_nombre = jornada_dia if jornada_dia in ('AM', 'PM') else jornada_base.nombre.upper()
            if jornada_nombre not in jornadas_cache:
                return

            if not Turno.objects.filter(explorador=empleado, fecha=fecha).exists():
                sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                Turno.objects.create(
                    explorador=empleado,
                    fecha=fecha,
                    jornada=jornadas_cache[jornada_nombre],
                    sala=sala,
                    tipo_cambio=None
                )
                logger.info(f"Turno base restaurado: {empleado.nombre} - {fecha} - {jornada_nombre}")

        # --- Revertir fecha de cesión ---
        _restaurar_turno_base(receptor, fecha_cesion)
        _restaurar_turno_base(solicitante, fecha_cesion)

        # --- Revertir fecha de pago ---
        _restaurar_turno_base(solicitante, fecha_pago)
        _restaurar_turno_base(receptor, fecha_pago)

        # --- Cancelar deudas entre exploradores ---
        DeudaExplorador.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')

        # --- Cancelar deudas corporativas ---
        DeudaCorporativa.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')

        # --- Reconciliar otras dobladas aprobadas sobre las mismas fechas ---
        afectados_sin_snap = {
            (solicitante.id, fecha_cesion), (receptor.id, fecha_cesion),
            (solicitante.id, fecha_pago), (receptor.id, fecha_pago),
        }
        DobladaAplicacionService.reconciliar_dobladas_aprobadas(afectados_sin_snap, solicitud.id)

        # --- Invalidar caché de Mis Turnos para ambos empleados ---
        from core.services.cache_service import CacheService
        for emp_id, f in afectados_sin_snap:
            if f:
                CacheService.invalidar_cache_turnos_empleado(emp_id, f.month, f.year)

        logger.info(
            f"Doblada revertida: Solicitud {solicitud.id} - "
            f"{solicitante.nombre} <-> {receptor.nombre}"
        )
