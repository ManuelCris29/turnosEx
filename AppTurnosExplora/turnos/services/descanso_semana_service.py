"""
Servicio del descanso de ENTRE SEMANA (manual).

El descanso normal de semana es el lunes de mantenimiento (descansan AM y PM). En semanas
con temporada/festivo el supervisor define manualmente el día de descanso por jornada
(modelo DescansoSemanaManual). Este servicio resuelve esa consulta de forma centralizada.
"""
import logging
from datetime import date
from collections import defaultdict
from django.db import transaction
from turnos.models import DescansoSemanaManual
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

# Motivo que gestiona la planeación ANUAL. Los descansos con otro motivo se crean/editan
# uno a uno desde la lista y la pantalla anual no los toca nunca.
MOTIVO_ANUAL = 'temporada'


class DescansoSemanaConflicto(Exception):
    """Se intentó alterar el descanso de un día que ya tiene solicitudes aprobadas."""


class DescansoSemanaService:

    @staticmethod
    def es_descanso_semana_manual(jornada_nombre: str, fecha: date) -> bool:
        """True si la jornada (AM/PM) tiene descanso manual configurado ese día (lun-vie)."""
        if not jornada_nombre or not fecha:
            return False
        if fecha.weekday() >= 5:  # esto es para entre semana, no fines de semana
            return False
        return DescansoSemanaManual.objects.filter(
            jornada__nombre__iexact=jornada_nombre,
            fecha=fecha,
            activo=True,
        ).exists()

    @staticmethod
    def es_dia_descanso_temporada(fecha: date) -> bool:
        """
        ¿`fecha` es uno de los días de descanso FIJADOS de la temporada (de CUALQUIER jornada)?

        REGLA DE NEGOCIO: esos días solo se modifican desde el formulario de CAMBIO DESCANSO,
        que para eso tiene sus cinco opciones (intercambiar el día, jornadas partidas, que me
        cubran mi día, cambio de doblada, permiso de media jornada). Ningún otro formulario
        puede tocarlos. El resto de la temporada SÍ queda disponible para los demás: esto veta
        dos fechas por semana, no la temporada entera.

        Se pregunta a nivel de FECHA y no de jornada a propósito: en una semana de temporada el
        descanso de un grupo es el día de trabajo COMPLETO del otro, y los dos lados son
        exactamente lo que el formulario de cambio de descanso intercambia. Una sola
        comprobación cubre el par.

        ⚠️ NO confundir con `DiaEspecial.es_temporada_en(fecha)` (usado por
        `ct_permanente_helper._dia_calendario_no_apto`): ese marca la SEMANA de temporada; este
        marca los DOS DÍAS de descanso que el supervisor fijó dentro de ella. Son conjuntos
        distintos — comprobado el 07/08/2026: `_dia_calendario_no_apto(2026-09-15)` devuelve
        None sobre un día que sí es descanso fijado de temporada.

        Complementa `es_descanso_semana_manual`, que responde por UNA jornada ("¿descanso AM
        este día?"); aquí interesa si la fecha pertenece al par, sea de quien sea.
        """
        if not fecha:
            return False
        if fecha.weekday() >= 5:  # el descanso de semana no aplica a fines de semana
            return False
        return DescansoSemanaManual.objects.filter(
            fecha=fecha, activo=True, motivo=MOTIVO_ANUAL,
        ).exists()

    @staticmethod
    def descansos_anual(anio: int, motivo: str = MOTIVO_ANUAL) -> dict:
        """
        {fecha_iso: [jornadas]} de los descansos de semana del año DEL MOTIVO dado (para
        precargar el calendario anual). Ej: {'2026-07-07': ['AM'], '2026-07-10': ['PM']}.

        Se filtra por motivo a propósito: `guardar_anual` solo borra/recrea ese motivo, así
        que precargar los demás haría que la pantalla anual se apropiara de descansos que no
        gestiona (y chocara con la unicidad (fecha, jornada) al guardar).
        """
        res = defaultdict(list)
        qs = (DescansoSemanaManual.objects
              .filter(fecha__year=anio, activo=True, motivo=motivo)
              .select_related('jornada'))
        for d in qs:
            res[d.fecha.isoformat()].append(d.jornada.nombre.upper())
        return {f: sorted(v) for f, v in res.items()}

    @staticmethod
    def descansos_anual_otros_motivos(anio: int, motivo: str = MOTIVO_ANUAL) -> dict:
        """
        {fecha_iso: [jornadas]} de los descansos del año que NO gestiona la pantalla anual
        (motivo distinto). Se muestran como referencia de solo lectura para que el supervisor
        vea que ese día ya tiene descanso y no quede invisible.
        """
        res = defaultdict(list)
        qs = (DescansoSemanaManual.objects
              .filter(fecha__year=anio, activo=True)
              .exclude(motivo=motivo)
              .select_related('jornada'))
        for d in qs:
            res[d.fecha.isoformat()].append(d.jornada.nombre.upper())
        return {f: sorted(v) for f, v in res.items()}

    @staticmethod
    def fechas_bloqueadas_por_solicitud(anio: int) -> set:
        """
        Fechas ISO (lun-vie) del año que NO se pueden alterar porque ya tienen al menos una
        solicitud APROBADA apoyada en ellas.

        Un cambio de descanso aprobado exige que exista el DescansoSemanaManual tanto en la
        fecha de cesión como en la de pago (lo validan la estrategia y el servicio de
        aplicación). Si la reprogramación anual borrara ese descanso, la solicitud quedaría
        huérfana: el turno aplicado sobrevive pero su fundamento desaparece.
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        ini, fin = date(anio, 1, 1), date(anio, 12, 31)
        qs = (SolicitudCambio.objects.filter(estado='aprobada')
              .filter(Q(fecha_cambio_turno__range=(ini, fin))
                      | Q(doblada__fecha_pago__range=(ini, fin))
                      | Q(doblada__fecha_pago_semana__range=(ini, fin)))
              .select_related('doblada'))
        bloqueadas = set()
        for s in qs:
            dob = getattr(s, 'doblada', None)
            fechas = (s.fecha_cambio_turno,
                      getattr(dob, 'fecha_pago', None),
                      getattr(dob, 'fecha_pago_semana', None))
            for d in fechas:
                # Solo lun-vie: el descanso de semana no aplica a fines de semana.
                if d and d.year == anio and d.weekday() < 5:
                    bloqueadas.add(d.isoformat())
        return bloqueadas

    @staticmethod
    @transaction.atomic
    def guardar_anual(anio: int, seleccion: dict, motivo: str = MOTIVO_ANUAL) -> int:
        """
        Reemplaza los descansos de semana del año (solo del MOTIVO dado, p.ej. 'temporada')
        con la selección del calendario. Los individuales con otro motivo no se tocan.
        seleccion: {fecha_iso: [jornadas]}. Devuelve cuántos descansos quedaron.

        REGLA DE NEGOCIO: un día con solicitudes aprobadas no se puede alterar. Si la
        selección lo cambia respecto a lo guardado, se rechaza TODO con DescansoSemanaConflicto.
        """
        from empleados.models import Jornada
        anio = int(anio)
        # Normalizar la selección: solo días lun-vie del año, jornadas en mayúsculas y ordenadas.
        normalizada = {}
        for fecha_iso, lista in (seleccion or {}).items():
            try:
                fecha = DateUtils.parse_date(fecha_iso)
            except (ValueError, TypeError):
                continue
            if fecha.weekday() >= 5 or fecha.year != anio:
                continue
            jns = sorted({str(jn).upper() for jn in (lista or [])})
            if jns:
                normalizada[fecha.isoformat()] = jns

        actuales = DescansoSemanaService.descansos_anual(anio, motivo=motivo)
        bloqueadas = DescansoSemanaService.fechas_bloqueadas_por_solicitud(anio)
        conflictos = sorted(iso for iso in bloqueadas
                            if actuales.get(iso, []) != normalizada.get(iso, []))
        if conflictos:
            raise DescansoSemanaConflicto(
                'No puedes cambiar el descanso de estos días porque ya tienen solicitudes '
                'aprobadas: ' + ', '.join(conflictos)
            )

        DescansoSemanaManual.objects.filter(fecha__year=anio, motivo=motivo).delete()

        # (fecha, jornada_id) ya ocupados por un descanso de OTRO motivo: no se pueden duplicar
        # (unicidad fecha+jornada) y funcionalmente ese día ya es descanso, así que se omiten.
        ocupados = set(DescansoSemanaManual.objects
                       .filter(fecha__year=anio)
                       .exclude(motivo=motivo)
                       .values_list('fecha', 'jornada_id'))

        jornadas = {j.nombre.upper(): j for j in Jornada.objects.all()}
        creados = 0
        for fecha_iso, jns in normalizada.items():
            fecha = DateUtils.parse_date(fecha_iso)
            for jn in jns:
                j = jornadas.get(jn)
                if not j:
                    continue
                if (fecha, j.id) in ocupados:
                    logger.warning(
                        "Descanso anual omitido: %s/%s ya existe con otro motivo", fecha_iso, jn
                    )
                    continue
                DescansoSemanaManual.objects.create(fecha=fecha, jornada=j, motivo=motivo, activo=True)
                creados += 1
        return creados

    @staticmethod
    def descansos_de_semana(fecha: date):
        """
        Devuelve los descansos manuales (AM/PM) configurados en la semana (lunes-domingo)
        que contiene `fecha`. Útil para mostrar la configuración de esa semana.
        """
        from datetime import timedelta
        lunes = fecha - timedelta(days=fecha.weekday())
        domingo = lunes + timedelta(days=6)
        return (
            DescansoSemanaManual.objects
            .filter(fecha__range=(lunes, domingo), activo=True)
            .select_related('jornada')
            .order_by('jornada__nombre', 'fecha')
        )
