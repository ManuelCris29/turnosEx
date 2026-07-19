"""
CierreSolicitudesService

Cierre semanal de solicitudes: cuando está habilitado, a partir del día/hora de cierre de cada
semana no se pueden enviar NUEVAS solicitudes (cambios de turno ni permisos) cuyo objetivo caiga
en la ventana cerrada = [día de cierre (incluido) … primer día hábil de la semana siguiente].

- Config global por defecto (`CierreSolicitudesConfig`) + overrides por semana (`CierreSemanaOverride`).
- El primer día hábil de la semana siguiente salta festivos y mantenimientos (temporada NO lo corre).
- Si el cierre no está habilitado para la semana del fin de semana, no hay restricción.
- Solo aplica a la CREACIÓN de solicitudes; lo ya aprobado y las acciones del supervisor no pasan aquí.
"""
from datetime import date, datetime, timedelta

from django.utils import timezone

_DIA_A_WEEKDAY = {'jueves': 3, 'viernes': 4, 'sabado': 5, 'domingo': 6}
_NOMBRE_DIA = {'jueves': 'jueves', 'viernes': 'viernes', 'sabado': 'sábado',
               'domingo': 'domingo', 'primer_habil': 'primer día hábil'}


class CierreSolicitudesService:

    # --------------------------------------------------------------- helpers base
    @staticmethod
    def _lunes_de(f: date) -> date:
        return f - timedelta(days=f.weekday())

    @staticmethod
    def _es_no_habil(f: date) -> bool:
        """Festivo o mantenimiento efectivo (temporada NO cuenta: es día hábil)."""
        from turnos.models import DiaEspecial
        from solicitudes.services.ct_permanente_helper import _es_festivo
        return bool(_es_festivo(f) or DiaEspecial.es_mantenimiento_efectivo(f))

    @classmethod
    def _primer_dia_habil(cls, lunes_siguiente: date) -> date:
        """Primer día hábil de la semana siguiente: parte del lunes y salta festivo/mantenimiento."""
        d = lunes_siguiente
        # tope de seguridad para no ciclar si toda la semana fuera no hábil
        for _ in range(7):
            if not cls._es_no_habil(d):
                return d
            d += timedelta(days=1)
        return lunes_siguiente

    @classmethod
    def _config_efectiva(cls, lunes: date):
        """(habilitado, dia_cierre, hora) para la semana `lunes`: override si existe, si no el default."""
        from solicitudes.models import CierreSolicitudesConfig, CierreSemanaOverride
        ov = CierreSemanaOverride.objects.filter(semana_lunes=lunes).first()
        if ov is not None:
            return ov.habilitado, ov.dia_cierre, ov.hora_cierre
        cfg = CierreSolicitudesConfig.obtener()
        return cfg.habilitado, cfg.dia_cierre, cfg.hora_cierre

    # ------------------------------------------------------ ventana / cutoff por fecha
    @classmethod
    def _ventana_semana(cls, lunes_finde: date):
        """
        Para la semana cuyo lunes es `lunes_finde`, devuelve (dia_cierre_fecha, primer_dia_habil,
        hora) si el cierre está habilitado esa semana, o None. La ventana cerrada es
        [dia_cierre_fecha … primer_dia_habil] (ambos inclusive).
        """
        habilitado, dia_cierre, hora = cls._config_efectiva(lunes_finde)
        if not habilitado:
            return None
        primer_habil = cls._primer_dia_habil(lunes_finde + timedelta(days=7))
        if dia_cierre == 'primer_habil':
            dia_cierre_fecha = primer_habil
        else:
            dia_cierre_fecha = lunes_finde + timedelta(days=_DIA_A_WEEKDAY[dia_cierre])
        return dia_cierre_fecha, primer_habil, hora, dia_cierre

    @classmethod
    def _semana_finde_de(cls, t: date):
        """Lunes de la semana del FIN DE SEMANA al que pertenece `t` (o None si `t` no es candidata):
        jueves–domingo → su propia semana; el primer día hábil → la semana anterior."""
        dow = t.weekday()
        if dow >= 3:  # jueves(3), viernes(4), sábado(5), domingo(6)
            return cls._lunes_de(t)
        # ¿`t` es el primer día hábil de su semana? Entonces cierra el finde de la semana ANTERIOR.
        lunes_t = cls._lunes_de(t)
        if t == cls._primer_dia_habil(lunes_t):
            return lunes_t - timedelta(days=7)
        return None

    @classmethod
    def cutoff_para_fecha(cls, t: date):
        """`datetime` de cierre que protege la fecha `t`, o None si `t` no está en ninguna ventana
        cerrada habilitada."""
        lunes_finde = cls._semana_finde_de(t)
        if lunes_finde is None:
            return None
        v = cls._ventana_semana(lunes_finde)
        if v is None:
            return None
        dia_cierre_fecha, primer_habil, hora, _dia = v
        if not (dia_cierre_fecha <= t <= primer_habil):
            return None
        naive = datetime.combine(dia_cierre_fecha, hora)
        return timezone.make_aware(naive) if timezone.is_aware(timezone.now()) else naive

    # ------------------------------------------------------------- API de validación
    @classmethod
    def fecha_bloqueada(cls, t: date, ahora=None) -> bool:
        cutoff = cls.cutoff_para_fecha(t)
        if cutoff is None:
            return False
        ahora = ahora or timezone.now()
        return ahora >= cutoff

    @classmethod
    def validar_fechas(cls, fechas, ahora=None):
        """Devuelve (fecha_bloqueada, mensaje) para la PRIMERA fecha cerrada, o (None, None)."""
        ahora = ahora or timezone.now()
        for t in fechas:
            if t is None:
                continue
            cutoff = cls.cutoff_para_fecha(t)
            if cutoff is not None and ahora >= cutoff:
                lunes = cls._semana_finde_de(t)
                _, _, _, dia = cls._ventana_semana(lunes)
                hora = cutoff.strftime('%H:%M')
                msg = (
                    f"Cierre de solicitudes activo: desde el {_NOMBRE_DIA.get(dia, dia)} a las {hora} "
                    f"la programación del fin de semana ya está cerrada; no se pueden enviar solicitudes "
                    f"para el {t.strftime('%d/%m/%Y')}."
                )
                return t, msg
        return None, None
