"""
ReprogramacionDobladaService

Gestiona el imprevisto de que UNA persona no pueda cumplir SU día de doblada en una doblada
ya aprobada (enfermedad, incapacidad…). Es simétrico (sirve para el solicitante o el receptor)
y NUNCA afecta al otro explorador. Todo queda en registro para auditoría:
- El día no cumplido se ANULA (soft-delete del Turno, ver Turno.anulado) y se le resta su deuda
  de 30 min (DeudaCorporativa → cancelada). Nada se borra físicamente.
- Al PROGRAMAR el día nuevo, la persona dobla esa fecha (tipo 'PAGO REPROGRAMADO') y se le vuelve
  a agregar la deuda de 30 min en la fecha real. Neto: 1 sola deuda de 30 min, en el día que sí dobla.

Para deshacer TODO el acuerdo se usa la cancelación mutua ya existente, permitida solo mientras
NADIE haya cumplido su día (ver `puede_cancelar`).
"""
import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from core.constants import JornadaDisplay, TipoCambioTurno, TipoSolicitud
from solicitudes.models import ReprogramacionDiaDoblada, SolicitudCambio

from .d_fds_aplicacion_service import DFDSAplicacionService
from .deuda_corporativa_service import DeudaCorporativaService
from .doblada_aplicacion_service import DobladaAplicacionService

logger = logging.getLogger(__name__)

# "No me pasaron el acuerdo del día" — distinto de None, que significa "ese día no tiene ninguno".
# El calendario precarga el mes entero y pasa None para los días sin acuerdo; quien no precarga
# (el POST) deja el centinela y la búsqueda se hace sola, y solo cuando hay que redactar un
# rechazo. Así el camino feliz no paga ninguna consulta extra.
_ACUERDO_NO_PRECARGADO = object()


