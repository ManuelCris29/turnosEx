"""
Use Case: CancelarSolicitud

Cancelar deshace un acuerdo, y quién puede deshacerlo depende de si ese acuerdo llegó a existir:

- PENDIENTE: nadie aceptó todavía, no hay nada aplicado. El solicitante la retira solo.
- APROBADA: el receptor ya dijo que sí y los turnos ya se movieron —los suyos también—. El
  solicitante NO la cancela por su cuenta: PIDE la cancelación y el receptor la aprueba o la
  rechaza. Mientras tanto el cambio sigue vigente.

Plazos (ver `core.constants`): el solicitante tiene 24 h desde la aprobación para pedirla, y el
receptor 24 h desde la petición para responder. Si el receptor no responde, la petición caduca y
el cambio queda firme: nadie se queda sin el turno que aceptó por el silencio del otro.

Un rechazo o una caducidad son definitivos —no se vuelve a pedir—. La salida es un cambio nuevo
o que un supervisor lo cancele desde Gestión (`execute_supervisor`, que no pasa por el receptor:
es una intervención administrativa, no una parte del acuerdo).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from core.constants import (
    EstadoCancelacion,
    VENTANA_PEDIR_CANCELACION_HORAS,
    VENTANA_RESPONDER_CANCELACION_HORAS,
)

if TYPE_CHECKING:
    from empleados.models import Empleado


# Formato de fecha de los mensajes al usuario (dd/mm/aaaa).
_FMT_FECHA = '%d/%m/%Y'


class CancelarSolicitudUseCase:

    def execute(self, solicitud_id: int, solicitante: "Empleado",
                motivo: str = '') -> Tuple[bool, str]:
        """
        Acción del SOLICITANTE sobre su propia solicitud.

        Si está pendiente la retira en el acto. Si ya está aprobada NO la cancela: registra la
        PETICIÓN de cancelación y deja la decisión en manos del receptor. En ese caso el segundo
        elemento de la tupla lo dice explícitamente — la vista lo devuelve tal cual al usuario,
        que si no creería que su cambio ya se deshizo.
        """
        from django.db import transaction
        from django.utils import timezone

        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar

        try:
            with transaction.atomic():
                solicitud = (
                    SolicitudCambio.objects
                    .select_for_update()
                    .select_related(
                        'explorador_solicitante',
                        'explorador_receptor',
                        'explorador_solicitante__supervisor',
                        'tipo_cambio',
                        'doblada',
                    )
                    .get(id=solicitud_id)
                )

                if solicitud.explorador_solicitante != solicitante:
                    return False, 'Solo puedes cancelar tus propias solicitudes'

                # Mismo lock que en la aprobación, y por el mismo motivo: cancelar LEE el estado
                # (guardia LIFO: ¿hay un cambio más reciente sobre estos días?) y después ESCRIBE
                # (revierte turnos y reconcilia). Sin bloquear a los exploradores, una aprobación
                # simultánea sobre uno de esos días no sería visible para la guardia y la
                # reversión la pisaría.
                from solicitudes.domain.bloqueo_partes import bloquear_partes
                bloquear_partes(solicitud)

                if solicitud.estado == 'pendiente':
                    transicionar(solicitud, 'cancelada', save=False)
                    # Una pendiente se resuelve Y se cancela en el mismo instante.
                    solicitud.fecha_resolucion = timezone.now()
                    solicitud.fecha_cancelacion = solicitud.fecha_resolucion
                    solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
                    solicitud.save()
                    return True, 'Solicitud cancelada correctamente'

                if solicitud.estado == 'aprobada':
                    # Ya hay acuerdo y turnos aplicados: se pide, no se cancela.
                    return self._pedir_cancelacion(solicitud, solicitante, motivo, timezone)

                return False, f'No se puede cancelar una solicitud en estado "{solicitud.estado}".'

        except SolicitudCambio.DoesNotExist:
            return False, 'Solicitud no encontrada'

    def execute_supervisor(self, solicitud_id: int, supervisor: "Empleado",
                           permitir_cierre_administrativo: bool = True) -> Tuple[bool, str]:
        """
        Cancelación desde GESTIÓN. El supervisor no pasa por el acuerdo —ni pide la cancelación
        ni espera al receptor, y tampoco le corren los plazos de 24 h: es una intervención
        administrativa—, pero sí le aplican las guardas que protegen los datos.

        Antes esta acción solo cambiaba el estado: la solicitud quedaba "cancelada" y los turnos
        seguían aplicados, así que el horario mostraba un intercambio que ya no existía.

        Las cuatro situaciones posibles:

        1. PENDIENTE — nunca se aplicó: basta con cancelarla.
        2. APROBADA y ningún día ha pasado — se revierte todo (turnos, deudas y reconciliación) y
           se cancela. Es la misma reversión que dispara el receptor al aprobar una cancelación.
        3. APROBADA y TODOS los días ya pasaron — se cancela SIN revertir: la gente ya trabajó esos
           días y borrar sus turnos sería reescribir el historial. Queda como cierre administrativo.
        4. APROBADA con días pasados Y futuros — se bloquea. Revertir borraría lo ya trabajado y no
           revertir dejaría el horario descuadrado hacia adelante. Para las dobladas la salida es
           reprogramar el día que falta; el mensaje lo dice.

        `permitir_cierre_administrativo=False` rechaza el caso 3. Lo usa ELIMINAR: cancelar una
        solicitud ya cumplida conserva los turnos y deja el registro explicando de dónde salen,
        pero BORRARLA los dejaría puestos y sin explicación — turnos huérfanos, imposibles de
        rastrear. Cerrar sí, borrar no.
        """
        from django.db import transaction
        from django.utils import timezone

        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar
        from solicitudes.domain.bloqueo_partes import bloquear_partes

        try:
            with transaction.atomic():
                solicitud = (
                    SolicitudCambio.objects
                    .select_for_update()
                    .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio',
                                    'doblada', 'doblada_permanente', 'cambio_permanente')
                    .get(id=solicitud_id)
                )

                if solicitud.estado not in ('pendiente', 'aprobada'):
                    return False, (f'La solicitud ya está '
                                   f'{solicitud.get_estado_display().lower()}.')

                # Mismo lock que la cancelación del explorador: se LEE el estado (guardias) y
                # después se ESCRIBE (reversión), así que las partes deben quedar bloqueadas.
                bloquear_partes(solicitud)

                nota = (f"\n\nCancelada desde gestión por "
                        f"{supervisor.nombre} {supervisor.apellido}.")

                if solicitud.estado == 'pendiente':
                    transicionar(solicitud, 'cancelada', save=False)
                    solicitud.fecha_resolucion = timezone.now()
                    solicitud.fecha_cancelacion = solicitud.fecha_resolucion
                    solicitud.comentario = f"{solicitud.comentario or ''}{nota}"
                    solicitud.save()
                    return True, 'Solicitud cancelada.'

                afectadas = self.fechas_afectadas(solicitud)
                pasadas = self.fechas_ya_cumplidas(solicitud)

                if pasadas and len(pasadas) < len(afectadas):
                    faltan = ', '.join(f.strftime(_FMT_FECHA)
                                       for f in afectadas if f not in pasadas)
                    hechas = ', '.join(f.strftime(_FMT_FECHA) for f in pasadas)
                    tipo = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else ''
                    alternativa = (
                        ' Usa "Reprogramar" para reasignar el día que falta.'
                        if tipo in ('DOBLADA', 'D FDS', 'DOBLADA PERMANENTE') else ''
                    )
                    return False, (
                        f'No se puede cancelar: esta solicitud ya se cumplió en parte '
                        f'({hechas}) y todavía tiene días por delante ({faltan}). Cancelarla '
                        f'borraría días ya trabajados.{alternativa}'
                    )

                if pasadas:
                    if not permitir_cierre_administrativo:
                        hechas = ', '.join(f.strftime(_FMT_FECHA) for f in pasadas)
                        return False, (
                            f'No se puede eliminar: estos días ya se trabajaron ({hechas}). '
                            f'Borrar la solicitud dejaría esos turnos puestos y sin nada que '
                            f'explique de dónde salen. Usa "Cancelar": conserva el historial y '
                            f'cierra el registro.'
                        )
                    # Todo ocurrió ya: se cierra el registro sin tocar el historial de turnos.
                    transicionar(solicitud, 'cancelada', save=False)
                    solicitud.fecha_cancelacion = timezone.now()
                    solicitud.comentario = (
                        f"{solicitud.comentario or ''}{nota} Los días ya transcurridos "
                        f"se conservan tal cual (no se reescribe el historial)."
                    )
                    solicitud.save()
                    return True, ('Solicitud cancelada. Los días ya trabajados se conservan '
                                  'en el historial.')

                bloqueo = self.bloqueo_lifo(solicitud)
                if bloqueo:
                    return False, bloqueo

                bloqueo = self.bloqueo_integridad(solicitud)
                if bloqueo:
                    return False, bloqueo

                self._revertir_por_tipo(solicitud)
                try:
                    solicitud.refresh_from_db(fields=['turno_origen', 'turno_destino'])
                except Exception:
                    solicitud.turno_origen = None
                    solicitud.turno_destino = None

                transicionar(solicitud, 'cancelada', save=False)
                solicitud.fecha_cancelacion = timezone.now()
                solicitud.comentario = f"{solicitud.comentario or ''}{nota}"
                solicitud.save()
                return True, 'Solicitud cancelada y turnos restaurados.'

        except SolicitudCambio.DoesNotExist:
            return False, 'Solicitud no encontrada.'

    # ------------------------------------------------------------------
    # Cancelación consensuada de una solicitud APROBADA
    # ------------------------------------------------------------------

    def _pedir_cancelacion(self, solicitud, solicitante, motivo, timezone):
        """
        Registra la petición de cancelación. NO toca turnos ni estado: la solicitud sigue
        'aprobada' y vigente hasta que el receptor responda.

        Las guardias LIFO y de integridad se comprueban YA, antes de molestar al receptor: si la
        reversión es imposible, la petición nunca llega a existir y el solicitante se entera al
        instante en vez de esperar un sí que no se podría cumplir. Se vuelven a comprobar al
        aprobar, porque entre una cosa y otra pueden pasar hasta 24 horas.
        """
        if solicitud.cancelacion_estado == EstadoCancelacion.PENDIENTE:
            receptor = solicitud.explorador_receptor
            return False, (
                f'Ya pediste cancelar esta solicitud. Está esperando la respuesta de '
                f'{receptor.nombre} {receptor.apellido}.'
            )
        if solicitud.cancelacion_estado in EstadoCancelacion.TERMINALES:
            return False, self._mensaje_cancelacion_cerrada(solicitud)

        if not solicitud.explorador_receptor_id:
            return False, ('No se puede cancelar: esta solicitud no tiene receptor registrado. '
                           'Pídele a tu supervisor que la cancele desde Gestión.')

        if not solicitud.fecha_resolucion:
            return False, 'No se puede cancelar: la solicitud no tiene fecha de aprobación registrada.'

        horas = (timezone.now() - solicitud.fecha_resolucion).total_seconds() / 3600
        if horas > VENTANA_PEDIR_CANCELACION_HORAS:
            return False, (
                f'Ya no es posible cancelar esta solicitud. Solo se puede pedir la cancelación '
                f'dentro de las {VENTANA_PEDIR_CANCELACION_HORAS} horas posteriores a su '
                f'aprobación (han pasado {int(horas)} horas). Pídele a tu supervisor que la '
                f'cancele desde Gestión.'
            )

        # Días ya trabajados: revertirlos reescribiría el historial. Mismo criterio que gestión.
        if self.fechas_ya_cumplidas(solicitud):
            return False, ('No se puede cancelar: esta solicitud ya se cumplió, en todo o en '
                           'parte. Consulta con tu supervisor.')

        bloqueo = self.bloqueo_lifo(solicitud) or self.bloqueo_integridad(solicitud)
        if bloqueo:
            return False, bloqueo

        solicitud.cancelacion_estado = EstadoCancelacion.PENDIENTE
        solicitud.cancelacion_solicitada_por = solicitante
        solicitud.cancelacion_solicitada_en = timezone.now()
        solicitud.cancelacion_motivo = (motivo or '').strip() or None
        solicitud.save(update_fields=[
            'cancelacion_estado', 'cancelacion_solicitada_por',
            'cancelacion_solicitada_en', 'cancelacion_motivo',
        ])

        receptor = solicitud.explorador_receptor
        return True, (
            f'Se envió tu solicitud de cancelación a {receptor.nombre} {receptor.apellido}. '
            f'El cambio sigue vigente hasta que la apruebe. Tiene '
            f'{VENTANA_RESPONDER_CANCELACION_HORAS} horas para responder.'
        )

    def responder_cancelacion(self, solicitud_id, receptor, aprueba, motivo=''):
        """
        Respuesta del RECEPTOR a una petición de cancelación.

        Aprobar es lo único que revierte los turnos: hasta aquí el cambio estuvo vigente.
        Rechazar (o dejar caducar el plazo) deja el cambio FIRME y cierra el asunto: no se
        vuelve a pedir; para eso está un cambio nuevo o la cancelación del supervisor.
        """
        from django.db import transaction
        from django.utils import timezone

        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar
        from solicitudes.domain.bloqueo_partes import bloquear_partes

        try:
            with transaction.atomic():
                solicitud = (
                    SolicitudCambio.objects
                    .select_for_update()
                    .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio',
                                    'doblada', 'doblada_permanente', 'cambio_permanente')
                    .get(id=solicitud_id)
                )

                if solicitud.explorador_receptor_id != receptor.id:
                    return False, 'No eres el receptor de esta solicitud.'

                if solicitud.cancelacion_estado != EstadoCancelacion.PENDIENTE:
                    if solicitud.cancelacion_estado in EstadoCancelacion.TERMINALES:
                        return False, self._mensaje_cancelacion_cerrada(solicitud)
                    return False, 'Esta solicitud no tiene ninguna cancelación pendiente.'

                if solicitud.estado != 'aprobada':
                    return False, (f'La solicitud ya está '
                                   f'{solicitud.get_estado_display().lower()}.')

                if self._caducar_si_vencida(solicitud, timezone):
                    return False, (
                        f'El plazo de {VENTANA_RESPONDER_CANCELACION_HORAS} horas para responder '
                        f'ya venció, así que el cambio quedó firme.'
                    )

                # Se bloquea a las partes por lo mismo que en el resto de cancelaciones: se LEE
                # el estado (guardias) y después se ESCRIBE (reversión).
                bloquear_partes(solicitud)

                ahora = timezone.now()
                solicitud.cancelacion_respondida_por = receptor
                solicitud.cancelacion_respondida_en = ahora
                quien = f"{receptor.nombre} {receptor.apellido}"
                nota_motivo = f" Motivo: {motivo.strip()}" if (motivo or '').strip() else ''

                if not aprueba:
                    solicitud.cancelacion_estado = EstadoCancelacion.RECHAZADA
                    solicitud.cancelacion_motivo = (
                        f"{solicitud.cancelacion_motivo or ''}\n\nCancelación rechazada por "
                        f"{quien}.{nota_motivo}"
                    ).strip()
                    solicitud.save(update_fields=[
                        'cancelacion_estado', 'cancelacion_respondida_por',
                        'cancelacion_respondida_en', 'cancelacion_motivo',
                    ])
                    return True, 'Rechazaste la cancelación. El cambio sigue vigente.'

                # Aprobar: se vuelven a comprobar las guardias, porque entre la petición y ahora
                # pudo entrar otro cambio sobre los mismos días.
                bloqueo = self.bloqueo_lifo(solicitud) or self.bloqueo_integridad(solicitud)
                if bloqueo:
                    return False, bloqueo

                if self.fechas_ya_cumplidas(solicitud):
                    return False, ('No se puede cancelar: estos días ya se trabajaron. '
                                   'Consulta con tu supervisor.')

                self._revertir_por_tipo(solicitud)

                # La reversión BORRA los turnos materializados (y los recrea con ids nuevos). Los
                # FK turno_origen/turno_destino apuntaban a esos turnos borrados; en BD ya
                # quedaron NULL (on_delete=SET_NULL), pero este objeto en memoria conserva el id
                # viejo. Sincronizamos para no reescribir un id inexistente al guardar.
                try:
                    solicitud.refresh_from_db(fields=['turno_origen', 'turno_destino'])
                except Exception:
                    solicitud.turno_origen = None
                    solicitud.turno_destino = None

                transicionar(solicitud, 'cancelada', save=False)
                # `fecha_resolucion` se queda con la hora de APROBACIÓN (de ahí cuelgan la ventana
                # y el orden LIFO); la hora de la cancelación va en su propio campo.
                solicitud.fecha_cancelacion = ahora
                solicitud.cancelacion_estado = EstadoCancelacion.APROBADA
                solicitud.comentario = (
                    f"{solicitud.comentario or ''}\n\n"
                    f"Cancelación pedida por el solicitante y aprobada por {quien}.{nota_motivo}"
                )
                solicitud.save()
                return True, ('Cancelación aprobada: la solicitud se canceló y los turnos '
                              'volvieron a su estado anterior.')

        except SolicitudCambio.DoesNotExist:
            return False, 'Solicitud no encontrada.'

    def _caducar_si_vencida(self, solicitud, timezone) -> bool:
        """
        Marca CADUCADA la petición si el receptor se pasó del plazo. Devuelve True si caducó.

        La caducidad se evalúa al leerla o al responderla, no con un proceso de fondo: una
        petición vencida no tiene ningún efecto pendiente que aplicar (el cambio simplemente
        sigue vigente), así que basta con reconocerla cuando alguien la mira.
        """
        if solicitud.cancelacion_estado != EstadoCancelacion.PENDIENTE:
            return False
        if not solicitud.cancelacion_solicitada_en:
            return False
        horas = (timezone.now() - solicitud.cancelacion_solicitada_en).total_seconds() / 3600
        if horas <= VENTANA_RESPONDER_CANCELACION_HORAS:
            return False
        solicitud.cancelacion_estado = EstadoCancelacion.CADUCADA
        solicitud.save(update_fields=['cancelacion_estado'])
        return True

    @staticmethod
    def _mensaje_cancelacion_cerrada(solicitud) -> str:
        """Por qué ya no se puede volver a pedir la cancelación de esta solicitud."""
        if solicitud.cancelacion_estado == EstadoCancelacion.RECHAZADA:
            return ('El receptor ya rechazó la cancelación de esta solicitud, así que el cambio '
                    'quedó firme. Si necesitas volver a tu turno original, solicita un cambio '
                    'nuevo o consulta con tu supervisor.')
        if solicitud.cancelacion_estado == EstadoCancelacion.CADUCADA:
            return (f'La cancelación caducó: el receptor no respondió dentro de las '
                    f'{VENTANA_RESPONDER_CANCELACION_HORAS} horas y el cambio quedó firme. Si '
                    f'necesitas volver a tu turno original, solicita un cambio nuevo o consulta '
                    f'con tu supervisor.')
        return 'Esta solicitud ya fue cancelada.'

    def bloqueo_lifo(self, solicitud) -> str | None:
        """
        Guardia LIFO: motivo por el que NO se puede revertir esta solicitud, o None si se puede.

        Si hay otra solicitud aprobada MÁS RECIENTE sobre alguno de los mismos (persona, día),
        revertir esta pisaría aquella. Se deshace en orden inverso. Vale para quien cancela:
        el explorador dentro de su ventana y el supervisor desde gestión.
        """
        from django.db.models import Q
        from datetime import date as _date
        from solicitudes.models import SolicitudCambio

        if not solicitud.fecha_resolucion:
            return None

        mios = self._pares_afectados(solicitud)
        personas = [solicitud.explorador_solicitante_id, solicitud.explorador_receptor_id]
        posteriores = (
            SolicitudCambio.objects
            .filter(estado='aprobada', fecha_resolucion__gt=solicitud.fecha_resolucion)
            .filter(Q(explorador_solicitante_id__in=personas) | Q(explorador_receptor_id__in=personas))
            .exclude(id=solicitud.id)
            .select_related('doblada', 'doblada_permanente', 'cambio_permanente')
        )
        for otra in posteriores:
            comunes = mios & self._pares_afectados(otra)
            if comunes:
                fechas = sorted({k.split(':', 1)[1] for k in comunes})
                fmt = ', '.join(_date.fromisoformat(f).strftime('%d/%m') for f in fechas)
                return (
                    f'No puedes cancelar este cambio: hay otro más reciente sobre el mismo '
                    f'día ({fmt}). Cancela primero el cambio más reciente.'
                )
        return None

    def bloqueo_integridad(self, solicitud) -> str | None:
        """
        Guardia de integridad: motivo por el que revertir PISARÍA un cambio ajeno, o None.

        Revertir consiste en restaurar `snapshot_turnos_previos`, y eso sólo es correcto si
        NADIE tocó esos días desde que se aprobó. La guardia LIFO no basta: sólo mira otras
        `SolicitudCambio` aprobadas después. No ve los permisos especiales, ni las
        reprogramaciones de doblada, ni las ediciones manuales/admin.

        Caso real que lo motivó: A y B hacen un CT. Antes de que A cancele, B cambia su turno
        por otra vía. Si A cancela, la restauración escribe sobre B el turno viejo del
        snapshot —que B ya no tiene— y quedan dos jornadas en conflicto.

        Por eso se compara el estado ACTUAL contra `snapshot_turnos_resultantes` (lo que esta
        solicitud dejó). Cualquier discrepancia, venga de donde venga, se detecta.

        Cuando bloquea, la solicitud sigue APROBADA y vigente: no hay forzar (ni el explorador
        ni el supervisor), porque forzar reintroduce exactamente el conflicto que se evita. La
        salida es solicitar un cambio de turno NUEVO, y el mensaje lo dice.
        """
        import logging
        from datetime import date as _date
        from turnos.models import Turno

        resultante = (
            getattr(solicitud, 'snapshot_turnos_resultantes', None)
            or getattr(getattr(solicitud, 'doblada', None), 'snapshot_turnos_resultantes', None)
            or getattr(getattr(solicitud, 'doblada_permanente', None), 'snapshot_turnos_resultantes', None)
            or {}
        )
        if not resultante:
            # Solicitud anterior a este mecanismo, o tipo al que no se le cableó la captura.
            # NO se bloquea: hacerlo volvería incancelable todo lo preexistente. Se queda con
            # las guardias antiguas (LIFO + fechas ya cumplidas).
            #
            # Es lo contrario del fallback de `_pares_afectados`, que falla CERRADO: allí
            # sobre-estimar no cuesta nada (bloquea de más), aquí sobre-estimar significaría
            # bloquear cancelaciones legítimas en masa.
            logging.getLogger(__name__).warning(
                'Cancelación de solicitud %s sin snapshot resultante: se omite la guardia de '
                'integridad.', solicitud.id,
            )
            return None

        conflictos = {}
        for clave, filas in resultante.items():
            try:
                emp_str, fecha_str = clave.split(':', 1)
                emp_id = int(emp_str)
                fecha = _date.fromisoformat(fecha_str)
            except (ValueError, TypeError, AttributeError):
                continue

            esperado = {self._huella_fila(f) for f in (filas or [])}
            actual = {
                self._huella_turno(t)
                for t in Turno.objects.filter(explorador_id=emp_id, fecha=fecha)
                                      .select_related('jornada')
            }
            if esperado != actual:
                conflictos.setdefault(emp_id, set()).add(fecha)

        if not conflictos:
            return None
        return self._mensaje_conflicto(solicitud, conflictos)

    @staticmethod
    def _huella_fila(fila: dict) -> tuple:
        """Identidad comparable de una fila de snapshot."""
        return (
            str(fila.get('jornada_nombre') or '').upper(),
            fila.get('sala_id'),
            fila.get('tipo_cambio') or '',
        )

    @staticmethod
    def _huella_turno(turno) -> tuple:
        """Misma identidad, leída de un Turno real. Debe casar con `_huella_fila`."""
        return (
            turno.jornada.nombre.upper(),
            turno.sala_id,
            turno.tipo_cambio or '',
        )

    @staticmethod
    def _mensaje_conflicto(solicitud, conflictos: dict) -> str:
        """Mensaje de bloqueo: quién, qué días, y cuál es la salida."""
        from empleados.models import Empleado

        nombres = {
            e.id: f"{e.nombre} {e.apellido}".strip()
            for e in Empleado.objects.filter(id__in=conflictos.keys())
        }
        partes = []
        for emp_id, fechas in sorted(conflictos.items()):
            dias = ', '.join(f.strftime('%d/%m') for f in sorted(fechas))
            partes.append(f"{nombres.get(emp_id, f'explorador {emp_id}')} ({dias})")
        detalle = '; '.join(partes)
        return (
            f'No se puede cancelar: el turno de {detalle} ya fue modificado por otro cambio '
            f'posterior a esta aprobación. Cancelar ahora dejaría un conflicto de jornadas, '
            f'así que esta solicitud se mantiene vigente. Si necesitas volver a tu turno '
            f'original, solicita un nuevo cambio de turno.'
        )

    @classmethod
    def fechas_afectadas(cls, solicitud) -> list:
        """Fechas concretas que la solicitud tocó (ordenadas), derivadas de los pares afectados."""
        from datetime import date as _date

        fechas = set()
        for clave in cls._pares_afectados(solicitud):
            try:
                fechas.add(_date.fromisoformat(clave.split(':', 1)[1]))
            except (ValueError, IndexError):
                continue
        return sorted(fechas)

    @classmethod
    def fechas_ya_cumplidas(cls, solicitud) -> list:
        """
        Fechas de la solicitud que YA PASARON: revertirlas reescribiría días efectivamente
        trabajados (borraría turnos que la gente hizo). Hoy es cancelable — el turno aún corre—,
        mismo criterio que `ReprogramacionDobladaService.puede_cancelar`.
        """
        from django.utils import timezone

        hoy = timezone.localdate()
        return [f for f in cls.fechas_afectadas(solicitud) if f < hoy]

    @staticmethod
    def _pares_afectados(solicitud) -> set:
        """
        Claves 'empleado_id:YYYY-MM-DD' que esta solicitud toca. Es la base de la guardia LIFO.

        La fuente preferida es el snapshot (dice exactamente qué se pisó). Pero NO puede ser la
        única: una solicitud sin snapshot —las anteriores al patrón #13, o cualquiera cuyo detalle
        quedara sin capturar— devolvía conjunto vacío, la guardia se saltaba entera y se podía
        cancelar por debajo de un cambio más reciente, pisándolo.

        Por eso, sin snapshot se DERIVAN los pares de las fechas propias de la solicitud. La
        guardia falla cerrado: puede sobre-estimar el solape (bloquea de más, el usuario cancela
        primero el reciente), nunca sub-estimarlo.
        """
        snap = (
            getattr(solicitud, 'snapshot_turnos_previos', None)
            or getattr(getattr(solicitud, 'doblada', None), 'snapshot_turnos_previos', None)
            or getattr(getattr(solicitud, 'doblada_permanente', None), 'snapshot_turnos_previos', None)
            or {}
        )
        if snap:
            return set(snap.keys())
        return CancelarSolicitudUseCase._pares_derivados_de_fechas(solicitud)

    @staticmethod
    def _pares_derivados_de_fechas(solicitud) -> set:
        """Fallback sin snapshot: pares (persona, fecha) a partir de los campos de la solicitud."""
        from datetime import timedelta

        personas = [pid for pid in (solicitud.explorador_solicitante_id,
                                    solicitud.explorador_receptor_id) if pid]
        fechas = set()
        if solicitud.fecha_cambio_turno:
            fechas.add(solicitud.fecha_cambio_turno)

        detalle = (getattr(solicitud, 'doblada', None)
                   or getattr(solicitud, 'doblada_permanente', None)
                   or getattr(solicitud, 'cambio_permanente', None))
        if detalle is not None:
            if getattr(detalle, 'fecha_pago', None):
                fechas.add(detalle.fecha_pago)
            if getattr(detalle, 'fecha_pago_semana', None):
                fechas.add(detalle.fecha_pago_semana)
            # Rangos (CT permanente, doblada permanente): todo el intervalo cuenta como tocado.
            inicio = getattr(detalle, 'fecha_inicio', None)
            fin = getattr(detalle, 'fecha_fin', None) or inicio
            if inicio and fin:
                d = inicio
                while d <= fin:
                    fechas.add(d)
                    d += timedelta(days=1)

        return {f"{pid}:{f.isoformat()}" for pid in personas for f in fechas}

    @staticmethod
    def _revertir_por_tipo(solicitud) -> None:
        """
        Deshace el efecto de la solicitud e invalida la cache de los meses tocados.
        Lo hace la STRATEGY.

        Aqui habia una cadena `if tipo == ...` con seis ramas, cada una con su
        revertidor y su calculo de meses. Anadir un tipo obligaba a editar el caso
        de uso de CANCELACION, que es el sitio del proyecto donde un descuido sale
        mas caro: revierte turnos ya aplicados.

        La guardia por modelo de detalle se conserva DENTRO de cada strategy: sin
        detalle no hay efecto que deshacer y no se toca nada. Revertir a ciegas si
        escribiria turnos.

        Un tipo sin strategy registrada no revierte nada, igual que antes: aquella
        cadena tampoco tenia `else`.
        """
        from solicitudes.services.solicitud_factory import SolicitudFactory

        # `get_strategy_registrada` y NO `get_strategy`: esta ultima cae a
        # CambioTurnoStrategy para un tipo desconocido, y aqui eso significaria
        # revertir "como si fuera un cambio de turno" algo que no lo es. La cadena
        # anterior no tenia `else` precisamente para no hacer nada en ese caso.
        estrategia = SolicitudFactory.get_strategy_registrada(solicitud.tipo_cambio)
        if estrategia is None:
            return
        estrategia.revertir_cambios(solicitud)
