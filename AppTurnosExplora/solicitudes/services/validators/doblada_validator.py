from django.core.exceptions import ValidationError  # type: ignore
from empleados.models import Empleado

from .base_validator import BaseValidator


class DobladaValidator:
    """Validaciones específicas de la Doblada (cesión de jornada con pago posterior)."""

    @staticmethod
    def validar_acuerdo_previo_obligatorio(fecha_cesion, fecha_pago, fecha_creacion_solicitud=None):
        """
        Validar que existe un acuerdo previo obligatorio para la doblada.

        Reglas:
        - fecha_pago es obligatoria
        - fecha_pago debe ser posterior a la fecha de creación de la solicitud
        - fecha_pago puede ser ANTES de fecha_cesion (el receptor puede pagar antes)

        Args:
            fecha_cesion: Fecha en que se cede la jornada
            fecha_pago: Fecha acordada para pagar
            fecha_creacion_solicitud: Fecha de creación de la solicitud (opcional, si no se proporciona usa hoy)

        Raises:
            ValidationError: Si no se cumple el acuerdo previo
        """
        from datetime import date
        from core.utils.date_utils import DateUtils

        if not fecha_pago:
            raise ValidationError('La fecha de pago es obligatoria. No existen dobladas abiertas.')

        fecha_pago_obj = DateUtils.parse_date(fecha_pago)

        # Si no se proporciona fecha_creacion_solicitud, usar hoy
        if fecha_creacion_solicitud:
            fecha_creacion_obj = DateUtils.parse_date(fecha_creacion_solicitud)
        else:
            fecha_creacion_obj = date.today()

        # Validar que fecha_pago sea posterior a fecha_creacion_solicitud
        if fecha_pago_obj <= fecha_creacion_obj:
            raise ValidationError(
                f'La fecha de pago ({fecha_pago_obj.strftime("%d/%m/%Y")}) debe ser posterior a la fecha de creación de la solicitud ({fecha_creacion_obj.strftime("%d/%m/%Y")})'
            )

    @staticmethod
    def validar_fecha_pago_diferente_cesion(fecha_cesion, fecha_pago):
        """
        Validar que fecha_pago sea diferente a fecha_cesion.

        Regla: No se puede pagar el mismo día que se cede la jornada.
        El pago puede ser ANTES o DESPUÉS de la cesión, pero nunca el mismo día.

        Ejemplo válido: cedo el 28/02, pago el 20/02 (antes está permitido).
        Ejemplo inválido: cedo el 20/02, pago el 20/02 (mismo día → bloqueado).

        Raises:
            ValidationError: Si fecha_pago == fecha_cesion
        """
        from core.utils.date_utils import DateUtils
        fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)
        fecha_pago_obj = DateUtils.parse_date(fecha_pago)

        if fecha_pago_obj == fecha_cesion_obj:
            raise ValidationError(
                f'La fecha de pago ({fecha_pago_obj.strftime("%d/%m/%Y")}) no puede ser '
                f'la misma que la fecha de cesión ({fecha_cesion_obj.strftime("%d/%m/%Y")}). '
                'Si cedes tu jornada ese día, no puedes trabajar y descansar al mismo tiempo.'
            )

    @staticmethod
    def validar_jornadas_contrarias_doblada(solicitante: Empleado, receptor: Empleado, fecha, jornada_cedida=None):
        """
        Validar que las jornadas sean contrarias para una doblada.

        Reglas:
        - Si solicitante tiene AM → receptor debe tener PM
        - Si solicitante tiene PM → receptor debe tener AM
        - Si solicitante está en doblada → puede solicitar a AM o PM según jornada_cedida

        Args:
            solicitante: Explorador que solicita la doblada
            receptor: Explorador que cubrirá la doblada
            fecha: Fecha de la doblada
            jornada_cedida: 'AM' o 'PM' (opcional, si solicitante está en doblada)

        Raises:
            ValidationError: Si las jornadas no son contrarias
        """
        from core.utils.date_utils import DateUtils
        from turnos.services.jornada_service import JornadaService
        from turnos.models import Turno

        fecha_obj = DateUtils.parse_date(fecha)
        fecha_str = fecha_obj.strftime('%Y-%m-%d')

        # Obtener jornada del solicitante (predeterminada, para el NOMBRE en la regla de contrarias)
        jornada_solicitante = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha_str)
        # ¿Trabaja REALMENTE ese día? Considera TODO descanso: fin de semana por alternancia,
        # descanso de semana manual y mantenimiento (la jornada predeterminada no los refleja).
        sol_trabaja = BaseValidator._explorador_trabaja(solicitante, fecha_obj)
        rec_trabaja = BaseValidator._explorador_trabaja(receptor, fecha_obj)

        # Si solicitante está en doblada, usar jornada_cedida
        if jornada_cedida:
            # Verificar si realmente está en doblada (tiene AM y PM)
            turnos_solicitante = Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_obj
            ).select_related('jornada')

            jornadas_solicitante = [t.jornada.nombre.upper() for t in turnos_solicitante]
            tiene_doblada = 'AM' in jornadas_solicitante and 'PM' in jornadas_solicitante

            if tiene_doblada:
                jornada_a_ceder = jornada_cedida.upper()
            else:
                # No está en doblada: debe TRABAJAR ese día para tener una jornada que ceder.
                if not sol_trabaja:
                    raise ValidationError('El solicitante no tiene jornada asignada para esa fecha')
                jornada_a_ceder = jornada_solicitante.nombre.upper()
        else:
            # No hay jornada_cedida: debe trabajar ese día para ceder.
            if not sol_trabaja:
                raise ValidationError('El solicitante no tiene jornada asignada para esa fecha')
            jornada_a_ceder = jornada_solicitante.nombre.upper()

        # Receptor: ¿trabaja realmente ese día? (considera descanso de fin de semana)
        if not rec_trabaja:
            # CASO 3 / 6: receptor en descanso (sin jornada efectiva) en fecha de cesión;
            # la cesión queda cubierta por el acuerdo de pago en otra fecha.
            if jornada_a_ceder in ('AM', 'PM'):
                return
            raise ValidationError('El receptor no tiene jornada asignada para esa fecha')
        jornada_receptor = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha_str)

        jornada_receptor_nombre = jornada_receptor.nombre.upper()

        # Validar que sean contrarias
        if jornada_a_ceder == 'AM' and jornada_receptor_nombre != 'PM':
            raise ValidationError(
                f'Para ceder jornada AM, el receptor debe tener jornada PM. El receptor tiene {jornada_receptor_nombre}'
            )
        elif jornada_a_ceder == 'PM' and jornada_receptor_nombre != 'AM':
            raise ValidationError(
                f'Para ceder jornada PM, el receptor debe tener jornada AM. El receptor tiene {jornada_receptor_nombre}'
            )

    @staticmethod
    def validar_no_triple_turno(receptor: Empleado, fecha):
        """
        Validar que el receptor no tenga doblada activa (evitar triple turno).

        Args:
            receptor: Explorador receptor
            fecha: Fecha a validar

        Raises:
            ValidationError: Si el receptor ya tiene doblada activa
        """
        try:
            BaseValidator.validar_no_doblada_activa(receptor, fecha)
        except ValidationError:
            raise ValidationError(
                'El receptor no puede tener doblada el día de la cesión.'
            ) from None

    @staticmethod
    def validar_dias_especiales_doblada(fecha):
        """
        Validar que la fecha no sea domingo ni mantenimiento.

        Los festivos de lunes a viernes y los días de temporada están permitidos
        (se pueden realizar solicitudes de doblada en temporada).

        Reglas:
        - No doblada en domingos ni mantenimiento.
        - Festivos (lunes a viernes) y temporada: permitidos.

        Args:
            fecha: Fecha a validar

        Raises:
            ValidationError: Si la fecha es domingo o mantenimiento
        """
        from core.utils.date_utils import DateUtils
        from turnos.models import DiaEspecial

        fecha_obj = DateUtils.parse_date(fecha)

        if fecha_obj.weekday() == 6:
            raise ValidationError('No se puede realizar doblada en domingos')

        # La temporada manda: un día de mantenimiento que cae en temporada NO es mantenimiento.
        if DiaEspecial.es_mantenimiento_efectivo(fecha_obj):
            raise ValidationError('No se puede realizar doblada en días de mantenimiento')

        # NOTA: Días de temporada y festivos de semana están permitidos para doblada

    @staticmethod
    def validar_festivos_mismo_mes(fecha1, fecha2):
        """
        Valida que dos fechas festivas sean del mismo mes calendario.
        Se usa para restringir cambios/pagos de dobladas entre festivos.

        Regla de negocio:
        - Los cambios de turno y pagos de dobladas entre festivos solo se permiten
          cuando ambas fechas festivas pertenecen al mismo mes calendario.

        Args:
            fecha1: Primera fecha (date o string YYYY-MM-DD)
            fecha2: Segunda fecha (date o string YYYY-MM-DD)

        Raises:
            ValidationError: Si alguna fecha no es festivo de semana o si no son del mismo mes
        """
        from datetime import datetime

        if isinstance(fecha1, str):
            fecha1_obj = datetime.strptime(fecha1, '%Y-%m-%d').date()
        else:
            fecha1_obj = fecha1

        if isinstance(fecha2, str):
            fecha2_obj = datetime.strptime(fecha2, '%Y-%m-%d').date()
        else:
            fecha2_obj = fecha2

        # Verificar que ambas sean festivos de semana
        if not BaseValidator.es_festivo_semana(fecha1_obj):
            raise ValidationError(
                f'La fecha {fecha1_obj.strftime("%d/%m/%Y")} no es un festivo de lunes a viernes.'
            )

        if not BaseValidator.es_festivo_semana(fecha2_obj):
            raise ValidationError(
                f'La fecha {fecha2_obj.strftime("%d/%m/%Y")} no es un festivo de lunes a viernes.'
            )

        # Validar que sean del mismo mes calendario
        if fecha1_obj.year != fecha2_obj.year or fecha1_obj.month != fecha2_obj.month:
            raise ValidationError(
                f'Los cambios y pagos de dobladas entre festivos solo se permiten cuando ambas fechas '
                f'pertenecen al mismo mes. Las fechas {fecha1_obj.strftime("%d/%m/%Y")} y '
                f'{fecha2_obj.strftime("%d/%m/%Y")} están en meses diferentes.'
            )

    @staticmethod
    def validar_ambos_descansando_fecha_pago(solicitante: Empleado, receptor: Empleado, fecha_pago):
        """
        Caso 1.2: Rechazar cuando deudor y acreedor están descansando en la fecha de pago.
        Si ninguno trabaja en fecha_pago (cualquier tipo de descanso), no se puede pagar.

        Args:
            solicitante: Explorador deudor (emisor)
            receptor: Explorador acreedor
            fecha_pago: Fecha de pago (string o date)

        Raises:
            ValidationError: Si ambos están descansando en fecha_pago
        """
        from core.utils.date_utils import DateUtils

        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        # _explorador_trabaja considera TODO descanso (fin de semana, semana manual, mantenimiento).
        if (not BaseValidator._explorador_trabaja(solicitante, fecha_pago_obj)
                and not BaseValidator._explorador_trabaja(receptor, fecha_pago_obj)):
            raise ValidationError(
                'Los dos están descansando en la fecha de pago. No se puede realizar el pago en esa fecha. '
                'Elige otra fecha de pago.'
            )

    @staticmethod
    def validar_receptor_tiene_jornada_en_fecha_pago(receptor: Empleado, fecha_pago):
        """
        Casos 1.5/1.8: Rechazar cuando el receptor (acreedor) no tiene turno/jornada en fecha de pago.
        Si el receptor está descansando ese día, no se le puede pagar.

        Args:
            receptor: Explorador acreedor (receptor)
            fecha_pago: Fecha de pago (string o date)

        Raises:
            ValidationError: Si el receptor no tiene jornada en fecha_pago
        """
        from core.utils.date_utils import DateUtils

        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        # _explorador_trabaja considera TODO descanso (fin de semana por alternancia, descanso de
        # semana manual y mantenimiento). Si el receptor no trabaja, no hay jornada que cubrir.
        if not BaseValidator._explorador_trabaja(receptor, fecha_pago_obj):
            raise ValidationError(
                f'El receptor ({receptor.nombre} {receptor.apellido}) no trabaja en la fecha de pago '
                f'({fecha_pago_obj.strftime("%d/%m/%Y")}): ese día descansa, así que no hay jornada que '
                f'cubrir y no se le puede pagar. Elige otra fecha de pago en la que el receptor sí trabaje.'
            )

    @staticmethod
    def validar_receptor_no_descansa_por_doblada_en_pago(receptor: Empleado, fecha_pago):
        """
        Caso F: El receptor no puede estar descansando en la fecha de pago por
        haber cedido su propia jornada (doblada aprobada como solicitante).

        Regla de negocio: Si el receptor ya cedió su jornada ese día (doblada aprobada),
        está descansando y no puede trabajar para pagar otra doblada.

        Args:
            receptor: Empleado que sería el receptor del pago
            fecha_pago: Fecha de pago (string o date)

        Raises:
            ValidationError: Si el receptor ya descansa por una doblada aprobada en fecha_pago
        """
        from datetime import datetime
        from solicitudes.models import SolicitudCambio

        if isinstance(fecha_pago, str):
            fecha_pago_obj = datetime.strptime(fecha_pago, '%Y-%m-%d').date()
        else:
            fecha_pago_obj = fecha_pago

        descansa_por_doblada = SolicitudCambio.objects.filter(
            explorador_solicitante=receptor,
            tipo_cambio__nombre='DOBLADA',
            estado='aprobada',
            fecha_cambio_turno=fecha_pago_obj
        ).exists()

        if descansa_por_doblada:
            raise ValidationError(
                f'El compañero receptor ya cedió su jornada el {fecha_pago_obj.strftime("%d/%m/%Y")} '
                '(tiene una doblada aprobada como solicitante en esa fecha) y estará descansando. '
                'No puede trabajar para pagar otra doblada el mismo día que está descansando.'
            )

    @staticmethod
    def validar_coincidencia_jornadas_pago(deudor: Empleado, acreedor: Empleado, fecha_pago):
        """
        Validar caso crítico: coincidencia de jornadas al pagar deuda.

        Si deudor y acreedor tienen la misma jornada en fecha de pago (ya sea de turno asignado
        o jornada predeterminada), no se puede pagar trabajando dos veces la misma jornada.

        La validación considera:
        1. Primero: Turnos asignados en tabla turnos_turno para esa fecha
        2. Si no hay turno: Jornada predeterminada de AsignarJornadaExplorador

        Args:
            deudor: Explorador deudor
            acreedor: Explorador acreedor
            fecha_pago: Fecha de pago

        Returns:
            dict con:
                - coinciden: bool
                - jornada_comun: str ('AM' o 'PM') si coinciden
                - requiere_cambio_turno: bool
        """
        import logging
        from core.utils.date_utils import DateUtils
        from turnos.services.jornada_service import JornadaService
        from turnos.models import Turno

        logger = logging.getLogger(__name__)

        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        fecha_pago_str = fecha_pago_obj.strftime('%Y-%m-%d')

        # ===========================
        # Pago en SÁBADO: no aplica la coincidencia de "misma jornada"
        # ===========================
        # La regla de "no se puede pagar trabajando dos veces la misma jornada" es un concepto
        # de DÍA DE SEMANA, donde cada explorador tiene una jornada fija (AM o PM). En un SÁBADO
        # la jornada la gobierna la ALTERNANCIA de fines de semana: el explorador o DESCANSA
        # (y entonces paga eligiendo libremente AM/PM/AMBAS, sin conflicto posible) o trabaja la
        # doblada completa (AM+PM, que se valida aparte como 'doblada activa'). Por eso, usar la
        # jornada PREDETERMINADA (que ignora el descanso de fin de semana) daba falsos positivos
        # como "ambos tienen PM" cuando en realidad ambos descansan ese sábado.
        if fecha_pago_obj.weekday() == 5:
            logger.info(
                "Validación coincidencia jornadas pago - OMITIDA por pago en sábado (alternancia)",
                extra={'deudor_id': deudor.id, 'acreedor_id': acreedor.id, 'fecha_pago': fecha_pago_str},
            )
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False,
            }

        # ===========================
        # DEUDOR LIBRE ese día: no hay "misma jornada"
        # ===========================
        # La regla de coincidencia compara la jornada PREDETERMINADA del deudor con la del acreedor.
        # Pero si el deudor DESCANSA ese día (fin de semana, temporada, descanso por otra solicitud),
        # no trabaja su base: simplemente cubre la jornada del acreedor sin doblar → nunca hay colisión.
        # Usar la base daba falsos positivos ("ambos AM") aunque el deudor esté libre.
        from turnos.services.turno_service import TurnoService as _TS_coinc
        if not _TS_coinc.estado_dia(deudor, fecha_pago_obj).get('trabaja'):
            logger.info(
                "Validación coincidencia jornadas pago - OMITIDA: el deudor descansa ese día",
                extra={'deudor_id': deudor.id, 'acreedor_id': acreedor.id, 'fecha_pago': fecha_pago_str},
            )
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False,
            }

        # ===========================
        # ACREEDOR LIBRE ese día: tampoco hay "misma jornada"
        # ===========================
        # Si el ACREEDOR (compañero) DESCANSA ese día, no tiene una jornada REAL con la que colisionar:
        # comparar contra su jornada PREDETERMINADA daba el falso positivo "ambos PM" y mostraba el
        # confuso aviso "trabajarías dos veces la misma jornada". El caso "el compañero descansa" se
        # rechaza aparte con un mensaje CLARO (guard del receptor en la estrategia); aquí solo se evita
        # que la coincidencia dispare un mensaje equivocado. Fuente de verdad: estado_dia.
        if not _TS_coinc.estado_dia(acreedor, fecha_pago_obj).get('trabaja'):
            logger.info(
                "Validación coincidencia jornadas pago - OMITIDA: el acreedor descansa ese día",
                extra={'deudor_id': deudor.id, 'acreedor_id': acreedor.id, 'fecha_pago': fecha_pago_str},
            )
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False,
            }

        # Obtener todos los turnos del deudor en fecha de pago para detectar dobladas
        turnos_deudor = Turno.objects.filter(explorador=deudor, fecha=fecha_pago_obj).select_related('jornada')
        turnos_acreedor = Turno.objects.filter(explorador=acreedor, fecha=fecha_pago_obj).select_related('jornada')

        # Verificar si el deudor tiene doblada (AM y PM en la misma fecha)
        jornadas_deudor = [t.jornada.nombre.upper() for t in turnos_deudor]
        tiene_doblada_deudor = 'AM' in jornadas_deudor and 'PM' in jornadas_deudor

        # Verificar si el acreedor tiene doblada en fecha de pago.
        # Si es así, el deudor siempre puede pagar la jornada que debe (Casos 1.7, 3.7, 4.5, 6.7):
        # no aplica validación de coincidencia porque el receptor cederá la jornada que el deudor le paga
        # y se queda con la otra — nunca hay colisión.
        jornadas_acreedor_lista = [t.jornada.nombre.upper() for t in turnos_acreedor]
        tiene_doblada_acreedor = 'AM' in jornadas_acreedor_lista and 'PM' in jornadas_acreedor_lista
        if tiene_doblada_acreedor:
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False
            }

        # Si el deudor tiene doblada, puede pagar cualquier deuda (tiene ambas jornadas)
        if tiene_doblada_deudor:
            logger.info("Validación coincidencia jornadas pago - Deudor tiene doblada", extra={
                'deudor_id': deudor.id,
                'deudor_nombre': f"{deudor.nombre} {deudor.apellido}",
                'fecha_pago': fecha_pago_str,
                'jornadas_deudor': jornadas_deudor
            })
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False
            }

        # Obtener jornadas (ya considera turnos primero, luego predeterminada)
        jornada_deudor = JornadaService.get_jornada_explorador_fecha(deudor.id, fecha_pago_str)
        jornada_acreedor = JornadaService.get_jornada_explorador_fecha(acreedor.id, fecha_pago_str)

        # Verificar si hay turnos asignados para diagnosticar la fuente
        turno_deudor = turnos_deudor.first()
        turno_acreedor = turnos_acreedor.first()

        fuente_deudor = 'Turno asignado' if turno_deudor else 'Jornada predeterminada'
        fuente_acreedor = 'Turno asignado' if turno_acreedor else 'Jornada predeterminada'

        # Logging detallado para diagnóstico
        logger.info("Validación coincidencia jornadas pago - Inicio", extra={
            'deudor_id': deudor.id,
            'deudor_nombre': f"{deudor.nombre} {deudor.apellido}",
            'acreedor_id': acreedor.id,
            'acreedor_nombre': f"{acreedor.nombre} {acreedor.apellido}",
            'fecha_pago': fecha_pago_str,
            'jornada_deudor': jornada_deudor.nombre if jornada_deudor else None,
            'jornada_acreedor': jornada_acreedor.nombre if jornada_acreedor else None,
            'fuente_deudor': fuente_deudor,
            'fuente_acreedor': fuente_acreedor,
            'turno_deudor_id': turno_deudor.id if turno_deudor else None,
            'turno_acreedor_id': turno_acreedor.id if turno_acreedor else None,
            'tiene_doblada_deudor': tiene_doblada_deudor,
            'jornadas_deudor': jornadas_deudor
        })

        if not jornada_deudor or not jornada_acreedor:
            logger.warning("Validación coincidencia jornadas pago - Sin jornada", extra={
                'deudor_tiene_jornada': jornada_deudor is not None,
                'acreedor_tiene_jornada': jornada_acreedor is not None
            })
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False
            }

        coinciden = jornada_deudor.nombre.upper() == jornada_acreedor.nombre.upper()

        resultado = {
            'coinciden': coinciden,
            'jornada_comun': jornada_deudor.nombre.upper() if coinciden else None,
            'requiere_cambio_turno': coinciden
        }

        # Logging del resultado
        if coinciden:
            logger.warning("Validación coincidencia jornadas pago - COINCIDENCIA DETECTADA", extra={
                'jornada_comun': resultado['jornada_comun'],
                'deudor': f"{deudor.nombre} {deudor.apellido}",
                'acreedor': f"{acreedor.nombre} {acreedor.apellido}",
                'fecha_pago': fecha_pago_str,
                'fuente_deudor': fuente_deudor,
                'fuente_acreedor': fuente_acreedor
            })
        else:
            logger.info("Validación coincidencia jornadas pago - Jornadas contrarias (OK)", extra={
                'jornada_deudor': jornada_deudor.nombre,
                'jornada_acreedor': jornada_acreedor.nombre
            })

        return resultado
