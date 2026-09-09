"""
Utilidades para cálculo de jornadas.

Responsabilidad única:
- Lógica de cálculo de la jornada efectiva de un día (trabaja o descansa),
  delegando las reglas de fines de semana al servicio de alternancia.
- Cache de objetos Jornada AM/PM para evitar consultas repetidas.
"""
from datetime import date
from typing import Dict


class JornadaUtils:
    """
    Utilidades para cálculo de jornadas.
    """

    @staticmethod
    def calcular_jornada_dia(jornada_base: str, fecha: date) -> str:
        """
        Calcula la jornada para un día específico, considerando:
        - Jornada base (AM o PM).
        - Alternancia real de fines de semana (sábados y domingos).

        Lógica de fines de semana:
        - En un fin de semana, un grupo (AM o PM) TRABAJA sábado (doblada completa)
          y DESCANSA domingo; el grupo contrario hace lo inverso.
        - Qué grupo trabaja cada día NO se calcula: se lee de la alternancia que el
          supervisor publicó para el año (`AsignacionEspecialManual`).

        Comportamiento:
        - Si la fecha es sábado o domingo:
          - Si jornada_base es la que TRABAJA ese día según alternancia → retorna jornada_base.
          - Si jornada_base es la que DESCANSA ese día → retorna "Descanso".
        - Si no es fin de semana → retorna siempre jornada_base.

        IMPORTANTE: jornada_base siempre debe ser "AM" o "PM", nunca None.
        Si un explorador no tiene jornada asignada, debe manejarse antes de llamar
        a esta función.

        Args:
            jornada_base: Nombre de la jornada base ("AM" o "PM")
            fecha: Fecha para calcular la jornada

        Returns:
            Nombre de la jornada ("AM", "PM", o "Descanso")

        Raises:
            ValueError: Si jornada_base no es "AM" o "PM"
        """
        if not jornada_base or jornada_base not in ["AM", "PM"]:
            raise ValueError(
                f"jornada_base debe ser 'AM' o 'PM', recibido: {jornada_base}. "
                "Todos los exploradores deben tener una jornada asignada."
            )

        # Lunes a viernes: siempre trabaja su jornada base
        if fecha.weekday() < 5:
            return jornada_base

        # Sábados y domingos: alternancia PUBLICADA por el supervisor.
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        jornada_trabaja = AsignacionEspecialService.grupo_trabaja(fecha)

        # Sin publicar no se puede afirmar nada del día. Se devuelve la jornada base como
        # antes (comportamiento conservador de esta utilidad, que no sabe expresar
        # "sin planificar"); la fuente de verdad para eso es `TurnoService.estado_dia`.
        if jornada_trabaja is None:
            return jornada_base

        return jornada_base if jornada_base.upper() == jornada_trabaja else "Descanso"


def obtener_jornada_base(empleado, fecha):
    """
    Jornada BASE (predeterminada) de un explorador en una fecha: la asignación vigente en
    `AsignarJornadaExplorador`. Devuelve el objeto Jornada o None.

    Es el estado "virtual" del día, independiente de lo que haya materializado en `Turno`.
    La usan las re-materializaciones de la reconciliación (patrón #22), que corren
    justamente cuando los turnos del día acaban de ser borrados y no se pueden consultar.
    """
    from turnos.models import AsignarJornadaExplorador

    asignacion = (
        AsignarJornadaExplorador.objects
        .filter(explorador=empleado, fecha_inicio__lte=fecha)
        .select_related('jornada')
        .order_by('-fecha_inicio')
        .first()
    )
    return asignacion.jornada if asignacion else None


def obtener_jornadas_am_pm() -> Dict[str, object]:
    """
    Retorna {'AM': Jornada, 'PM': Jornada} en UNA sola consulta.

    Uso centralizado para evitar consultas repetidas en los servicios de doblada: resuelve las
    dos jornadas de golpe en vez de dos `.get()` sueltos.

    NO se cachea entre llamadas, a propósito. Antes guardaba las instancias en caché una hora y
    devolvía objetos con IDs que ya no existían si la tabla se recreaba (el caso claro es la BD
    de test, que se reconstruye entre corridas: el ID viejo reventaba con un fallo de clave
    foránea al crear un Turno). Cachear los IDs en lugar de las instancias no arregla nada — un
    ID obsoleto sigue siendo obsoleto. Son dos filas con índice por nombre: la consulta es
    barata y siempre correcta.
    """
    from turnos.models import Jornada

    return {
        (j.nombre or '').upper(): j
        for j in Jornada.objects.filter(nombre__in=['AM', 'PM'])
    }
