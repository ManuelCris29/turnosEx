"""
Servicio del descanso de ENTRE SEMANA (manual).

El descanso normal de semana es el lunes de mantenimiento (descansan AM y PM). En semanas
con temporada/festivo el supervisor define manualmente el día de descanso por jornada
(modelo DescansoSemanaManual). Este servicio resuelve esa consulta de forma centralizada.
"""
from datetime import date, datetime
from collections import defaultdict
from django.db import transaction
from turnos.models import DescansoSemanaManual


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
    def descansos_anual(anio: int) -> dict:
        """
        {fecha_iso: [jornadas]} de los descansos de semana del año (para precargar el
        calendario anual). Ej: {'2026-07-07': ['AM'], '2026-07-10': ['PM']}.
        """
        res = defaultdict(list)
        qs = (DescansoSemanaManual.objects
              .filter(fecha__year=anio, activo=True)
              .select_related('jornada'))
        for d in qs:
            res[d.fecha.isoformat()].append(d.jornada.nombre.upper())
        return dict(res)

    @staticmethod
    @transaction.atomic
    def guardar_anual(anio: int, seleccion: dict, motivo: str = 'temporada') -> int:
        """
        Reemplaza los descansos de semana del año (solo del MOTIVO dado, p.ej. 'temporada')
        con la selección del calendario. Los individuales con otro motivo no se tocan.
        seleccion: {fecha_iso: [jornadas]}. Devuelve cuántos descansos quedaron.
        """
        from empleados.models import Jornada
        DescansoSemanaManual.objects.filter(fecha__year=anio, motivo=motivo).delete()
        jornadas = {j.nombre.upper(): j for j in Jornada.objects.all()}
        creados = 0
        for fecha_iso, lista in (seleccion or {}).items():
            try:
                fecha = datetime.strptime(fecha_iso, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                continue
            if fecha.weekday() >= 5 or fecha.year != int(anio):
                continue
            for jn in lista:
                j = jornadas.get(str(jn).upper())
                if j:
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