class ReprogramacionDobladaService:

    @staticmethod
    def _dia_doblada_de(solicitud: SolicitudCambio, explorador) -> date:
        """El día en que `explorador` se dobla en una DOBLADA sencilla: el receptor dobla en la
        fecha de cesión; el solicitante dobla en la fecha de pago."""
        detalle = solicitud.doblada
        if explorador.id == solicitud.explorador_receptor_id:
            return solicitud.fecha_cambio_turno
        if explorador.id == solicitud.explorador_solicitante_id:
            return detalle.fecha_pago
        raise ValueError('El explorador no participa en esta doblada.')

    @staticmethod
    def _fechas_activas_perm(explorador, det, lado: str) -> list:
        """Fechas en que `explorador` SE DOBLA en una doblada permanente (receptor en cesión;
        solicitante en devolución) y que siguen ACTIVAS (doblada PERM sin anular). Sirve para que
        el supervisor elija cuál día específico no se cumplió."""
        from turnos.models import Turno
        fechas_txt = det.fechas_cesion if lado == 'cesion' else det.fechas_devolucion
        fechas = []
        for s in (fechas_txt or '').split(','):
            s = s.strip()
            if s:
                try:
                    fechas.append(date.fromisoformat(s))
                except ValueError:
                    # Estas fechas vienen de la BASE DE DATOS, no del formulario: que una no
                    # parsee es dato corrupto, no entrada del usuario. Se sigue con las que sí
                    # valen (comportamiento original), pero se registra: la reprogramación
                    # estaría operando sobre menos días de los que la solicitud tiene guardados.
                    logger.warning('Fecha corrupta %r en fechas_%s del detalle id=%s; se omite',
                                   s, lado, getattr(det, 'pk', '?'))
        # Legacy (patrón por weekday, sin fechas): usar las dobladas PERM aplicadas en el rango.
        if not fechas:
            fechas = list(Turno.objects.filter(
                explorador=explorador, tipo_cambio=TipoCambioTurno.DOBLADA_PERM,
                fecha__range=(det.fecha_inicio, det.fecha_fin)).values_list('fecha', flat=True))
        activas = set(Turno.objects.filter(
            explorador=explorador, tipo_cambio=TipoCambioTurno.DOBLADA_PERM, fecha__in=fechas
        ).values_list('fecha', flat=True))
        return sorted(f for f in fechas if f in activas)

    @staticmethod
    def _fechas_activas_sencilla(explorador, fechas: list) -> list:
        """De las fechas en que `explorador` se dobla en una DOBLADA / D FDS sencilla, deja solo
        las que SIGUEN VIVAS (turno de doblada activo).

        Un día ya anulado —porque su inasistencia ya se registró, o porque otra solicitud aprobada
        después le quitó la doblada— no se puede volver a reprogramar: no hay doblada que incumplir.
        Sin este filtro el supervisor veía el día en 'Reprogramar' y registraba una inasistencia
        fantasma sobre un día que ya no debía nada. (Mismo criterio que `_fechas_activas_perm`;
        `Turno.objects` ya excluye los anulados.)"""
        from turnos.models import Turno
        activas = set(Turno.objects.filter(
            explorador=explorador, fecha__in=fechas,
            tipo_cambio__in=[TipoCambioTurno.DOBLADA, TipoCambioTurno.D_FDS, TipoCambioTurno.PAGO_REPROGRAMADO],
        ).values_list('fecha', flat=True))
        return [f for f in fechas if f in activas]

    @staticmethod
    def participantes_y_dias(solicitud: SolicitudCambio) -> list:
        """[(rol, explorador, [fechas de doblada reprogramables])] para DOBLADA, D FDS o DOBLADA
        PERMANENTE. En las sencillas cada uno tiene 1 día; en permanente, varias fechas específicas.

        D FDS comparte estructura con DOBLADA (mismo `DobladaDetalle`: el receptor dobla en la
        fecha de cesión y el solicitante en la de pago), así que entra por la misma rama. Lo que
        cambia es el DÍA DE COMPENSACIÓN, que en finde tiene sus propias reglas — ver `programar`.
        """
        tipo = solicitud.tipo_cambio.nombre
        if tipo in (TipoSolicitud.DOBLADA, TipoSolicitud.D_FDS):
            det = solicitud.doblada
            _act = ReprogramacionDobladaService._fechas_activas_sencilla
            return [
                ('receptor', solicitud.explorador_receptor,
                 _act(solicitud.explorador_receptor, [solicitud.fecha_cambio_turno])),
                ('solicitante', solicitud.explorador_solicitante,
                 _act(solicitud.explorador_solicitante, [det.fecha_pago])),
            ]
        if tipo == TipoSolicitud.DOBLADA_PERMANENTE:
            det = solicitud.doblada_permanente
            return [
                ('receptor', solicitud.explorador_receptor,
                 ReprogramacionDobladaService._fechas_activas_perm(solicitud.explorador_receptor, det, 'cesion')),
                ('solicitante', solicitud.explorador_solicitante,
                 ReprogramacionDobladaService._fechas_activas_perm(solicitud.explorador_solicitante, det, 'devolucion')),
            ]
        return []

    @staticmethod
    def _jornada_debida(explorador, fecha) -> str | None:
        """
        Jornada que la persona quedó debiendo = la CONTRARIA a la que REALMENTE tenía ese día.

        Se lee de la FUENTE DE VERDAD `TurnoService.estado_dia`, no de `AsignarJornadaExplorador`
        (la jornada PREDETERMINADA), que es lo que hacía antes: si el día no cumplido tenía un
        cambio de turno, la predeterminada dice AM cuando la persona en realidad trabajaba PM, y
        la jornada debida quedaba invertida.

        Se llama DESPUÉS de `anular_doblada_de_un_dia` (ver `registrar_inasistencia`), así que
        `estado_dia` ya devuelve la jornada única restaurada de ese día — justo la que se debía
        haber doblado. Devuelve None si ese día no hay una jornada única (descanso o doblada que
        no se pudo anular).
        """
        from turnos.services.turno_service import TurnoService

        real = TurnoService.estado_dia(explorador, fecha).get('jornada')
        if real == 'AM':
            return 'PM'
        if real == 'PM':
            return 'AM'
        return None

    @staticmethod
    def _validar_dia_compensacion_finde(explorador, fecha_nueva: date, fecha_original: date) -> None:
        """
        Reglas del día con el que se compensa una D FDS no cumplida. Lanza ValueError con el
        motivo, o no hace nada si el día sirve.

        Qué se está compensando: la persona debía trabajar un día de FIN DE SEMANA que no era suyo
        y no lo hizo, así que ese turno se quedó corto. Lo devuelve trabajando otro día de finde
        que tenía libre. El compañero NO entra: su descanso ya lo tuvo el día original.
        """
        from turnos.services.turno_service import TurnoService

        if fecha_nueva.weekday() not in (5, 6):
            raise ValueError(
                'El día de compensación de una Doblada de Fin de Semana debe ser un sábado o un '
                'domingo. Elige un día de fin de semana.'
            )

        # Mismo día de la semana: es la regla que mantiene intacta la cantidad de sábados y de
        # domingos de cada persona en el mes (los domingos se pagan distinto).
        if fecha_nueva.weekday() != fecha_original.weekday():
            dia = 'domingo' if fecha_original.weekday() == 6 else 'sábado'
            raise ValueError(
                f'El día que no se cumplió era un {dia}: la compensación también debe ser un '
                f'{dia}, para no alterar su cantidad de {dia}s del mes.'
            )

        estado = TurnoService.estado_dia(explorador, fecha_nueva)
        if estado.get('trabaja'):
            raise ValueError(
                f'Esa persona ya trabaja el {fecha_nueva.strftime("%d/%m/%Y")}; no puede doblarse '
                'de nuevo. Elige un día de fin de semana en el que descanse.'
            )

        # Estar libre no basta: si ese día lo CEDIÓ en otra solicitud, hay un compañero cubriéndolo
        # COMO EXTRA. Trabajarlo dejaría a dos personas en el mismo turno y desperdiciaría el favor.
        # (Un descanso por CAMBIO DE DESCANSO no estorba: es un intercambio ya saldado y quien
        # trabaja ese día lo hace en su lugar, no de más. Mismo criterio que la validación de la
        # fecha de pago en `d_fds_strategy`.)
        comprometido = TurnoService.dia_comprometido_por_solicitud(explorador, fecha_nueva)
        if (comprometido and comprometido.get('tipo') == 'cedio'
                and comprometido.get('origen') != 'cambio_descanso'):
            motivo = comprometido.get('motivo') or 'ya lo cedió'
            raise ValueError(
                f'El {fecha_nueva.strftime("%d/%m/%Y")} esa persona ya se lo cedió a un compañero '
                f'({motivo}), que lo está cubriendo. Elige otro día de fin de semana.'
            )

    @staticmethod
    def es_dfds(reprog: ReprogramacionDiaDoblada) -> bool:
        """La doblada de origen es de FIN DE SEMANA (reglas de compensación propias)."""
        tipo = getattr(reprog.doblada_origen, 'tipo_cambio', None)
        return bool(tipo) and tipo.nombre == TipoSolicitud.D_FDS

    # ------------------------------------------------------------------ motivo del rechazo

    @staticmethod
    def _nombre(persona) -> str:
        """Nombre presentable de un explorador. Acepta el str que trae `AcuerdoPorDiaService`,
        el dict `companero` de `estado_dia`, o el propio modelo."""
        if isinstance(persona, str):
            return persona.strip() or 'un compañero'
        if isinstance(persona, dict):
            return (persona.get('nombre') or '').strip() or 'un compañero'
        nombre = f"{getattr(persona, 'nombre', '') or ''} {getattr(persona, 'apellido', '') or ''}"
        return nombre.strip() or 'un compañero'

    @staticmethod
    def motivo_dia_no_apto(explorador, fecha: date, acuerdo=_ACUERDO_NO_PRECARGADO) -> str | None:
        """
        Razón DETALLADA, en tercera persona (la lee el supervisor), por la que `fecha` no sirve
        para pagar la doblada; None si sí sirve.

        Existe porque el mensaje anterior era una lista de cuatro causas metidas en una sola
        frase —"ya dobla, descansa, es festivo/fin de semana, o no tiene turno"— que se mostraba
        en TODOS los rechazos, incluidos aquellos en los que ninguna de las cuatro era cierta.
        Caso real (reprogramación 12, septiembre de 2026): el 15 y el 18 la persona tenía jornada
        única AM —la propia pantalla lo mostraba en la columna "Jornada real"— y el bloqueo venía
        de la puerta de calendario por descanso de temporada. El supervisor leía "ya dobla" al
        lado de una celda que decía "AM", sin forma de saber qué pasaba.

        Recorre las causas en el MISMO orden que `jornada_doblada_perm`, que es quien decide de
        verdad: primero el calendario (`dia_calendario_no_apto`) y después el estado real del
        día (`estado_dia`). Que ambos no se separen con el tiempo lo fija
        `test_motivo_y_veredicto_no_divergen`.

        Responde solo por la reprogramación ENTRE SEMANA (la que exige jornada única). Una D FDS
        se compensa trabajando un día de finde libre y tiene sus propias reglas y sus propios
        mensajes en `_validar_dia_compensacion_finde`; `validar_dia_pago` nunca llega aquí en
        ese caso.

        `acuerdo` es la entrada de `AcuerdoPorDiaService.en_fecha`/`en_rango` para ese día (la
        misma que enriquece Mis Turnos): permite nombrar la solicitud y el compañero. El
        calendario la trae precargada del mes entero, así que pasarla aquí no cuesta consultas.
        """
        from solicitudes.services.acuerdo_por_dia_service import AcuerdoPorDiaService
        from solicitudes.services.cambios_permanentes_helper import dia_calendario_no_apto
        from turnos.services.descanso_semana_service import DescansoSemanaService
        from turnos.services.turno_service import TurnoService

        if acuerdo is _ACUERDO_NO_PRECARGADO:
            acuerdo = AcuerdoPorDiaService.en_fecha(explorador, fecha)

        f = fecha.strftime('%d/%m/%Y')

        calendario = dia_calendario_no_apto(fecha)
        if calendario == 'mantenimiento':
            return f'El {f} es día de mantenimiento: nadie trabaja, así que no hay jornada que doblar.'
        if calendario == 'festivo':
            return f'El {f} es festivo: ese día el grupo que rota trabaja AM + PM, no media jornada.'
        if calendario == 'temporada':
            jornadas = DescansoSemanaService.jornadas_descanso_temporada(fecha)
            if jornadas:
                # Los DOS días de descanso que el supervisor fija son territorio exclusivo del
                # formulario de CAMBIO DESCANSO, que obliga a compensar dentro de la misma
                # semana. Una doblada paga en cualquier fecha, así que rompería ese cómputo.
                # Se nombra la jornada porque el veto es POR FECHA: alcanza también a quien ese
                # día trabaja con normalidad, y sin decirlo el bloqueo parece arbitrario.
                texto = (
                    f'El {f} es un día de descanso de temporada (descanso de la jornada '
                    f'{" y ".join(jornadas)}). Esos días solo se mueven desde "Cambio de Día de '
                    f'Descanso", que tiene las cinco opciones para hacerlo (intercambiar el día, '
                    f'jornadas partidas, que le cubran su día, cambio de doblada o permiso de '
                    f'media jornada) y obliga a compensar en la misma semana; una doblada paga en '
                    f'cualquier fecha y rompería ese cómputo.'
                )
                if acuerdo and acuerdo.get('tipo') == TipoSolicitud.CAMBIO_DESCANSO:
                    texto += (
                        f' Además, ese día ya está comprometido en un cambio de descanso aprobado '
                        f'con {ReprogramacionDobladaService._nombre(acuerdo.get("companero_nombre"))} '
                        f'(solicitud #{acuerdo.get("solicitud_id")})'
                    )
                    if acuerdo.get('fecha_relacionada'):
                        texto += f', que compensa el {acuerdo["fecha_relacionada"]}'
                    texto += '.'
                return texto
            return (f'El {f} está dentro de la semana de temporada: ese día no está en jornada '
                    f'predeterminada, así que no hay media jornada sobre la que doblar.')

        est = TurnoService.estado_dia(explorador, fecha) or {}
        jornada = est.get('jornada')
        if jornada in ('AM', 'PM'):
            return None
        if jornada == JornadaDisplay.DOBLADA:
            texto = f'El {f} ya dobla (AM + PM): no le queda jornada contraria que agregar.'
            if acuerdo and acuerdo.get('tipo'):
                texto += (f' Viene de {acuerdo["tipo"]} con '
                          f'{ReprogramacionDobladaService._nombre(acuerdo.get("companero_nombre"))}.')
            return texto
        if not est.get('trabaja'):
            motivo = est.get('motivo')
            texto = f'El {f} descansa ({motivo}).' if motivo else f'El {f} descansa.'
            companero = est.get('companero')
            if companero:
                texto += f' Se lo cedió a {ReprogramacionDobladaService._nombre(companero)}.'
            return texto
        return f'El {f} no tiene turno planificado: no hay una jornada única sobre la que doblar.'

    @staticmethod
    def validar_dia_pago(reprog: ReprogramacionDiaDoblada, fecha_nueva: date,
                         hoy: date | None = None, acuerdo=_ACUERDO_NO_PRECARGADO):
        """
        FUENTE ÚNICA de "¿sirve este día para pagar la doblada no cumplida?". La usan el calendario
        del supervisor (para pintar qué días son elegibles) y `programar` (para revalidar el POST),
        así lo que se ve y lo que se acepta no pueden divergir.

        Devuelve la jornada única que la persona tiene ese día (la que se guarda para restaurar al
        cancelar), o None en D FDS —donde la unidad es el día completo y no hay jornada previa—.
        Lanza ValueError con el motivo si el día no sirve.

        `acuerdo`: la entrada de `AcuerdoPorDiaService` para ese día, si quien llama ya la
        tiene precargada (None = ese día no tiene acuerdo). Solo enriquece el MENSAJE de error;
        nunca decide. Si no se pasa, se busca sola y solo cuando hay que redactar el rechazo.
        """
        from solicitudes.services.cambios_permanentes_helper import jornada_doblada_perm

        hoy = hoy or timezone.localdate()
        if fecha_nueva == reprog.fecha_original:
            raise ValueError('El día de pago debe ser distinto al día que no se cumplió.')
        if fecha_nueva < hoy:
            raise ValueError('El día de pago no puede estar en el pasado.')

        if ReprogramacionDobladaService.es_dfds(reprog):
            # FIN DE SEMANA: la unidad es el DÍA COMPLETO, no media jornada. Aquí no se "agrega la
            # jornada contraria" a un día que ya se trabaja: se trabaja un día de finde que se tenía
            # LIBRE. Por eso no hay jornada previa que guardar (al cancelar, la persona simplemente
            # vuelve a descansar) y los 30 min no aplican — el guard de `aplica_deuda_doblada` ya
            # los descarta en sábado y domingo.
            ReprogramacionDobladaService._validar_dia_compensacion_finde(
                reprog.explorador, fecha_nueva, reprog.fecha_original)
            return None

        # La persona debe tener jornada única real ese día (para poder doblar = agregar la contraria).
        # El VEREDICTO lo da `jornada_doblada_perm`; `motivo_dia_no_apto` solo explica el
        # porqué con detalle, recorriendo las mismas causas en el mismo orden.
        j = jornada_doblada_perm(reprog.explorador, fecha_nueva)
        if j is None:
            motivo = ReprogramacionDobladaService.motivo_dia_no_apto(
                reprog.explorador, fecha_nueva, acuerdo)
            raise ValueError(
                f'{motivo} Elige otro día.' if motivo
                else 'Ese día la persona no tiene una jornada única para doblar. Elige otro día.'
            )
        return j

    @staticmethod
    def puede_cancelar(solicitud: SolicitudCambio) -> bool:
        """Solo se puede CANCELAR (deshacer todo) si NINGÚN día de doblada se ha cumplido aún
        (ambas fechas de doblada son hoy o futuras). Si uno ya pasó, cancelar afectaría a quien
        ya cumplió → bloqueado (solo queda reprogramar el día del que falta)."""
        detalle = getattr(solicitud, 'doblada', None)
        if not detalle:
            return False
        hoy = timezone.localdate()
        return solicitud.fecha_cambio_turno >= hoy and detalle.fecha_pago >= hoy

    @staticmethod
    @transaction.atomic
    def registrar_inasistencia(solicitud: SolicitudCambio, explorador, supervisor=None,
                               motivo: str | None = None, fecha_original: date | None = None) -> ReprogramacionDiaDoblada:
        """Registra que `explorador` no cumplió UN día de doblada: anula ese día (soft-delete +
        resta sus 30 min) y crea la reprogramación en estado 'pendiente'.

        Para DOBLADA sencilla `fecha_original` se deriva (cada uno tiene 1 día); para DOBLADA
        PERMANENTE se pasa la fecha específica que no se cumplió."""
        if fecha_original is None:
            fecha_original = ReprogramacionDobladaService._dia_doblada_de(solicitud, explorador)

        ya = ReprogramacionDiaDoblada.objects.filter(
            doblada_origen=solicitud, explorador=explorador, fecha_original=fecha_original,
            estado__in=['pendiente', 'pagada'],
        ).first()
        if ya:
            raise ValueError('Ya existe una reprogramación para el día de doblada de esta persona.')

        DobladaAplicacionService.anular_doblada_de_un_dia(
            solicitud, explorador, fecha_original,
            motivo=f'Anulado por reprogramación (inasistencia){": " + motivo if motivo else ""}',
        )

        reprog = ReprogramacionDiaDoblada.objects.create(
            doblada_origen=solicitud,
            explorador=explorador,
            fecha_original=fecha_original,
            jornada_debida=ReprogramacionDobladaService._jornada_debida(explorador, fecha_original),
            estado='pendiente',
            motivo=motivo,
            registrado_por=supervisor,
        )
        logger.info("Reprogramación registrada: %s no cumplió %s (doblada %s).",
                    explorador, fecha_original, solicitud.id)
        return reprog

    @staticmethod
    @transaction.atomic
    def programar(reprog: ReprogramacionDiaDoblada, fecha_nueva: date) -> ReprogramacionDiaDoblada:
        """El supervisor programa el día en que la persona paga doblándose. Aplica la doblada ese
        día (sin pasar por el flujo normal) y le regenera los 30 min en la fecha real."""
        from core.services.cache_service import CacheService

        if reprog.estado != 'pendiente':
            raise ValueError('Esta reprogramación no está pendiente de programar.')

        # Misma validación que pinta el calendario: el POST no puede colar un día que la pantalla
        # no ofrecía (fecha pasada, formulario viejo, request directo).
        # Guarda la jornada única que tenía ese día ANTES de doblar, para poder restaurar
        # exactamente su turno original si luego se cancela (None en D FDS: día completo).
        reprog.jornada_pago_previa = ReprogramacionDobladaService.validar_dia_pago(reprog, fecha_nueva)

        DFDSAplicacionService._crear_doblada_dia(
            reprog.explorador, fecha_nueva, tipo_cambio=TipoCambioTurno.PAGO_REPROGRAMADO)

        # Regenerar los 30 min en la fecha real (misma regla que una doblada: solo lun-vie no festivo).
        if DeudaCorporativaService.aplica_deuda_doblada(fecha_nueva):
            # Variante IDEMPOTENTE (patrón #21): clave explorador+fecha_doblada+solicitud. Si el
            # supervisor vuelve a programar el mismo día de pago —o el flujo se re-ejecuta— no se
            # cobran 60 min por un solo día doblado. Es el guard compartido: no usar la cruda.
            DeudaCorporativaService.crear_deuda_corporativa_idempotente(
                explorador=reprog.explorador, minutos=30,
                fecha_doblada=fecha_nueva, solicitud=reprog.doblada_origen,
                comentario=f'Pago reprogramado por inasistencia del {reprog.fecha_original.strftime("%d/%m/%Y")}',
            )

        reprog.fecha_reprogramada = fecha_nueva
        reprog.estado = 'pagada'
        reprog.save(update_fields=['fecha_reprogramada', 'estado', 'jornada_pago_previa', 'actualizado_en'])

        CacheService.invalidar_cache_turnos_empleado(reprog.explorador_id, fecha_nueva.month, fecha_nueva.year)
        logger.info("Reprogramación %s programada: %s paga doblando el %s.",
                    reprog.id, reprog.explorador, fecha_nueva)
        return reprog

    @staticmethod
    @transaction.atomic
    def deshacer_pago(reprog: ReprogramacionDiaDoblada) -> ReprogramacionDiaDoblada:
        """Deshace SOLO el día de pago programado y devuelve la reprogramación a 'pendiente'.

        Es la acción correcta cuando el día de pago ya no sirve (se programó mal, la persona
        volvió a faltar, cambió el cuadro): la DEUDA SIGUE VIVA. Cerrar la reprogramación aquí
        —lo que hacía antes el botón de cancelar— la sacaba de los pendientes y la persona se
        quedaba sin pagar la doblada y sin forma de que se la volvieran a programar: en Gestión de
        Solicitudes aparecía 'Reprogramar', pero ese día ya no tenía doblada que incumplir.

        Idempotente: si ya está en 'pendiente' sin día de pago, no hace nada (patrón #21).
        Para perdonar la deuda se usa `cerrar_sin_pago` desde 'pendiente' — dos pasos deliberados,
        para que un doble submit no borre una deuda real.
        """
        from core.services.cache_service import CacheService

        if reprog.estado == 'pendiente' and not reprog.fecha_reprogramada:
            return reprog
        if reprog.estado != 'pagada' or not reprog.fecha_reprogramada:
            raise ValueError('Esta reprogramación no tiene un día de pago programado que deshacer.')

        fecha_pago = reprog.fecha_reprogramada
        DobladaAplicacionService.anular_doblada_de_un_dia(
            reprog.doblada_origen, reprog.explorador, fecha_pago,
            motivo='Anulado: día de pago deshecho (vuelve a pendiente)',
        )
        ReprogramacionDobladaService._restaurar_turno_previo(reprog, fecha_pago)
        CacheService.invalidar_cache_turnos_empleado(
            reprog.explorador_id, fecha_pago.month, fecha_pago.year)

        reprog.estado = 'pendiente'
        reprog.fecha_reprogramada = None
        reprog.jornada_pago_previa = None
        reprog.save(update_fields=['estado', 'fecha_reprogramada', 'jornada_pago_previa', 'actualizado_en'])
        logger.info("Reprogramación %s: pago del %s deshecho, vuelve a PENDIENTE.", reprog.id, fecha_pago)
        return reprog

    @staticmethod
    @transaction.atomic
    def cerrar_sin_pago(reprog: ReprogramacionDiaDoblada) -> ReprogramacionDiaDoblada:
        """Cierra una reprogramación PENDIENTE sin que la persona pague: el día no cumplido queda
        anulado y nadie lo repone. Solo desde 'pendiente' — si hay un día de pago aplicado hay que
        deshacerlo primero (`deshacer_pago`), para no dejar turnos vivos de un pago cancelado."""
        if reprog.estado == 'cancelada':
            return reprog  # idempotente
        if reprog.estado != 'pendiente':
            raise ValueError('Primero deshaz el día de pago programado; luego puedes cerrarla sin pago.')
        reprog.estado = 'cancelada'
        reprog.save(update_fields=['estado', 'actualizado_en'])
        logger.info("Reprogramación %s cerrada sin pago.", reprog.id)
        return reprog

    @staticmethod
    def _restaurar_turno_previo(reprog: ReprogramacionDiaDoblada, fecha: date) -> None:
        """Recrea el turno único (AM/PM) que el explorador tenía ese día antes de doblar, para
        que Mis Turnos muestre exactamente su jornada original tras cancelar. No-op si no se
        guardó la jornada previa (reprogramaciones antiguas caen al fallback de base)."""
        jornada_previa = reprog.jornada_pago_previa
        if not jornada_previa:
            return
        from turnos.models import Jornada, Turno
        from turnos.services.doblada_turno_service import DobladaTurnoService
        try:
            jornada = Jornada.objects.get(nombre=jornada_previa)
        except Jornada.DoesNotExist:
            logger.warning("No se pudo restaurar el turno previo (jornada %s inexistente)", jornada_previa)
            return
        # Entre programar y cancelar, otra vía (un CT, un permiso, un ajuste manual) pudo darle
        # ya esa jornada ese día. Crearla otra vez violaría `turno_unico_activo_por_jornada` y
        # reventaría la cancelación entera; y aunque no reventara, estaríamos pisando el turno
        # que esa otra vía dejó puesto. Si ya está, no hay nada que restaurar.
        if Turno.objects.filter(explorador=reprog.explorador, fecha=fecha, jornada=jornada).exists():
            logger.info(
                "Turno previo (%s) NO restaurado para %s el %s: ya tiene esa jornada por otra vía.",
                jornada_previa, reprog.explorador, fecha,
            )
            return
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(reprog.explorador, fecha)
        Turno.objects.create(
            explorador=reprog.explorador, fecha=fecha, jornada=jornada, sala=sala, tipo_cambio=None,
        )
        logger.info("Turno previo (%s) restaurado para %s el %s tras cancelar reprogramación.",
                    jornada_previa, reprog.explorador, fecha)
