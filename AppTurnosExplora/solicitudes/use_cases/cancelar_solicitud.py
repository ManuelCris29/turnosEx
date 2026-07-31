"""
Use Case: CancelarSolicitud

Encapsula la regla de negocio de cancelación:
- Pendiente: puede cancelar sin restricción de tiempo.
- Aprobada: solo dentro de la ventana de 30 minutos (guardia LIFO).
- Cualquier otro estado: no se puede cancelar.

Extrae toda la lógica de negocio que estaba en CancelarSolicitudView
y la coloca en la capa de aplicación correcta.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from empleados.models import Empleado


VENTANA_CANCELACION_MINUTOS = 30


class CancelarSolicitudUseCase:

    def execute(self, solicitud_id: int, solicitante: "Empleado") -> Tuple[bool, str]:
        from django.db import transaction
        from django.utils import timezone
        from datetime import date as _date

        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar
        from solicitudes.repositories.solicitud_repository import SolicitudRepository

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
                    solicitud.fecha_resolucion = timezone.now()
                    solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
                    solicitud.save()
                    return True, 'Solicitud cancelada correctamente'

                if solicitud.estado == 'aprobada':
                    ok, msg = self._cancelar_aprobada(solicitud, solicitante, timezone)
                    if not ok:
                        return False, msg
                    return True, 'Solicitud cancelada correctamente'

                return False, f'No se puede cancelar una solicitud en estado "{solicitud.estado}".'

        except SolicitudCambio.DoesNotExist:
            return False, 'Solicitud no encontrada'

    def execute_supervisor(self, solicitud_id: int, supervisor: "Empleado",
                           permitir_cierre_administrativo: bool = True) -> Tuple[bool, str]:
        """
        Cancelación desde GESTIÓN. El supervisor no tiene la ventana de 30 minutos —esa limita al
        explorador—, pero sí las guardas que protegen los datos.

        Antes esta acción solo cambiaba el estado: la solicitud quedaba "cancelada" y los turnos
        seguían aplicados, así que el horario mostraba un intercambio que ya no existía.

        Las cuatro situaciones posibles:

        1. PENDIENTE — nunca se aplicó: basta con cancelarla.
        2. APROBADA y ningún día ha pasado — se revierte todo (turnos, deudas y reconciliación) y
           se cancela. Es lo mismo que hace el explorador en su ventana.
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
                    solicitud.comentario = f"{solicitud.comentario or ''}{nota}"
                    solicitud.save()
                    return True, 'Solicitud cancelada.'

                afectadas = self.fechas_afectadas(solicitud)
                pasadas = self.fechas_ya_cumplidas(solicitud)

                if pasadas and len(pasadas) < len(afectadas):
                    faltan = ', '.join(f.strftime('%d/%m/%Y')
                                       for f in afectadas if f not in pasadas)
                    hechas = ', '.join(f.strftime('%d/%m/%Y') for f in pasadas)
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
                        hechas = ', '.join(f.strftime('%d/%m/%Y') for f in pasadas)
                        return False, (
                            f'No se puede eliminar: estos días ya se trabajaron ({hechas}). '
                            f'Borrar la solicitud dejaría esos turnos puestos y sin nada que '
                            f'explique de dónde salen. Usa "Cancelar": conserva el historial y '
                            f'cierra el registro.'
                        )
                    # Todo ocurrió ya: se cierra el registro sin tocar el historial de turnos.
                    transicionar(solicitud, 'cancelada', save=False)
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
                solicitud.comentario = f"{solicitud.comentario or ''}{nota}"
                solicitud.save()
                return True, 'Solicitud cancelada y turnos restaurados.'

        except SolicitudCambio.DoesNotExist:
            return False, 'Solicitud no encontrada.'

    def _cancelar_aprobada(self, solicitud, solicitante, timezone) -> Tuple[bool, str]:
        from django.db.models import Q
        from datetime import date as _date
        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar

        if not solicitud.fecha_resolucion:
            return False, 'No se puede cancelar: la solicitud no tiene fecha de aprobación registrada.'

        minutos = (timezone.now() - solicitud.fecha_resolucion).total_seconds() / 60
        if minutos > VENTANA_CANCELACION_MINUTOS:
            return False, (
                f'Ya no es posible cancelar esta solicitud. Solo se puede cancelar dentro de los '
                f'{VENTANA_CANCELACION_MINUTOS} minutos posteriores a su aprobación '
                f'(han pasado {int(minutos)} minutos).'
            )

        bloqueo = self.bloqueo_lifo(solicitud)
        if bloqueo:
            return False, bloqueo

        bloqueo = self.bloqueo_integridad(solicitud)
        if bloqueo:
            return False, bloqueo

        self._revertir_por_tipo(solicitud)

        # La reversión BORRA los turnos materializados (y los recrea con ids nuevos). Los FK
        # turno_origen/turno_destino apuntaban a esos turnos borrados; en BD ya quedaron NULL
        # (on_delete=SET_NULL), pero este objeto en memoria conserva el id viejo. Sincronizamos
        # para no reescribir un id inexistente al guardar (evita IntegrityError al cancelar CT).
        try:
            solicitud.refresh_from_db(fields=['turno_origen', 'turno_destino'])
        except Exception:
            solicitud.turno_origen = None
            solicitud.turno_destino = None

        transicionar(solicitud, 'cancelada', save=False)
        solicitud.comentario = (
            f"{solicitud.comentario or ''}\n\n"
            f"Cancelada por el solicitante dentro de la ventana de {VENTANA_CANCELACION_MINUTOS} minutos."
        )
        solicitud.save()
        return True, 'ok'

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
        from core.services.cache_service import CacheService as CS
        from datetime import timedelta

        tipo = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else ''

        if tipo == 'DOBLADA' and getattr(solicitud, 'doblada', None):
            from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
            DobladaAplicacionService.revertir_doblada_aplicada(solicitud)
            detalle = solicitud.doblada
            for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

        elif tipo == 'D FDS' and getattr(solicitud, 'doblada', None):
            from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService
            DFDSAplicacionService.revertir(solicitud)
            detalle = solicitud.doblada
            for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                if fecha:
                    CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                    CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

        elif tipo == 'CAMBIO TURNO':
            from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy
            CambioTurnoStrategy.revertir(solicitud)
            f = solicitud.fecha_cambio_turno
            if f:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, f.month, f.year)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, f.month, f.year)

        elif tipo == 'CT PERMANENTE' and getattr(solicitud, 'cambio_permanente', None):
            from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy
            CTPermanenteStrategy.revertir(solicitud)
            det = solicitud.cambio_permanente
            fin = det.fecha_fin or det.fecha_inicio
            meses = set()
            d = det.fecha_inicio
            while d <= fin:
                meses.add((d.month, d.year))
                d += timedelta(days=28)
            meses.add((fin.month, fin.year))
            for (m, y) in meses:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, m, y)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, m, y)

        elif tipo == 'CAMBIO DESCANSO' and getattr(solicitud, 'doblada', None):
            from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
            CambioDescansoAplicacionService.revertir(solicitud)
            # Incluye los días OPUESTOS del finde: pueden caer en otro mes (ver fechas_afectadas).
            for fecha in CambioDescansoAplicacionService.fechas_afectadas(solicitud):
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

        elif tipo == 'DOBLADA PERMANENTE' and getattr(solicitud, 'doblada_permanente', None):
            from solicitudes.services.doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService
            DobladaPermanenteAplicacionService.revertir(solicitud)
            det = solicitud.doblada_permanente
            meses = set()
            d = det.fecha_inicio
            while d <= det.fecha_fin:
                meses.add((d.month, d.year))
                d += timedelta(days=28)
            meses.add((det.fecha_fin.month, det.fecha_fin.year))
            for (m, y) in meses:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, m, y)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, m, y)
