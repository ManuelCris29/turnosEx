"""
D FDS Strategy - Doblada de Fin de Semana

Implementa la lógica de "D FDS": un explorador cede un día de fin de semana que trabaja
(sábado o domingo) a un compañero que ESE día descansa, y que pasa a trabajarlo completo
(AM+PM). El solicitante devuelve el favor cubriendo al compañero en otro fin de semana del
mismo mes y del mismo día de la semana (fecha de pago).

La elegibilidad se decide por el ESTADO REAL de cada día (`TurnoService.estado_dia`, las
mismas capas que Mis Turnos), no por el grupo AM/PM ni por la alternancia teórica: en la
operación conviven quienes trabajan los dos días del finde, quienes descansan los dos y
quienes tienen media jornada por un cambio previo.

Reutiliza:
- TurnoService.estado_dia: fuente de verdad del estado de cada día.
- SolicitudValidator.validar_fecha_pago_mismo_mes_cesion: pago en el mismo mes.
- DobladaDetalle: modelo de detalle (fecha_pago, minutos_deuda).
- DFDSAplicacionService: aplicación de turnos y deudas al aprobar.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction

# A nivel de módulo, no dentro de la función: los tests parchean `localdate`
# alcanzando el módulo por aquí (`patch.object(_d_fds_mod.timezone, 'localdate')`).
from django.utils import timezone

from core.constants import JornadaDisplay
from core.utils.date_utils import DateUtils
from core.utils.mensajes_error import texto_de_error
from empleados.models import Empleado
from solicitudes.models import DobladaDetalle, SolicitudCambio

from .base_strategy import SolicitudStrategy
from .estrategia_fin_de_semana import EstrategiaFinDeSemana

logger = logging.getLogger(__name__)


class DFDSStrategy(SolicitudStrategy, EstrategiaFinDeSemana):
    """Strategy para "D FDS" (Doblada de Fin de Semana)."""

    def __init__(self):
        super().__init__("D FDS")

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _parse(fecha) -> Optional[Any]:
        if not fecha:
            return None
        if isinstance(fecha, str):
            try:
                return DateUtils.parse_date(fecha)
            except ValueError:
                return None
        return fecha

    # NOTA: aquí vivían `_grupo_base` y `_grupo_efectivo` (grupo AM/PM del explorador). La
    # elegibilidad ya no se decide por grupo sino por el ESTADO REAL de cada día (`estado_dia`),
    # así que dejaron de usarse. La jornada base solo se sigue consultando para etiquetar la
    # deuda, y eso lo hace `JornadaService` desde el servicio de aplicación.

    def _datos_desde_solicitud(self, solicitud):
        """
        Reconstruye los datos para re-validar al aprobar (ver base).

        `solicitud_actual_id` —para que los chequeos de compromiso previo no se detecten a SÍ
        MISMOS al re-validar— lo añade `revalidar_para_aprobar` en la clase base.
        """
        det = getattr(solicitud, 'doblada', None)
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_cambio_turno': solicitud.fecha_cambio_turno,
            'fecha_pago': det.fecha_pago if det else None,
        }

    # --------------------------------------------------------------- validación
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            from ..solicitud_validator import SolicitudValidator

            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            fecha_cesion_raw = datos.get('fecha_cambio_turno')
            fecha_pago_raw = datos.get('fecha_pago')
            comentario = datos.get('comentario') or ''

            # 1. Requeridos
            if not solicitante:
                return False, "Explorador solicitante es requerido"
            if not receptor:
                return False, "Debe seleccionar el compañero que se doblará el fin de semana"
            if not fecha_cesion_raw:
                return False, "La fecha de fin de semana es requerida"
            if not fecha_pago_raw:
                return False, "La fecha de pago es obligatoria (otro fin de semana del mismo mes)"

            fecha_cesion = self._parse(fecha_cesion_raw)
            fecha_pago = self._parse(fecha_pago_raw)
            if not fecha_cesion or not fecha_pago:
                return False, "Formato de fecha inválido"

            # 2. Empleados
            SolicitudValidator.validar_empleado_activo(solicitante)
            SolicitudValidator.validar_empleado_activo(receptor)
            SolicitudValidator.validar_no_mismo_empleado(solicitante, receptor)
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de D FDS')

            # No DUPLICADOS pendientes (regla de CREACIÓN; se OMITE al re-validar para aprobar).
            # Se comprueban las DOS fechas (cesión y pago) y contra las dos fechas de las otras
            # solicitudes (su cesión y su pago): antes solo se cruzaba `fecha_cambio_turno`, así que
            # dos pendientes que apuntaban al mismo día de pago —o una D FDS que pagaba el día que
            # otra pendiente cede— convivían y se aprobaban en paralelo.
            if not datos.get('es_revalidacion'):
                SolicitudValidator.validar_sin_pendiente_en_fechas(
                    solicitante, [fecha_cesion, fecha_pago])
                SolicitudValidator.validar_sin_pendiente_en_fechas(
                    receptor, [fecha_cesion, fecha_pago], es_receptor=True)

            # 3. Ambas fechas deben ser fin de semana (sáb/dom)
            if fecha_cesion.weekday() not in (5, 6):
                return False, "La fecha de cesión debe ser un fin de semana (sábado o domingo)"
            if fecha_pago.weekday() not in (5, 6):
                return False, "La fecha de pago debe ser un fin de semana (sábado o domingo)"

            # 4. Fechas no pasadas / coherencia
            hoy = timezone.localdate()
            # Al CREAR, la cesión tampoco puede ser HOY: el día ya está en curso (mismo criterio
            # que la fecha de pago). Al re-validar para APROBAR solo se exige que no sea pasada,
            # para no bloquear al supervisor que aprueba el mismo día del finde.
            if fecha_cesion < hoy or (fecha_cesion == hoy and not datos.get('es_revalidacion')):
                return False, (
                    "La fecha de cesión debe ser posterior a hoy: no se puede ceder un fin de "
                    "semana pasado ni el día en curso."
                )
            if fecha_pago <= hoy:
                return False, "La fecha de pago debe ser posterior a hoy"
            if fecha_pago == fecha_cesion:
                return False, "La fecha de pago no puede ser la misma que la fecha de cesión"

            # 4b. El pago debe ser el MISMO día del fin de semana que la cesión:
            #     si cedes un domingo, devuelves un domingo; si cedes un sábado, un sábado.
            #     Así cada quien conserva la misma cantidad de sábados/domingos del mes.
            if fecha_cesion.weekday() != fecha_pago.weekday():
                dia_ces = 'domingo' if fecha_cesion.weekday() == 6 else 'sábado'
                return False, (
                    f"Cediste un {dia_ces}: la devolución (pago) también debe ser un {dia_ces}, "
                    f"para que ambos conserven la misma cantidad de {dia_ces}s en el mes."
                )

            # 5. Pago en el mismo mes que la cesión (regla reutilizada de doblada)
            SolicitudValidator.validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion)

            # 6. No mantenimiento en ninguna fecha
            SolicitudValidator.validar_no_dia_mantenimiento(fecha_cesion.strftime('%Y-%m-%d'))
            SolicitudValidator.validar_no_dia_mantenimiento(fecha_pago.strftime('%Y-%m-%d'))

            # 7-9. ELEGIBILIDAD POR ESTADO REAL DEL DÍA (fuente única `estado_dia`, las mismas
            #      capas que Mis Turnos), NO por grupo AM/PM ni por alternancia teórica.
            #
            #      La operación real no encaja en el molde "un grupo trabaja el sábado y el otro
            #      el domingo": hay quien trabaja los DOS días (el suyo más uno que cubre por un
            #      favor), quien descansa los dos, y quien tiene media jornada por un cambio
            #      previo. Con el criterio de grupos, quien trabajaba ambos días no podía ceder
            #      ninguno, y un compañero libre del MISMO grupo —justo a quien se le puede
            #      ceder— se rechazaba.
            #
            #      Reglas: se cede un día que se trabaja COMPLETO y que el compañero tiene libre;
            #      se paga un día que el compañero trabaja COMPLETO y que uno tiene libre.
            from turnos.services.turno_service import TurnoService

            est_sol_ces = TurnoService.estado_dia(solicitante, fecha_cesion)
            est_rec_ces = TurnoService.estado_dia(receptor, fecha_cesion)
            f_ces = fecha_cesion.strftime('%d/%m/%Y')
            f_pago = fecha_pago.strftime('%d/%m/%Y')

            # 7. Cesión: hay que trabajar ese día, y a jornada completa.
            if not est_sol_ces['trabaja']:
                motivo = est_sol_ces.get('motivo') or 'descansas ese día'
                return False, f"No tienes un turno que ceder el {f_ces} ({motivo})."
            if est_sol_ces.get('jornada') != JornadaDisplay.DOBLADA:
                return False, (
                    f"El {f_ces} solo tienes media jornada ({est_sol_ces.get('jornada') or 'parcial'}) "
                    "por un cambio previo; no tienes el día completo del fin de semana para ceder."
                )

            # 8. Cesión: el compañero debe tener ese día LIBRE para poder tomarlo.
            if est_rec_ces['trabaja']:
                return False, (
                    f"Tu compañero ya trabaja el {f_ces}; no tiene ese día libre para cubrirte. "
                    "Elige a alguien que descanse ese día."
                )

            # 9. Pago: el compañero trabaja ese día COMPLETO (es el día que se le cubre) y el
            #    solicitante lo tiene LIBRE (si ya trabajara, no podría doblarse encima).
            est_rec_pago = TurnoService.estado_dia(receptor, fecha_pago)
            est_sol_pago = TurnoService.estado_dia(solicitante, fecha_pago)

            if not est_rec_pago['trabaja']:
                motivo = est_rec_pago.get('motivo') or 'descansa ese día'
                return False, (
                    f"Tu compañero no trabaja el {f_pago} ({motivo}); no hay día que cubrir."
                )
            if est_rec_pago.get('jornada') != JornadaDisplay.DOBLADA:
                return False, (
                    f"En la fecha de pago ({f_pago}) tu compañero solo tiene media jornada "
                    f"({est_rec_pago.get('jornada') or 'parcial'}) por un cambio previo; "
                    "no hay día completo del fin de semana para cubrir."
                )
            if est_sol_pago['trabaja']:
                return False, (
                    f"No puedes pagar el {f_pago}: ese día ya trabajas y no puedes doblarte de "
                    "nuevo. Elige un fin de semana en el que ese mismo día descanses."
                )

            # 9c. No se puede pagar con un día que YA SE CEDIÓ POR UN FAVOR: ese día lo está
            #     cubriendo un compañero COMO EXTRA, y si además se trabaja quedarían dos personas
            #     en el mismo turno y el favor de quien cubre se desperdiciaría.
            #
            #     Tres formas de descansar la fecha de pago, y solo una estorba:
            #       · por ALTERNANCIA — es lo normal: es el día del compañero y por eso se dobla.
            #       · porque alguien te está PAGANDO a ti — ese descanso es tuyo, te lo ganaste, y
            #         puedes renunciar a él para cubrir a un tercero.
            #       · por un CAMBIO DE DESCANSO — tampoco estorba: es un INTERCAMBIO ya saldado,
            #         diste tu día y tomaste otro, y quien trabaja ese día lo hace en tu lugar, no
            #         como extra. Si cubres a un compañero ese día, sustituyes a ESE compañero: el
            #         turno sigue teniendo la misma gente. (Es el mismo criterio que ya se aplica
            #         en `dia_cubriendo_por_solicitud`, que también deja fuera los intercambios.)
            #       · por haber CEDIDO el día en una doblada/D FDS — aquí sí: hay una deuda viva.
            comp_sol_pago = TurnoService.dia_comprometido_por_solicitud(solicitante, fecha_pago)
            if (comp_sol_pago and comp_sol_pago.get('tipo') == 'cedio'
                    and comp_sol_pago.get('origen') != 'cambio_descanso'):
                motivo = comp_sol_pago.get('motivo') or 'ya lo cediste'
                return False, (
                    f"No puedes pagar el {f_pago}: ese día ya se lo cediste a un compañero "
                    f"({motivo}) y él lo está cubriendo. Elige otro fin de semana."
                )

            # 9d. NO IMPORTA POR QUÉ trabaja cada uno su día, solo que el día quede cubierto.
            #
            #     Un día se puede trabajar porque es el propio o porque se está CUBRIENDO a un
            #     tercero por un favor. Los dos casos valen, en los dos sentidos:
            #       · ceder un día de cobertura (traspaso): el sustituto lo trabaja completo
            #         (`_crear_doblada_dia`), así que el acreedor original conserva su descanso y
            #         su deuda sigue saldada; solo cambia QUIÉN cubre. Se avisa al acreedor
            #         (ver `_avisar_traspaso_cobertura` y `aplicar_cambios`).
            #       · pagar cubriendo un día que el compañero trabaja por un favor ajeno: también
            #         vale. Un favor se mide en DÍAS TRABAJADOS, no en de quién es el día: si el
            #         compañero estaba comprometido a trabajarlo y se lo cubren, trabaja un día
            #         menos, que es exactamente la compensación que se le debe. Las cuentas de los
            #         tres implicados quedan en cero y el día sigue teniendo una sola persona.
            #
            #     Hubo aquí un bloqueo para el segundo caso. Era incoherente: en turnos es la MISMA
            #     operación que el traspaso, solo que expresada desde el otro lado, así que se
            #     prohibía por un camino lo que se permitía por el otro.
            #
            #     Lo que sí sigue bloqueado es distinto y está en el paso 9c: pagar con un día que
            #     TÚ ya cediste. Eso dejaría DOS personas en el mismo turno.

            # (El antiguo paso 10 —"ni el receptor ni el solicitante pueden tener ya una doblada
            #  AM+PM en su día"— desapareció porque los pasos 8 y 9 ya lo cubren: `estado_dia`
            #  incluye los turnos reales, así que quien ya está doblado figura como que TRABAJA
            #  ese día y se rechaza ahí, con un mensaje más concreto.)

            return True, "Solicitud de D FDS válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando D FDS: {str(e)}"

    # ------------------------------------------------------------------- crear
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        try:
            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cesion = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')
            # D FDS es doblada de fin de semana: NO genera deuda corporativa de 30 min
            # (los 30 min solo aplican a dobladas de lunes a viernes).
            minutos_deuda = datos.get('minutos_deuda', 0)

            with transaction.atomic():
                solicitud = SolicitudCambio.objects.create(
                    explorador_solicitante=solicitante,
                    explorador_receptor=receptor,
                    tipo_cambio=tipo_cambio,
                    comentario=comentario,
                    fecha_cambio_turno=fecha_cesion,
                    estado='pendiente',
                )
                DobladaDetalle.objects.create(
                    solicitud=solicitud,
                    fecha_pago=fecha_pago,
                    minutos_deuda=minutos_deuda,
                    tipo_cesion='cesion_completa',
                    empleado_receptor=receptor,
                )

            return solicitud, "Solicitud de D FDS creada correctamente"

        except Exception as e:
            return None, f"Error creando solicitud de D FDS: {str(e)}"

    # ----------------------------------------------------------------- aplicar
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        try:
            from core.services.cache_service import CacheService

            from ..d_fds_aplicacion_service import DFDSAplicacionService
            from ..doblada_aplicacion_service import DobladaAplicacionService

            with transaction.atomic():
                detalle = solicitud.doblada

                # ¿Es un TRASPASO DE COBERTURA? Hay que mirarlo ANTES de aplicar, mientras el día
                # todavía figura a nombre del cedente. Ver `_avisar_traspaso_cobertura`.
                from turnos.services.turno_service import TurnoService
                info_cobertura = TurnoService.dia_cubriendo_por_solicitud(
                    solicitud.explorador_solicitante, solicitud.fecha_cambio_turno,
                    excluir_id=solicitud.id)

                # Snapshot para poder revertir (cancelación de 30 min, igual que doblada).
                # Solo la PRIMERA vez: si ya existe, no sobrescribir (una doble aplicación
                # grabaría el estado ya aplicado como "previo" y rompería la reversión).
                if not getattr(detalle, 'snapshot_turnos_previos', None):
                    snapshot = DobladaAplicacionService.capturar_snapshot_turnos_previos(solicitud, detalle)
                    DobladaDetalle.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
                    detalle.snapshot_turnos_previos = snapshot

                DFDSAplicacionService.aplicar(solicitud, detalle)
                DFDSAplicacionService.generar_deudas(solicitud, detalle)

                # Estado RESULTANTE: lo que esta D FDS deja en esas fechas. Al cancelar se
                # compara contra los turnos actuales para no pisar un cambio ajeno posterior.
                DobladaAplicacionService.capturar_snapshot_resultante(detalle)

                if info_cobertura:
                    self._avisar_traspaso_cobertura(solicitud, info_cobertura)

            # Invalidar caché de ambos en ambos meses (cesión y pago)
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            for fecha in (solicitud.fecha_cambio_turno, detalle.fecha_pago):
                if fecha:
                    CacheService.invalidar_cache_turnos_empleado(solicitante.id, fecha.month, fecha.year)
                    CacheService.invalidar_cache_turnos_empleado(receptor.id, fecha.month, fecha.year)

            return True, "D FDS aplicada correctamente (favor y pago agendados)."

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error aplicando D FDS")
            return False, f"Error aplicando D FDS: {texto_de_error(e)}"

    @staticmethod
    def _avisar_traspaso_cobertura(solicitud: SolicitudCambio, info_cobertura: dict) -> None:
        """
        Deja constancia y avisa cuando el día cedido se trabajaba por un favor de un tercero.

        La solicitud original NO se toca —sigue aprobada y vigente: el acreedor conserva su
        descanso y su deuda sigue saldada, porque el día lo trabaja el sustituto—. Lo único que
        cambia es QUIÉN cubre, así que basta con anotarlo en la solicitud nueva y avisar.

        (Se descartó marcarla como `reemplazada`: ese estado la sacaría de 'aprobada' y con ella
        desaparecería el descanso del acreedor en Mis Turnos y su deuda de las consultas, que es
        justo lo que aquí NO cambia.)
        """
        from ..notificacion_service import NotificacionService

        acreedor = (info_cobertura.get('companero') or {}).get('nombre') or 'otro compañero'
        nota = (
            f"\n\n[Traspaso de cobertura] El {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')} "
            f"lo trabajaba por el acuerdo de la solicitud #{info_cobertura.get('solicitud_id')} "
            f"con {acreedor}; ese día pasa a cubrirlo "
            f"{solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}. "
            f"El acuerdo original sigue vigente."
        )
        SolicitudCambio.objects.filter(pk=solicitud.pk).update(
            comentario=(solicitud.comentario or '') + nota)
        try:
            NotificacionService.crear_notificacion_traspaso_cobertura(
                solicitud, info_cobertura, solicitud.explorador_receptor)
        except Exception:
            # Un fallo notificando no puede tumbar la aplicación de la solicitud (los turnos ya
            # están escritos); queda en el log y en el comentario de la solicitud.
            logging.getLogger(__name__).exception(
                "No se pudo notificar el traspaso de cobertura de la solicitud %s", solicitud.pk)

    # --------------------------------------------------- empleados disponibles
    def disponibilidad_companero(self, candidato: Empleado, fecha_cesion) -> Tuple[bool, Optional[str]]:
        """
        Regla de D FDS: puede recibir el día quien lo tenga LIBRE.

        No se mira el grupo AM/PM, se mira el ESTADO REAL de los dos días del finde
        (`estado_dia`, la misma fuente que Mis Turnos):
          - debe DESCANSAR el día que se le cede (si no, no podría trabajarlo);
          - no puede trabajar ya los DOS días del finde;
          - no puede tener MEDIA jornada en ninguno de los dos días: el finde se trabaja a día
            completo (AM+PM) y una media jornada suelta viene de un cambio previo, así que ni
            cede ni recibe un día entero.

        El criterio anterior (grupo contrario + trabajar el otro día del finde) dejaba fuera a
        quien descansa los dos días y a los compañeros del mismo grupo, que en la operación real
        son justamente a quienes se les puede ceder.
        """
        from datetime import timedelta

        from turnos.services.turno_service import TurnoService

        otro = (fecha_cesion + timedelta(days=1) if fecha_cesion.weekday() == 5
                else fecha_cesion - timedelta(days=1))
        dia_ced = 'sábado' if fecha_cesion.weekday() == 5 else 'domingo'
        dia_otro = 'sábado' if otro.weekday() == 5 else 'domingo'

        # El día que se cede se mira primero y se corta ahí si ya lo trabaja: se ahorra la mitad
        # de las consultas, porque quien trabaja ese día ya está descartado pase lo que pase.
        est_ced = TurnoService.estado_dia(candidato, fecha_cesion)
        if est_ced['trabaja']:
            est_otro = TurnoService.estado_dia(candidato, otro)
            if est_otro['trabaja']:
                return False, 'ya trabaja los dos días de ese finde'
            return False, f'ya trabaja ese {dia_ced}'

        est_otro = TurnoService.estado_dia(candidato, otro)
        if est_otro['trabaja'] and est_otro.get('jornada') in ('AM', 'PM'):
            return False, f'solo tiene media jornada ({est_otro.get("jornada")}) el {dia_otro} de ese finde'
        return True, None

    def etiqueta_companero(self, candidato: Empleado, fecha_cesion) -> str:
        """
        En D FDS lo que habilita a un compañero es tener LIBRE el día que se le cede, así que eso
        es lo que se dice. La etiqueta por defecto ("trabaja el otro día del finde") describía el
        calendario, no a la persona, y afirmaba cosas falsas de quien descansa los dos días.
        """
        dia_ced = 'sábado' if fecha_cesion.weekday() == 5 else 'domingo'
        return f'descansa {dia_ced} {fecha_cesion.strftime("%d/%m")}'

    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Pool de compañeros para D FDS: todos los exploradores activos salvo uno mismo.

        El filtro fino (quién descansa ese día, medias jornadas, dobles) lo aplica
        `disponibilidad_companero`, para que el formulario pueda mostrar también a los NO
        disponibles con su motivo en vez de esconderlos.
        """
        try:
            fecha_obj = self._parse(fecha)
            if not fecha_obj or fecha_obj.weekday() not in (5, 6):
                return []

            return list(
                Empleado.objects.operativos()
                .exclude(id=usuario_actual.id)
                .select_related('supervisor')
                .order_by('nombre', 'apellido')
            )
        except Exception:
            logging.getLogger(__name__).exception("Error listando compañeros de D FDS")
            return []

    def detalle(self, solicitud, datos):
        """
        Detalle propio de D FDS para la pantalla de consulta.

        Movido desde `views/detalle.py` en la Fase 2 (cerrar el OCP): la vista
        elegía con una cadena `if tipo_nombre == ...`, así que cada tipo nuevo
        obligaba a editarla. El cuerpo se trasladó SIN cambios de lógica; solo
        los imports relativos pasaron a absolutos al cambiar de paquete.
        """
        try:
            detalle = solicitud.doblada  # D FDS usa el mismo modelo que DOBLADA
            if detalle:
                _rec_nom = solicitud.explorador_receptor.nombre
                _fc = solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'No especificada'
                _fp = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'Pendiente de pago'
                datos['informacion_adicional']['modalidad'] = 'Doblada de fin de semana (intercambio de días de finde)'
                datos['informacion_adicional']['intercambio_dia_a'] = (
                    f'{_fc} — tu día del finde: lo cubre {_rec_nom} doblándose y tú descansas'
                )
                datos['informacion_adicional']['intercambio_dia_b'] = (
                    f'{_fp} — día del finde de {_rec_nom}: lo cubres tú doblándote y él/ella descansa'
                )
                datos['informacion_adicional']['deuda_30min'] = (
                    'No genera deuda de 30 min (las dobladas de fin de semana no la generan).'
                )
        except Exception as e:
            logger.error(f"Error obteniendo detalles de D FDS: {e}")

    def validar_campos_requeridos(self, post):
        """Campos obligatorios de D FDS (movido del parser en la Fase 2)."""
        if not post.get('fecha_solicitud'):
            return False, 'La fecha del fin de semana es requerida'
        if not post.get('empleado_receptor'):
            return False, 'Debe seleccionar el compañero que se doblará el fin de semana'
        if not post.get('fecha_pago'):
            return False, 'La fecha de pago es obligatoria (otro fin de semana del mismo mes).'
        return True, ''

    def parsear_datos(self, post, solicitante, receptor):
        """
        Traduce el POST de D FDS (movido del parser en la Fase 2).

        En el parser los dos tipos compartían UNA rama. Al separarlos, el
        diccionario queda idéntico a propósito: lo fija un test que compara
        las dos salidas entre sí.
        """
        return {
            'explorador_solicitante': solicitante,
            'explorador_receptor': receptor,
            'comentario': post.get('comentarios', ''),
            'fecha_cambio_turno': post.get('fecha_solicitud'),
            'fecha_pago': post.get('fecha_pago'),
            # Sub-modalidades de CAMBIO DESCANSO entre semana (temporada)
            'submodalidad_semana': post.get('submodalidad_semana'),
            'tipo_cesion': post.get('tipo_cesion'),
            'jornada_cedida': post.get('jornada_cedida'),
            # Cobertura: jornada que YO cubro el día de pago (si estoy libre y el
            # compañero trabaja ambas, puedo elegir AM o PM; si no, va la cedida).
            'jornada_cubre_en_pago': post.get('jornada_cubre_en_pago'),
            'fecha_creacion_solicitud': timezone.localdate(),
        }

    usa_detalle_doblada = True

    def reaplicar(self, solicitud, fechas):
        """
        D FDS comparte `DobladaDetalle` con DOBLADA, pero NO su logica: se re-aplica
        con la de fin de semana, no con la de doblada entre semana.
        """
        from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService

        detalle = getattr(solicitud, 'doblada', None)
        if detalle is None:
            return
        DFDSAplicacionService.aplicar(solicitud, detalle)

    def pares_que_reescribe(self, solicitud, fechas):
        """
        SIEMPRE sus dos dias. `DFDSAplicacionService.aplicar` los muta de una vez,
        sin importar cual coincidio con la reconciliacion: declarar solo el
        coincidente dejaria el otro fuera del cierre.
        """
        detalle = getattr(solicitud, 'doblada', None)
        if detalle is None:
            return set()
        return self._pares(solicitud,
                           [solicitud.fecha_cambio_turno, detalle.fecha_pago], todas=True)

    def revertir_cambios(self, solicitud):
        """D FDS comparte `DobladaDetalle` con DOBLADA, pero su reversion es otra."""
        from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService

        detalle = getattr(solicitud, 'doblada', None)
        if not detalle:
            return
        DFDSAplicacionService.revertir(solicitud)
        self._invalidar_meses(solicitud,
                              [solicitud.fecha_cambio_turno, detalle.fecha_pago])
