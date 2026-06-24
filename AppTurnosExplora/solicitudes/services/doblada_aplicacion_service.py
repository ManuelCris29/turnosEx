"""
Servicio para aplicar cambios de doblada.

Responsabilidad única: Aplicar los cambios de turnos y generar deudas cuando
una solicitud de doblada es aprobada.
"""
from typing import Tuple, Dict
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.cache import cache
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from turnos.models import Jornada, Turno
from turnos.services.jornada_service import JornadaService
from turnos.services.doblada_turno_service import DobladaTurnoService
from .deuda_service import DeudaService
from .deuda_corporativa_service import DeudaCorporativaService
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


def _obtener_jornadas_cache() -> Dict[str, Jornada]:
    """
    Obtiene las jornadas AM y PM con cache para evitar múltiples consultas.
    
    Returns:
        Diccionario con {'AM': Jornada, 'PM': Jornada}
    """
    cache_key = 'jornadas_am_pm'
    jornadas = cache.get(cache_key)
    
    if jornadas is None:
        jornadas = {
            'AM': Jornada.objects.get(nombre='AM'),
            'PM': Jornada.objects.get(nombre='PM')
        }
        # Cache por 1 hora (las jornadas no cambian frecuentemente)
        cache.set(cache_key, jornadas, 3600)
    
    return jornadas


