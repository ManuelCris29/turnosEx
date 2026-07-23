"""
Servicio del OVERRIDE manual de días especiales (fines de semana y festivos).

La alternancia de fines de semana y la rotación de festivos son automáticas. Este
servicio deja que el supervisor FIJE manualmente qué grupo (AM/PM) trabaja el día
completo en fechas puntuales; cuando existe un registro activo, MANDA sobre el
cálculo automático. Sin registro, el que consulta cae al automático (fallback).
"""
from datetime import date, datetime, timedelta
from django.db import transaction

from turnos.models import AsignacionEspecialManual
from core.utils.date_utils import DateUtils


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
    def fechas_bloqueadas_por_solicitud(anio: int) -> set:
        """
        Fechas ISO (findes y festivos) que NO se pueden alterar manualmente porque tienen
        al menos una solicitud APROBADA. Regla: si el sábado O el domingo de un finde tiene
        solicitud, se bloquean AMBOS días del finde (alterarlo cambiaría todo).
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        ini, fin = date(anio, 1, 1), date(anio, 12, 31)
        qs = (SolicitudCambio.objects.filter(estado='aprobada')
              .filter(Q(fecha_cambio_turno__range=(ini, fin)) | Q(doblada__fecha_pago__range=(ini, fin)))
              .select_related('doblada'))
        bloqueadas = set()
        for s in qs:
            fp = getattr(getattr(s, 'doblada', None), 'fecha_pago', None)
            for d in (s.fecha_cambio_turno, fp):
                if not d or d.year != anio:
                    continue
                if d.weekday() >= 5:
                    sab, dom = AsignacionEspecialService._fechas_finde(d)
                    bloqueadas.add(sab.isoformat())
                    bloqueadas.add(dom.isoformat())
                else:
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
            tipo = 'finde' if fecha.weekday() >= 5 else 'festivo'
            AsignacionEspecialManual.objects.create(
                fecha=fecha, jornada_trabaja=j, tipo=tipo, activo=True
            )
            creados += 1
        return creados
