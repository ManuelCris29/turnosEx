import logging

"""
Cambio de Día de Descanso (fin de semana y entre semana).

MODALIDAD FIN DE SEMANA:
- Intercambio IDA Y VUELTA de días trabajados en el fin de semana.
- Ej: Mariana trabaja SAB 4, Jhon trabaja DOM 5 → después: Mariana trabaja DOM 5, Jhon trabaja SAB 4.
- En otra semana del mismo mes se revierte.
- No hay dobladas ni deudas: cada explorador sigue trabajando UN solo día por finde, solo cambia CUÁL.
- Balance: si el mes tiene 5 domingos (impar) se avisa, pero NO bloquea. Al ser informativo, ese
  aviso vive solo en el formulario (`validarBalanceDomingos` en solicitar_cambio_descanso.js).

MODALIDAD ENTRE SEMANA (Temporada):
- Intercambio DIRECTO de descansos asignados por el supervisor.
- Ej: Mariana descansa martes, Jhon descansa el día completo de esa semana → se intercambian.
- SIN devolución, es un intercambio simple.
- Ambos días deben estar en la MISMA semana de temporada (misma regla dura que las
  sub-modalidades; ver _validar_semana_comun).
"""
from typing import Any, Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.constants import JornadaDisplay
from core.utils.date_utils import DateUtils
from empleados.models import Empleado
from solicitudes.models import DobladaDetalle, SolicitudCambio

from .base_strategy import SolicitudStrategy

logger = logging.getLogger(__name__)


