"""
Validación de FLUJO de la doblada: los tramos de `DobladaStrategy.validar_solicitud`.

QUÉ ES ESTO Y POR QUÉ NO ESTÁ EN `doblada_validator.py`
--------------------------------------------------------
Hay dos clases de validación en la doblada, y hablan idiomas distintos a propósito:

  `DobladaValidator` (validators/doblada_validator.py) son PRIMITIVAS de regla: "esto
  está prohibido". Cada una comprueba una cosa y LANZA `ValidationError`. Se reutilizan
  desde varios sitios y no saben nada del flujo que las llama.

  Esto son TRAMOS DE FLUJO: secuencias de comprobaciones en un orden que importa, que
  DEVUELVEN el mensaje que verá el usuario en vez de lanzarlo.

Mezclarlas costaría un fallo real, no solo elegancia. La traducción de excepción a
mensaje, al final de `validar_solicitud`, es `except ValidationError as e: return
False, str(e)`. Y `validar_pago_en_sabado` devuelve un `RequiereCambioTurnoPrevio`,
que es una subclase de `str` con `fecha_pago` y `jornada_comun` colgados: si viajara
dentro de un `ValidationError`, ese `str(e)` lo aplanaría a texto plano y el formulario
dejaría de pintar el recuadro «Ir a Cambio de Turno Sencillo» —sin error en el
servidor y sin test rojo—. Es el mismo fallo que documenta `errores_validacion.py`,
por otra puerta.

De ahí este módulo: el traslado que la auditoría pedía, pero al sitio cuyo contrato
coincide con el del código que se mueve.

QUÉ CAMBIÓ AL MOVERLO
---------------------
Nada de comportamiento. Los ocho métodos recibían `self` y ninguno lo usaba, así que
pasan a `@staticmethod`; y pierden el guion bajo inicial, porque dejan de ser privados
de una clase para ser la interfaz de este módulo. `EntradaDoblada` viene con ellos:
es su parámetro, no un dato de la strategy.

LAS TRES CONVENCIONES DE RETORNO
--------------------------------
Se conservan tal cual estaban, y conviene saberlas antes de tocar nada:
  - `validar_jornadas_y_coincidencia`, `validar_dia_no_comprometido`,
    `validar_cesion_en_festivo`, `validar_reglas_comunes`, `validar_cobertura_en_pago`
    devuelven el MENSAJE de error, o `None` si todo pasa.
  - `validar_pago_sabado`, `validar_intercambio` y `validar_pago_en_sabado` devuelven
    la TUPLA `(False, mensaje)`, o `None`. Heredan la forma de la función a la que
    delegan, y normalizarla habría mezclado un cambio de contrato con el traslado.

Unificarlas es un trabajo aparte y con su propio riesgo: `validar_pago_en_sabado` es
justamente la que devuelve el error tipado.
"""
import logging
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.constants import JornadaDisplay
from core.utils.date_utils import DateUtils
from solicitudes.models import SolicitudCambio
from turnos.services.jornada_service import JornadaService

from ..errores_validacion import RequiereCambioTurnoPrevio

