"""
CT Permanente Strategy - Implementation for "CT PERMANENTE" solicitud type

This strategy implements the specific logic for "CT PERMANENTE" solicitudes,
which are requests for permanent shift changes.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from core.constants import TipoCambioTurno
from core.services import get_empleado_disponibilidad_service
from core.utils.date_utils import DateUtils
from empleados.models import Empleado
from solicitudes.models import CambioPermanenteDetalle, CambioPermanenteDia, SolicitudCambio

from .base_strategy import SolicitudStrategy

logger = logging.getLogger(__name__)


class CTPermanenteStrategy(SolicitudStrategy):
    """
    Strategy for "CT PERMANENTE" solicitudes.
    
    This implements the specific logic for permanent shift change requests,
    including validation, creation, and application of changes.
    """
    
    def __init__(self):
        super().__init__("CT PERMANENTE")

    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base). Rearma
        dias_seleccionados desde los CambioPermanenteDia del detalle."""
        from ..ct_permanente_helper import rango_detalle

        det = getattr(solicitud, 'cambio_permanente', None)
        if not det:
            return None
        fechas_especificas, dias_semana = [], []
        for d in det.dias.all():
            if d.tipo == 'fecha_especifica' and d.fecha_especifica:
                fechas_especificas.append(d.fecha_especifica.strftime('%Y-%m-%d'))
            elif d.tipo == 'dia_semana' and d.dia_semana is not None:
                dias_semana.append(d.dia_semana)
        # `fecha_fin` es obligatoria desde hace tiempo, pero los registros HEREDADOS pueden no
        # tenerla. Se usa el mismo cierre de rango que la aplicación y el detalle (`rango_detalle`:
        # hasta fin de año) en vez de pasar None: con None, `validar_solicitud` cortaba en
        # "Faltan datos requeridos" y esas solicitudes antiguas quedaban INAPROBABLES para siempre.
        _inicio, fecha_fin = rango_detalle(det)
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_inicio': det.fecha_inicio.strftime('%Y-%m-%d'),
            'fecha_fin': fecha_fin.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'fechas_especificas': fechas_especificas, 'dias_semana': dias_semana},
        }

    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate CT permanente specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance
                - fecha_inicio: Date string
                - fecha_fin: Date string (optional)
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_validator import SolicitudValidator
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha_inicio = datos.get('fecha_inicio')
            fecha_fin = datos.get('fecha_fin')
            dias_seleccionados = datos.get('dias_seleccionados', {})
            comentario = datos.get('comentario') or ''
            
            # Validar datos básicos
            if not all([explorador_solicitante, explorador_receptor, fecha_inicio, fecha_fin]):
                return False, "Faltan datos requeridos para la validación (fecha_fin es obligatoria)"
            
            # Validaciones básicas (empleados activos, no mismo empleado)
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            # Comentario obligatorio
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de cambio de turno permanente')

            es_revalidacion = bool(datos.get('es_revalidacion'))

            # Validaciones específicas de CT PERMANENTE
            SolicitudValidator.validar_fechas_cambio_permanente(fecha_inicio, fecha_fin, es_revalidacion)

            # No DUPLICADOS pendientes (regla de CREACIÓN; se OMITE al re-validar para aprobar).
            # Se miran TODOS los días que el cambio tocaría, no solo `fecha_inicio`.
            if not es_revalidacion:
                from ..ct_permanente_helper import generar_fechas_candidatas_ct_permanente
                SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fechas(
                    explorador_solicitante,
                    generar_fechas_candidatas_ct_permanente(
                        DateUtils.parse_date(fecha_inicio) if isinstance(fecha_inicio, str) else fecha_inicio,
                        DateUtils.parse_date(fecha_fin) if isinstance(fecha_fin, str) else fecha_fin,
                        dias_seleccionados,
                    ),
                )

            # Validar días seleccionados si existen
            if dias_seleccionados:
                SolicitudValidator.validar_dias_seleccionados_permanente(fecha_inicio, fecha_fin, dias_seleccionados)

            # Jornadas contrarias: se valida SIEMPRE, también con `fechas_especificas`.
            # Antes se omitía "confiando" en la evaluación previa del frontend, así que un POST
            # con fechas fabricadas —o una jornada que cambiara entre el envío y la aprobación—
            # no encontraba ningún control en el backend.
            SolicitudValidator.validar_jornada_contraria_rango_permanente(
                explorador_solicitante,
                explorador_receptor,
                fecha_inicio,
                fecha_fin,
                dias_seleccionados if dias_seleccionados else None
            )

            # Al menos un día realmente aplicable (misma evaluación que la vista previa y la
            # aplicación: excluye festivos, descansos, días ya cambiados y días sin intercambio).
            SolicitudValidator.validar_rango_completo_cambio_permanente(
                explorador_solicitante,
                explorador_receptor,
                fecha_inicio,
                fecha_fin,
                dias_seleccionados if dias_seleccionados else None,
                es_revalidacion=es_revalidacion,
            )

            # Validar superposición con otros cambios permanentes (excluyendo la propia solicitud
            # al re-validar para aprobar).
            SolicitudValidator.validar_no_cambio_permanente_superpuesto(
                explorador_solicitante, explorador_receptor, fecha_inicio, fecha_fin,
                excluir_id=datos.get('solicitud_actual_id')
            )
            
            return True, "Solicitud de CT permanente válida"
            
        except Exception as e:
            return False, str(e)
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a CT permanente solicitud.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_inicio = datos.get('fecha_inicio')
            fecha_fin = datos.get('fecha_fin')
            dias_seleccionados = datos.get('dias_seleccionados', {})  # Dict con 'fechas_especificas' y 'dias_semana'
            
            # Convert fecha_inicio to date for the main solicitud
            fecha_inicio_obj = DateUtils.parse_date(fecha_inicio)
            
            # Create the main solicitud
            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_inicio_obj,  # Use fecha_inicio as the main date
                estado='pendiente'
            )
            
            # Create the CT permanente detail
            fecha_fin_obj = None
            if fecha_fin:
                fecha_fin_obj = DateUtils.parse_date(fecha_fin)
            
            detalle = CambioPermanenteDetalle.objects.create(
                solicitud=solicitud,
                fecha_inicio=fecha_inicio_obj,
                fecha_fin=fecha_fin_obj
            )
            
            # Crear registros de días seleccionados si existen
            if dias_seleccionados:
                dias_semana = dias_seleccionados.get('dias_semana', [])
                fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
                
                # Crear registros para días de semana
                for dia_semana in dias_semana:
                    CambioPermanenteDia.objects.create(
                        cambio_permanente=detalle,
                        dia_semana=int(dia_semana),
                        tipo='dia_semana'
                    )
                
                # Crear registros para fechas específicas (compatibilidad parcial)
                for fecha_str in fechas_especificas:
                    try:
                        if isinstance(fecha_str, str):
                            fecha_obj = DateUtils.parse_date(fecha_str)
                        else:
                            fecha_obj = fecha_str
                        
                        CambioPermanenteDia.objects.create(
                            cambio_permanente=detalle,
                            fecha_especifica=fecha_obj,
                            tipo='fecha_especifica'
                        )
                    except (ValueError, TypeError) as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Error procesando fecha específica {fecha_str}: {e}")
                        continue
            
            # Crear notificaciones y enviar emails
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception:
                import logging
                logger = logging.getLogger(__name__)
                logger.exception("Error creando notificaciones para CT PERMANENTE")
            
            return solicitud, "Solicitud de CT permanente creada correctamente"
            
        except Exception as e:
            return None, f"Error creando solicitud de CT permanente: {str(e)}"

    @staticmethod
    def revertir(solicitud: SolicitudCambio) -> None:
        """
        Revierte un CT permanente aprobado (cancelación de 30 min) con BORRADO DIRIGIDO:
        borra solo los turnos `CT PERMANENTE` que esta gestión creó (en las fechas exactas
        guardadas en el snapshot). NO toca cambios posteriores sobre esos días (p. ej. un CT
        sencillo que mutó el turno a 'CT'): como ya no es 'CT PERMANENTE', se respeta.
        El estado previo de esos días suele ser virtual (lista vacía en el snapshot); cuando NO
        lo era (había un turno real, p. ej. del horario importado), el snapshot lo guarda y aquí
        se RESTAURA — pero solo si de verdad borramos nuestro turno de ese día, para no duplicar
        turnos sobre un cambio posterior que ya pisó el día.
        """
        from datetime import date as _date

        from empleados.models import Empleado as EmpleadoModel
        from turnos.models import Jornada as JornadaModel
        from turnos.models import Turno
        from turnos.services.doblada_turno_service import DobladaTurnoService
        snap = getattr(solicitud, 'snapshot_turnos_previos', None) or {}
        meses_afectados = set()
        for key, filas in snap.items():
            try:
                emp_str, fecha_str = key.split(':', 1)
                emp_id = int(emp_str)
                fecha = _date.fromisoformat(fecha_str)
            except (ValueError, TypeError):
                continue
            borrados, _ = Turno.objects.filter(
                explorador_id=emp_id, fecha=fecha, tipo_cambio=TipoCambioTurno.CT_PERMANENTE,
            ).delete()
            meses_afectados.add((emp_id, fecha.month, fecha.year))

            # Solo restauramos si nuestro turno seguía ahí: si un cambio posterior ya pisó el
            # día, ese cambio manda y no debemos añadirle nada encima.
            if not borrados or not filas:
                continue
            empleado = EmpleadoModel.objects.filter(pk=emp_id).first()
            if not empleado:
                continue
            for fila in filas:
                jornada = JornadaModel.objects.filter(nombre__iexact=(fila.get('jornada_nombre') or '')).first()
                if not jornada:
                    logger.warning('CT permanente revert: jornada %r desconocida para %s en %s',
                                   fila.get('jornada_nombre'), emp_id, fecha)
                    continue
                sala_id = fila.get('sala_id')
                if not sala_id:
                    sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                    sala_id = sala.id if sala else None
                if not sala_id:
                    continue
                Turno.objects.create(
                    explorador_id=emp_id, fecha=fecha, jornada=jornada,
                    sala_id=sala_id, tipo_cambio=fila.get('tipo_cambio'),
                )

        from core.services.cache_service import CacheService
        for emp_id, mes, anio in meses_afectados:
            CacheService.invalidar_cache_turnos_empleado(emp_id, mes, anio)

    @staticmethod
    def _jornada_previa_ct(snap: dict, empleado: Empleado, fecha: date):
        """
        Jornada que `empleado` tenía en `fecha` ANTES de que esta gestión la pisara, para poder
        re-materializar el intercambio exactamente como se aplicó.

        Prioriza el SNAPSHOT: si allí quedó registrado un turno real único, esa era su jornada
        efectiva ese día. Es el caso que la jornada base no puede reproducir — un turno del
        horario importado (con `tipo_cambio` NULL, así que `_tipo_cambio_previo` no lo excluye)
        puede diferir de la asignación de `AsignarJornadaExplorador`, y re-derivar desde la base
        habría restaurado un intercambio distinto del original.

        Si el snapshot está vacío (el día estaba en su estado virtual, lo normal) se usa la
        jornada base. Devuelve un objeto Jornada o None.
        """
        from core.utils.jornada_utils import obtener_jornada_base, obtener_jornadas_am_pm

        filas = snap.get(f"{empleado.id}:{fecha.isoformat()}") or []
        nombres = {
            (f.get('jornada_nombre') or '').upper()
            for f in filas
            if (f.get('jornada_nombre') or '').upper() in ('AM', 'PM')
        }
        # Solo sirve una jornada ÚNICA: si el snapshot trae AM+PM, ese día era una doblada y no
        # hay una "jornada previa" que intercambiar; se deja que la comprobación AM/PM del
        # llamador descarte la fecha.
        if len(nombres) > 1:
            return None
        if len(nombres) == 1:
            jornada = obtener_jornadas_am_pm().get(next(iter(nombres)))
            if jornada:
                return jornada
        return obtener_jornada_base(empleado, fecha)

    @staticmethod
    def reaplicar_fechas(solicitud: SolicitudCambio, fechas) -> int:
        """
        Re-materializa un CT PERMANENTE APROBADO sobre `fechas` (patrón #22).

        La reconciliación restaura el snapshot de otra solicitud, y ese `delete()` arrasa el
        día entero: se llevaba por delante los turnos `CT PERMANENTE` que seguían vigentes.

        Solo se re-materializan las fechas que ESTA gestión aplicó — las claves del snapshot
        son exactamente esas (ver `aplicar_cambios`), así que no se re-deriva la elegibilidad
        del estado en vivo (el día recién pisado ya no parecería elegible). Devuelve nº de días.
        """
        from datetime import date as _date

        from turnos.models import Turno
        from turnos.services.doblada_turno_service import DobladaTurnoService

        objetivo = set(fechas)
        snap = getattr(solicitud, 'snapshot_turnos_previos', None) or {}
        aplicadas = set()
        for key in snap:
            try:
                _emp_str, fecha_str = key.split(':', 1)
                aplicadas.add(_date.fromisoformat(fecha_str))
            except (ValueError, TypeError):
                continue

        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor

        dias = 0
        for fecha in sorted(aplicadas & objetivo):
            # Se re-materializa el INTERCAMBIO: cada uno recupera la jornada que el otro tenía
            # ANTES de aplicar esta gestión. Esa jornada previa se lee del propio snapshot cuando
            # allí quedó un turno real (p. ej. el del horario importado, que puede diferir de la
            # asignación base); si el día estaba en su estado virtual, el snapshot va vacío y se
            # cae a la jornada base. No se consulta el estado EN VIVO a propósito: la
            # reconciliación corre con el día a medio reconstruir y el estado del compañero puede
            # ser el que esta misma gestión escribió, lo que daría un intercambio degenerado.
            j_sol = CTPermanenteStrategy._jornada_previa_ct(snap, solicitante, fecha)
            j_rec = CTPermanenteStrategy._jornada_previa_ct(snap, receptor, fecha)
            nombres = {(j_sol.nombre or '').upper() if j_sol else None,
                       (j_rec.nombre or '').upper() if j_rec else None}
            if not j_sol or not j_rec or nombres != {'AM', 'PM'}:
                logger.warning(
                    "CT permanente %s no re-materializado en %s: sin jornadas contrarias (%s/%s).",
                    solicitud.id, fecha,
                    getattr(j_sol, 'nombre', None), getattr(j_rec, 'nombre', None),
                )
                continue
            for empleado, jornada in ((solicitante, j_rec), (receptor, j_sol)):
                sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                Turno.objects.filter(explorador=empleado, fecha=fecha).delete()
                Turno.objects.create(
                    explorador=empleado, fecha=fecha, jornada=jornada,
                    sala=sala, tipo_cambio=TipoCambioTurno.CT_PERMANENTE,
                )
            dias += 1
        return dias

    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Materializa el CT PERMANENTE al aprobarlo: en cada día aplicable, solicitante y receptor
        INTERCAMBIAN su jornada (cada uno recibe la del otro).

        Las fechas se derivan de `evaluar_fechas_ct_permanente` — la MISMA función que usan la
        validación y la vista previa—, así que lo que el usuario vio es exactamente lo que se
        aplica. Si no queda ningún día aplicable se devuelve False: aprobar sin materializar nada
        dejaba solicitudes "aprobadas" fantasma, sin turnos ni snapshot.

        NO toca el estado de la solicitud: de eso se encarga el orquestador
        (`SolicitudAprobacionService._confirmar_aprobacion_y_aplicar`) a través de la máquina de
        estados, dentro de la misma transacción.
        """
        try:
            from core.utils.jornada_utils import obtener_jornadas_am_pm
            from turnos.models import Turno
            from turnos.services.doblada_turno_service import DobladaTurnoService

            from ..ct_permanente_helper import (
                dias_seleccionados_desde_detalle,
                evaluar_fechas_ct_permanente,
                jornadas_intercambiables_ct,
                rango_detalle,
            )

            detalle = solicitud.cambio_permanente
            if not detalle:
                return False, "No se encontró el detalle del cambio permanente"

            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            fecha_inicio, fecha_fin_cambio = rango_detalle(detalle)

            fechas_aplicables, fechas_excluidas = evaluar_fechas_ct_permanente(
                fecha_inicio, fecha_fin_cambio, solicitante, receptor,
                dias_seleccionados_desde_detalle(detalle),
                # Una aprobación tardía no debe reescribir turnos de días ya transcurridos.
                excluir_pasadas=True,
            )

            dias_omitidos = [
                f"{e['fecha'].strftime('%d/%m/%Y')} ({e['razon']})" for e in fechas_excluidas
            ]

            if not fechas_aplicables:
                detalle_omitidos = f" Días descartados: {', '.join(dias_omitidos[:10])}." if dias_omitidos else ""
                return False, (
                    "No queda ningún día válido para aplicar el cambio permanente."
                    + detalle_omitidos
                )

            jornadas = obtener_jornadas_am_pm()
            if not {'AM', 'PM'} <= set(jornadas):
                return False, "No se encontraron las jornadas AM/PM del sistema"

            snapshot_previos = {}
            turnos_creados = []
            dias_procesados = 0

            for fecha_actual in fechas_aplicables:
                par = jornadas_intercambiables_ct(solicitante, receptor, fecha_actual)
                if not par:
                    # Defensivo: `evaluar_fechas_ct_permanente` ya lo garantiza.
                    logger.warning(
                        "CT permanente %s: %s dejó de tener jornadas contrarias al aplicar; se omite.",
                        solicitud.id, fecha_actual,
                    )
                    dias_omitidos.append(f"{fecha_actual.strftime('%d/%m/%Y')} (Sin jornada contraria)")
                    continue

                jornada_solicitante, jornada_receptor = par
                # El INTERCAMBIO: cada uno recibe la jornada del otro.
                asignaciones = (
                    (solicitante, jornadas.get(jornada_receptor)),
                    (receptor, jornadas.get(jornada_solicitante)),
                )
                if any(j is None for _, j in asignaciones):
                    return False, "No se encontraron las jornadas AM/PM del sistema"

                creados_dia = []
                for empleado, jornada_nueva in asignaciones:
                    # La sala se resuelve ANTES de borrar (prioriza la del turno vigente).
                    sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha_actual)
                    previos = list(
                        Turno.objects.filter(explorador=empleado, fecha=fecha_actual)
                        .select_related('jornada')
                        .order_by('jornada_id')
                    )
                    # Snapshot del estado REAL previo (normalmente vacío: el día está en su
                    # estado virtual). Guardarlo permite restaurarlo al cancelar.
                    snapshot_previos[f"{empleado.id}:{fecha_actual.isoformat()}"] = [
                        {'jornada_nombre': t.jornada.nombre.upper(),
                         'sala_id': t.sala_id,
                         'tipo_cambio': t.tipo_cambio}
                        for t in previos if t.jornada
                    ]
                    # delete + create (igual que el CT sencillo): crear sin borrar dejaba dos
                    # turnos el mismo día y "Mis Turnos" leía el día como DOBLADA.
                    Turno.objects.filter(explorador=empleado, fecha=fecha_actual).delete()
                    creados_dia.append(Turno.objects.create(
                        explorador=empleado,
                        fecha=fecha_actual,
                        jornada=jornada_nueva,
                        sala=sala,
                        tipo_cambio=TipoCambioTurno.CT_PERMANENTE,
                    ))

                turnos_creados.append(tuple(creados_dia))
                dias_procesados += 1

            if not dias_procesados:
                return False, "No se pudo aplicar el cambio permanente en ningún día del rango"

            primer_turno_solicitante, primer_turno_receptor = turnos_creados[0]
            solicitud.turno_origen = primer_turno_solicitante
            solicitud.turno_destino = primer_turno_receptor
            solicitud.snapshot_turnos_previos = snapshot_previos
            solicitud.save(update_fields=['turno_origen', 'turno_destino', 'snapshot_turnos_previos'])

            # Estado RESULTANTE: lo que este cambio permanente deja en esas fechas. Al cancelar
            # se compara contra los turnos actuales para no pisar un cambio ajeno posterior.
            from ..doblada_snapshot_service import DobladaSnapshotService
            DobladaSnapshotService.capturar_snapshot_resultante(solicitud, snapshot_previos)

            # Invalidar caché de todos los meses realmente afectados.
            from core.services.cache_service import CacheService
            meses_afectados = {(f.year, f.month) for f in fechas_aplicables}
            for anio, mes in sorted(meses_afectados):
                CacheService.invalidar_cache_turnos_empleado(solicitante.id, mes, anio)
                CacheService.invalidar_cache_turnos_empleado(receptor.id, mes, anio)
                logger.info(
                    "CT PERMANENTE: caché invalidado para solicitante (ID: %s) y receptor (ID: %s) en %s/%s",
                    solicitante.id, receptor.id, mes, anio,
                )

            mensaje = f"Cambio permanente aplicado para {dias_procesados} días"
            if dias_omitidos:
                mensaje += f". Días omitidos: {', '.join(dias_omitidos)}"

            return True, mensaje

        except Exception as e:
            logger.exception("Error aplicando cambio permanente para solicitud %s", getattr(solicitud, 'id', '?'))
            return False, f"Error aplicando cambio permanente: {str(e)}"

    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for CT permanente with 'Best Match' logic.
        
        Args:
            fecha: Date string in YYYY-MM-DD format (start date)
            usuario_actual: Current user's empleado instance
            **kwargs:
                - fecha_fin: Date string (optional)
                - dias_seleccionados: Dict with 'dias_semana' and 'fechas_especificas'
            
        Returns:
            List of available empleados with compatibility metadata
        """
        try:
            fecha_inicio_str = fecha
            fecha_fin_str = kwargs.get('fecha_fin')
            dias_seleccionados = kwargs.get('dias_seleccionados', {})
            
            # Si no hay rango o días seleccionados, usar comportamiento por defecto (solo fecha inicio)
            if not fecha_fin_str:
                return super().get_empleados_disponibles(fecha, usuario_actual)
            
            # Convertir fechas
            fecha_inicio = DateUtils.parse_date(fecha_inicio_str)
            fecha_fin = DateUtils.parse_date(fecha_fin_str)
            
            # 1. Generar todas las fechas válidas del rango
            fechas_a_evaluar = self._generar_fechas_validas_params(
                fecha_inicio, 
                fecha_fin, 
                dias_seleccionados
            )
            
            if not fechas_a_evaluar:
                return []
            
            # 2. Candidatos base: TODOS los activos no administradores.
            #
            # NO se le pasa `fecha_inicio`: en este modo el servicio IGNORA la fecha (ver su
            # docstring), así que pasársela sugería un filtro de disponibilidad por día que no
            # existe. La disponibilidad REAL se evalúa más abajo, fecha a fecha, con
            # `razones_exclusion_ct_permanente`.
            #
            # El `usuario_actual` sí se pasa: el servicio acepta un Empleado y lo excluye él mismo
            # (antes se pasaba None "porque espera un User", pero eso dejó de ser cierto).
            servicio_disp = get_empleado_disponibilidad_service()
            candidatos_base = servicio_disp.get_empleados_disponibles(None, usuario_actual)
            
            # Asegurar que el usuario actual no esté en la lista
            # Convertir a lista si es QuerySet para manejar ambos casos de forma consistente
            import logging
            logger = logging.getLogger(__name__)
            
            # Contar antes de filtrar (evaluar QuerySet si es necesario)
            total_antes = candidatos_base.count() if hasattr(candidatos_base, 'count') else len(candidatos_base) if hasattr(candidatos_base, '__len__') else 0
            logger.debug(f"Filtrando usuario actual (ID: {usuario_actual.id}, Nombre: {usuario_actual.nombre}) de candidatos. Total antes: {total_antes}")
            
            # Filtrar el usuario actual
            if hasattr(candidatos_base, 'exclude'):
                # Es un QuerySet, excluir y convertir a lista
                candidatos_base = list(candidatos_base.exclude(id=usuario_actual.id))
            else:
                # Es una lista, filtrar manualmente
                candidatos_base = [c for c in candidatos_base if hasattr(c, 'id') and c.id != usuario_actual.id]
            
            # Verificar que el usuario actual no esté en la lista
            ids_candidatos = [c.id for c in candidatos_base if hasattr(c, 'id')]
            if usuario_actual.id in ids_candidatos:
                logger.warning(f"ERROR: Usuario actual (ID: {usuario_actual.id}) aún está en la lista de candidatos después del filtro!")
                # Filtrar nuevamente de forma más estricta
                candidatos_base = [c for c in candidatos_base if hasattr(c, 'id') and c.id != usuario_actual.id]
            
            logger.debug(f"Total candidatos después de filtrar: {len(candidatos_base)}. IDs: {ids_candidatos}")
            
            # Mapa de compatibilidad: {empleado_id: {'compatibles': [], 'incompatibles': [], 'empleado': obj}}
            mapa_compatibilidad = {}
            for cand in candidatos_base:
                mapa_compatibilidad[cand.id] = {
                    'empleado': cand,
                    'dias_compatibles': [],
                    'dias_incompatibles': []
                }
            
            # 3. Evaluar día a día con la MISMA definición de "día aplicable" que usan la
            # previsualización y la aplicación (`razones_exclusion_ct_permanente`), para que el
            # porcentaje signifique de verdad "días que se van a aplicar con este compañero".
            from ..ct_permanente_helper import (
                estado_ct,
                precargar_ct_permanente,
                razones_exclusion_ct_permanente,
            )

            # PRECARGA EN LOTE de la matriz empleado×día. Esto es lo que hace viable el cálculo:
            # antes cada celda resolvía su estado por separado (~13 consultas y ~17 ms), de modo
            # que un rango de 90 días con una decena de candidatos costaba ~13.000 consultas y
            # ~40 s, creciendo linealmente con la plantilla. Ahora todo el estado se trae de una
            # vez y el doble bucle de abajo no toca la base de datos.
            with precargar_ct_permanente(
                [usuario_actual, *candidatos_base],
                min(fechas_a_evaluar), max(fechas_a_evaluar),
            ):
                # Días descartados por el LADO del solicitante (festivo, mantenimiento, temporada,
                # su descanso, su día libre, un cambio previo suyo). No dependen del candidato, así
                # que se calculan una sola vez y además fijan el denominador honesto del porcentaje:
                # antes se dividía entre los días de calendario, inflando la compatibilidad.
                fechas_evaluables = [
                    f for f in fechas_a_evaluar if not razones_exclusion_ct_permanente(f, usuario_actual)
                ]
                if not fechas_evaluables:
                    logger.debug("CT PERMANENTE: el solicitante no tiene ningún día aplicable en el rango")
                    return []

                logger.debug("Evaluación día a día para %s fechas aplicables del solicitante", len(fechas_evaluables))
                for fecha_eval in fechas_evaluables:
                    # La jornada del SOLICITANTE ese día no depende del candidato: se resuelve UNA
                    # vez por fecha. Antes se llamaba a `jornadas_intercambiables_ct(usuario_actual,
                    # ...)` dentro del bucle de candidatos, que recalculaba `estado_dia` del
                    # solicitante tantas veces como candidatos hubiera. El resultado es idéntico:
                    # contraria ⇔ ambas son AM/PM y distintas.
                    j_sol = estado_ct(usuario_actual, fecha_eval).get('jornada')
                    j_sol = j_sol if j_sol in ('AM', 'PM') else None
                    fecha_fmt = fecha_eval.strftime('%Y-%m-%d')
                    for cand_id, info in mapa_compatibilidad.items():
                        candidato = info['empleado']
                        # El candidato debe estar disponible ese día Y tener jornada contraria.
                        # `razones_exclusion_ct_permanente` ya resuelve el estado del candidato,
                        # así que la jornada se lee de ese mismo estado en vez de volver a
                        # derivarlo con `_jornada_efectiva_ct` (era un 40 % de recálculo puro).
                        es_compatible = False
                        if j_sol and not razones_exclusion_ct_permanente(fecha_eval, candidato):
                            j_cand = estado_ct(candidato, fecha_eval).get('jornada')
                            es_compatible = j_cand in ('AM', 'PM') and j_cand != j_sol
                        if es_compatible:
                            info['dias_compatibles'].append(fecha_fmt)
                        else:
                            info['dias_incompatibles'].append(fecha_fmt)

            # 4. Construir lista de resultados con metadatos
            resultados = []
            total_dias = len(fechas_evaluables)

            for info in mapa_compatibilidad.values():
                empleado = info['empleado']
                compatibles_count = len(info['dias_compatibles'])

                # Solo incluir si tiene al menos un día compatible
                if compatibles_count > 0:
                    # Inyectar metadatos en el objeto empleado (temporalmente para serialización)
                    empleado.compatibilidad_percent = int((compatibles_count / total_dias) * 100)
                    empleado.dias_compatibles = info['dias_compatibles']
                    empleado.dias_incompatibles = info['dias_incompatibles']
                    empleado.total_dias_rango = total_dias
                    resultados.append(empleado)

            # 5. Ordenar por porcentaje de compatibilidad descendente
            resultados.sort(key=lambda x: x.compatibilidad_percent, reverse=True)

            logger.debug("Total resultados finales: %s empleados con compatibilidad > 0%%", len(resultados))

            return resultados
            
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error en get_empleados_disponibles CT PERMANENTE (Rango)")
            return []

    def _generar_fechas_validas_params(self, fecha_inicio: date, fecha_fin: date, dias_seleccionados: dict) -> List[date]:
        """
        Fechas de calendario (lunes-viernes) que abarca el cambio, sin filtrar por estado del día.

        Delega en el helper: antes esta lógica estaba duplicada en cinco sitios y las copias
        habían divergido. Para el conjunto realmente aplicable (que además excluye festivos,
        descansos, días ya cambiados y días sin jornada contraria) usar
        `evaluar_fechas_ct_permanente`.
        """
        from ..ct_permanente_helper import generar_fechas_candidatas_ct_permanente
        return generar_fechas_candidatas_ct_permanente(fecha_inicio, fecha_fin, dias_seleccionados)

    def detalle(self, solicitud, datos):
        """
        Detalle propio de CT PERMANENTE para la pantalla de consulta.

        Movido desde `views/detalle.py` en la Fase 2 (cerrar el OCP): la vista
        elegía con una cadena `if tipo_nombre == ...`, así que cada tipo nuevo
        obligaba a editarla. El cuerpo se trasladó SIN cambios de lógica; solo
        los imports relativos pasaron a absolutos al cambiar de paquete.
        """
        try:
            detalle = solicitud.cambio_permanente
            if detalle:
                datos['fechas']['inicio'] = detalle.fecha_inicio.strftime('%d/%m/%Y')
                datos['fechas']['fin'] = detalle.fecha_fin.strftime('%d/%m/%Y') if detalle.fecha_fin else 'Sin fecha de fin'
                
                # Obtener días de semana seleccionados
                dias_seleccionados = detalle.dias.filter(tipo='dia_semana')
                dias_semana_nombres = []
                for dia in dias_seleccionados:
                    if dia.dia_semana is not None:
                        dias_semana_nombres.append(dia.get_dia_semana_display())
                
                if dias_semana_nombres:
                    datos['informacion_adicional']['dias_semana_seleccionados'] = ', '.join(dias_semana_nombres)
                else:
                    datos['informacion_adicional']['dias_semana_seleccionados'] = 'Todos los días hábiles'
                
                # Calcular fechas aplicables y excluidas
                from solicitudes.services.ct_permanente_helper import (
                    calcular_fechas_aplicables_y_excluidas_ct_permanente,
                )
                fechas_aplicables, fechas_excluidas = calcular_fechas_aplicables_y_excluidas_ct_permanente(
                    detalle,
                    solicitud.explorador_solicitante,
                    solicitud.explorador_receptor
                )
                
                datos['fechas']['aplicables'] = [fecha.strftime('%d/%m/%Y') for fecha in fechas_aplicables]
                datos['fechas']['total_dias'] = len(fechas_aplicables)
                
                # Agregar fechas excluidas con sus razones
                datos['fechas']['excluidas'] = [
                    {
                        'fecha': fecha_info['fecha'].strftime('%d/%m/%Y'),
                        'razon': fecha_info['razon']
                    }
                    for fecha_info in fechas_excluidas
                ]

                # Resumen informativo del rango (UX)
                try:
                    fi = detalle.fecha_inicio
                    ff = detalle.fecha_fin or DateUtils.parse_date(f"{fi.year}-12-31")
                    total_dias_rango = (ff - fi).days + 1
                    fines_semana = 0
                    cur = fi
                    while cur <= ff:
                        if cur.weekday() in (5, 6):
                            fines_semana += 1
                        # Era `timezone.timedelta`, que funciona solo porque
                        # django.utils.timezone reexporta timedelta por dentro. Al
                        # mover el código aquí, ruff lo detectó como nombre indefinido.
                        cur = cur + timedelta(days=1)
                    datos['fechas']['resumen'] = {
                        'total_dias_rango': total_dias_rango,
                        'fines_de_semana_en_rango': fines_semana,
                        'prioridad': 'Mantenimiento > Festivo > Temporada > Descanso Solicitante > Descanso Receptor > Fines de semana',
                    }
                except Exception:
                    datos['fechas']['resumen'] = None
                
                datos['informacion_adicional']['nota'] = 'Se excluyen domingos, festivos, días de mantenimiento y días de descanso de los exploradores.'
        except Exception as e:
            logger.error(f"Error obteniendo detalles de CT PERMANENTE: {e}")
            datos['fechas']['error'] = 'No se pudieron obtener los detalles del cambio permanente'

    def validar_campos_requeridos(self, post):
        """Campos obligatorios de CT PERMANENTE (movido del parser en la Fase 2)."""
        if not post.get('empleado_receptor'):
            return False, 'Debe seleccionar un compañero para el intercambio'
        if not post.get('fecha_inicio'):
            return False, 'La fecha de inicio es requerida'
        if not post.get('fecha_fin'):
            return False, 'La fecha de fin es requerida'
        return True, ''

    def parsear_datos(self, post, solicitante, receptor):
        """
        Traduce el POST de CT PERMANENTE (movido del parser en la Fase 2).
        """
        fecha_inicio = post.get('fecha_inicio')
        try:
            dias_seleccionados = json.loads(post.get('dias_seleccionados', '{}') or '{}')
        except (json.JSONDecodeError, TypeError):
            dias_seleccionados = {}
        return {
            'explorador_solicitante': solicitante,
            'explorador_receptor': receptor,
            'comentario': post.get('comentarios', ''),
            'fecha_cambio_turno': fecha_inicio,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': post.get('fecha_fin'),
            'dias_seleccionados': dias_seleccionados,
        }

    def reaplicar(self, solicitud, fechas):
        n = CTPermanenteStrategy.reaplicar_fechas(solicitud, fechas)
        if n:
            logger.info(
                "Reconciliacion post-revert: re-materializado CT PERMANENTE %s en %d dia(s).",
                solicitud.id, n,
            )

    def revertir_cambios(self, solicitud):
        detalle = getattr(solicitud, 'cambio_permanente', None)
        if not detalle:
            return
        CTPermanenteStrategy.revertir(solicitud)
        self._invalidar_rango(solicitud, detalle.fecha_inicio, detalle.fecha_fin)

    excluye_fin_de_semana = True

    def fecha_valida(self, analisis):
        """Igual de estricto que el cambio de turno sencillo: nada se perdona."""
        return not (analisis.get('razones_exclusion') or [])