class CambioDescansoStrategy(SolicitudStrategy):

    def __init__(self):
        super().__init__("CAMBIO DESCANSO")

    @staticmethod
    def _parse(fecha):
        if not fecha:
            return None
        if isinstance(fecha, str):
            try:
                return DateUtils.parse_date(fecha)
            except ValueError:
                return None
        return fecha

    @staticmethod
    def _grupo_base(explorador: Empleado, fecha) -> Optional[str]:
        """
        Jornada BASE (grupo AM/PM) del explorador según su asignación, NO según los turnos
        del día. En fin de semana quien trabaja lo hace AM+PM, así que los turnos no sirven
        para distinguir el grupo: hay que mirar la asignación base.
        """
        from turnos.models import AsignarJornadaExplorador
        asg = (AsignarJornadaExplorador.objects
               .filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        return asg.jornada.nombre.upper() if asg else None

    @staticmethod
    def _otro_dia_finde(fecha):
        """Retorna el otro día del fin de semana (sábado <-> domingo)."""
        from datetime import timedelta
        if fecha.weekday() == 5:  # sábado
            return fecha + timedelta(days=1)  # domingo
        elif fecha.weekday() == 6:  # domingo
            return fecha - timedelta(days=1)  # sábado
        return None

    @staticmethod
    def _es_duplicado_pendiente(solicitante, receptor, fecha_cesion, fecha_pago):
        """¿Ya hay una solicitud de cambio de descanso PENDIENTE con el mismo PAR de fechas
        {cesión, pago} (en cualquier orden) entre las dos personas (en cualquier rol)?

        El intercambio es SIMÉTRICO (cesión↔pago dan el mismo resultado), por eso miramos el
        par en ambos sentidos. El validador genérico solo mira fecha_cambio_turno, así que NO
        ve la versión invertida (cesión=A/pago=B vs cesión=B/pago=A)."""
        from django.db.models import Q

        from solicitudes.models import SolicitudCambio
        return (SolicitudCambio.objects
                .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='pendiente')
                .filter(Q(explorador_solicitante=solicitante, explorador_receptor=receptor) |
                        Q(explorador_solicitante=receptor, explorador_receptor=solicitante))
                .filter(Q(fecha_cambio_turno=fecha_cesion, doblada__fecha_pago=fecha_pago) |
                        Q(fecha_cambio_turno=fecha_pago,   doblada__fecha_pago=fecha_cesion))
                .exists())

    @staticmethod
    def _trabaja_dia(explorador, fecha):
        """
        Verifica que el explorador TRABAJE ese día y que ese día esté DISPONIBLE para un
        cambio de descanso, con la regla del sistema:
        1) ¿El día está BLOQUEADO para un nuevo cambio de descanso
           (`dia_bloqueado_para_nuevo_cambio`)? Solo lo bloquea otro tipo de cambio (doblada,
           d_fds, CT, doblada permanente). Un CAMBIO DESCANSO previo NO bloquea: el día vuelve a
           estar disponible en cuanto se aplica ("última aprobada gana por día").
        2) Turno REAL del día (horario importado, o un CAMBIO DESCANSO ya aplicado) → trabaja.
        3) En otro caso, turno VIRTUAL (jornada base + alternancia).

        Devuelve (True, jornada) o (False, motivo).
        En fin de semana, quien trabaja lo hace el día completo (AM+PM): eso es NORMAL.
        """
        from turnos.models import Turno
        from turnos.services.turno_service import TurnoService

        from ..cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        # 1) Bloqueo (ver docstring). Solo lo dispara otro TIPO de cambio: un CAMBIO DESCANSO
        #    previo dejó de bloquear el día, así que aquí siempre hay tipos que nombrar.
        if CambioDescansoAplicacionService.dia_bloqueado_para_nuevo_cambio(explorador, fecha):
            turnos_bloq = list(
                Turno.objects.filter(explorador=explorador, fecha=fecha)
                .exclude(tipo_cambio__isnull=True).exclude(tipo_cambio='')
            )
            otros_tipos = sorted({t.tipo_cambio for t in turnos_bloq if t.tipo_cambio != 'CAMBIO DESCANSO'})
            return False, (
                f"Ese día ya tiene un cambio aplicado ({', '.join(otros_tipos)}). "
                f"Para usarlo en un intercambio, primero hay que deshacer ese cambio: pídeselo a "
                f"tu compañero si aún está en plazo, o a tu supervisor."
            )

        # 2) Turno real (importado, o dejado por un CAMBIO DESCANSO ya aplicado) → trabaja.
        # En fin de semana el día completo es AM+PM (DOBLADA); si el Turno real es de
        # MEDIA jornada (solo AM o solo PM, por un cambio previo), no hay día completo
        # para intercambiar.
        turnos = list(Turno.objects.filter(explorador=explorador, fecha=fecha))
        if turnos:
            js = {t.jornada.nombre.upper() for t in turnos if t.jornada}
            if not ({'AM', 'PM'} <= js):
                jornada_parcial = 'AM' if 'AM' in js else ('PM' if 'PM' in js else 'parcial')
                return False, (
                    f"Solo tienes media jornada ({jornada_parcial}) ese día por un cambio previo; "
                    "no tienes el día completo del fin de semana para el intercambio."
                )
            t = TurnoService.get_turno_explorador(explorador.id, fecha.strftime('%Y-%m-%d'))
            return True, (t.get('jornada') if t else 'TRABAJA')

        # 3) Turno virtual (predeterminado)
        t = TurnoService.get_turno_explorador(explorador.id, fecha.strftime('%Y-%m-%d'))
        if not t:
            return False, "Descanso"
        return True, t.get('jornada') or 'TRABAJA'

    # ------------------------------------------------ re-validación al aprobar
    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base)."""
        det = getattr(solicitud, 'doblada', None)
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_cambio_turno': solicitud.fecha_cambio_turno,
            'fecha_pago': det.fecha_pago if det else None,
            'submodalidad_semana': getattr(det, 'submodalidad_semana', None) if det else None,
            'tipo_cesion': det.tipo_cesion if det else None,
            'jornada_cedida': det.jornada_cedida if det else None,
            'jornada_cubre_en_pago': getattr(det, 'jornada_cubre_en_pago', None) if det else None,
        }

    # --------------------------------------------------------------- validación
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            from ..solicitud_validator import SolicitudValidator

            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            fecha_cesion = self._parse(datos.get('fecha_cambio_turno'))
            fecha_pago = self._parse(datos.get('fecha_pago'))
            comentario = datos.get('comentario') or ''

            if not solicitante:
                return False, "Explorador solicitante es requerido"
            if not receptor:
                return False, "Debe seleccionar el compañero con quien intercambia el descanso"
            if not fecha_cesion:
                return False, "El día que cambias es requerido"
            if not fecha_pago:
                return False, "El día de devolución es obligatorio (otro día del mismo mes)"

            SolicitudValidator.validar_empleado_activo(solicitante)
            SolicitudValidator.validar_empleado_activo(receptor)
            SolicitudValidator.validar_no_mismo_empleado(solicitante, receptor)
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'el cambio de día de descanso')

            # No DUPLICADOS pendientes (regla de CREACIÓN; se OMITE al re-validar para aprobar,
            # donde la solicitud ya existe y no se está creando otra).
            # Cobertura con DOS compañeros: se crean 2 solicitudes con la MISMA fecha de cesión
            # (una por jornada), así que el chequeo genérico por fecha se sustituye por uno
            # específico por jornada dentro de _validar_semana_cobertura.
            es_cobertura = (datos.get('submodalidad_semana') or '') == 'cobertura_misma_semana'
            if not datos.get('es_revalidacion') and not es_cobertura:
                SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fecha(solicitante, fecha_cesion)
                SolicitudValidator.validar_receptor_sin_solicitud_pendiente_en_fecha(receptor, fecha_cesion)

            # FESTIVO ENTRE SEMANA: no se puede intercambiar el descanso.
            #
            # Un festivo de lunes a viernes tiene su PROPIA alternancia: ese día un grupo
            # trabaja la jornada completa (AM+PM) y el otro descansa, y la planificación
            # anual decide cuál. Ese descanso no es el de la rotación ordinaria, así que
            # no se puede ceder ni usar como devolución: moverlo desbarataría el reparto
            # del festivo.
            #
            # `es_festivo_semana()` devuelve False para un festivo que cae en sábado o
            # domingo, y eso es DELIBERADO, no un descuido: un festivo en fin de semana
            # sigue siendo fin de semana, y ahí manda la alternancia de findes, que sí
            # admite el intercambio. Por eso una sola comprobación cubre las dos
            # modalidades y no hace falta ramificar. (Confirmado con el usuario el
            # 2026-08-20.)
            for _f, _que in ((fecha_cesion, 'que cambias'), (fecha_pago, 'de devolución')):
                if SolicitudValidator.es_festivo_semana(_f):
                    return False, (
                        f"El día {_que} ({_f.strftime('%d/%m/%Y')}) es un festivo entre semana. "
                        f"Los festivos tienen su propia alternancia —un grupo dobla y el otro "
                        f"descansa— y ese descanso no se puede intercambiar. Elige otro día."
                    )

            # Detectar modalidad: fin de semana (sáb/dom) o ENTRE SEMANA (lun-vie).
            es_finde = fecha_cesion.weekday() in (5, 6)
            if not es_finde:
                sub = datos.get('submodalidad_semana') or 'intercambio_dia'
                if sub == 'jornadas_partidas':
                    return self._validar_semana_jornadas_partidas(
                        solicitante, receptor, fecha_cesion, fecha_pago, datos)
                if sub == 'cobertura_misma_semana':
                    return self._validar_semana_cobertura(
                        solicitante, receptor, fecha_cesion, fecha_pago, datos)
                if sub == 'cambio_doblada':
                    return self._validar_semana_cambio_doblada(
                        solicitante, receptor, fecha_cesion, fecha_pago, datos)
                return self._validar_entre_semana(solicitante, receptor, fecha_cesion, fecha_pago,
                                                  es_revalidacion=datos.get('es_revalidacion'))

            # --- Fin de semana ---
            # Extraida en la Fase 3 para que las dos modalidades queden al mismo nivel:
            # la de ENTRE SEMANA ya vivia en `_validar_entre_semana`, y esta seguia en
            # linea dentro de `validar_solicitud`.
            return self._validar_fin_de_semana(solicitante, receptor, fecha_cesion,
                                               fecha_pago, datos)
            return True, "Solicitud de cambio de descanso válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando cambio de descanso: {str(e)}"


    def _validar_fin_de_semana(self, solicitante, receptor, fecha_cesion, fecha_pago, datos):
        """
        Modalidad de FIN DE SEMANA: se intercambia un finde por otro.

        Devuelve `(ok, mensaje)`, como sus hermanas `_validar_entre_semana` y las
        de submodalidad. Se sigue la convencion de ESTE archivo y no la de
        `doblada_strategy` ("mensaje o None"): mezclarlas obligaria a recordar cual
        rige en cada sitio.

        Los parametros se llaman igual que las variables locales que sustituyen. No
        es casualidad: asi el traslado no necesita renombrar nada dentro del cuerpo,
        y se elimina de raiz la clase de error que aparecio tres veces al trocear
        `doblada_strategy` con reemplazos automaticos.
        """
        # Import local, igual que en `validar_solicitud`: el modulo de validadores
        # importa de vuelta las strategies y a nivel de modulo daria un ciclo.
        from ..solicitud_validator import SolicitudValidator

        # --- Fin de semana ---
        if fecha_cesion.weekday() not in (5, 6):
            return False, "El día que cambias debe ser un fin de semana (sábado o domingo)"
        if fecha_pago.weekday() not in (5, 6):
            return False, "El día de devolución debe ser un fin de semana (sábado o domingo)"

        from django.utils import timezone
        hoy = timezone.localdate()
        # El día en curso YA se está trabajando: no hay jornada que intercambiar sin
        # reescribir un turno que la persona está cubriendo ahora mismo (misma regla que
        # D FDS). Se omite al re-validar: una solicitud enviada ayer para hoy no debe
        # volverse inaprobable por el paso del tiempo, la decide el supervisor.
        if fecha_cesion < hoy or (fecha_cesion == hoy and not datos.get('es_revalidacion')):
            return False, (
                "El fin de semana que cambias debe ser posterior a hoy: el día en curso "
                "ya se está trabajando."
            )
        if fecha_pago <= hoy:
            return False, "La fecha de devolución debe ser posterior a hoy"
        if fecha_pago == fecha_cesion:
            return False, "La devolución debe ser un fin de semana distinto al que cambias"

        # DÍA OPUESTO (sáb↔dom): el balance de domingos se conserva porque en la cesión
        # trabajas un día y en la devolución trabajas el día contrario por alternancia.
        # Ej: cesión sábado (trabajas) → devolución domingo (trabajas el otro finde).
        if fecha_cesion.weekday() == fecha_pago.weekday():
            dia = 'domingo' if fecha_cesion.weekday() == 6 else 'sábado'
            otro = 'sábado' if fecha_cesion.weekday() == 6 else 'domingo'
            return False, (
                f"Cambiaste un {dia}: la devolución debe ser un {otro} "
                f"(el día contrario), para mantener tu balance de domingos en el mes."
            )

        # Mismo mes que la cesión
        SolicitudValidator.validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion)

        # Duplicado (par de fechas en cualquier orden, mismas personas). Ver _es_duplicado_pendiente.
        # Se omite al re-validar para aprobar (regla de creación).
        if not datos.get('es_revalidacion') and self._es_duplicado_pendiente(solicitante, receptor, fecha_cesion, fecha_pago):
            return False, (
                f"Ya enviaste esta solicitud de cambio de descanso (mismas fechas: "
                f"{fecha_cesion.strftime('%d/%m')} y {fecha_pago.strftime('%d/%m')}). "
                f"Está pendiente de aprobación."
            )

        # Grupos contrarios
        grupo_sol = self._grupo_base(solicitante, fecha_cesion)
        grupo_rec = self._grupo_base(receptor, fecha_cesion)
        if not grupo_sol or not grupo_rec:
            return False, "No se pudo determinar la jornada base de los exploradores"
        if grupo_sol == grupo_rec:
            return False, (
                "El compañero debe ser del grupo contrario (el que descansa el otro día del "
                "fin de semana). No puedes intercambiar con alguien de tu mismo grupo."
            )

        # VALIDACIÓN CRÍTICA: Verificar que AMBOS tengan turnos REALES en las fechas.
        # El solicitante debe tener UN turno (su jornada base) en fecha_cesion
        tiene_turno_sol_ces, jor_sol_ces = self._trabaja_dia(solicitante, fecha_cesion)
        if not tiene_turno_sol_ces:
            return False, jor_sol_ces or (
                f"No tienes un turno válido el {fecha_cesion.strftime('%d/%m/%Y')}. "
                f"No puedes cambiar descanso sin tu turno normal."
            )

        otro_dia_cesion = self._otro_dia_finde(fecha_cesion)
        tiene_turno_rec_otro, jor_rec_otro = self._trabaja_dia(receptor, otro_dia_cesion)
        if not tiene_turno_rec_otro:
            return False, jor_rec_otro or (
                f"Tu compañero no tiene un turno válido el {otro_dia_cesion.strftime('%d/%m/%Y')}. "
                f"No puede hacer el intercambio."
            )

        # CADA UNO debe DESCANSAR el día que va a RECIBIR en el intercambio (fuente de
        # verdad estado_dia). Si alguno ya trabaja los DOS días del finde (p. ej. doblada
        # sábado y domingo), no tiene día libre para recibir y el intercambio es imposible.
        from turnos.services.turno_service import TurnoService as _TSfinde
        if _TSfinde.estado_dia(receptor, fecha_cesion)['trabaja']:
            return False, (
                f"Tu compañero ya trabaja el {fecha_cesion.strftime('%d/%m/%Y')} "
                f"(trabaja los dos días de ese fin de semana). No tiene ese día libre para "
                f"recibir el intercambio."
            )
        if _TSfinde.estado_dia(solicitante, otro_dia_cesion)['trabaja']:
            return False, (
                f"Ya trabajas el {otro_dia_cesion.strftime('%d/%m/%Y')} "
                f"(trabajas los dos días de ese fin de semana). No tienes ese día libre para "
                f"el intercambio."
            )

        # El solicitante debe tener UN turno (su jornada base) en fecha_pago
        tiene_turno_sol_pago, jor_sol_pago = self._trabaja_dia(solicitante, fecha_pago)
        if not tiene_turno_sol_pago:
            return False, jor_sol_pago or (
                f"No tienes un turno válido el {fecha_pago.strftime('%d/%m/%Y')} (devolución). "
                f"No puedes completar el intercambio."
            )

        otro_dia_pago = self._otro_dia_finde(fecha_pago)
        tiene_turno_rec_otro_pago, jor_rec_otro_pago = self._trabaja_dia(receptor, otro_dia_pago)
        if not tiene_turno_rec_otro_pago:
            return False, jor_rec_otro_pago or (
                f"Tu compañero no tiene un turno válido el {otro_dia_pago.strftime('%d/%m/%Y')} (devolución). "
                f"No puede completar el intercambio."
            )

        # Mismo control en el finde de DEVOLUCIÓN: cada uno debe descansar el día que recibe.
        if _TSfinde.estado_dia(receptor, fecha_pago)['trabaja']:
            return False, (
                f"Tu compañero ya trabaja el {fecha_pago.strftime('%d/%m/%Y')} (devolución); "
                f"trabaja los dos días de ese fin de semana y no tiene ese día libre."
            )
        if _TSfinde.estado_dia(solicitante, otro_dia_pago)['trabaja']:
            return False, (
                f"Ya trabajas el {otro_dia_pago.strftime('%d/%m/%Y')} (devolución); "
                f"trabajas los dos días de ese fin de semana."
            )

        # NOTA: la advertencia de "mes con 5 domingos" (balance impar) es informativa y NO
        # bloquea, por eso vive solo en el formulario (`validarBalanceDomingos` en
        # solicitar_cambio_descanso.js). Aquí no hay nada que validar.

        return True, "Solicitud de cambio de descanso válida"

    def _validar_entre_semana(self, solicitante, receptor, fecha_cesion, fecha_pago, es_revalidacion=False):
        """
        Validación del cambio de descanso ENTRE SEMANA (lun-vie) en temporada.

        Es un intercambio DIRECTO de descansos (SIN devolución):
        Solicitante descansa fecha_cesion, Receptor descansa fecha_pago.
        Después del intercambio: Solicitante descansa fecha_pago, Receptor descansa fecha_cesion.

        NOTA: fecha_pago en este contexto es el "otro descanso" que intercambian,
        no una devolución posterior (no hay ida y vuelta como en fin de semana).
        """
        from django.utils import timezone

        from turnos.services.descanso_semana_service import DescansoSemanaService
        hoy = timezone.localdate()

        if fecha_cesion.weekday() >= 5:
            return False, "El día que cambias debe ser de lunes a viernes."
        if fecha_pago.weekday() >= 5:
            return False, "El compañero solo puede descansar de lunes a viernes."
        # Igual que en finde: el día en curso ya se está trabajando. Se omite al re-validar.
        if fecha_cesion < hoy or (fecha_cesion == hoy and not es_revalidacion):
            return False, (
                "El día que cambias debe ser posterior a hoy: el día en curso ya se está "
                "trabajando."
            )
        if fecha_pago <= hoy:
            return False, "El descanso del compañero debe ser posterior a hoy."
        if fecha_pago == fecha_cesion:
            return False, "Los descansos deben ser días distintos."

        # MISMA SEMANA: misma regla dura que el resto de sub-modalidades de temporada
        # (ver _validar_semana_comun). El formulario nunca ofreció otra semana —solo el
        # descanso del grupo contrario de la semana seleccionada—, así que esto cierra el
        # hueco de un POST directo sin cambiar lo que el usuario puede hacer.
        # Aplica TAMBIÉN al re-validar para aprobar, igual que _validar_semana_comun: es una
        # regla de negocio del intercambio, no una regla de creación.
        from datetime import timedelta
        if (fecha_cesion - timedelta(days=fecha_cesion.weekday())) != \
                (fecha_pago - timedelta(days=fecha_pago.weekday())):
            return False, (
                "El intercambio de descansos de temporada debe ser en la MISMA semana. "
                "Elige el descanso del grupo contrario de esa misma semana."
            )

        # Duplicado (par de fechas en cualquier orden, mismas personas). Igual que en finde:
        # el genérico solo mira fecha_cesion y no ve la versión invertida (roles intercambiados).
        # Se omite al re-validar para aprobar (regla de creación).
        if not es_revalidacion and self._es_duplicado_pendiente(solicitante, receptor, fecha_cesion, fecha_pago):
            return False, "Ya enviaste este intercambio de descanso (mismos días). Está pendiente de aprobación."

        # Grupos contrarios
        grupo_sol = self._grupo_base(solicitante, fecha_cesion)
        grupo_rec = self._grupo_base(receptor, fecha_cesion)
        if not grupo_sol or not grupo_rec:
            return False, "No se pudo determinar la jornada base de los exploradores."
        if grupo_sol == grupo_rec:
            return False, "El compañero debe ser del grupo contrario para intercambiar."

        # VALIDACIÓN CRÍTICA: Ambos deben tener DescansoSemanaManual en sus fechas
        # El solicitante debe tener descanso en fecha_cesion
        if not DescansoSemanaService.es_descanso_semana_manual(grupo_sol, fecha_cesion):
            return False, (
                f"No tienes un descanso asignado el {fecha_cesion.strftime('%d/%m/%Y')}. "
                f"No puedes cambiar un descanso que no existe."
            )

        # El receptor debe tener descanso en fecha_pago
        if not DescansoSemanaService.es_descanso_semana_manual(grupo_rec, fecha_pago):
            return False, (
                f"Tu compañero no tiene descanso asignado el {fecha_pago.strftime('%d/%m/%Y')}. "
                f"No pueden intercambiar descansos que no están asignados."
            )

        # FUENTE DE VERDAD (L2): además de estar configurado como descanso de temporada, el
        # día debe seguir SIENDO descanso HOY (no ya intercambiado ni comprometido por otra
        # solicitud aprobada). es_descanso_semana_manual mira la CONFIGURACIÓN; estado_dia mira
        # el ESTADO real (igual que "Mis Turnos").
        from turnos.services.turno_service import TurnoService
        if TurnoService.estado_dia(solicitante, fecha_cesion)['trabaja']:
            return False, (
                f"Ese día ({fecha_cesion.strftime('%d/%m/%Y')}) ya no es tu descanso disponible "
                f"(ya lo intercambiaste o está comprometido en otra solicitud). Elige otro."
            )
        if TurnoService.estado_dia(receptor, fecha_pago)['trabaja']:
            return False, (
                f"Tu compañero ya no descansa el {fecha_pago.strftime('%d/%m/%Y')} "
                f"(ya lo intercambió o está comprometido). Elige otro día o compañero."
            )

        # Los días que cada uno RECIBE también se reescriben al aplicar (`_descansa_dia` borra
        # los turnos de receptor@cesión y de solicitante@pago). Si esos días ya están
        # comprometidos por otra solicitud aprobada (una doblada, un d_fds…), aplicar este
        # intercambio los borraría en silencio dejando la otra solicitud aprobada sin turnos.
        # Las tres sub-modalidades ya hacían este chequeo; esta ruta era la única que faltaba,
        # y es la que asume el docstring de `_marcar_reemplazadas` ("entre semana lo impide la
        # validación, no el reemplazo").
        for emp, f, quien in ((receptor, fecha_cesion, 'Tu compañero tiene'),
                              (solicitante, fecha_pago, 'Tienes')):
            comp = self._comprometido(emp, f)
            if comp:
                return False, (
                    f"{quien} el {f.strftime('%d/%m/%Y')} comprometido por otra solicitud "
                    f"({comp.get('motivo')}). No se puede usar en el intercambio."
                )

        return True, "Solicitud de cambio de descanso (entre semana) válida"

    # ---------------------------------------------- sub-modalidades de semana
    @staticmethod
    def _validar_semana_comun(fecha_a, fecha_b, es_revalidacion=False):
        """
        Validaciones comunes de las sub-modalidades nuevas de temporada:
        lun-vie, futuras, MISMA semana (regla dura del negocio) y que la semana
        tenga descansos de temporada configurados.

        "Futuras" excluye HOY al crear (el día en curso ya se está trabajando), igual que en
        finde y en D FDS; al re-validar solo se exige que no sea pasado.
        """
        from datetime import timedelta

        from django.utils import timezone

        from turnos.services.descanso_semana_service import DescansoSemanaService

        hoy = timezone.localdate()
        if fecha_a.weekday() >= 5 or fecha_b.weekday() >= 5:
            return False, "Ambos días deben ser de lunes a viernes."
        limite = hoy if es_revalidacion else hoy + timedelta(days=1)
        if fecha_a < limite or fecha_b < limite:
            return False, ("No se pueden usar días pasados ni el día en curso."
                           if not es_revalidacion else "No se pueden usar días pasados.")
        if fecha_a == fecha_b:
            return False, "Los días deben ser distintos."
        lunes_a = fecha_a - timedelta(days=fecha_a.weekday())
        lunes_b = fecha_b - timedelta(days=fecha_b.weekday())
        if lunes_a != lunes_b:
            return False, (
                "El día de temporada modificado debe compensarse EN LA MISMA SEMANA. "
                "No se puede pagar en otra semana."
            )
        if not DescansoSemanaService.descansos_de_semana(fecha_a):
            return False, "Esa semana no tiene descansos de temporada configurados."
        return True, "ok"

    @staticmethod
    def _dia_completo_temporada(explorador, fecha):
        """¿El explorador trabaja `fecha` como día completo (AM+PM) según la fuente de verdad?"""
        from turnos.services.turno_service import TurnoService
        e = TurnoService.estado_dia(explorador, fecha)
        return bool(e['trabaja']) and e['jornada'] == JornadaDisplay.DOBLADA

    @staticmethod
    def _comprometido(explorador, fecha):
        """dict {motivo, companero} si el día ya está comprometido por otra solicitud aprobada."""
        from turnos.services.turno_service import TurnoService
        return TurnoService.dia_comprometido_por_solicitud(explorador, fecha)

    def _validar_semana_jornadas_partidas(self, solicitante, receptor, fecha_cesion, fecha_pago, datos):
        """
        Jornadas partidas: solicitante trabaja `jornada_cedida` los DOS días especiales;
        receptor la contraria. fecha_cesion = día de trabajo del solicitante;
        fecha_pago = día de trabajo del receptor. Sin deuda.
        """
        ok, msg = self._validar_semana_comun(fecha_cesion, fecha_pago, datos.get('es_revalidacion'))
        if not ok:
            return False, msg

        j = (datos.get('jornada_cedida') or '').upper()
        if j not in ('AM', 'PM'):
            return False, "Debes indicar qué jornada trabajarás tú ambos días (AM o PM)."

        if not self._dia_completo_temporada(solicitante, fecha_cesion):
            return False, (
                f"El {fecha_cesion.strftime('%d/%m/%Y')} no es tu día completo de temporada "
                f"(o ya fue modificado)."
            )
        if not self._dia_completo_temporada(receptor, fecha_pago):
            return False, (
                f"El {fecha_pago.strftime('%d/%m/%Y')} no es el día completo de temporada de tu "
                f"compañero (o ya fue modificado)."
            )
        for emp, f, quien in ((solicitante, fecha_pago, 'tu'), (receptor, fecha_cesion, 'su')):
            comp = self._comprometido(emp, f)
            if comp:
                return False, (
                    f"El {f.strftime('%d/%m/%Y')} ya está comprometido por otra solicitud "
                    f"({comp.get('motivo')})."
                )
        return True, "Solicitud de jornadas partidas válida"

    def _validar_semana_cobertura(self, solicitante, receptor, fecha_cesion, fecha_pago, datos):
        """
        Cobertura con pago en la misma semana: el receptor cubre jornada(s) de mi día
        completo (fecha_cesion) y yo le pago lo equivalente en fecha_pago.
        La deuda de 30 min (si alguien dobla sobre su propia jornada) se calcula al aplicar.
        """
        from ..cambio_descanso_aplicacion_service import CambioDescansoAplicacionService as _App

        ok, msg = self._validar_semana_comun(fecha_cesion, fecha_pago, datos.get('es_revalidacion'))
        if not ok:
            return False, msg

        tipo_cesion = datos.get('tipo_cesion') or 'cesion_completa'
        completa = tipo_cesion == 'cesion_completa'
        # La cobertura de día completo con UN solo compañero se retiró: su resultado es idéntico
        # a «Intercambiar el día» (mismo estado final, sin deuda). En cobertura solo quedan Solo AM,
        # Solo PM y día completo con DOS compañeros (dos solicitudes parciales AM+PM). No se bloquea
        # en re-validación para no romper solicitudes en curso creadas antes del cambio.
        if completa and not datos.get('es_revalidacion'):
            return False, (
                "Para que una sola persona tome tu día completo usa «Intercambiar el día». "
                "En «Que me cubran mi día» elige Solo AM, Solo PM, o día completo con 2 compañeros."
            )
        j = (datos.get('jornada_cedida') or '').upper()
        if not completa and j not in ('AM', 'PM'):
            return False, "Debes indicar qué jornada te cubrirán (AM o PM)."
        cedidas = {'AM', 'PM'} if completa else {j}

        # DUPLICADOS específicos de cobertura (por jornada, no por fecha): permite las 2
        # solicitudes del flujo "dos compañeros" (AM+PM) pero bloquea repetir la misma jornada.
        if not datos.get('es_revalidacion'):
            from solicitudes.models import SolicitudCambio as _SC
            pendientes = _SC.objects.filter(
                tipo_cambio__nombre='CAMBIO DESCANSO', estado='pendiente',
                explorador_solicitante=solicitante, fecha_cambio_turno=fecha_cesion,
                doblada__submodalidad_semana='cobertura_misma_semana',
            ).select_related('doblada')
            for p in pendientes:
                det = getattr(p, 'doblada', None)
                previas = ({'AM', 'PM'} if (det and det.tipo_cesion == 'cesion_completa')
                           else ({(det.jornada_cedida or '').upper()} if det else set()))
                if previas & cedidas:
                    return False, (
                        "Ya tienes una solicitud de cobertura pendiente para esa jornada de ese día."
                    )

        # El día cedido debe ser un día especial de temporada de MI grupo (el contrario
        # descansa por configuración) y las jornadas cedidas deben estar HOY a mi cargo.
        # No se exige día completo: en el flujo de 2 compañeros, al aprobar la 2ª
        # solicitud ya cedí media jornada y solo me queda la otra.
        from turnos.services.descanso_semana_service import DescansoSemanaService
        grupo_sol = self._grupo_base(solicitante, fecha_cesion)
        grupo_contrario = 'PM' if grupo_sol == 'AM' else 'AM'
        if not DescansoSemanaService.es_descanso_semana_manual(grupo_contrario, fecha_cesion):
            return False, (
                f"El {fecha_cesion.strftime('%d/%m/%Y')} no es tu día completo de temporada "
                f"(ese día no descansa el grupo contrario)."
            )
        mias_fc = _App._jornadas_actuales(solicitante, fecha_cesion)
        if not (cedidas <= mias_fc):
            return False, (
                f"No tienes a tu cargo la(s) jornada(s) que quieres ceder el "
                f"{fecha_cesion.strftime('%d/%m/%Y')} (ya las cediste o el día fue modificado)."
            )

        # El receptor debe poder asumir las jornadas cedidas ese día.
        comp = self._comprometido(receptor, fecha_cesion)
        if comp:
            return False, (
                f"Tu compañero ya tiene el {fecha_cesion.strftime('%d/%m/%Y')} comprometido "
                f"({comp.get('motivo')})."
            )
        pre_rec_fc = _App._jornadas_actuales(receptor, fecha_cesion)
        if pre_rec_fc & cedidas:
            return False, "Tu compañero ya trabaja esa jornada ese día; no puede cubrirla."
        if pre_rec_fc >= {'AM', 'PM'}:
            return False, "Tu compañero ya tiene el día completo ocupado; no puede cubrirte."

        # El pago: el receptor debe trabajar ese día algo que yo pueda cubrir.
        pre_rec_fp = _App._jornadas_actuales(receptor, fecha_pago)
        if not pre_rec_fp:
            return False, (
                f"Tu compañero no trabaja el {fecha_pago.strftime('%d/%m/%Y')}; "
                f"no hay jornada que puedas pagarle ese día."
            )
        comp = self._comprometido(solicitante, fecha_pago)
        if comp:
            return False, (
                f"Tu día de pago ({fecha_pago.strftime('%d/%m/%Y')}) ya está comprometido "
                f"({comp.get('motivo')})."
            )
        pre_sol_fp = _App._jornadas_actuales(solicitante, fecha_pago)
        # Jornada que YO cubro el día de pago: la elegida (si estoy libre y el compañero
        # trabaja ambas puedo escoger AM o PM); si no viene, la cedida.
        j_pago = (datos.get('jornada_cubre_en_pago') or '').upper()
        if j_pago not in ('AM', 'PM'):
            j_pago = j
        if not completa and j_pago and j_pago not in pre_rec_fp:
            return False, (
                f"Tu compañero no trabaja {j_pago} el {fecha_pago.strftime('%d/%m/%Y')}; "
                f"elige otra jornada de pago."
            )
        tomadas = set(pre_rec_fp) if completa else ({j_pago} if j_pago in pre_rec_fp else set(list(pre_rec_fp)[:1]))
        if tomadas & pre_sol_fp:
            return False, (
                f"El {fecha_pago.strftime('%d/%m/%Y')} ya trabajas esa jornada; "
                f"para pagar con esa jornada primero haz un Cambio de Turno sencillo, o elige otra."
            )
        return True, "Solicitud de cobertura válida"

    def _validar_semana_cambio_doblada(self, solicitante, receptor, fecha_cesion, fecha_pago, datos):
        """
        Cambio de doblada: el receptor tiene una doblada real (AM+PM) en fecha_pago y
        yo tengo mi día completo de temporada en fecha_cesion; se intercambian los días.
        Sin deuda (ambos ya doblaban; solo cambia cuál día).
        """
        from turnos.models import Turno

        from ..cambio_descanso_aplicacion_service import CambioDescansoAplicacionService as _App

        ok, msg = self._validar_semana_comun(fecha_cesion, fecha_pago, datos.get('es_revalidacion'))
        if not ok:
            return False, msg

        if not self._dia_completo_temporada(solicitante, fecha_cesion):
            return False, (
                f"El {fecha_cesion.strftime('%d/%m/%Y')} no es tu día completo de temporada "
                f"(o ya fue modificado)."
            )

        # El receptor debe tener una doblada REAL (Turno AM+PM) en fecha_pago.
        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=receptor, fecha=fecha_pago).select_related('jornada')}
        if not ({'AM', 'PM'} <= js):
            return False, (
                f"Tu compañero no tiene una doblada (AM+PM) el {fecha_pago.strftime('%d/%m/%Y')}."
            )

        # El receptor debe estar libre mi día para poder tomarlo completo.
        comp = self._comprometido(receptor, fecha_cesion)
        if comp:
            return False, (
                f"Tu compañero ya tiene el {fecha_cesion.strftime('%d/%m/%Y')} comprometido "
                f"({comp.get('motivo')})."
            )
        if _App._jornadas_actuales(receptor, fecha_cesion):
            return False, (
                f"Tu compañero trabaja el {fecha_cesion.strftime('%d/%m/%Y')}; "
                f"debe estar descansando para tomar tu día completo."
            )

        # Yo no debo tener ese día de pago comprometido por otra solicitud.
        comp = self._comprometido(solicitante, fecha_pago)
        if comp:
            return False, (
                f"El {fecha_pago.strftime('%d/%m/%Y')} ya lo tienes comprometido "
                f"({comp.get('motivo')})."
            )
        return True, "Solicitud de cambio de doblada válida"

    # ------------------------------------------------------------------- crear
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        try:
            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cesion = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')

            # Sub-modalidad (solo entre semana; None en fin de semana)
            fc = self._parse(fecha_cesion)
            es_finde = bool(fc) and fc.weekday() in (5, 6)
            submodalidad = None if es_finde else (datos.get('submodalidad_semana') or 'intercambio_dia')
            tipo_cesion = datos.get('tipo_cesion') or 'cesion_completa'
            jornada_cedida = (datos.get('jornada_cedida') or '').upper() or None
            # Cobertura: jornada que el solicitante cubre el día de pago (elegible cuando está
            # libre y el receptor trabaja ambas). Si no viene, se usa la cedida al aplicar.
            jornada_cubre_pago = (datos.get('jornada_cubre_en_pago') or '').upper() or None
            if jornada_cubre_pago not in ('AM', 'PM'):
                jornada_cubre_pago = None
            # minutos_deuda informativo: la deuda real se calcula al aplicar según la
            # regla de negocio (solo quien dobla sobre su propia jornada).
            minutos = 30 if submodalidad == 'cobertura_misma_semana' else 0

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
                    minutos_deuda=minutos,
                    tipo_cesion=tipo_cesion,
                    jornada_cedida=jornada_cedida,
                    jornada_cubre_en_pago=jornada_cubre_pago,
                    submodalidad_semana=submodalidad,
                    empleado_receptor=receptor,
                )
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception:
                import logging
                logging.getLogger(__name__).warning("Error creando notificación de cambio de descanso", exc_info=True)
            return solicitud, "Solicitud de cambio de descanso creada correctamente"
        except Exception as e:
            return None, f"Error creando solicitud de cambio de descanso: {str(e)}"

    # ----------------------------------------------------------------- aplicar
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        try:
            from core.services.cache_service import CacheService

            from ..cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

            with transaction.atomic():
                detalle = solicitud.doblada
                if solicitud.fecha_cambio_turno and solicitud.fecha_cambio_turno.weekday() in (5, 6):
                    CambioDescansoAplicacionService.aplicar(solicitud, detalle)
                else:
                    sub = getattr(detalle, 'submodalidad_semana', None) or 'intercambio_dia'
                    if sub == 'jornadas_partidas':
                        CambioDescansoAplicacionService.aplicar_semana_jornadas_partidas(solicitud, detalle)
                    elif sub == 'cobertura_misma_semana':
                        CambioDescansoAplicacionService.aplicar_semana_cobertura(solicitud, detalle)
                    elif sub == 'cambio_doblada':
                        CambioDescansoAplicacionService.aplicar_semana_cambio_doblada(solicitud, detalle)
                    else:
                        CambioDescansoAplicacionService.aplicar_entre_semana(solicitud, detalle)

                # Estado RESULTANTE: lo que este cambio de descanso deja en esas fechas. Al
                # cancelar se compara contra los turnos actuales para no pisar un cambio ajeno
                # posterior. Va aquí (tras el dispatch) porque cada sub-flujo captura su propio
                # snapshot previo con fechas distintas.
                from ..doblada_snapshot_service import DobladaSnapshotService
                DobladaSnapshotService.capturar_snapshot_resultante(detalle)

            for fecha in CambioDescansoAplicacionService.fechas_afectadas(solicitud):
                CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)
            return True, "Cambio de día de descanso aplicado correctamente."
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error aplicando cambio de descanso")
            return False, f"Error aplicando cambio de descanso: {str(e)}"

    # --------------------------------------------------- empleados disponibles
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """Compañeros del grupo CONTRARIO al solicitante en ese fin de semana."""
        try:
            fecha_obj = self._parse(fecha)
            if not fecha_obj:
                return []
            grupo_sol = self._grupo_base(usuario_actual, fecha_obj)
            if not grupo_sol:
                return []
            grupo_contrario = 'PM' if grupo_sol == 'AM' else 'AM'

            from turnos.models import AsignarJornadaExplorador
            empleados = (Empleado.objects.filter(activo=True)
                         .exclude(id=usuario_actual.id).select_related('supervisor'))
            bases = {}
            for asg in (AsignarJornadaExplorador.objects
                        .filter(explorador__in=empleados, fecha_inicio__lte=fecha_obj)
                        .select_related('jornada', 'explorador').order_by('explorador_id', '-fecha_inicio')):
                bases.setdefault(asg.explorador_id, asg.jornada.nombre.upper())
            return [e for e in empleados if bases.get(e.id) == grupo_contrario]
        except Exception:
            return []

    def detalle(self, solicitud, datos):
        """
        Detalle propio de CAMBIO DESCANSO para la pantalla de consulta.

        Movido desde `views/detalle.py` en la Fase 2 (cerrar el OCP): la vista
        elegía con una cadena `if tipo_nombre == ...`, así que cada tipo nuevo
        obligaba a editarla. El cuerpo se trasladó SIN cambios de lógica; solo
        los imports relativos pasaron a absolutos al cambiar de paquete.
        """
        try:
            detalle = solicitud.doblada
            if detalle:
                fc = solicitud.fecha_cambio_turno
                datos['fechas']['fecha_cesion'] = fc.strftime('%d/%m/%Y') if fc else 'No especificada'
                datos['fechas']['fecha_pago'] = detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else '—'
                es_finde = bool(fc) and fc.weekday() in (5, 6)
                if es_finde:
                    datos['informacion_adicional']['modalidad'] = 'Fin de semana (intercambio ida y vuelta)'
                else:
                    sub = getattr(detalle, 'submodalidad_semana', None) or 'intercambio_dia'
                    sub_legible = {
                        'intercambio_dia': 'Entre semana: intercambio de día',
                        'jornadas_partidas': 'Entre semana: jornadas partidas',
                        'cobertura_misma_semana': 'Entre semana: cobertura con pago en la misma semana',
                        'cambio_doblada': 'Entre semana: cambio de doblada',
                    }.get(sub, sub)
                    datos['informacion_adicional']['modalidad'] = sub_legible
                    if sub == 'jornadas_partidas' and detalle.jornada_cedida:
                        datos['informacion_adicional']['jornada_cedida_partida'] = detalle.jornada_cedida.upper()
                    if sub == 'cobertura_misma_semana':
                        _tc = {
                            'cesion_completa': 'Día completo (AM y PM)',
                            'cesion_parcial_am': 'Solo jornada AM',
                            'cesion_parcial_pm': 'Solo jornada PM',
                        }.get(detalle.tipo_cesion, detalle.tipo_cesion)
                        datos['informacion_adicional']['te_cubren'] = _tc
                        # Deuda de 30 min: real si ya está aprobada; regla si sigue pendiente.
                        if solicitud.estado in ('aprobada', 'completada'):
                            from solicitudes.models import DeudaCorporativa as _DC
                            _dcs = list(_DC.objects.filter(solicitud_origen=solicitud)
                                        .exclude(estado='cancelada').select_related('explorador'))
                            if _dcs:
                                datos['informacion_adicional']['deuda_30min'] = '; '.join(
                                    f'{x.explorador.nombre}: {x.minutos} min '
                                    f'(dobla el {x.fecha_doblada.strftime("%d/%m/%Y")})'
                                    for x in _dcs
                                )
                            else:
                                datos['informacion_adicional']['deuda_30min'] = (
                                    'No se generó deuda de 30 min.'
                                )
                        else:
                            datos['informacion_adicional']['deuda_30min'] = (
                                'Se calcula al aprobar: 30 min solo para quien doble '
                                'sobre su propia jornada.'
                            )
                    elif sub == 'cambio_doblada':
                        datos['informacion_adicional']['nota'] = (
                            'Sin deuda: ambos ya doblaban un día, solo se intercambia cuál.'
                        )
                    else:
                        datos['informacion_adicional']['nota'] = 'Intercambio directo, sin deuda.'
        except Exception as e:
            logger.error(f"Error obteniendo detalles de CAMBIO DESCANSO: {e}")
            datos['fechas']['error'] = 'No se pudieron obtener los detalles del cambio de descanso'

    def validar_campos_requeridos(self, post):
        """Campos obligatorios de CAMBIO DESCANSO (movido del parser en la Fase 2)."""
        if not post.get('fecha_solicitud'):
            return False, 'El fin de semana que cambias es requerido'
        if not post.get('empleado_receptor'):
            return False, 'Debe seleccionar el compañero con quien intercambia el descanso'
        if not post.get('fecha_pago'):
            return False, 'El fin de semana de devolución es obligatorio (otro finde del mismo mes).'
        return True, ''

    def parsear_datos(self, post, solicitante, receptor):
        """
        Traduce el POST de CAMBIO DESCANSO (movido del parser en la Fase 2).

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
        Re-materializa un CAMBIO DESCANSO aprobado. Solo turnos, sin deudas: este
        tipo no genera deuda corporativa.

        Movido de `DobladaSnapshotService._reaplicar_cambio_descanso` en la Fase 2.
        """
        from solicitudes.services.cambio_descanso_aplicacion_service import (
            CambioDescansoAplicacionService as _CDS,
        )

        detalle = getattr(solicitud, 'doblada', None)
        if detalle is None:
            return

        fc = solicitud.fecha_cambio_turno
        if fc and fc.weekday() in (5, 6):
            # Sin `marcar_reemplazos`: aqui solo se reconstruyen turnos de una solicitud
            # que YA estaba aplicada; marcar reemplazos volveria 'reemplazada' una
            # solicitud vigente.
            _CDS.aplicar(solicitud, detalle, marcar_reemplazos=False)
            return

        sub = getattr(detalle, 'submodalidad_semana', None) or 'intercambio_dia'
        if sub == 'jornadas_partidas':
            _CDS.aplicar_semana_jornadas_partidas(solicitud, detalle)
        elif sub == 'cobertura_misma_semana':
            _CDS.aplicar_semana_cobertura(solicitud, detalle)
        elif sub == 'cambio_doblada':
            _CDS.aplicar_semana_cambio_doblada(solicitud, detalle)
        else:
            _CDS.aplicar_entre_semana(solicitud, detalle)

    def pares_que_reescribe(self, solicitud, fechas):
        """
        No deduce sus dias de la solicitud: los pide a `fechas_afectadas`, la misma
        fuente que usa la invalidacion de cache de su cancelacion. Incluye los dias
        OPUESTOS del finde, que pueden caer en otro mes.
        """
        from solicitudes.services.cambio_descanso_aplicacion_service import (
            CambioDescansoAplicacionService as _CDS,
        )

        return self._pares(solicitud, _CDS.fechas_afectadas(solicitud), todas=True)

    def revertir_cambios(self, solicitud):
        """
        Los meses NO se deducen de la solicitud: salen de `fechas_afectadas`, que
        incluye los dias OPUESTOS del finde y puede cruzar de mes.
        """
        from solicitudes.services.cambio_descanso_aplicacion_service import (
            CambioDescansoAplicacionService as _CDS,
        )

        if not getattr(solicitud, 'doblada', None):
            return
        _CDS.revertir(solicitud)
        self._invalidar_meses(solicitud, _CDS.fechas_afectadas(solicitud))

    def fecha_valida(self, analisis):
        """
        Los universales y -solo ENTRE SEMANA- el festivo.

        Un festivo de lunes a viernes tiene su propia alternancia: un grupo dobla y
        el otro descansa, y ese descanso no es el de la rotacion ordinaria, asi que
        no se puede intercambiar. Un festivo en SABADO O DOMINGO sigue siendo fin de
        semana, ahi manda la alternancia de findes y el intercambio si vale.

        Misma regla que aplica `validar_solicitud` en este archivo via
        `es_festivo_semana()`, que devuelve False para los festivos de finde.
        """
        if not self.fecha_valida_generica(analisis):
            return False
        festivo_entre_semana = (analisis.get('es_festivo')
                                and not analisis.get('es_sabado')
                                and not analisis.get('es_domingo'))
        return not festivo_entre_semana