# La fachada, no `DobladaValidator` directamente: estos tramos usan primitivas de VARIOS
# validadores (base, CT y doblada), que es justo lo que la fachada reúne. No hay ciclo:
# `solicitud_validator` importa `validators/doblada_validator`, no este módulo.
from ..solicitud_validator import SolicitudValidator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntradaDoblada:
    """
    La entrada de una solicitud de doblada, ya extraida y normalizada.

    POR QUE EXISTE
    --------------
    `validar_solicitud` sacaba trece variables locales de `datos` y las arrastraba
    por 500 lineas. Al empezar a trocear el metodo (Fase 3), el primer bloque
    extraido necesito ONCE parametros: la firma era mas larga que varias de las
    validaciones que contenia, y cada corte siguiente iba a ser peor.

    Este objeto es lo que hace baratos los cortes siguientes. No es un dato nuevo:
    es exactamente lo que ya habia en las locales, con un nombre.

    QUE NO GUARDA, Y POR QUE
    ------------------------
    No guarda `es_cesion_festivo` ni `es_pago_festivo`. Esos dos se calculan con
    una consulta a la base a mitad del metodo, DESPUES de varias validaciones que
    pueden cortar antes. Meterlos aqui adelantaria esas consultas y cambiaria
    cuando se ejecutan, que es justo el tipo de efecto lateral que un refactor no
    debe introducir. Se pasan aparte a quien los necesite.

    Es `frozen` a proposito: la entrada de una peticion no cambia mientras se
    valida, y congelarla impide que un bloque extraido modifique lo que lee otro.
    """
    solicitante: Any
    receptor: Any
    fecha_cesion: Any
    fecha_pago: Any
    fecha_cesion_obj: Any
    fecha_pago_obj: Any
    jornada_cedida: Optional[str]
    jornada_pago_sabado: Optional[str]
    fecha_pago_semana: Any
    jornada_cubre_en_pago: str
    tipo_cesion: str
    fecha_creacion_solicitud: Any
    comentario: str
    excluir_id: Any
    es_revalidacion: bool

