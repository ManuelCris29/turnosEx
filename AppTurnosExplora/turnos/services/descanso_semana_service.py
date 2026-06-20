"""
Servicio del descanso de ENTRE SEMANA (manual).

El descanso normal de semana es el lunes de mantenimiento (descansan AM y PM). En semanas
con temporada/festivo el supervisor define manualmente el día de descanso por jornada
(modelo DescansoSemanaManual). Este servicio resuelve esa consulta de forma centralizada.
"""
from datetime import date
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
