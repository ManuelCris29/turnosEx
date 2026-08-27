"""
TurnoRepository

Centraliza las queries a Turno. Evita que vistas y servicios hagan
Turno.objects.filter(...) directamente para los casos cubiertos aquí.
"""
from django.db.models import QuerySet

from turnos.models import Turno


class TurnoRepository:

    @staticmethod
    def por_explorador_fecha(explorador, fecha) -> QuerySet:
        """Turnos de un explorador en una fecha, con jornada precargada."""
        return (Turno.objects
                .filter(explorador=explorador, fecha=fecha)
                .select_related('jornada'))

    @staticmethod
    def jornadas_en_fecha(explorador_id: int, fecha) -> set[str]:
        """
        Conjunto de nombres de jornada que tiene el explorador en la fecha.
        Útil para validar si tiene doblada (AM y PM) o solo una jornada.
        """
        return set(
            Turno.objects
            .filter(explorador_id=explorador_id, fecha=fecha)
            .values_list('jornada__nombre', flat=True)
        )

    @staticmethod
    def tiene_doblada(explorador_id: int, fecha) -> bool:
        """True si el explorador tiene AM+PM en la fecha (doblada completa)."""
        jornadas = TurnoRepository.jornadas_en_fecha(explorador_id, fecha)
        return {'AM', 'PM'}.issubset({j.upper() for j in jornadas if j})

    @staticmethod
    def por_explorador_rango(explorador, fecha_inicio, fecha_fin) -> QuerySet:
        """Turnos de un explorador en un rango de fechas."""
        return (Turno.objects
                .filter(explorador=explorador, fecha__range=(fecha_inicio, fecha_fin))
                .select_related('jornada')
                .order_by('fecha'))
