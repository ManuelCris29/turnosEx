"""
Servicio del OVERRIDE manual de días especiales (fines de semana y festivos).

La alternancia de fines de semana y la rotación de festivos son automáticas. Este
servicio deja que el supervisor FIJE manualmente qué grupo (AM/PM) trabaja el día
completo en fechas puntuales; cuando existe un registro activo, MANDA sobre el
cálculo automático. Sin registro, el que consulta cae al automático (fallback).
"""
import logging
from datetime import date, datetime, timedelta
from django.db import transaction

from turnos.models import AsignacionEspecialManual
from core.utils.date_utils import DateUtils

logger = logging.getLogger(__name__)


class AsignacionEspecialConflicto(Exception):
    """Se intentó alterar la alternancia de un finde/festivo que ya tiene solicitudes aprobadas."""


class AsignacionEspecialService:

    @staticmethod
    def get_grupo_trabaja(fecha: date):
        """
        Grupo ('AM'/'PM') fijado manualmente para trabajar el día completo esa fecha,
        o None si no hay override activo (entonces aplica la alternancia automática).
        """
        if not fecha:
            return None
        reg = (AsignacionEspecialManual.objects
               .filter(fecha=fecha, activo=True)
               .select_related('jornada_trabaja')
               .first())
        return reg.jornada_trabaja.nombre.upper() if reg else None

    @staticmethod
    def grupo_trabaja_efectivo(fecha: date):
        """
        Grupo que TRABAJA el día completo un fin de semana, considerando el override:
        si hay asignación manual manda; si no, la alternancia automática.
        Fuente única para validar/aplicar solicitudes de finde de forma consistente
        con lo que muestra Mis Turnos.
        """
        override = AsignacionEspecialService.get_grupo_trabaja(fecha)
        if override:
            return override
        # Festivo entre semana: la regla automática es la ROTACIÓN, no la alternancia de finde
        # (que devolvería None y dejaría el día sin grupo).
        if fecha.weekday() < 5:
            from turnos.models import DiaEspecial
            if DiaEspecial.es_festivo(fecha):
                from turnos.services.festivos_rotacion_service import FestivosRotacionService
                try:
                    return FestivosRotacionService.get_grupo_que_dobla_en_festivo(fecha)
                except Exception:
                    logger.warning("Sin rotación de festivo para %s", fecha, exc_info=True)
            return None
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        return AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha)

    @staticmethod
    def mapa_grupo_trabaja(ini: date, fin: date) -> dict:
        """
        {fecha: 'AM'/'PM'} de los overrides activos en el rango [ini, fin]. Para el
        batch de estado_mes: una sola consulta en vez de N.
        """
        res = {}
        for reg in (AsignacionEspecialManual.objects
                    .filter(fecha__range=(ini, fin), activo=True)
                    .select_related('jornada_trabaja')):
            res[reg.fecha] = reg.jornada_trabaja.nombre.upper()
        return res

    @staticmethod
    def asignaciones_anual(anio: int) -> dict:
        """{fecha_iso: 'AM'/'PM'} de los overrides del año (para precargar el calendario)."""
        res = {}
        for reg in (AsignacionEspecialManual.objects
                    .filter(fecha__year=anio, activo=True)
                    .select_related('jornada_trabaja')):
            res[reg.fecha.isoformat()] = reg.jornada_trabaja.nombre.upper()
        return res

    @staticmethod
    def _fechas_finde(fecha: date):
        """(sábado, domingo) del fin de semana al que pertenece la fecha."""
        if fecha.weekday() == 5:
            return fecha, fecha + timedelta(days=1)
        if fecha.weekday() == 6:
            return fecha - timedelta(days=1), fecha
        return fecha, fecha

    @staticmethod
    def _fechas_comprometidas(anio: int) -> set:
        """
        Fechas (objetos `date`) del año que alguna solicitud APROBADA ya comprometió, mirando
        TODOS los tipos que atan a un explorador a un día concreto. Si aquí falta una fuente,
        el supervisor podría invertir la alternancia bajo una solicitud ya aprobada.
        """
        from django.db.models import Q
        from solicitudes.models import (
            SolicitudCambio, CambioPermanenteDia, DobladaPermanenteDetalle,
            ReprogramacionDiaDoblada, DeudaExplorador,
        )
        from turnos.models import DiaEspecial

        ini, fin = date(anio, 1, 1), date(anio, 12, 31)
        fechas = set()

        def _add(d):
            if d and d.year == anio:
                fechas.add(d)

        # DOBLADA / D FDS / CT…: cesión, pago de doblada y pago de la semana.
        for s in (SolicitudCambio.objects.filter(estado='aprobada')
                  .filter(Q(fecha_cambio_turno__range=(ini, fin))
                          | Q(doblada__fecha_pago__range=(ini, fin))
                          | Q(doblada__fecha_pago_semana__range=(ini, fin)))
                  .select_related('doblada')):
            det = getattr(s, 'doblada', None)
            _add(s.fecha_cambio_turno)
            _add(getattr(det, 'fecha_pago', None))
            _add(getattr(det, 'fecha_pago_semana', None))

        # CAMBIO PERMANENTE: días específicos elegidos.
        for d in CambioPermanenteDia.objects.filter(
                cambio_permanente__solicitud__estado='aprobada',
                fecha_especifica__range=(ini, fin)).values_list('fecha_especifica', flat=True):
            _add(d)

        # REPROGRAMACIÓN de día de doblada: el día nuevo que el supervisor ya programó.
        for d in ReprogramacionDiaDoblada.objects.filter(
                estado__in=('pendiente', 'pagada'),
                fecha_reprogramada__range=(ini, fin)).values_list('fecha_reprogramada', flat=True):
            _add(d)

        # DEUDAS pendientes: la fecha de pago pactada ya está comprometida.
        for d in DeudaExplorador.objects.filter(
                estado='pendiente',
                fecha_pago_pactada__range=(ini, fin)).values_list('fecha_pago_pactada', flat=True):
            _add(d)

        # DOBLADA PERMANENTE: fechas específicas si las hay; si no, se expanden los weekdays
        # del rango. Se replica la regla de aplicación (`DescansoPorSolicitudService`): la
        # doblada permanente nunca cae en domingo ni en festivo.
        festivos = set(DiaEspecial.objects.filter(
            fecha__range=(ini, fin), tipo='festivo', activo=True).values_list('fecha', flat=True))

        def _add_permanente(d):
            if d and d.year == anio and d.weekday() != 6 and d not in festivos:
                fechas.add(d)

        for det in DobladaPermanenteDetalle.objects.filter(
                solicitud__estado='aprobada', fecha_inicio__lte=fin, fecha_fin__gte=ini):
            if det.fechas_cesion or det.fechas_devolucion:
                for csv in (det.fechas_cesion, det.fechas_devolucion):
                    for x in (csv or '').split(','):
                        x = x.strip()
                        if not x:
                            continue
                        try:
                            _add_permanente(date.fromisoformat(x))
                        except ValueError:
                            logger.warning("Fecha inválida en doblada permanente %s: %r", det.pk, x)
                continue
            dias = {int(x) for x in f'{det.dias_cesion},{det.dias_devolucion}'.split(',')
                    if x.strip().isdigit()}
            if not dias:
                continue
            d, dlast = max(det.fecha_inicio, ini), min(det.fecha_fin, fin)
            while d <= dlast:
                if d.weekday() in dias:
                    _add_permanente(d)
                d += timedelta(days=1)

        return fechas

    @staticmethod
    def fechas_bloqueadas_por_solicitud(anio: int) -> set:
        """
        Fechas ISO (findes y festivos) que NO se pueden alterar manualmente porque tienen
        al menos una solicitud APROBADA. Regla: si el sábado O el domingo de un finde tiene
        solicitud, se bloquean AMBOS días del finde (alterarlo cambiaría todo).

        Solo se reportan findes y festivos entre semana: son los únicos días que esta pantalla
        puede alterar. Una solicitud sobre un martes normal no bloquea nada, y así
        `anio_editable_completo` sigue significando "ningún finde/festivo comprometido".
        """
        from turnos.models import DiaEspecial
        ini, fin = date(anio, 1, 1), date(anio, 12, 31)
        festivos_semana = set(
            f for f in DiaEspecial.objects.filter(
                fecha__range=(ini, fin), tipo='festivo', activo=True).values_list('fecha', flat=True)
            if f.weekday() < 5
        )
        bloqueadas = set()
        for d in AsignacionEspecialService._fechas_comprometidas(anio):
            if d.weekday() >= 5:
                sab, dom = AsignacionEspecialService._fechas_finde(d)
                bloqueadas.add(sab.isoformat())
                bloqueadas.add(dom.isoformat())
            elif d in festivos_semana:
                bloqueadas.add(d.isoformat())
        return bloqueadas

    @staticmethod
    def anio_editable_completo(anio: int) -> bool:
        """
        True si el año NO tiene ninguna solicitud aprobada sobre findes/festivos: en ese
        caso el supervisor puede reprogramar TODA la alternancia del año.
        """
        return len(AsignacionEspecialService.fechas_bloqueadas_por_solicitud(anio)) == 0

    @staticmethod
    @transaction.atomic
    def guardar_anual(anio: int, seleccion: dict) -> int:
        """
        Reemplaza los overrides del año con la selección del calendario.
        seleccion: {fecha_iso: 'AM'/'PM'}. El tipo (finde/festivo) se infiere del weekday.

        REGLA DE NEGOCIO: un finde/festivo con solicitudes aprobadas NO se puede alterar.
        Si la selección intenta cambiar (crear/quitar/modificar) una fecha bloqueada respecto
        a lo ya guardado, se rechaza TODO con AsignacionEspecialConflicto.
        Devuelve cuántos overrides quedaron.
        """
        from turnos.models import Jornada
        seleccion = {k: str(v).upper() for k, v in (seleccion or {}).items()}
        actuales = AsignacionEspecialService.asignaciones_anual(anio)
        bloqueadas = AsignacionEspecialService.fechas_bloqueadas_por_solicitud(anio)

        # No permitir tocar fechas bloqueadas (deben quedar EXACTAMENTE como están).
        conflictos = sorted(iso for iso in bloqueadas if actuales.get(iso) != seleccion.get(iso))
        if conflictos:
            raise AsignacionEspecialConflicto(
                'No puedes alterar la alternancia de estos días porque ya tienen solicitudes '
                'aprobadas: ' + ', '.join(conflictos)
            )

        from turnos.models import DiaEspecial
        festivos_semana = set(
            f for f in DiaEspecial.objects.filter(
                fecha__year=anio, tipo='festivo', activo=True).values_list('fecha', flat=True)
            if f.weekday() < 5
        )

        AsignacionEspecialManual.objects.filter(fecha__year=anio).delete()
        jornadas = {j.nombre.upper(): j for j in Jornada.objects.all()}
        creados = 0
        for fecha_iso, grupo in seleccion.items():
            try:
                fecha = DateUtils.parse_date(fecha_iso)
            except (ValueError, TypeError):
                continue
            if fecha.year != int(anio):
                continue
            j = jornadas.get(str(grupo).upper())
            if not j:
                continue
            # Solo findes y festivos entre semana: esta pantalla no fija días normales.
            if fecha.weekday() < 5 and fecha not in festivos_semana:
                logger.warning(
                    "Asignación especial omitida: %s no es fin de semana ni festivo activo.", fecha_iso)
                continue
            tipo = 'finde' if fecha.weekday() >= 5 else 'festivo'
            AsignacionEspecialManual.objects.create(
                fecha=fecha, jornada_trabaja=j, tipo=tipo, activo=True
            )
            creados += 1
        return creados