class DobladaFlujoValidator:
    """Los tramos de validación de la doblada. Ver el docstring del módulo."""

    @staticmethod
    def validar_jornadas_y_coincidencia(entrada, es_cesion_festivo, es_pago_festivo):
        """
        Ultimo tramo de `validar_solicitud`: jornadas contrarias, triple turno,
        doblada activa en la fecha de pago y coincidencia de jornadas.

        Devuelve el MENSAJE de error, o None si todo pasa. Se eligio esa forma en
        vez de (bool, str) porque aqui "sin error" es el caso normal y un None se
        lee mejor que un (True, "") en el punto de llamada.

        Las validaciones que lanzan ValidationError siguen propagandola: la captura
        vive en `validar_solicitud`, que es quien la traduce a (False, mensaje).
        Por eso este metodo NO lleva su propio try/except: duplicarlo cambiaria el
        punto donde se decide que es regla de negocio y que es bug.

        Los once parametros son fieles a lo que el bloque usaba como variables
        locales. Es mucha firma, y es justo la señal de que el siguiente paso de
        esta fase deberia ser un objeto de contexto con la entrada ya normalizada.
        """
        from ..solicitud_validator import SolicitudValidator

        # Validar jornadas contrarias — se omite para festivos de semana porque en esos días
        # el grupo que descansa (misma jornada base) cubre válidamente al grupo que trabaja.
        if not es_cesion_festivo:
            SolicitudValidator.validar_jornadas_contrarias_doblada(
                entrada.solicitante,
                entrada.receptor,
                entrada.fecha_cesion,
                entrada.jornada_cedida
            )
        
        # Validar que receptor no tenga doblada activa en fecha de CESIÓN (evitar triple turno)
        SolicitudValidator.validar_no_triple_turno(entrada.receptor, entrada.fecha_cesion)
        # NO validar triple turno del receptor en fecha_pago:
        # en la fecha de pago el receptor PIERDE una jornada (el deudor se la devuelve),
        # no gana una. La protección real la da la validación de jornada_cedida más abajo.
        
        # Validar que deudor no tenga doblada activa en fecha de pago. Mensaje contextual:
        # ya estamos en el formulario de doblada, así que NO decir "usa la Solicitud de Dobladas".
        SolicitudValidator.validar_no_doblada_activa(
            entrada.solicitante, entrada.fecha_pago,
            mensaje=(
                f'No puedes pagar la doblada el {entrada.fecha_pago_obj.strftime("%d/%m/%Y")}: ese día ya '
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
                entrada.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm')
                and not (entrada.fecha_pago_obj.weekday() == 5 and entrada.jornada_pago_sabado)
                and entrada.jornada_cubre_en_pago
            ):
                jcp_coinc = str(entrada.jornada_cubre_en_pago).strip().upper()
                if jcp_coinc in ('AM', 'PM'):
                    # Fuente de verdad (estado_dia), no turnos reales: la doblada del receptor y
                    # la jornada del deudor pueden ser VIRTUALES (temporada/alternancia/festivo).
                    # Si el receptor dobla y el deudor trabaja UNA jornada contraria a la que va a
                    # cubrir, el pago es limpio → omitir la verificación clásica de coincidencia.
                    from turnos.services.turno_service import TurnoService as _TS_coinc
                    rec_dobla = _TS_coinc.estado_dia(
                        entrada.receptor, entrada.fecha_pago_obj).get('jornada') == JornadaDisplay.DOBLADA
                    sol_jorn = _TS_coinc.estado_dia(
                        entrada.solicitante, entrada.fecha_pago_obj).get('jornada')
                    if rec_dobla and sol_jorn in ('AM', 'PM') and sol_jorn != jcp_coinc:
                        omitir_coincidencia_pago = True
            if not omitir_coincidencia_pago:
                coincidencia = SolicitudValidator.validar_coincidencia_jornadas_pago(
                    entrada.solicitante,
                    entrada.receptor,
                    entrada.fecha_pago
                )
                if coincidencia['requiere_cambio_turno']:
                    return RequiereCambioTurnoPrevio(
                        'No se puede pagar trabajando dos veces la misma jornada. Debes '
                        'primero realizar un cambio de turno sencillo para tener jornada '
                        'contraria en la fecha de pago.',
                        fecha_pago=entrada.fecha_pago,
                        jornada_comun=coincidencia['jornada_comun'],
                    )
        
        return None

    @staticmethod
    def validar_dia_no_comprometido(entrada):
        """
        El dia no puede estar YA comprometido en otra solicitud APROBADA (capa L2).
        Devuelve el mensaje de error o None.

        Se consulta solo la capa de SOLICITUDES y no `estado_dia` completo, porque
        una doblada si admite temporada y festivo: mirar el estado entero rechazaria
        dias validos.

        Usa `entrada.fecha_cesion_obj` y `entrada.fecha_pago_obj` en vez de volver a
        parsear las dos fechas, como hacia el bloque original. Es el mismo valor: el
        contexto se construye con `DateUtils.parse_date` sobre esas mismas cadenas.
        """
        # L2 (fuente de verdad): el día no puede estar YA comprometido en otra solicitud
        # APROBADA (cambio descanso / d_fds / doblada / doblada permanente). Evita el
        # doble-compromiso del mismo día. (DOBLADA sí permite temporada/festivo, por eso
        # no se usa estado_dia completo, solo la capa de solicitudes.)
        from turnos.services.turno_service import TurnoService as _TSv
        _comp_ces = _TSv.dia_comprometido_por_solicitud(
            entrada.solicitante, entrada.fecha_cesion_obj, excluir_id=entrada.excluir_id)
        if _comp_ces:
            return (
                f"Ya tienes el {entrada.fecha_cesion_obj.strftime('%d/%m/%Y')} comprometido en otra "
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
            entrada.receptor, entrada.fecha_pago_obj, excluir_id=entrada.excluir_id)
        if _comp_pago:
            # EXCEPCIÓN (sábado, dos mitades al MISMO compañero): si el compromiso del compañero
            # viene de OTRA doblada TUYA que le pagas ESE MISMO sábado con la mitad CONTRARIA,
            # no está "no disponible" — lo estás relevando tú de la otra media jornada. En ese
            # caso se permite: tú terminas doblado (AM+PM) y él descansa el día completo.
            _es_complemento_sabado = False
            if entrada.fecha_pago_obj.weekday() == 5:
                _jps_nueva = str(entrada.jornada_pago_sabado or '').upper()
                if _jps_nueva in ('AM', 'PM'):
                    _contraria_nueva = 'PM' if _jps_nueva == 'AM' else 'AM'
                    _q_comp = SolicitudCambio.objects.filter(
                        explorador_solicitante=entrada.solicitante,
                        explorador_receptor=entrada.receptor,
                        tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                        estado='aprobada',
                        doblada__fecha_pago=entrada.fecha_pago_obj,
                        doblada__jornada_pago_sabado__iexact=_contraria_nueva,
                    )
                    if entrada.excluir_id:
                        _q_comp = _q_comp.exclude(id=entrada.excluir_id)
                    _es_complemento_sabado = _q_comp.exists()
            if not _es_complemento_sabado:
                return (
                    f"Tu compañero ya tiene el {entrada.fecha_pago_obj.strftime('%d/%m/%Y')} comprometido en "
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
        if entrada.fecha_pago_obj.weekday() < 5 and not SolicitudValidator.es_festivo_semana(entrada.fecha_pago_obj):
            if not _TSv.estado_dia(entrada.receptor, entrada.fecha_pago_obj).get('trabaja'):
                return (
                    f"El compañero receptor descansa el {entrada.fecha_pago_obj.strftime('%d/%m/%Y')}: ese día no "
                    f"tiene una jornada que puedas cubrir para pagarle la doblada. Elige otra fecha "
                    f"de pago en la que él trabaje."
                )

        return None

    @staticmethod
    def validar_cesion_en_festivo(entrada, es_cesion_festivo, es_pago_festivo):
        """
        Reglas propias de ceder un festivo. Devuelve el mensaje de error o None.

        En un festivo se trabaja la DOBLADA COMPLETA (AM+PM), así que la cesión es
        todo-o-nada: una cesión parcial dejaría media jornada colgando en un día que
        por rotación es doblada o descanso.

        Recibe los dos indicadores de festivo aparte y no dentro de `entrada`, por
        la misma razón que el resto de bloques: se calculan con una consulta a la
        base a mitad de `validar_solicitud`, después de validaciones que pueden
        cortar antes, y meterlos en el contexto adelantaría esas consultas.
        """
        if not (es_cesion_festivo or es_pago_festivo):
            return None

        # Se mira TAMBIÉN `jornada_cedida`: al APLICAR manda ella, no `tipo_cesion`
        # (ver doblada_aplicacion_service._aplicar_cesion), así que un
        # `cesion_completa` con `jornada_cedida='AM'` cedía media jornada del festivo
        # sin que nadie protestara.
        if es_cesion_festivo and (
            entrada.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm')
            or entrada.jornada_cedida
        ):
            return (
                f"El {entrada.fecha_cesion_obj.strftime('%d/%m/%Y')} es festivo: ese día trabajas la "
                f"doblada completa (AM + PM) y debes cederla entera. No puedes ceder solo una "
                f"mitad — elige 'ceder la doblada completa'."
            )

        # Solo puedes ceder ese festivo si tu grupo REALMENTE dobla ese día (tu
        # jornada base coincide con el grupo que dobla). Si te toca descansar (dobla
        # el grupo contrario) no tienes ninguna jornada que ceder.
        from turnos.services.turno_service import TurnoService as _TSfv
        if es_cesion_festivo and not _TSfv.dobla_en_festivo(
                entrada.solicitante, entrada.fecha_cesion_obj):
            return (
                f"No doblas el festivo {entrada.fecha_cesion_obj.strftime('%d/%m/%Y')}: ese día descansa "
                f"tu grupo (dobla el grupo contrario), así que no tienes una doblada que ceder. "
                f"Elige un festivo en el que te corresponda doblar."
            )

        # Solo traza: qué grupo dobla cada uno de los dos días. No valida nada, y por
        # eso su fallo se registra y se sigue — perder una línea de log no puede
        # tumbar una solicitud.
        try:
            from turnos.services.asignacion_especial_service import AsignacionEspecialService
            grupo_cesion = AsignacionEspecialService.grupo_trabaja(entrada.fecha_cesion_obj)
            grupo_pago = AsignacionEspecialService.grupo_trabaja(entrada.fecha_pago_obj)
            logger.info(
                f"DobladaStrategy: Cesión festiva {entrada.fecha_cesion_obj} (grupo {grupo_cesion}) "
                f"<-> Pago festivo {entrada.fecha_pago_obj} (grupo {grupo_pago})"
            )
        except Exception as e:
            logger.warning(f"Error al obtener rotación de festivos: {str(e)}", exc_info=True)

        return None

    @staticmethod
    def validar_reglas_comunes(fecha_cesion, fecha_pago, fecha_creacion_solicitud):
        """
        Reglas del TIPO de solicitud: cuándo se puede doblar, sea cual sea el
        mecanismo. Rigen tanto la cesión/pago normal como el intercambio.

        No devuelve nada: las tres validaciones lanzan `ValidationError`, que
        `validar_solicitud` traduce a `(False, mensaje)`. Se conserva esa forma en
        vez de normalizarla a "mensaje o None" como en los otros bloques extraídos,
        porque aquí no había ningún `return` que trasladar y cambiarlo habría
        mezclado un cambio de contrato con el movimiento.

        OJO CON SU POSICIÓN. Van ANTES del corte del intercambio a propósito.
        Estaban más abajo, y el `return` del intercambio las evadía: así se coló un
        sábado↔sábado. Si algún día se reordena este método, este bloque tiene que
        seguir por delante de ese corte.

        No usa `EntradaDoblada` porque se ejecuta antes de que el contexto exista:
        el contexto necesita las dos fechas ya parseadas, y `fecha_pago_obj` se
        calcula justo después de estas comprobaciones.
        """
        # Acuerdo previo obligatorio: la fecha de pago (día B) debe ser posterior a
        # la creación de la solicitud.
        SolicitudValidator.validar_acuerdo_previo_obligatorio(
            fecha_cesion,
            fecha_pago,
            fecha_creacion_solicitud
        )

        # Caso A: fecha_pago debe estar en el mismo mes que fecha_cesion
        SolicitudValidator.validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion)

        # No hay doblada en domingo ni en día de mantenimiento (festivos de semana y
        # temporada sí se permiten), en ninguna de las dos fechas.
        SolicitudValidator.validar_dias_especiales_doblada(fecha_cesion)
        SolicitudValidator.validar_dias_especiales_doblada(fecha_pago)

    @staticmethod
    def validar_pago_sabado(entrada):
        """
        Reglas del pago en sabado. Devuelve (False, mensaje) o None.

        Un sabado se reparte en dos MITADES (AM/PM), y por eso admite un SEGUNDO
        pago de doblada siempre que use la mitad libre: se termina doblado (AM+PM)
        y cada mitad paga a una persona distinta. Se bloquea si la mitad pedida ya
        esta ocupada, si el sabado esta lleno, o si este pago pide el dia completo
        con una mitad ya tomada.

        La exigencia de indicar la media jornada NO es un capricho del formulario:
        sin ese dato, ni la validacion ni la aplicacion entran en su rama de fin de
        semana y se cae a la logica de dia de semana, que usa la jornada
        predeterminada e IGNORA la alternancia de findes, dejando turnos
        incoherentes.
        """
        # Regla especial: pago en sábado (día de semana ↔ sábado)
        # ===========================
        # (fecha_pago_obj ya se parseó una sola vez en las reglas comunes.)

        # Un sábado se reparte en dos MITADES (AM/PM). Se permite un SEGUNDO pago de doblada en
        # el mismo sábado SOLO si usa la mitad LIBRE: así terminas doblado (AM+PM) y cada mitad
        # paga a una persona distinta (p. ej. cediste AM a X y PM a Y y pagas ambas ese sábado).
        # Se bloquea si la mitad que pides ya está ocupada, si el sábado ya está lleno, o si
        # este pago pide el día completo (AMBAS) con una mitad ya tomada.
        if entrada.fecha_pago_obj and entrada.fecha_pago_obj.weekday() == 5:
            _otras_pago_sab = SolicitudCambio.objects.filter(
                explorador_solicitante=entrada.solicitante,
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                estado='aprobada',
                doblada__fecha_pago=entrada.fecha_pago_obj,
            ).select_related('doblada')
            _sid = entrada.excluir_id
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
                _nueva = str(entrada.jornada_pago_sabado or '').upper()
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
                            f"Ese sábado ({entrada.fecha_pago_obj.strftime('%d/%m/%Y')}) ya pagas la jornada "
                            f"{_ocu_txt} con otra doblada. Solo queda libre la jornada {_libre_j}: "
                            f"elige {_libre_j} para pagar esta doblada, o paga en otro día."
                        )
                    return False, (
                        f"Ese sábado ({entrada.fecha_pago_obj.strftime('%d/%m/%Y')}) ya está comprometido como "
                        f"pago de otra doblada tuya (jornada {_ocu_txt}). Un sábado admite un solo pago "
                        f"por cada media jornada; elige otro día de pago."
                    )

        # Pagar en sábado EXIGE elegir la media jornada (AM/PM/AMBAS). Sin ese dato, ni la
        # validación de sábado ni la aplicación entran en su rama de fin de semana: se caía a
        # la lógica de día de semana, que usa la jornada predeterminada e IGNORA la alternancia
        # de fines de semana → turnos incoherentes. El formulario siempre lo envía; esto es el
        # guard de servidor equivalente.
        if entrada.fecha_pago_obj.weekday() == 5 and not entrada.jornada_pago_sabado:
            return False, (
                f"Para pagar el sábado {entrada.fecha_pago_obj.strftime('%d/%m/%Y')} debes indicar qué "
                f"jornada cubrirás ese día (AM, PM o ambas)."
            )

        es_pago_sabado = entrada.fecha_pago_obj.weekday() == 5 and entrada.jornada_pago_sabado

        if es_pago_sabado:
            res = DobladaFlujoValidator.validar_pago_en_sabado(
                entrada.solicitante, entrada.receptor, entrada.fecha_pago_obj,
                entrada.jornada_pago_sabado, entrada.jornada_cedida, entrada.fecha_cesion, entrada.fecha_pago_semana,
                excluir_id=entrada.excluir_id,
            )
            if res is not None:
                return res
        return None

    @staticmethod
    def validar_cobertura_en_pago(entrada):
        """
        Que jornada cubre el deudor el dia de pago, cuando el companero dobla.

        Devuelve el mensaje de error o None. Extraido de `validar_solicitud` en
        la Fase 3; la logica no cambia.

        Dos de sus reglas se apoyan en `estado_dia` y no en los turnos reales, y
        eso es deliberado: la doblada del companero puede ser VIRTUAL (temporada,
        alternancia de fin de semana, festivo) y no tener filas Turno. Mirar solo
        turnos reales disparaba un falso "el companero no tiene doblada".
        """
        # Cobertura explícita AM / PM / AMBAS cuando el receptor tiene doblada en fecha de pago (no aplica a pago sábado especial)
        if entrada.jornada_cubre_en_pago and entrada.jornada_cubre_en_pago not in ('AM', 'PM', 'AMBAS'):
            return "Valor inválido para la jornada que cubrirás en la fecha de pago."
        if entrada.fecha_pago_obj.weekday() == 5 and entrada.jornada_pago_sabado and entrada.jornada_cubre_en_pago:
            return "No uses la opción AM/PM/toda la doblada junto con el pago en sábado; elige solo la jornada del sábado."
        # La elección "¿qué cubrirás?" (jornada_cubre_en_pago) aplica siempre que el receptor
        # tenga doblada en la fecha de pago, sin importar el tipo de cesión (parcial o completa).
        if entrada.jornada_cubre_en_pago and not (
            entrada.fecha_pago_obj.weekday() == 5 and entrada.jornada_pago_sabado
        ):
            # Fuente de verdad (estado_dia), NO solo turnos reales: la doblada del receptor
            # puede ser VIRTUAL (temporada, alternancia de fin de semana, festivo) sin filas
            # Turno. Mirar solo turnos reales disparaba un falso "el compañero no tiene doblada"
            # cuando la doblada venía de temporada (mismo criterio que el deudor unas líneas más
            # abajo, que ya usa obtener_jornada_display).
            from turnos.services.turno_service import TurnoService as _TS_rec
            receptor_doblada_pago = (
                _TS_rec.estado_dia(entrada.receptor, entrada.fecha_pago_obj).get('jornada') == JornadaDisplay.DOBLADA
            )
            if entrada.jornada_cubre_en_pago and not receptor_doblada_pago:
                return (
                    "La opción de cubrir AM, PM o toda la doblada solo aplica cuando el compañero tiene "
                    "doblada (AM+PM) en la fecha de pago."
                )

            # El deudor SOLO puede cubrir la jornada CONTRARIA a la que él trabaja ese día.
            # IMPORTANTE: usar la jornada REAL del deudor (incluida la PREDETERMINADA/virtual,
            # sin fila Turno), no solo turnos explícitos. Si ese día el deudor trabaja una jornada:
            #   - No puede cubrir AMBAS (su propia jornada quedaría sin cubrir).
            #   - No puede cubrir la MISMA jornada que ya trabaja (la haría dos veces).
            if receptor_doblada_pago and entrada.jornada_cubre_en_pago:
                jcp_u = str(entrada.jornada_cubre_en_pago).strip().upper()
                from turnos.services.turno_service import TurnoService as _TS_pago
                jornada_deudor_pago = _TS_pago.obtener_jornada_display(
                    entrada.solicitante, entrada.fecha_pago_obj
                )
                if jornada_deudor_pago in ('AM', 'PM'):
                    contraria = 'PM' if jornada_deudor_pago == 'AM' else 'AM'
                    if jcp_u == 'AMBAS':
                        return (
                            f'Ese día ya trabajas tu jornada {jornada_deudor_pago}. No puedes cubrir la '
                            f'doblada completa del compañero porque tu propia jornada quedaría sin cubrir. '
                            f'Solo puedes cubrir la jornada contraria ({contraria}), o elige otra fecha de pago '
                            f'en la que estés libre.'
                        )
                    if jcp_u == jornada_deudor_pago:
                        return RequiereCambioTurnoPrevio(
                            f'La jornada que quieres cubrir ({jcp_u}) es la MISMA que ya trabajas ese día: '
                            f'no puedes hacerla dos veces. Solo puedes cubrir la jornada contraria ({contraria}). '
                            f'Si necesitas cambiar tu jornada, primero realiza un cambio de turno sencillo.',
                            fecha_pago=entrada.fecha_pago,
                            jornada_comun=jcp_u,
                        )
        return None

    @staticmethod
    def validar_intercambio(explorador_solicitante, explorador_receptor, fecha_cesion_obj, fecha_pago,
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
        if _TSint.estado_dia(explorador_solicitante, fecha_cesion_obj).get('jornada') != JornadaDisplay.DOBLADA:
            return False, (f"Para intercambiar, debes tener una DOBLADA (AM+PM) el "
                           f"{fecha_cesion_obj.strftime('%d/%m/%Y')}.")
        if _TSint.estado_dia(explorador_receptor, fp_obj).get('jornada') != JornadaDisplay.DOBLADA:
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
    def validar_pago_en_sabado(explorador_solicitante, explorador_receptor, fecha_pago_obj, jornada_pago_sabado, jornada_cedida, fecha_cesion, fecha_pago_semana, excluir_id=None) -> Optional[Tuple[bool, str]]:
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
            # Misma guarda que arriba para la cesión y el pago: `DateUtils.parse_date`
            # LANZA con basura ('31/02/2027', 'abc'), no devuelve None. Sin el try, el
            # `if not fps_obj` de aquí abajo era inalcanzable y una fecha malformada en
            # este campo subía hasta el manejador genérico y salía como 500, en vez de
            # como el mensaje de negocio que ya estaba escrito para ella. Es la tercera
            # fecha de la solicitud y fue la que se quedó sin la guarda que sí tienen las
            # otras dos.
            try:
                fps_obj = DateUtils.parse_date(fecha_pago_semana)
            except (ValueError, TypeError):
                fps_obj = None
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
                return False, RequiereCambioTurnoPrevio(
                    f"El {fps_obj.strftime('%d/%m/%Y')} tú y el compañero tienen la misma jornada "
                    f"({j_sol.nombre.upper()}). Para que él te pague (doblándose por ti) ese día deben "
                    f"quedar en jornadas contrarias. Realiza primero un cambio de turno sencillo.",
                    fecha_pago=fps_obj,
                    jornada_comun=j_sol.nombre.upper(),
                )

        return None