"""
Doblada Strategy - Implementation for "DOBLADA" solicitud type

This strategy implements the specific logic for "DOBLADA" solicitudes,
which are requests where one explorer covers another's shift (cesión),
creating a debt that must be paid back later.
"""

import logging
import json
from typing import Dict, Any, Tuple, Optional
from django.core.exceptions import ValidationError
from django.db import transaction
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from ..solicitud_validator import SolicitudValidator
from turnos.services.jornada_service import JornadaService
from core.services import get_empleado_disponibilidad_service, get_turno_service
from core.utils.date_utils import DateUtils
from django.utils import timezone

logger = logging.getLogger(__name__)


class DobladaStrategy(SolicitudStrategy):
    """
    Strategy for "DOBLADA" solicitudes.
    
    This implements the specific logic for double shift requests,
    including validation, creation, and application of changes.
    
    IMPORTANT: When a doblada request is approved by BOTH receptor AND supervisor,
    BOTH dobladas (receptor's and deudor's) are applied IMMEDIATELY.
    There are no "pending dobladas".
    """
    
    def __init__(self):
        super().__init__("DOBLADA")

    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base). Todos los campos
        viven en DobladaDetalle."""
        det = getattr(solicitud, 'doblada', None)
        if not det:
            return None
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_cambio_turno': solicitud.fecha_cambio_turno,
            'fecha_pago': det.fecha_pago,
            'jornada_cedida': det.jornada_cedida,
            'jornada_pago_sabado': det.jornada_pago_sabado,
            'jornada_cubre_en_pago': det.jornada_cubre_en_pago,
            'fecha_pago_semana': det.fecha_pago_semana,
            'tipo_cesion': det.tipo_cesion,
            # INTERCAMBIO: sin este flag, la re-validación al aprobar corría las reglas de cesión
            # normal (jornadas contrarias, etc.) en vez de la rama de intercambio → falso rechazo.
            'es_intercambio': bool(getattr(det, 'es_intercambio', False)),
            'fecha_creacion_solicitud': solicitud.fecha_solicitud.date() if solicitud.fecha_solicitud else None,
        }

    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate doblada specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance (the one who covers)
                - fecha_cambio_turno: Date string (fecha de cesión)
                - fecha_pago: Date string (obligatory)
                - jornada_cedida: 'AM' or 'PM' (optional, if solicitante is in doblada)
                - tipo_cesion: 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm'
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            from ..solicitud_validator import SolicitudValidator
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha_cesion = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')
            jornada_cedida = datos.get('jornada_cedida')
            jornada_pago_sabado = datos.get('jornada_pago_sabado')
            # Día de semana para devolver la jornada cuando se paga el sábado completo (AMBAS).
            # Debe extraerse aquí: se usa más abajo al validar el caso AMBAS (antes solo se leía
            # en crear_solicitud, lo que provocaba un NameError al validar un pago AMBAS).
            fecha_pago_semana = datos.get('fecha_pago_semana')
            jornada_cubre_en_pago = (datos.get('jornada_cubre_en_pago') or '').strip().upper()
            tipo_cesion = datos.get('tipo_cesion', 'cesion_completa')
            fecha_creacion_solicitud = datos.get('fecha_creacion_solicitud')
            comentario = datos.get('comentario') or ''
            # Al RE-VALIDAR para aprobar, la propia solicitud debe excluirse de todo chequeo de
            # "día ya comprometido"; si no, se auto-detecta y se rechaza a sí misma.
            _excluir_id = datos.get('solicitud_actual_id')

            # Validaciones básicas de campos requeridos
            if not explorador_solicitante:
                return False, "Explorador solicitante es requerido"
            
            if not explorador_receptor:
                return False, "Explorador receptor es requerido"
            
            if not fecha_cesion:
                return False, "Fecha de cesión es requerida"
            
            if not fecha_pago:
                return False, "Fecha de pago es obligatoria. No existen dobladas abiertas."
            
            # Comentario obligatorio
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de doblada')

            # Fechas MALFORMADAS = entrada inválida del cliente, no un fallo del sistema.
            # `DateUtils.parse_date` lanza ValueError con basura ('abc', '2026-13-45'…), que sin
            # esta guarda subiría hasta el manejador genérico y saldría como 500. No se llega por
            # el formulario (usa datepicker), pero sí manipulando la petición. Se responde con un
            # mensaje de negocio claro y un 400.
            try:
                fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)
                DateUtils.parse_date(fecha_pago)
            except (ValueError, TypeError):
                return False, "Las fechas enviadas no son válidas. Usa el calendario del formulario."

            # La cesión tiene que ser un día FUTURO: ni pasado ni HOY. Ceder el día en curso no da
            # margen para nada — el compañero puede haber trabajado ya su jornada, y encima la
            # solicitud aún tiene que pasar por su aprobación y la del supervisor.
            # `es_revalidacion` sí admite hoy: una solicitud creada ayer para hoy se aprueba hoy, y
            # sin la excepción quedaría atrapada sin poder aprobarse ni rechazarse.
            # Mismo criterio (y misma forma) que cambio de descanso y D FDS; aquí la comparación era
            # solo `< hoy`, así que el día en curso se colaba: pasó de verdad con la solicitud #561.
            # Va antes del corte del intercambio, así que también rige para el swap de dobladas.
            fecha_actual = timezone.localdate()
            _es_reval = bool(datos.get('es_revalidacion'))
            if fecha_cesion_obj < fecha_actual:
                return False, f"La fecha de cesión ({fecha_cesion_obj.strftime('%d/%m/%Y')}) no puede ser en el pasado."
            if fecha_cesion_obj == fecha_actual and not _es_reval:
                return False, (
                    f"La fecha de cesión ({fecha_cesion_obj.strftime('%d/%m/%Y')}) no puede ser hoy: "
                    "ese día ya está en curso. Elige un día posterior para que tu compañero pueda "
                    "organizarse y la solicitud alcance a aprobarse."
                )
            
            # Validar empleados activos
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            
            # Validar que no sea el mismo empleado
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)

            # ===========================
            # REGLAS COMUNES A TODA DOBLADA (cesión/pago E intercambio)
            # ===========================
            # Van ANTES del corte del intercambio: son reglas del TIPO de solicitud (cuándo se
            # puede doblar), no del mecanismo de pago, así que deben regir también el swap. Estaban
            # más abajo y el `return` del intercambio las evadía (así se coló un sábado↔sábado).

            # Validar acuerdo previo obligatorio (la fecha de pago / día B debe ser posterior a la
            # creación de la solicitud).
            SolicitudValidator.validar_acuerdo_previo_obligatorio(
                fecha_cesion,
                fecha_pago,
                fecha_creacion_solicitud
            )

            # Caso A: fecha_pago debe estar en el mismo mes que fecha_cesion
            SolicitudValidator.validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion)

            # No hay doblada en domingo ni en día de mantenimiento (festivos de semana y temporada
            # sí se permiten), en ninguna de las dos fechas.
            SolicitudValidator.validar_dias_especiales_doblada(fecha_cesion)
            SolicitudValidator.validar_dias_especiales_doblada(fecha_pago)

            fecha_pago_obj = DateUtils.parse_date(fecha_pago)

            # Sábado por sábado se gestiona en Doblada de Fin de Semana (D FDS), no en doblada
            # normal. Se permite el sábado en UN solo lado (sábado ↔ día de semana), pero no en
            # ambos. Es una regla del TIPO de solicitud, así que rige también el intercambio.
            if fecha_cesion_obj.weekday() == 5 and fecha_pago_obj.weekday() == 5:
                return False, ("No puedes hacer una doblada de sábado por sábado. "
                               "Para intercambiar sábados usa una Doblada de Fin de Semana (D FDS).")

            # Un FESTIVO solo se cruza con otro FESTIVO del mismo mes. También es regla del tipo:
            # en un festivo el grupo que rota trabaja AM+PM, así que cuenta como DOBLADA y encajaría
            # con cualquier otra (una cobertura, un día de temporada…) si no se restringiera.
            es_cesion_festivo = SolicitudValidator.es_festivo_semana(fecha_cesion_obj)
            es_pago_festivo = SolicitudValidator.es_festivo_semana(fecha_pago_obj)
            if es_cesion_festivo or es_pago_festivo:
                # Lanza ValidationError si alguna fecha no es festivo o si son de distinto mes.
                SolicitudValidator.validar_festivos_mismo_mes(fecha_cesion_obj, fecha_pago_obj)

            # Casos C/D: sin solicitud pendiente en fecha_cesion (reglas de CREACIÓN; se OMITEN
            # al re-validar para aprobar, donde la solicitud ya existe).
            if not datos.get('es_revalidacion'):
                SolicitudValidator.validar_receptor_sin_solicitud_pendiente_en_fecha(
                    explorador_receptor, fecha_cesion
                )
                SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fecha(
                    explorador_solicitante, fecha_cesion
                )

            # ===========================
            # INTERCAMBIO DE DOBLADAS (swap de días doblados; sin cesión/pago normales ni deuda)
            # ===========================
            # Requiere que AMBOS tengan DOBLADA (AM+PM) en su día: solicitante en el día A
            # (fecha de cesión) y receptor en el día B (fecha de pago), con A != B.
            if datos.get('es_intercambio'):
                return DobladaStrategy._validar_intercambio(
                    explorador_solicitante, explorador_receptor, fecha_cesion_obj, fecha_pago,
                    fecha_actual, es_revalidacion=_es_reval)

            # Caso 1.2: ambos descansando en fecha de pago → rechazar
            SolicitudValidator.validar_ambos_descansando_fecha_pago(
                explorador_solicitante, explorador_receptor, fecha_pago
            )
            # Casos 1.5/1.8: receptor sin jornada en fecha de pago → rechazar
            SolicitudValidator.validar_receptor_tiene_jornada_en_fecha_pago(explorador_receptor, fecha_pago)

            # Caso F: receptor no descansa por doblada en fecha_pago
            SolicitudValidator.validar_receptor_no_descansa_por_doblada_en_pago(
                explorador_receptor, fecha_pago
            )

            # Validar que fecha_pago no sea el mismo día que fecha_cesion
            SolicitudValidator.validar_fecha_pago_diferente_cesion(fecha_cesion, fecha_pago)

            # L2 (fuente de verdad): el día no puede estar YA comprometido en otra solicitud
            # APROBADA (cambio descanso / d_fds / doblada / doblada permanente). Evita el
            # doble-compromiso del mismo día. (DOBLADA sí permite temporada/festivo, por eso
            # no se usa estado_dia completo, solo la capa de solicitudes.)
            from turnos.services.turno_service import TurnoService as _TSv
            _fc_obj = DateUtils.parse_date(fecha_cesion)
            _fp_obj = DateUtils.parse_date(fecha_pago)
            _comp_ces = _TSv.dia_comprometido_por_solicitud(
                explorador_solicitante, _fc_obj, excluir_id=_excluir_id)
            if _comp_ces:
                return False, (
                    f"Ya tienes el {_fc_obj.strftime('%d/%m/%Y')} comprometido en otra "
                    f"solicitud aprobada ({_comp_ces['motivo']}); no puedes cederlo de nuevo."
                )
            # NO se bloquea ceder un día que se TRABAJA por un favor (ni la jornada que te cedieron
            # ni la que estás pagando). Antes sí, con el argumento de que el acreedor se quedaba sin
            # cobertura — y eso no ocurre nunca: quien recibe la jornada la cubre, así que el turno
            # sigue lleno. La contabilidad también cierra:
            #
            #  - Jornada RECIBIDA: es tuya desde que se aprobó el favor. La cedes, el nuevo receptor
            #    la cubre, y quien te la cedió te sigue debiendo su pago (intacto).
            #  - Jornada de PAGO: al cederla, el nuevo receptor cubre al acreedor y tu deuda con él
            #    queda saldada, pero nace una deuda del MISMO tamaño con el nuevo receptor. No te
            #    libras de trabajar esa media jornada: solo cambia a quién se la debes.
            #
            # Los 30 min corporativos siguen a quien REALMENTE dobla: se crean sobre el estado real
            # de los turnos y se cancelan a quien deja de doblar (ver DobladaDeudaService y
            # DeudaCorporativaService.sincronizar_deuda_corporativa).
            #
            # Los compromisos que sí bloquean son los DESCANSOS (arriba, `dia_comprometido_por_
            # solicitud`): un día que ya cediste no lo puedes ceder dos veces.
            _comp_pago = _TSv.dia_comprometido_por_solicitud(
                explorador_receptor, _fp_obj, excluir_id=_excluir_id)
            if _comp_pago:
                # EXCEPCIÓN (sábado, dos mitades al MISMO compañero): si el compromiso del compañero
                # viene de OTRA doblada TUYA que le pagas ESE MISMO sábado con la mitad CONTRARIA,
                # no está "no disponible" — lo estás relevando tú de la otra media jornada. En ese
                # caso se permite: tú terminas doblado (AM+PM) y él descansa el día completo.
                _es_complemento_sabado = False
                if _fp_obj.weekday() == 5:
                    _jps_nueva = str(jornada_pago_sabado or '').upper()
                    if _jps_nueva in ('AM', 'PM'):
                        _contraria_nueva = 'PM' if _jps_nueva == 'AM' else 'AM'
                        _q_comp = SolicitudCambio.objects.filter(
                            explorador_solicitante=explorador_solicitante,
                            explorador_receptor=explorador_receptor,
                            tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                            estado='aprobada',
                            doblada__fecha_pago=_fp_obj,
                            doblada__jornada_pago_sabado__iexact=_contraria_nueva,
                        )
                        if _excluir_id:
                            _q_comp = _q_comp.exclude(id=_excluir_id)
                        _es_complemento_sabado = _q_comp.exists()
                if not _es_complemento_sabado:
                    return False, (
                        f"Tu compañero ya tiene el {_fp_obj.strftime('%d/%m/%Y')} comprometido en "
                        f"otra solicitud aprobada ({_comp_pago['motivo']}); no puede cubrir ese día."
                    )
            # PAGAR en un día en que ESTÁS LIBRE está permitido, sea cual sea el motivo del descanso
            # (temporada, fin de semana, o porque CEDISTE ese día en otra solicitud). Un día libre está
            # disponible para cubrir la jornada que debes: la última jornada aprobada del día es la
            # vigente. No se materializa doblada indebida porque `aplicar_doblada_pago` solo suma la
            # jornada propia del deudor si ESE día trabaja (si está libre, cubre únicamente la del
            # acreedor → queda con UNA jornada), y `validar_coincidencia_jornadas_pago` omite la
            # comparación cuando el deudor descansa. Por eso ya no se bloquea el pago en día cedido.

            # El COMPAÑERO (receptor/acreedor) debe TRABAJAR en la fecha de pago: si ese día DESCANSA
            # por cualquier motivo REAL (temporada, alternancia de fin de semana, u otra solicitud) no
            # tiene una jornada que el deudor pueda cubrir para "devolverle" el día → se rechaza con
            # mensaje CLARO, en vez del confuso "trabajarías dos veces la misma jornada" (que salía al
            # comparar contra su jornada predeterminada ignorando el descanso). Fuente de verdad:
            # estado_dia. El sábado y los festivos de semana tienen reglas propias (alternancia /
            # cobertura del grupo que descansa), por eso se excluyen aquí.
            if _fp_obj.weekday() < 5 and not SolicitudValidator.es_festivo_semana(_fp_obj):
                if not _TSv.estado_dia(explorador_receptor, _fp_obj).get('trabaja'):
                    return False, (
                        f"El compañero receptor descansa el {_fp_obj.strftime('%d/%m/%Y')}: ese día no "
                        f"tiene una jornada que puedas cubrir para pagarle la doblada. Elige otra fecha "
                        f"de pago en la que él trabaje."
                    )

            # (Días especiales, sábado×sábado y festivos-del-mismo-mes: ya validados arriba, en las
            # reglas comunes. Aquí solo quedan las reglas propias de la CESIÓN en festivo.)
            if es_cesion_festivo or es_pago_festivo:
                # En un festivo se trabaja la DOBLADA COMPLETA (AM+PM) y se cede ENTERA: la doblada
                # de festivo es todo-o-nada. No se admiten cesiones parciales (dejarían media jornada
                # colgando en un día que por rotación es doblada o descanso).
                if es_cesion_festivo and tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
                    return False, (
                        f"El {fecha_cesion_obj.strftime('%d/%m/%Y')} es festivo: ese día trabajas la "
                        f"doblada completa (AM + PM) y debes cederla entera. No puedes ceder solo una "
                        f"mitad — elige 'ceder la doblada completa'."
                    )
                # Solo puedes ceder ese festivo si tu grupo REALMENTE dobla ese día (tu jornada base
                # coincide con el grupo que dobla). Si te toca descansar (dobla el grupo contrario) no
                # tienes ninguna jornada que ceder.
                from turnos.services.turno_service import TurnoService as _TSfv
                if es_cesion_festivo and not _TSfv.dobla_en_festivo(explorador_solicitante, fecha_cesion_obj):
                    return False, (
                        f"No doblas el festivo {fecha_cesion_obj.strftime('%d/%m/%Y')}: ese día descansa "
                        f"tu grupo (dobla el grupo contrario), así que no tienes una doblada que ceder. "
                        f"Elige un festivo en el que te corresponda doblar."
                    )

                try:
                    from turnos.services.asignacion_especial_service import AsignacionEspecialService
                    grupo_cesion = AsignacionEspecialService.grupo_trabaja(fecha_cesion_obj)
                    grupo_pago = AsignacionEspecialService.grupo_trabaja(fecha_pago_obj)
                    logger.info(
                        f"DobladaStrategy: Cesión festiva {fecha_cesion_obj} (grupo {grupo_cesion}) "
                        f"<-> Pago festivo {fecha_pago_obj} (grupo {grupo_pago})"
                    )
                except Exception as e:
                    logger.warning(f"Error al obtener rotación de festivos: {str(e)}", exc_info=True)
            
            # ===========================
            # Regla especial: pago en sábado (día de semana ↔ sábado)
            # ===========================
            # (fecha_pago_obj ya se parseó una sola vez en las reglas comunes.)

            # Un sábado se reparte en dos MITADES (AM/PM). Se permite un SEGUNDO pago de doblada en
            # el mismo sábado SOLO si usa la mitad LIBRE: así terminas doblado (AM+PM) y cada mitad
            # paga a una persona distinta (p. ej. cediste AM a X y PM a Y y pagas ambas ese sábado).
            # Se bloquea si la mitad que pides ya está ocupada, si el sábado ya está lleno, o si
            # este pago pide el día completo (AMBAS) con una mitad ya tomada.
            if fecha_pago_obj and fecha_pago_obj.weekday() == 5:
                _otras_pago_sab = SolicitudCambio.objects.filter(
                    explorador_solicitante=explorador_solicitante,
                    tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                    estado='aprobada',
                    doblada__fecha_pago=fecha_pago_obj,
                ).select_related('doblada')
                _sid = _excluir_id
                if _sid:
                    _otras_pago_sab = _otras_pago_sab.exclude(id=_sid)
                _ocupadas = set()
                for _o in _otras_pago_sab:
                    _jps = (getattr(_o.doblada, 'jornada_pago_sabado', '') or '').upper()
                    if _jps in ('AM', 'PM'):
                        _ocupadas.add(_jps)
                    else:
                        # AMBAS, o un pago en sábado sin media jornada explícita: ocupa el día completo.
                        _ocupadas |= {'AM', 'PM'}
                if _ocupadas:
                    _nueva = str(jornada_pago_sabado or '').upper()
                    _libre = {'AM', 'PM'} - _ocupadas
                    _conflicto = (
                        not _libre                     # sábado lleno
                        or _nueva not in ('AM', 'PM')  # este no paga una media jornada concreta (AMBAS/none)
                        or _nueva in _ocupadas          # esa media jornada ya está tomada
                    )
                    if _conflicto:
                        _ocu_txt = '/'.join(sorted(_ocupadas))
                        if _libre and _nueva not in _libre and _nueva != 'AMBAS':
                            _libre_j = next(iter(_libre))
                            return False, (
                                f"Ese sábado ({fecha_pago_obj.strftime('%d/%m/%Y')}) ya pagas la jornada "
                                f"{_ocu_txt} con otra doblada. Solo queda libre la jornada {_libre_j}: "
                                f"elige {_libre_j} para pagar esta doblada, o paga en otro día."
                            )
                        return False, (
                            f"Ese sábado ({fecha_pago_obj.strftime('%d/%m/%Y')}) ya está comprometido como "
                            f"pago de otra doblada tuya (jornada {_ocu_txt}). Un sábado admite un solo pago "
                            f"por cada media jornada; elige otro día de pago."
                        )

            # Pagar en sábado EXIGE elegir la media jornada (AM/PM/AMBAS). Sin ese dato, ni la
            # validación de sábado ni la aplicación entran en su rama de fin de semana: se caía a
            # la lógica de día de semana, que usa la jornada predeterminada e IGNORA la alternancia
            # de fines de semana → turnos incoherentes. El formulario siempre lo envía; esto es el
            # guard de servidor equivalente.
            if fecha_pago_obj.weekday() == 5 and not jornada_pago_sabado:
                return False, (
                    f"Para pagar el sábado {fecha_pago_obj.strftime('%d/%m/%Y')} debes indicar qué "
                    f"jornada cubrirás ese día (AM, PM o ambas)."
                )

            es_pago_sabado = fecha_pago_obj.weekday() == 5 and jornada_pago_sabado

            if es_pago_sabado:
                res = DobladaStrategy._validar_pago_en_sabado(
                    explorador_solicitante, explorador_receptor, fecha_pago_obj,
                    jornada_pago_sabado, jornada_cedida, fecha_cesion, fecha_pago_semana,
                    excluir_id=_excluir_id,
                )
                if res is not None:
                    return res
            # Cobertura explícita AM / PM / AMBAS cuando el receptor tiene doblada en fecha de pago (no aplica a pago sábado especial)
            if jornada_cubre_en_pago and jornada_cubre_en_pago not in ('AM', 'PM', 'AMBAS'):
                return False, "Valor inválido para la jornada que cubrirás en la fecha de pago."
            if fecha_pago_obj.weekday() == 5 and jornada_pago_sabado and jornada_cubre_en_pago:
                return False, "No uses la opción AM/PM/toda la doblada junto con el pago en sábado; elige solo la jornada del sábado."
            # La elección "¿qué cubrirás?" (jornada_cubre_en_pago) aplica siempre que el receptor
            # tenga doblada en la fecha de pago, sin importar el tipo de cesión (parcial o completa).
            if jornada_cubre_en_pago and not (
                fecha_pago_obj.weekday() == 5 and jornada_pago_sabado
            ):
                # Fuente de verdad (estado_dia), NO solo turnos reales: la doblada del receptor
                # puede ser VIRTUAL (temporada, alternancia de fin de semana, festivo) sin filas
                # Turno. Mirar solo turnos reales disparaba un falso "el compañero no tiene doblada"
                # cuando la doblada venía de temporada (mismo criterio que el deudor unas líneas más
                # abajo, que ya usa obtener_jornada_display).
                from turnos.services.turno_service import TurnoService as _TS_rec
                receptor_doblada_pago = (
                    _TS_rec.estado_dia(explorador_receptor, fecha_pago_obj).get('jornada') == 'DOBLADA'
                )
                if jornada_cubre_en_pago and not receptor_doblada_pago:
                    return False, (
                        "La opción de cubrir AM, PM o toda la doblada solo aplica cuando el compañero tiene "
                        "doblada (AM+PM) en la fecha de pago."
                    )

                # El deudor SOLO puede cubrir la jornada CONTRARIA a la que él trabaja ese día.
                # IMPORTANTE: usar la jornada REAL del deudor (incluida la PREDETERMINADA/virtual,
                # sin fila Turno), no solo turnos explícitos. Si ese día el deudor trabaja una jornada:
                #   - No puede cubrir AMBAS (su propia jornada quedaría sin cubrir).
                #   - No puede cubrir la MISMA jornada que ya trabaja (la haría dos veces).
                if receptor_doblada_pago and jornada_cubre_en_pago:
                    jcp_u = str(jornada_cubre_en_pago).strip().upper()
                    from turnos.services.turno_service import TurnoService as _TS_pago
                    jornada_deudor_pago = _TS_pago.obtener_jornada_display(
                        explorador_solicitante, fecha_pago_obj
                    )
                    if jornada_deudor_pago in ('AM', 'PM'):
                        contraria = 'PM' if jornada_deudor_pago == 'AM' else 'AM'
                        if jcp_u == 'AMBAS':
                            return False, (
                                f'Ese día ya trabajas tu jornada {jornada_deudor_pago}. No puedes cubrir la '
                                f'doblada completa del compañero porque tu propia jornada quedaría sin cubrir. '
                                f'Solo puedes cubrir la jornada contraria ({contraria}), o elige otra fecha de pago '
                                f'en la que estés libre.'
                            )
                        if jcp_u == jornada_deudor_pago:
                            return False, json.dumps({
                                'code': 'requiere_cambio_turno_previo',
                                'message': (
                                    f'La jornada que quieres cubrir ({jcp_u}) es la MISMA que ya trabajas ese día: '
                                    f'no puedes hacerla dos veces. Solo puedes cubrir la jornada contraria ({contraria}). '
                                    f'Si necesitas cambiar tu jornada, primero realiza un cambio de turno sencillo.'
                                ),
                                'fecha_pago': str(fecha_pago),
                                'jornada_comun': jcp_u,
                            })

            # Validar jornadas contrarias — se omite para festivos de semana porque en esos días
            # el grupo que descansa (misma jornada base) cubre válidamente al grupo que trabaja.
            if not es_cesion_festivo:
                SolicitudValidator.validar_jornadas_contrarias_doblada(
                    explorador_solicitante,
                    explorador_receptor,
                    fecha_cesion,
                    jornada_cedida
                )
            
            # Validar que receptor no tenga doblada activa en fecha de CESIÓN (evitar triple turno)
            SolicitudValidator.validar_no_triple_turno(explorador_receptor, fecha_cesion)
            # NO validar triple turno del receptor en fecha_pago:
            # en la fecha de pago el receptor PIERDE una jornada (el deudor se la devuelve),
            # no gana una. La protección real la da la validación de jornada_cedida más abajo.
            
            # Validar que deudor no tenga doblada activa en fecha de pago. Mensaje contextual:
            # ya estamos en el formulario de doblada, así que NO decir "usa la Solicitud de Dobladas".
            SolicitudValidator.validar_no_doblada_activa(
                explorador_solicitante, fecha_pago,
                mensaje=(
                    f'No puedes pagar la doblada el {fecha_pago_obj.strftime("%d/%m/%Y")}: ese día ya '
                    f'tienes una jornada doblada (AM + PM), así que no te queda jornada libre para '
                    f'trabajar y devolverla. Elige otra fecha de pago en la que estés libre.'
                )
            )
            
            # Validar coincidencia de jornadas en fecha de pago (caso crítico) para pagos NO festivos.
            # Si el acreedor tiene doblada y el deudor un solo turno, jcp es la media jornada que trabajará el deudor
            # (puede ser la contraria a su turno actual). get_jornada del acreedor puede coincidir con el deudor por
            # .first() y disparar un falso "requiere CT". En ese caso no aplicar coincidencia clásica.
            if not es_pago_festivo:
                omitir_coincidencia_pago = False
                if (
                    tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm')
                    and not (fecha_pago_obj.weekday() == 5 and jornada_pago_sabado)
                    and jornada_cubre_en_pago
                ):
                    jcp_coinc = str(jornada_cubre_en_pago).strip().upper()
                    if jcp_coinc in ('AM', 'PM'):
                        # Fuente de verdad (estado_dia), no turnos reales: la doblada del receptor y
                        # la jornada del deudor pueden ser VIRTUALES (temporada/alternancia/festivo).
                        # Si el receptor dobla y el deudor trabaja UNA jornada contraria a la que va a
                        # cubrir, el pago es limpio → omitir la verificación clásica de coincidencia.
                        from turnos.services.turno_service import TurnoService as _TS_coinc
                        rec_dobla = _TS_coinc.estado_dia(
                            explorador_receptor, fecha_pago_obj).get('jornada') == 'DOBLADA'
                        sol_jorn = _TS_coinc.estado_dia(
                            explorador_solicitante, fecha_pago_obj).get('jornada')
                        if rec_dobla and sol_jorn in ('AM', 'PM') and sol_jorn != jcp_coinc:
                            omitir_coincidencia_pago = True
                if not omitir_coincidencia_pago:
                    coincidencia = SolicitudValidator.validar_coincidencia_jornadas_pago(
                        explorador_solicitante,
                        explorador_receptor,
                        fecha_pago
                    )
                    if coincidencia['requiere_cambio_turno']:
                        return False, json.dumps({
                            'code': 'requiere_cambio_turno_previo',
                            'message': 'No se puede pagar trabajando dos veces la misma jornada. Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago.',
                            'fecha_pago': str(fecha_pago),
                            'jornada_comun': coincidencia['jornada_comun']
                        })
            
            return True, "Solicitud de doblada válida"
            
        except ValidationError as e:
            # ÚNICO caso que se traduce a "(False, mensaje)": una regla de negocio incumplida.
            return False, str(e)
        except Exception:
            # Cualquier otra excepción es un BUG, no una regla de negocio. Antes se devolvía
            # como (False, "Error validando doblada: ..."), con la misma forma que un rechazo
            # legítimo: el explorador leía un traceback y entendía "mi solicitud está mal",
            # la solicitud quedaba bloqueada y nadie se enteraba de que había un fallo.
            # Ahora se propaga para que salga como error del sistema y se pueda corregir.
            logger.exception("Error INESPERADO validando doblada (no es una regla de negocio)")
            raise
    

    @staticmethod
    def _validar_intercambio(explorador_solicitante, explorador_receptor, fecha_cesion_obj, fecha_pago,
                             fecha_actual, es_revalidacion=False) -> Tuple[bool, str]:
        from turnos.services.turno_service import TurnoService as _TSint
        fp_obj = DateUtils.parse_date(fecha_pago)
        if not fp_obj:
            return False, "La fecha del día B (doblada del compañero) no es válida."
        # Igual que el día A: ni pasado ni HOY. El intercambio no pasa por
        # `validar_acuerdo_previo` (que ya exige pago posterior a la creación), así que sin esto el
        # día B podía ser el día en curso.
        if fp_obj < fecha_actual:
            return False, f"El día B ({fp_obj.strftime('%d/%m/%Y')}) no puede ser en el pasado."
        if fp_obj == fecha_actual and not es_revalidacion:
            return False, (
                f"El día B ({fp_obj.strftime('%d/%m/%Y')}) no puede ser hoy: ese día ya está en "
                "curso. Elige un día posterior."
            )
        if fecha_cesion_obj == fp_obj:
            return False, "Para intercambiar dobladas, el día A y el día B deben ser distintos."
        # NOTA: sábado×sábado y "festivo solo contra festivo del mismo mes" NO se repiten aquí.
        # Son reglas del TIPO de solicitud y viven en el bloque de REGLAS COMUNES de
        # `validar_solicitud`, que corre ANTES del corte del intercambio. Estaban duplicadas en
        # este método porque el `return` del intercambio se saltaba el flujo normal, y cada una
        # se añadió después de que se colara una solicitud inválida. Al subirlas, este método
        # queda con lo ÚNICO específico del swap: que ambos tengan doblada y estén libres.
        if _TSint.estado_dia(explorador_solicitante, fecha_cesion_obj).get('jornada') != 'DOBLADA':
            return False, (f"Para intercambiar, debes tener una DOBLADA (AM+PM) el "
                           f"{fecha_cesion_obj.strftime('%d/%m/%Y')}.")
        if _TSint.estado_dia(explorador_receptor, fp_obj).get('jornada') != 'DOBLADA':
            return False, (f"El compañero debe tener una DOBLADA (AM+PM) el "
                           f"{fp_obj.strftime('%d/%m/%Y')} para intercambiar.")
        # El que ASUME la doblada del otro debe estar LIBRE ese día: una doblada es AM+PM
        # (día completo), así que si ya trabaja no puede cubrirla. Simétrico en ambos días.
        if _TSint.estado_dia(explorador_receptor, fecha_cesion_obj).get('trabaja'):
            return False, (f"El compañero no está libre el {fecha_cesion_obj.strftime('%d/%m/%Y')}: "
                           f"ese día ya trabaja y no puede cubrir tu doblada. Elige un compañero que "
                           f"descanse ese día.")
        if _TSint.estado_dia(explorador_solicitante, fp_obj).get('trabaja'):
            return False, (f"No estás libre el {fp_obj.strftime('%d/%m/%Y')} (día de la doblada del "
                           f"compañero): ese día ya trabajas y no puedes cubrirla.")
        if _TSint.dia_comprometido_por_solicitud(explorador_solicitante, fecha_cesion_obj):
            return False, (f"Tu doblada del {fecha_cesion_obj.strftime('%d/%m/%Y')} ya está "
                           f"comprometida en otra solicitud aprobada.")
        if _TSint.dia_comprometido_por_solicitud(explorador_receptor, fp_obj):
            return False, (f"La doblada del compañero del {fp_obj.strftime('%d/%m/%Y')} ya está "
                           f"comprometida en otra solicitud aprobada.")
        return True, "Intercambio de dobladas válido."


    @staticmethod
    def _validar_pago_en_sabado(explorador_solicitante, explorador_receptor, fecha_pago_obj, jornada_pago_sabado, jornada_cedida, fecha_cesion, fecha_pago_semana, excluir_id=None) -> Optional[Tuple[bool, str]]:
        from ..solicitud_validator import SolicitudValidator
        jornada_pago_sabado_upper = str(jornada_pago_sabado).upper()
        if jornada_pago_sabado_upper not in ("AM", "PM", "AMBAS"):
            logger.warning(f"Validación fallida: jornada_pago_sabado inválida: {jornada_pago_sabado}")
            return False, "Para pagar en sábado debes seleccionar una jornada válida (AM, PM o ambas)."

        # Validar que el receptor TRABAJA ese sábado según la alternancia PUBLICADA.
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        jornada_trabaja_sabado = AsignacionEspecialService.grupo_trabaja(fecha_pago_obj)
        if not jornada_trabaja_sabado:
            logger.warning("Sin alternancia publicada para el sábado %s", fecha_pago_obj)
            return False, (
                f"El año {fecha_pago_obj.year} aún no tiene publicada la alternancia de fines de "
                f"semana, así que no se puede saber quién trabaja ese sábado. "
                f"Pídele al supervisor que la publique."
            )

        # Si el receptor tiene un Turno REAL en ese sábado (p. ej. por un cambio de
        # descanso previo que le asignó ese día), ese turno es la fuente de verdad:
        # ya trabaja ahí independientemente de la alternancia.
        from turnos.services.turno_service import TurnoService
        estado_receptor_sab = TurnoService.estado_dia(explorador_receptor, fecha_pago_obj)
        receptor_trabaja_sab_por_turno = (
            estado_receptor_sab.get('trabaja') and
            estado_receptor_sab.get('fuente') == 'turno'
        )

        jornada_receptor_pago = JornadaService.get_jornada_explorador_fecha(
            explorador_receptor.id, fecha_pago_obj.strftime('%Y-%m-%d')
        )
        if not jornada_receptor_pago:
            logger.warning(f"Validación fallida: receptor {explorador_receptor.id} sin jornada para {fecha_pago_obj}")
            return False, "El receptor no tiene jornada asignada para la fecha de pago (sábado)."

        if not receptor_trabaja_sab_por_turno and jornada_receptor_pago.nombre.upper() != jornada_trabaja_sabado:
            logger.warning(
                f"Validación fallida: receptor {explorador_receptor.id} tiene {jornada_receptor_pago.nombre.upper()} "
                f"pero debe ser {jornada_trabaja_sabado} para sábado {fecha_pago_obj}"
            )
            return False, (
                f"Para pagar el sábado {fecha_pago_obj.strftime('%d/%m/%Y')}, el receptor debe ser del grupo "
                f"que trabaja ese sábado ({jornada_trabaja_sabado}). El receptor tiene {jornada_receptor_pago.nombre.upper()}."
            )

        # ===========================
        # Validar que sábado de pago corresponda a jornada del receptor (quien hizo doble turno)
        # ===========================
        # Regla de negocio:
        # - Si cedes jornada AM → receptor es PM → sábado de pago debe ser para PM
        # - Si cedes jornada PM → receptor es AM → sábado de pago debe ser para AM
        # Excepción: si el receptor tiene un Turno real en ese sábado (p. ej. swapeado
        # por un cambio de descanso previo), esa asignación real supera a la alternancia.
        jornada_a_ceder = None
        if jornada_cedida:
            jornada_a_ceder = jornada_cedida.upper()
        else:
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                explorador_solicitante.id, fecha_cesion
            )
            if jornada_solicitante:
                jornada_a_ceder = jornada_solicitante.nombre.upper()

        if jornada_a_ceder and not receptor_trabaja_sab_por_turno:
            jornada_receptor_cesion = JornadaService.get_jornada_explorador_fecha(
                explorador_receptor.id, fecha_cesion
            )
            if not jornada_receptor_cesion:
                logger.warning(
                    f"Validación fallida: receptor {explorador_receptor.id} sin jornada para {fecha_cesion}"
                )
                return False, "El receptor no tiene jornada asignada para la fecha de cesión."

            jornada_receptor_nombre = jornada_receptor_cesion.nombre.upper()

            if jornada_receptor_nombre != jornada_trabaja_sabado:
                logger.warning(
                    f"Validación fallida: receptor {explorador_receptor.id} tiene jornada {jornada_receptor_nombre} "
                    f"pero el sábado {fecha_pago_obj} es para {jornada_trabaja_sabado}. "
                    f"El sábado debe corresponder a la jornada del receptor (quien hizo el doble turno)."
                )
                return False, (
                    f"No se puede realizar esta solicitud. El sábado {fecha_pago_obj.strftime('%d/%m/%Y')} "
                    f"corresponde al turno {jornada_trabaja_sabado}, pero el compañero que cubrirá tu jornada "
                    f"({jornada_a_ceder}) tiene jornada {jornada_receptor_nombre}. "
                    f"El sábado de pago siempre debe coincidir con el turno de la persona que realizó el doble turno. "
                    f"Por favor, selecciona otro sábado que corresponda al turno {jornada_receptor_nombre}."
                )

        # ===========================
        # Pago en sábado AMBAS: validar el día de devolución en semana
        # ===========================
        # Al cubrir el sábado completo, el receptor queda debiendo una jornada que devuelve
        # un día de semana (lun-vie) del mismo mes; ese día el receptor dobla y el solicitante
        # descansa, por lo que deben tener jornadas contrarias.
        if jornada_pago_sabado_upper == 'AMBAS':
            if not fecha_pago_semana:
                return False, ("Al cubrir ambas jornadas el sábado, debes elegir el día de la semana "
                               "en que el compañero te devolverá la jornada.")
            fps_obj = DateUtils.parse_date(fecha_pago_semana)
            if not fps_obj:
                return False, "El día de pago en semana no es una fecha válida."
            if fps_obj.weekday() >= 5:
                return False, "El día de pago en semana debe ser de lunes a viernes."
            if (fps_obj.year, fps_obj.month) != (fecha_pago_obj.year, fecha_pago_obj.month):
                return False, "El día de pago en semana debe estar dentro del mismo mes que el sábado."
            from turnos.models import DiaEspecial
            if SolicitudValidator.es_festivo_semana(fps_obj) or DiaEspecial.es_mantenimiento_efectivo(fps_obj):
                return False, "El día de pago en semana no puede ser festivo ni de mantenimiento."
            if fps_obj < timezone.localdate():
                return False, "El día de pago en semana no puede ser en el pasado."

            # El día de devolución es un TERCER día que esta solicitud MUTA (el receptor se dobla
            # y el solicitante descansa), así que necesita las mismas guardas L2 que la cesión y la
            # fecha de pago. Sin esto se podía programar sobre un día ya comprometido por otra
            # solicitud aprobada, o sobre un día en que el receptor ya dobla (triple turno).
            from turnos.services.turno_service import TurnoService as _TSsem
            _comp_rec = _TSsem.dia_comprometido_por_solicitud(
                explorador_receptor, fps_obj, excluir_id=excluir_id)
            if _comp_rec:
                return False, (
                    f"El compañero ya tiene el {fps_obj.strftime('%d/%m/%Y')} comprometido en otra "
                    f"solicitud aprobada ({_comp_rec['motivo']}); no puede doblarse ese día para "
                    f"devolverte la jornada. Elige otro día de la semana."
                )
            _comp_sol = _TSsem.dia_comprometido_por_solicitud(
                explorador_solicitante, fps_obj, excluir_id=excluir_id)
            if _comp_sol:
                return False, (
                    f"Ya tienes el {fps_obj.strftime('%d/%m/%Y')} comprometido en otra solicitud "
                    f"aprobada ({_comp_sol['motivo']}); ese día no trabajas, así que el compañero "
                    f"no tiene nada que devolverte. Elige otro día de la semana."
                )
            _cubre_sol = _TSsem.dia_cubriendo_por_solicitud(
                explorador_solicitante, fps_obj, excluir_id=excluir_id)
            if _cubre_sol:
                _c = (_cubre_sol.get('companero') or {}).get('nombre') or 'otro compañero'
                return False, (
                    f"No puedes descansar el {fps_obj.strftime('%d/%m/%Y')}: trabajas ese día porque "
                    f"{_cubre_sol['motivo']} con {_c} (solicitud #{_cubre_sol['solicitud_id']}). "
                    "Elige otro día de la semana para que te devuelva la jornada."
                )
            try:
                SolicitudValidator.validar_no_doblada_activa(
                    explorador_receptor, fps_obj,
                    mensaje=(
                        f'El compañero ya tiene una jornada doblada (AM + PM) el '
                        f'{fps_obj.strftime("%d/%m/%Y")}: no le queda jornada libre para devolverte '
                        f'la tuya. Elige otro día de la semana.'
                    ),
                )
            except ValidationError as e:
                return False, str(e.messages[0] if getattr(e, 'messages', None) else e)

            j_sol = JornadaService.get_jornada_explorador_fecha(
                explorador_solicitante.id, fps_obj.strftime('%Y-%m-%d'))
            j_rec = JornadaService.get_jornada_explorador_fecha(
                explorador_receptor.id, fps_obj.strftime('%Y-%m-%d'))
            if not j_sol or not j_rec:
                return False, "No se pudo determinar la jornada de los exploradores en el día de pago en semana."
            if j_sol.nombre.upper() == j_rec.nombre.upper():
                # Reutiliza el mismo recuadro + botón "Ir a Cambio de Turno Sencillo"
                # que ya existe para la fecha de pago, pero apuntando al día de semana.
                return False, json.dumps({
                    'code': 'requiere_cambio_turno_previo',
                    'message': (
                        f"El {fps_obj.strftime('%d/%m/%Y')} tú y el compañero tienen la misma jornada "
                        f"({j_sol.nombre.upper()}). Para que él te pague (doblándose por ti) ese día deben "
                        f"quedar en jornadas contrarias. Realiza primero un cambio de turno sencillo."
                    ),
                    'fecha_pago': str(fps_obj),
                    'jornada_comun': j_sol.nombre.upper(),
                })

        return None
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a doblada solicitud.
        
        IMPORTANT: This is NOT a self-request anymore.
        empleado_receptor is the one who covers (not the same as solicitante).
        
        Args:
            datos: Dictionary containing solicitud data
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance (the one who covers)
                - tipo_cambio: TipoSolicitudCambio instance
                - fecha_cambio_turno: Date string (fecha de cesión)
                - fecha_pago: Date string (obligatory)
                - jornada_cedida: 'AM' or 'PM' (optional)
                - tipo_cesion: 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm'
                - comentario: Optional string
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cambio_turno = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')
            jornada_cedida = datos.get('jornada_cedida')
            jornada_pago_sabado = datos.get('jornada_pago_sabado')
            jornada_cubre_en_pago = datos.get('jornada_cubre_en_pago')
            fecha_pago_semana = datos.get('fecha_pago_semana')
            tipo_cesion = datos.get('tipo_cesion', 'cesion_completa')
            # Un INTERCAMBIO cambia el día COMPLETO por los dos lados (ambos tenían AM+PM), así que
            # no admite cesión parcial: lo que traiga el formulario en `tipo_cesion`/`jornada_cedida`
            # es ruido de otro sub-flujo. Normalizarlo al crear evita filas que se contradicen con
            # lo que `aplicar_intercambio` hace de verdad (borrar el día entero a cada uno).
            if datos.get('es_intercambio'):
                tipo_cesion = 'cesion_completa'
                jornada_cedida = None

            # Sin transaction.atomic(): en MySQL + reintentos tras error SQL, atomic() dejaba la conexión
            # en estado "roto" (TransactionManagementError). Si falla el detalle, borramos la solicitud.
            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_cambio_turno,
                estado='pendiente',
            )

            doblada_detalle_data: Dict[str, Any] = {
                'solicitud': solicitud,
                'minutos_deuda': 30,
                'fecha_pago': fecha_pago,
                'tipo_cesion': tipo_cesion,
                'empleado_receptor': explorador_receptor,
                'es_intercambio': bool(datos.get('es_intercambio')),
            }
            if jornada_cedida:
                doblada_detalle_data['jornada_cedida'] = jornada_cedida
            if jornada_pago_sabado:
                doblada_detalle_data['jornada_pago_sabado'] = jornada_pago_sabado
            # Pago en sábado AMBAS: guardar el día de devolución en semana
            if str(jornada_pago_sabado or '').upper() == 'AMBAS' and fecha_pago_semana:
                doblada_detalle_data['fecha_pago_semana'] = fecha_pago_semana
            if jornada_cubre_en_pago:
                jcp = str(jornada_cubre_en_pago).strip().upper()
                if jcp in ('AM', 'PM', 'AMBAS'):
                    doblada_detalle_data['jornada_cubre_en_pago'] = jcp

            try:
                doblada_detalle = DobladaDetalle.objects.create(**doblada_detalle_data)
            except Exception:
                solicitud.delete()
                raise

            logger.info(
                "DobladaDetalle creado: ID=%s, jornada_pago_sabado=%s, jornada_cubre_en_pago=%s",
                doblada_detalle.id,
                jornada_pago_sabado,
                jornada_cubre_en_pago,
            )
            logger.info(
                f"Doblada solicitud creada: {solicitud.id} - {explorador_solicitante.nombre} -> {explorador_receptor.nombre}"
            )
            
            # Crear notificaciones y enviar emails
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
                logger.info(f"Notificaciones y emails procesados para solicitud {solicitud.id}")
            except Exception as e:
                logger.exception(f"Error creando notificaciones para DOBLADA {solicitud.id}: {e}")
                # No re-lanzar el error para que la solicitud se cree exitosamente
                # pero loguear el problema para diagnóstico
            
            return solicitud, "Solicitud de doblada creada correctamente"

        except Exception:
            # Mismo criterio que `validar_solicitud`: aquí ya NO quedan reglas de negocio (se
            # validaron antes), así que cualquier excepción es un BUG. Antes se devolvía
            # (None, str(e)), y el orquestador lo publicaba como 'creation_failed' 400 con el
            # texto de la excepción: el explorador leía un error de BD como si su solicitud
            # estuviera mal, y el fallo real no se distinguía de un rechazo legítimo.
            # Propagando, el orquestador lo convierte en 500 'internal_error' logueado.
            logger.exception("Error INESPERADO creando solicitud de doblada (no es una regla de negocio)")
            raise
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply doblada when solicitud is approved by BOTH receptor AND supervisor.
        
        IMPORTANT: This method applies BOTH dobladas IMMEDIATELY:
        - Receptor's doblada in fecha_cesion
        - Deudor's doblada in fecha_pago
        
        There are no "pending dobladas". Both are applied when both approve.
        
        Args:
            solicitud: The approved solicitud instance
        
        Returns:
            Tuple of (success, message)
        """
        try:
            
            from ..doblada_aplicacion_service import DobladaAplicacionService
            
            with transaction.atomic():
                detalle = solicitud.doblada
                
                # Snapshot de turnos antes de mutar (revertir cancelación 30 min debe restaurar CT sencillos, etc.)
                # Solo se captura la PRIMERA vez: si ya existe un snapshot (p. ej. una doble aplicación
                # accidental por reintento/doble clic), NO se sobrescribe. De lo contrario grabaríamos el
                # estado YA aplicado (DOBLADA) como si fuera el previo, y la cancelación no revertiría nada.
                if not getattr(detalle, 'snapshot_turnos_previos', None):
                    snapshot = DobladaAplicacionService.capturar_snapshot_turnos_previos(solicitud, detalle)
                    DobladaDetalle.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
                    detalle.snapshot_turnos_previos = snapshot

                if getattr(detalle, 'es_intercambio', False):
                    # INTERCAMBIO DE DOBLADAS: swap de días doblados, SIN deuda (ni corporativa
                    # ni entre exploradores). Cada uno ya tenía su doblada; solo cambian de día.
                    DobladaAplicacionService.aplicar_intercambio(solicitud, detalle)
                else:
                    # Aplicar doblada en fecha de cesión
                    DobladaAplicacionService.aplicar_doblada_cesion(solicitud, detalle)

                    # Aplicar doblada en fecha de pago
                    DobladaAplicacionService.aplicar_doblada_pago(solicitud, detalle)

                    # Pago en sábado AMBAS: aplicar también la devolución de la jornada en semana
                    # (ese día el receptor dobla y el solicitante descansa).
                    if (str(getattr(detalle, 'jornada_pago_sabado', '') or '').upper() == 'AMBAS'
                            and getattr(detalle, 'fecha_pago_semana', None)):
                        DobladaAplicacionService.aplicar_pago_residual_semana(solicitud, detalle)

                    # Generar deudas
                    DobladaAplicacionService.generar_deudas_doblada(solicitud, detalle)

                # Estado RESULTANTE: lo que esta doblada deja en esas fechas. Al cancelar se
                # compara contra los turnos actuales para no pisar un cambio ajeno posterior.
                DobladaAplicacionService.capturar_snapshot_resultante(detalle)

                logger.info(f"Doblada aplicada: Solicitud {solicitud.id}")
            
            # IMPORTANTE: Limpiar caché DESPUÉS de que la transacción se confirme
            # Esto asegura que los turnos ya estén guardados en BD antes de limpiar el caché
            from core.services.cache_service import CacheService
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            fecha_cesion = solicitud.fecha_cambio_turno
            fecha_pago = detalle.fecha_pago
            
            # Limpiar caché para solicitante y receptor (mes de cesión, pago y pago en semana)
            # Usar helper centralizado que normaliza el formato de la clave de caché
            fechas_cache = [fecha_cesion, fecha_pago]
            if getattr(detalle, 'fecha_pago_semana', None):
                fechas_cache.append(detalle.fecha_pago_semana)
            for fecha in fechas_cache:
                CacheService.invalidar_cache_turnos_empleado(solicitante.id, fecha.month, fecha.year)
                CacheService.invalidar_cache_turnos_empleado(receptor.id, fecha.month, fecha.year)
                logger.info(
                    f"Caché invalidado para solicitante (ID: {solicitante.id}) y receptor (ID: {receptor.id}) "
                    f"en {fecha.month}/{fecha.year}"
                )
            
            return True, "Doblada aplicada correctamente. Ambas dobladas (cesión y pago) fueron aplicadas inmediatamente."
                
        except Exception as e:
            logger.error(f"Error aplicando doblada: {str(e)}", exc_info=True)
            return False, f"Error aplicando doblada: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for doblada according to visibility rules.
        
        Rules:
        - If fecha is Saturday: show employees who WORK that Saturday (by alternancia).
        - Otherwise (weekday): show employees with opposite shift (jornada contraria).
        - If solicitante is in doblada:
          - To cede AM → show PM employees (except those in doblada)
          - To cede PM → show AM employees (except those in doblada)
        - Exclude employees who already have doblada active in that date
        
        Args:
            fecha: Date string in YYYY-MM-DD format (cesión or payment date)
            usuario_actual: Current user's empleado instance
            **kwargs: Additional arguments
                - jornada_cedida: 'AM' or 'PM' (optional, if usuario is in doblada)
        
        Returns:
            List of available empleados
        """
        try:
            from ..doblada_filtro_service import DobladaFiltroService
            from turnos.services.jornada_service import JornadaService
            
            fecha_obj = DateUtils.parse_date(fecha)
            es_sabado = fecha_obj.weekday() == 5

            solicitante_descansa = bool(kwargs.get('solicitante_descansa'))

            if es_sabado:
                # Fecha de pago (o cesión) es sábado
                from turnos.services.asignacion_especial_service import AsignacionEspecialService
                jornada_trabaja_sabado = AsignacionEspecialService.grupo_trabaja(fecha_obj)
                if not jornada_trabaja_sabado:
                    return []

                jornada_cedida = kwargs.get('jornada_cedida')
                if jornada_cedida:
                    # REGLA ESPECIAL SÁBADOS:
                    # - El grupo que TRABAJA el sábado (según alternancia) hace la DOBLADA.
                    # - El grupo que DESCANSA ese sábado es el que puede recibir la cesión.
                    #   Ejemplo 14/02: trabajan AM → descansa PM → compañeros deben ser PM,
                    #   tanto si se cede AM como si se cede PM.
                    grupo_descansa = 'PM' if jornada_trabaja_sabado.upper() == 'AM' else 'AM'

                    empleados_activos = (
                        Empleado.objects.filter(activo=True)
                        .exclude(id=usuario_actual.id)
                        .select_related('supervisor')
                    )
                    empleados_contrarios = []

                    # Obtener jornadas base directamente de AsignarJornadaExplorador
                    from turnos.models import AsignarJornadaExplorador
                    asignaciones = AsignarJornadaExplorador.objects.filter(
                        explorador__in=empleados_activos,
                        fecha_inicio__lte=fecha_obj
                    ).select_related('jornada', 'explorador').order_by('explorador_id', '-fecha_inicio')

                    # Crear diccionario de jornadas base por empleado
                    jornadas_base = {}
                    for asignacion in asignaciones:
                        if asignacion.explorador_id not in jornadas_base:
                            jornadas_base[asignacion.explorador_id] = asignacion.jornada.nombre.upper()

                    for empleado in empleados_activos:
                        # Usar jornada base del empleado (no la alternancia del sábado)
                        jornada_base_empleado = jornadas_base.get(empleado.id)
                        # Solo empleados del grupo que DESCANSA ese sábado
                        if jornada_base_empleado and jornada_base_empleado == grupo_descansa:
                            empleados_contrarios.append(empleado)

                    logger.info(
                        f"get_empleados_disponibles sábado: {fecha} jornada_cedida={jornada_cedida} "
                        f"grupo_descansa={grupo_descansa} jornada_trabaja={jornada_trabaja_sabado} "
                        f"→ {len(empleados_contrarios)} empleados"
                    )
                else:
                    # Sin jornada_cedida específica: mantener lógica original:
                    # mostrar quienes TRABAJAN ese sábado según alternancia.
                    empleados_activos = (
                        Empleado.objects.filter(activo=True)
                        .exclude(id=usuario_actual.id)
                        .select_related('supervisor')
                    )
                    empleados_contrarios = []
                    for empleado in empleados_activos:
                        jornada_empleado = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha)
                        if jornada_empleado and jornada_empleado.nombre.upper() == jornada_trabaja_sabado.upper():
                            empleados_contrarios.append(empleado)

                    logger.info(
                        f"get_empleados_disponibles sábado: {fecha} jornada_trabaja={jornada_trabaja_sabado} "
                        f"→ {len(empleados_contrarios)} empleados"
                    )
            else:
                # Día entre semana: lógica por jornada contraria + regla especial festivos de semana
                jornada_cedida = kwargs.get('jornada_cedida')

                # Detectar si es festivo de lunes a viernes y si al solicitante le toca doblar por rotación global
                es_festivo_semana = SolicitudValidator.es_festivo_semana(fecha_obj)
                grupo_que_dobla = None
                jornada_solicitante = None
                if es_festivo_semana:
                    try:
                        from turnos.services.asignacion_especial_service import AsignacionEspecialService
                        from turnos.models import AsignarJornadaExplorador
                        grupo_que_dobla = AsignacionEspecialService.grupo_trabaja(fecha_obj)
                        # Usar jornada BASE del solicitante (AsignarJornadaExplorador), NO la jornada
                        # del día (que en festivos puede devolver 'DOBLADA' y romper la comparación).
                        asignacion_base = (
                            AsignarJornadaExplorador.objects
                            .filter(explorador=usuario_actual, fecha_inicio__lte=fecha_obj)
                            .select_related('jornada')
                            .order_by('-fecha_inicio')
                            .first()
                        )
                        jornada_solicitante = asignacion_base.jornada.nombre.upper() if asignacion_base else None
                    except Exception as _exc_festivo:
                        grupo_que_dobla = None
                        jornada_solicitante = None

                # Regla especial festivos entre semana:
                # Cuando al solicitante le corresponde doblar por festivo (grupo_que_dobla),
                # solo pueden cubrir compañeros del grupo CONTRARIO al que dobla,
                # independientemente de si cede AM o PM.

                # La condición aplica cuando:
                # (a) jornada_cedida está presente (usuario cede una doblada existente — puede ser de
                #     cualquier grupo porque fue receptor de alguien del grupo trabajador), O
                # (b) el usuario es del grupo que trabaja ese festivo (solicitante normal de doblada).
                if es_festivo_semana and grupo_que_dobla and (
                    jornada_cedida or (jornada_solicitante and jornada_solicitante == grupo_que_dobla.upper())
                ):
                    grupo_descansa = 'PM' if grupo_que_dobla.upper() == 'AM' else 'AM'
                    empleados_activos = (
                        Empleado.objects.filter(activo=True)
                        .exclude(id=usuario_actual.id)
                        .select_related('supervisor')
                    )
                    # Obtener jornadas base en una sola query para todos los empleados
                    # (igual que lógica de sábados — evita N+1 y usa jornada real, no DOBLADA)
                    from turnos.models import AsignarJornadaExplorador
                    asignaciones_comp = (
                        AsignarJornadaExplorador.objects
                        .filter(explorador__in=empleados_activos, fecha_inicio__lte=fecha_obj)
                        .select_related('jornada', 'explorador')
                        .order_by('explorador_id', '-fecha_inicio')
                    )
                    jornadas_base_comp = {}
                    for asig in asignaciones_comp:
                        if asig.explorador_id not in jornadas_base_comp:
                            jornadas_base_comp[asig.explorador_id] = asig.jornada.nombre.upper()
                    empleados_contrarios = [
                        emp for emp in empleados_activos
                        if jornadas_base_comp.get(emp.id) == grupo_descansa
                    ]
                else:
                    # Día de semana sin festivo especial.
                    servicio = get_empleado_disponibilidad_service()
                    
                    if solicitante_descansa:
                        # Caso especial: el solicitante está DESCANSANDO en la fecha de cesión.
                        # Regla: puede escoger cualquier compañero que trabaje ese día (AM, PM o doblando),
                        # siempre que esté activo y sin doblada activa para esa fecha.
                        empleados_contrarios = list(servicio.get_empleados_disponibles(fecha, usuario_actual))
                        jornada_a_ceder = None
                    else:
                        # Lógica original: usar jornada contraria del solicitante.
                        jornada_a_ceder = DobladaFiltroService.obtener_jornada_a_ceder(
                            usuario_actual, fecha, jornada_cedida
                        )
                        if not jornada_a_ceder:
                            logger.warning(
                                f"No se pudo determinar jornada a ceder para {usuario_actual.nombre} en {fecha}"
                            )
                            return []

                        if jornada_cedida:
                            jornada_contraria = 'PM' if jornada_a_ceder == 'AM' else 'AM'
                            empleados_activos = Empleado.objects.filter(activo=True).exclude(id=usuario_actual.id)
                            empleados_contrarios = []
                            for empleado in empleados_activos:
                                jornada_empleado = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha)
                                if jornada_empleado and jornada_empleado.nombre.upper() == jornada_contraria:
                                    empleados_contrarios.append(empleado)
                        else:
                            empleados_contrarios = list(servicio.get_empleados_jornada_contraria(fecha, usuario_actual))
            
            # Filtrar empleados con doblada activa para evitar triple turno
            empleados_filtrados = DobladaFiltroService.filtrar_empleados_sin_doblada_activa(
                empleados_contrarios, fecha_obj
            )
            
            return DobladaFiltroService.convertir_empleados_a_dict(empleados_filtrados, fecha)
            
        except Exception:
            # NO devolver [] ante un fallo: la lista vacía YA SIGNIFICA otra cosa ("no hay ningún
            # compañero que cumpla las condiciones ese día", los `return []` legítimos de arriba).
            # Devolver lo mismo ante un bug hacía que el desplegable saliera vacío y el explorador
            # concluyera "ese día no hay nadie", sin señal de que el código había reventado.
            # Propagando, la vista responde 500/'internal_error' y el JS muestra "Error al cargar
            # compañeros" — distinguible de la lista vacía legítima.
            logger.exception("Error obteniendo empleados disponibles para doblada")
            raise

    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer.
        
        Args:
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
        
        Returns:
            Dictionary with turn information
        """
        # Sin try/except: un `{}` silencioso se interpreta aguas arriba como "no tiene turno",
        # que es una respuesta de negocio válida. Un fallo real debe verse, no disfrazarse de
        # día sin turno.
        turno_service = get_turno_service()
        return turno_service.get_turno_explorador(explorador_id, fecha)
