"""
Servicio para rotación global AM/PM en festivos entre semana.

Regla de negocio:
- Se toman TODOS los festivos de lunes a viernes (tipo='festivo', activo=True) en orden cronológico.
- Al primer festivo de la historia le corresponde doblar el grupo PM (índice 0).
- Al segundo festivo le corresponde doblar el grupo AM (índice 1).
- Se alterna así sucesivamente (PM, AM, PM, AM, ...) SIN reiniciar por mes.

Esto permite que, por ejemplo:
- 1 de enero de 2026 (primer festivo de semana registrado) -> grupo PM
- 12 de enero de 2026 (segundo festivo de semana) -> grupo AM
- El siguiente festivo de semana, aunque sea en otro mes, vuelve a ser PM, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from django.core.exceptions import ValidationError

from turnos.models import DiaEspecial

GrupoTipo = Literal["AM", "PM"]


@dataclass(frozen=True)
class RotacionFestivo:
    fecha: date
    indice_global: int
    grupo_que_dobla: GrupoTipo


class FestivosRotacionService:
    """
    Servicio estático para resolver la rotación AM/PM en festivos entre semana.

    NOTA IMPORTANTE:
    - No reinicia por mes. El índice se calcula contando TODOS los festivos de semana
      anteriores a la fecha dada.
    - Si en el futuro se decide reiniciar por año calendario, bastaría con limitar
      el filtro a fecha__year=fecha.year en _contar_festivos_semana_previos().
    """

    @staticmethod
    def _es_festivo_semana(fecha: date) -> bool:
        """
        Verifica si la fecha es un festivo activo y cae de lunes a viernes.
        """
        # weekday(): 0=lunes, ..., 6=domingo
        if fecha.weekday() > 4:
            return False

        return DiaEspecial.objects.filter(
            fecha=fecha,
            tipo__iexact="festivo",
            activo=True,
        ).exists()

    @staticmethod
    def _contar_festivos_semana_previos(fecha: date) -> int:
        """
        Retorna cuántos festivos de lunes a viernes existen ANTES de la fecha dada.
        Se usa para obtener el índice global (0-based) de la fecha actual.
        """
        # Django week_day: 2=lunes ... 6=viernes
        return (
            DiaEspecial.objects.filter(
                tipo__iexact="festivo",
                activo=True,
                fecha__lt=fecha,
                fecha__week_day__in=[2, 3, 4, 5, 6],
            ).count()
        )

    @classmethod
    def get_rotacion_festivo(cls, fecha: date) -> RotacionFestivo:
        """
        Devuelve información de rotación para un festivo de semana:
        - índice global (0-based)
        - grupo que debe doblar (AM/PM)

        Raises:
            ValidationError: si la fecha no es un festivo de lunes a viernes activo.
        """
        if not isinstance(fecha, date):
            raise ValidationError("La fecha debe ser un objeto date.")

        if not cls._es_festivo_semana(fecha):
            raise ValidationError(
                "La fecha indicada no es un festivo de lunes a viernes activo."
            )

        indice_previos = cls._contar_festivos_semana_previos(fecha)
        indice_actual = indice_previos  # 0-based
        grupo: GrupoTipo = "PM" if indice_actual % 2 == 0 else "AM"

        return RotacionFestivo(
            fecha=fecha,
            indice_global=indice_actual,
            grupo_que_dobla=grupo,
        )

    @classmethod
    def get_grupo_que_dobla_en_festivo(cls, fecha: date) -> GrupoTipo:
        """
        Atajo para obtener únicamente el grupo que debe doblar (AM/PM)
        en un festivo de semana.
        """
        rotacion = cls.get_rotacion_festivo(fecha)
        return rotacion.grupo_que_dobla