class DobladaAplicacionService:
    """
    Servicio para aplicar cambios de doblada.
    
    Responsabilidad única: Aplicar cambios de turnos y generar deudas.
    Incluye validación post-aplicación para garantizar integridad de datos.
    """

    @staticmethod
    def capturar_snapshot_turnos_previos(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> dict:
        """
        Copia el estado real de Turno en BD para solicitante y receptor en fecha de cesión y de pago,
        antes de aplicar la doblada. Así la cancelación en 30 min puede restaurar cambios de turno
        sencillos u otras asignaciones que no son solo jornada predeterminada.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        pairs = [
            (solicitante.id, fecha_cesion),
            (receptor.id, fecha_cesion),
            (solicitante.id, fecha_pago),
            (receptor.id, fecha_pago),
        ]
        snapshot: dict = {}
        for emp_id, fecha in pairs:
            key = f"{emp_id}:{fecha.isoformat()}"
            turnos_qs = (
                Turno.objects.filter(explorador_id=emp_id, fecha=fecha)
                .select_related('jornada')
                .order_by('jornada_id')
            )
            snapshot[key] = [
                {
                    'jornada_nombre': t.jornada.nombre.upper(),
                    'sala_id': t.sala_id,
                    'tipo_cambio': t.tipo_cambio,
                }
                for t in turnos_qs
            ]
        return snapshot

    @staticmethod
    def restaurar_turnos_desde_snapshot(snapshot: dict) -> None:
        """Reemplaza turnos en las fechas del snapshot por el contenido guardado."""
        if not snapshot:
            return
        jornadas_cache = _obtener_jornadas_cache()
        from turnos.models import Jornada as JornadaModel

        for key, rows in snapshot.items():
            try:
                emp_str, fecha_str = key.split(':', 1)
                emp_id = int(emp_str)
                fecha = date.fromisoformat(fecha_str)
            except (ValueError, TypeError):
                logger.warning('Snapshot doblada: clave inválida %r', key)
                continue

            Turno.objects.filter(explorador_id=emp_id, fecha=fecha).delete()

            for row in rows or []:
                jn = (row.get('jornada_nombre') or '').upper()
                jornada_obj = jornadas_cache.get(jn)
                if not jornada_obj:
                    jornada_obj = JornadaModel.objects.filter(nombre__iexact=jn).first()
                if not jornada_obj:
                    logger.warning(
                        'Snapshot doblada: jornada %r no encontrada para %s en %s',
                        jn, emp_id, fecha,
                    )
                    continue
                sala_id = row.get('sala_id')
                if not sala_id:
                    empleado = Empleado.objects.filter(pk=emp_id).first()
                    if not empleado:
                        continue
                    sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                    sala_id = sala.id if sala else None
                if not sala_id:
                    logger.warning('Snapshot doblada: sin sala para %s en %s', emp_id, fecha)
                    continue
                Turno.objects.create(
                    explorador_id=emp_id,
                    fecha=fecha,
                    jornada=jornada_obj,
                    sala_id=sala_id,
                    tipo_cambio=row.get('tipo_cambio'),
                )
                logger.info('Turno restaurado desde snapshot: explorador %s, %s, %s', emp_id, fecha, jn)

    @staticmethod
    def _fechas_explorador_afectados(snapshot: dict):
        """Extrae el conjunto de (explorador_id, fecha) que cubre un snapshot."""
        afectados = set()
        for key in (snapshot or {}).keys():
            try:
                emp_str, fecha_str = key.split(':', 1)
                afectados.add((int(emp_str), date.fromisoformat(fecha_str)))
            except (ValueError, TypeError):
                continue
        return afectados

    @staticmethod
    def reconciliar_dobladas_aprobadas(afectados, excluir_solicitud_id) -> None:
        """
        Tras restaurar el snapshot de una doblada CANCELADA, re-aplica el efecto de las
        dobladas que SIGUEN APROBADAS cuyo cesión/pago cae en las fechas afectadas.

        Motivo: el snapshot de una cesión total (2 solicitudes enlazadas que comparten la
        fecha de cesión) refleja un estado INTERMEDIO. Restaurarlo tal cual deja el estado
        inconsistente según el orden de cancelación (p. ej. el solicitante pierde una jornada
        de su doblada). Re-aplicar las dobladas vigentes —en ORDEN CRONOLÓGICO de aprobación—
        reconstruye el estado correcto sin importar el orden en que se cancelaron.

        Solo se re-aplica el lado (cesión o pago) que cae en una fecha afectada, para
        mantener la operación acotada a esas fechas. No genera deudas (eso es aparte).
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        if not afectados:
            return
        fechas = {f for (_e, f) in afectados}
        exploradores = {e for (e, _f) in afectados}
        candidatas = (
            SolicitudCambio.objects
            .filter(estado='aprobada', doblada__isnull=False)
            .exclude(id=excluir_solicitud_id)
            .filter(Q(fecha_cambio_turno__in=fechas) | Q(doblada__fecha_pago__in=fechas))
            .select_related('doblada')
            .order_by('fecha_resolucion', 'id')
            .distinct()
        )
        for s in candidatas:
            if (s.explorador_solicitante_id not in exploradores
                    and s.explorador_receptor_id not in exploradores):
                continue
            det = s.doblada
            if s.fecha_cambio_turno in fechas:
                DobladaAplicacionService.aplicar_doblada_cesion(s, det)
            if det.fecha_pago in fechas:
                DobladaAplicacionService.aplicar_doblada_pago(s, det)
            logger.info(
                "Reconciliación post-revert: re-aplicada doblada aprobada %s sobre fechas afectadas.",
                s.id,
            )

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
    def _explorador_descansa(explorador, fecha, base_nombre) -> bool:
        """
        True si el explorador NO trabaja ninguna jornada ese día (está LIBRE), considerando:
        - Fin de semana: su grupo descansa por alternancia.
        - Entre semana: descanso de semana (manual) o lunes de mantenimiento efectivo.
        - Día libre por una doblada previa aprobada (cedió ese día).
        Sirve para que, cuando el receptor está libre, cubra SOLO la jornada cedida (no se
        doble con una jornada base que en realidad no trabaja).
        """
        try:
            if fecha.weekday() in (5, 6):
                from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
                trabaja = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha)
                return bool(base_nombre) and trabaja is not None and base_nombre != trabaja

            from turnos.services.descanso_semana_service import DescansoSemanaService
            from turnos.models import DiaEspecial
            if DescansoSemanaService.es_descanso_semana_manual(base_nombre, fecha):
                return True
            if DiaEspecial.es_mantenimiento_efectivo(fecha):
                return True

            # Día libre por una doblada/D FDS previa aprobada donde este explorador cedió.
            from solicitudes.models import SolicitudCambio as _SC
            return _SC.objects.filter(
                explorador_solicitante=explorador,
                fecha_cambio_turno=fecha,
                estado='aprobada',
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
            ).exists()
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
        
        # Receptor: según tipo de cesión
        if detalle.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
            # Cesión parcial: el receptor solo trabaja la jornada cedida (media jornada), no doblada
            Turno.objects.filter(explorador=receptor, fecha=fecha_cesion).delete()
            sala_receptor = DobladaTurnoService.obtener_sala_explorador_fecha(receptor, fecha_cesion)
            Turno.objects.create(
                explorador=receptor,
                fecha=fecha_cesion,
                jornada=jornada_cedida_obj,
                sala=sala_receptor,
                tipo_cambio="DOBLADA"
            )
        else:
            # Cesión completa: receptor dobla (su jornada + jornada cedida)
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
                    receptor, fecha_cesion, _base_rec
                )
                if _es_cesion_festivo or _receptor_libre:
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
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_cesion, jornada_otra_obj):
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
                f"Solicitante {solicitante.nombre} mantiene PM"
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
            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_cesion, jornada_otra_obj):
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
                f"Solicitante {solicitante.nombre} mantiene AM"
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

            # 1) Solicitante: dejar SOLO la jornada seleccionada
            Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).delete()
            sala_solicitante = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
            Turno.objects.create(
                explorador=solicitante,
                fecha=fecha_pago,
                jornada=jornada_sel_obj,
                sala=sala_solicitante,
                tipo_cambio="DOBLADA"
            )

            # 2) Receptor: dejar SOLO la jornada contraria
            # - Si tenía doblada completa (AM+PM) ese sábado, se elimina la jornada que ahora cubre el solicitante.
            Turno.objects.filter(explorador=receptor, fecha=fecha_pago, jornada=jornada_sel_obj).delete()

            # Si el receptor no tiene aún la jornada contraria en BD, crearla (caso raro)
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
            # El deudor, al pagar, DOBLA: trabaja su propia jornada (la contraria a jcp) MÁS la
            # que cubre. El acreedor pierde la jornada cubierta y conserva la otra.
            j_cubre = jcp                                   # ej. AM (la del acreedor que cubro)
            j_propia = 'PM' if j_cubre == 'AM' else 'AM'    # mi propia jornada ese día (contraria)
            jornadas_cache = _obtener_jornadas_cache()
            j_cubre_obj = jornadas_cache[j_cubre]
            j_propia_obj = jornadas_cache[j_propia]

            # Deudor: queda con AM+PM (su propia + la que cubre) → doblada.
            for j_obj in (j_propia_obj, j_cubre_obj):
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
            # Solo se materializa si el deudor no tiene ya turnos ese día y su base es jornada real.
            deudor_sin_turnos = not Turno.objects.filter(explorador=solicitante, fecha=fecha_pago).exists()
            if deudor_sin_turnos:
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

            if not turnos_deudor_antes:
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

            if not DobladaTurnoService.tiene_jornada_en_fecha(solicitante, fecha_pago, _jc_obj):
                sala_sol = DobladaTurnoService.obtener_sala_explorador_fecha(solicitante, fecha_pago)
                Turno.objects.create(
                    explorador=solicitante,
                    fecha=fecha_pago,
                    jornada=_jc_obj,
                    sala=sala_sol,
                    tipo_cambio="DOBLADA",
                )

            jornada_acreedor = JornadaService.get_jornada_explorador_fecha(
                receptor.id, fecha_pago_str
            )
            if jornada_acreedor:
                _ja_nombre = jornada_acreedor.nombre.upper()
                if _ja_nombre != _jc_nombre:
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

            logger.info(
                f"Doblada pago (quirúrgico) aplicada: {solicitante.nombre} gana {_jc_nombre}, "
                f"{receptor.nombre} pierde {_jc_nombre} en {fecha_pago}"
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
            f"Doblada pago (legacy) aplicada: Deudor {solicitante.nombre} dobla en {fecha_pago}, "
            f"Acreedor {receptor.nombre} descansa"
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
        """
        Genera las deudas entre exploradores y corporativas asociadas a una doblada.
        
        Reglas:
        - Se crea una deuda entre exploradores (estado 'pagada' porque ambas dobladas ya están aplicadas)
        - La deuda corporativa (30 minutos) **solo se genera si la doblada es efectiva en esa fecha**,
          es decir, si la jornada real del día es DOBLADA (AM+PM) según los turnos aplicados.
        
        Args:
            solicitud: Solicitud de doblada aprobada
            detalle: Detalle de la doblada
        """
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        
        # Determinar jornada cedida
        if detalle.jornada_cedida:
            jornada_cedida_nombre = detalle.jornada_cedida.upper()
        else:
            fecha_cesion_str = fecha_cesion.strftime('%Y-%m-%d')
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, fecha_cesion_str
            )
            jornada_cedida_nombre = jornada_solicitante.nombre.upper()
        
        # Generar deuda entre exploradores (estado 'pagada' porque, conceptualmente,
        # ambas partes se comprometen a realizar la doblada en cesión y pago).
        DeudaService.crear_deuda(
            deudor=solicitante,
            acreedor=receptor,
            solicitud=solicitud,
            fecha_generacion=fecha_cesion,
            fecha_pago_pactada=fecha_pago,
            fecha_pago_real=fecha_pago,  # Ya se aplicó
            jornada_cedida=jornada_cedida_nombre,
            media_jornada=True
        )

        # ===========================
        # Deuda residual: pago en sábado cubriendo AMBAS jornadas
        # ===========================
        # Si el solicitante cubrió el día completo del sábado (AMBAS), trabajó de más una
        # jornada respecto a lo que debía. Por eso el RECEPTOR le queda debiendo esa jornada
        # al solicitante, que se devuelve el día de semana elegido (detalle.fecha_pago_semana):
        # ese día el receptor dobla y el solicitante descansa. Como se aplica al aprobar,
        # la deuda queda registrada como PAGADA (con su fecha real = el día de semana).
        if (fecha_pago.weekday() == 5
                and (getattr(detalle, 'jornada_pago_sabado', '') or '').upper() == 'AMBAS'
                and getattr(detalle, 'fecha_pago_semana', None)):
            fecha_semana = detalle.fecha_pago_semana
            # La jornada que se devuelve es la del SOLICITANTE (la que el receptor le cubre ese día).
            jornada_sol_semana = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, fecha_semana.strftime('%Y-%m-%d')
            )
            jornada_residual = (
                jornada_sol_semana.nombre.upper()
                if jornada_sol_semana else jornada_cedida_nombre
            )
            DeudaService.crear_deuda(
                deudor=receptor,        # el receptor queda debiendo...
                acreedor=solicitante,   # ...a favor del solicitante
                solicitud=solicitud,
                fecha_generacion=fecha_pago,
                fecha_pago_pactada=fecha_semana,
                fecha_pago_real=fecha_semana,  # se aplica al aprobar → pagada
                jornada_cedida=jornada_residual,
                media_jornada=True,
            )
            logger.info(
                f"Deuda residual (pago sábado AMBAS): {receptor.nombre} devuelve la jornada "
                f"{jornada_residual} a {solicitante.nombre} el {fecha_semana} (en semana)."
            )

        # ===========================
        # Deuda corporativa SOLO por doblada efectiva
        # ===========================
        # Regla de negocio:
        # - La deuda corporativa (30 minutos) se genera únicamente cuando el explorador
        #   realmente trabaja una jornada DOBLADA (AM+PM) en una fecha concreta.
        # - No basta con que la solicitud esté aprobada; debemos verificar los turnos reales.
        #
        # Implementación:
        # - Usamos TurnoService.obtener_jornada_display() como fuente de verdad.
        # - Si jornada_display == 'DOBLADA' → se crea la deuda corporativa.
        # - Si jornada_display es 'AM', 'PM' o None (descanso / media jornada) → NO se genera deuda.
        from turnos.services.turno_service import TurnoService

        def _registrar_deuda_corporativa_si_doblada(explorador: Empleado, fecha_doblada: date, comentario: str) -> None:
            # Los 30 min solo aplican de lunes a viernes (no sábados, domingos ni festivos).
            if not DeudaCorporativaService.aplica_deuda_doblada(fecha_doblada):
                logger.info(
                    f"No se genera deuda corporativa para {explorador.nombre} en {fecha_doblada}: "
                    f"fin de semana o festivo (jornada completa, sin 30 min)."
                )
                return
            jornada_display = TurnoService.obtener_jornada_display(explorador, fecha_doblada)
            if jornada_display == 'DOBLADA':
                DeudaCorporativaService.crear_deuda_corporativa(
                    explorador=explorador,
                    minutos=30,
                    fecha_generacion=date.today(),
                    fecha_doblada=fecha_doblada,
                    solicitud=solicitud,
                    comentario=comentario
                )
                logger.info(
                    f"Deuda corporativa generada (30 min) para {explorador.nombre} "
                    f"en {fecha_doblada} por jornada DOBLADA."
                )
            else:
                logger.info(
                    f"No se genera deuda corporativa para {explorador.nombre} en {fecha_doblada}: "
                    f"jornada_display={jornada_display!r}"
                )

        # Receptor: posible doblada en fecha de cesión
        _registrar_deuda_corporativa_si_doblada(
            explorador=receptor,
            fecha_doblada=fecha_cesion,
            comentario=f'Doblada efectiva en fecha de cesión ({fecha_cesion})'
        )

        # Solicitante (deudor): posible doblada en fecha de pago
        _registrar_deuda_corporativa_si_doblada(
            explorador=solicitante,
            fecha_doblada=fecha_pago,
            comentario=f'Doblada efectiva en fecha de pago ({fecha_pago})'
        )

        # Pago en sábado AMBAS: el día de pago en semana el RECEPTOR dobla en un día de semana
        # (cambia un sábado por un día de semana) → sí genera 30 min para el receptor.
        if (fecha_pago.weekday() == 5
                and (getattr(detalle, 'jornada_pago_sabado', '') or '').upper() == 'AMBAS'
                and getattr(detalle, 'fecha_pago_semana', None)):
            _registrar_deuda_corporativa_si_doblada(
                explorador=receptor,
                fecha_doblada=detalle.fecha_pago_semana,
                comentario=f'Doblada efectiva (pago en semana del sábado AMBAS) ({detalle.fecha_pago_semana})'
            )

        # ===========================
        # Cambio de un DÍA DE SEMANA por un SÁBADO: 30 min también para el EMISOR
        # ===========================
        # Regla de negocio: si el EMISOR (solicitante) cedió una jornada de una DOBLADA que
        # tenía en un día de SEMANA y paga ese favor en SÁBADO, debe igual los 30 min de esa
        # doblada de semana. El sábado por sí solo no genera 30 min (aplica_deuda_doblada=False),
        # por eso la rama del solicitante en fecha_pago no los crea; pero la doblada de semana
        # que cedió sí los debe. El receptor ya recibió SUS 30 min en la fecha de cesión (donde
        # queda con AM+PM). La deuda del emisor se asocia al DÍA DE SEMANA de la cesión.
        if (fecha_cesion.weekday() < 5
                and fecha_pago.weekday() == 5
                and DeudaCorporativaService.aplica_deuda_doblada(fecha_cesion)):
            _key_emisor = f"{solicitante.id}:{fecha_cesion.isoformat()}"
            _prev = (getattr(detalle, 'snapshot_turnos_previos', None) or {}).get(_key_emisor, [])
            _jornadas_prev = {(t.get('jornada_nombre') or '').upper() for t in _prev}
            _emisor_tenia_doblada_semana = ('AM' in _jornadas_prev and 'PM' in _jornadas_prev)
            if _emisor_tenia_doblada_semana:
                from solicitudes.models import DeudaCorporativa
                _ya = DeudaCorporativa.objects.filter(
                    explorador=solicitante, fecha_doblada=fecha_cesion
                ).exclude(estado='cancelada').exists()
                if not _ya:
                    DeudaCorporativaService.crear_deuda_corporativa(
                        explorador=solicitante,
                        minutos=30,
                        fecha_generacion=date.today(),
                        fecha_doblada=fecha_cesion,
                        solicitud=solicitud,
                        comentario=(
                            f'Doblada de semana cedida y pagada en sábado ({fecha_pago}): '
                            f'30 min del emisor por la jornada que cedió'
                        ),
                    )
                    logger.info(
                        f"Deuda corporativa (30 min) generada para el EMISOR {solicitante.nombre} "
                        f"en {fecha_cesion} (doblada de semana cedida, pagada en sábado {fecha_pago})."
                    )

        logger.info(
            f"Deudas generadas: Solicitud {solicitud.id} - "
            f"Deuda entre {solicitante.nombre} y {receptor.nombre}, "
            f"Deudas corporativas para ambos"
        )

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
            """
            Turno.objects.filter(explorador=empleado, fecha=fecha, tipo_cambio='DOBLADA').delete()

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
        logger.info(
            f"Doblada revertida: Solicitud {solicitud.id} - "
            f"{solicitante.nombre} <-> {receptor.nombre}"
        )
