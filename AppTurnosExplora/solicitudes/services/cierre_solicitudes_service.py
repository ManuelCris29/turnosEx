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
import logging
from datetime import date, datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

_SIN_PRECARGA = object()  # centinela: distingue "no me lo pasaron" de "me pasaron None"

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
    def _config_efectiva(cls, lunes: date, override=_SIN_PRECARGA, cfg=None):
        """(habilitado, dia_cierre, hora) para la semana `lunes`: override si existe, si no el default.

        `override`/`cfg` permiten a quien ya los tenga cargados (p. ej. el panel, que pinta varias
        semanas) evitar una consulta por semana. `override=None` significa "ya miré y no hay";
        omitirlo significa "búscalo tú".
        """
        from solicitudes.models import CierreSolicitudesConfig, CierreSemanaOverride
        ov = (CierreSemanaOverride.objects.filter(semana_lunes=lunes).first()
              if override is _SIN_PRECARGA else override)
        if ov is not None:
            return ov.habilitado, ov.dia_cierre, ov.hora_cierre
        cfg = cfg or CierreSolicitudesConfig.obtener()
        return cfg.habilitado, cfg.dia_cierre, cfg.hora_cierre

    # ------------------------------------------------------ ventana / cutoff por fecha
    @classmethod
    def _ventana_semana(cls, lunes_finde: date, override=_SIN_PRECARGA, cfg=None):
        """
        Para la semana cuyo lunes es `lunes_finde`, devuelve
        (inicio_ventana, fin_ventana, cutoff_fecha, hora, dia_cierre) si el cierre está habilitado
        esa semana, o None.

        - La ventana cerrada es [inicio_ventana … fin_ventana] (ambos inclusive), donde
          `fin_ventana` es siempre el primer día hábil de la semana siguiente.
        - `cutoff_fecha` es el día a cuya `hora` empieza a aplicarse el bloqueo. Normalmente
          coincide con `inicio_ventana` (jueves/viernes/sábado/domingo). Con `primer_habil` la
          ventana sigue cubriendo el fin de semana completo (desde el jueves) pero el bloqueo
          solo se activa el primer día hábil a la hora configurada.
        """
        habilitado, dia_cierre, hora = cls._config_efectiva(lunes_finde, override, cfg)
        if not habilitado:
            return None
        if dia_cierre != 'primer_habil' and dia_cierre not in _DIA_A_WEEKDAY:
            # Un valor fuera de las choices (guardado por admin/shell) haría KeyError, y este método
            # se llama tanto al crear solicitudes como al pintar el panel: reventaría el panel justo
            # donde se corrige el dato. Se degrada al jueves —el cierre más amplio— y se avisa.
            logger.critical("Día de cierre inválido %r para la semana %s; se usa 'jueves'.",
                            dia_cierre, lunes_finde)
            dia_cierre = 'jueves'
        fin_ventana = cls._primer_dia_habil(lunes_finde + timedelta(days=7))
        if dia_cierre == 'primer_habil':
            inicio_ventana = lunes_finde + timedelta(days=_DIA_A_WEEKDAY['jueves'])
            cutoff_fecha = fin_ventana
        else:
            inicio_ventana = lunes_finde + timedelta(days=_DIA_A_WEEKDAY[dia_cierre])
            cutoff_fecha = inicio_ventana
        return inicio_ventana, fin_ventana, cutoff_fecha, hora, dia_cierre

    @classmethod
    def _semana_finde_de(cls, t: date):
        """Lunes de la semana del FIN DE SEMANA al que pertenece `t` (o None si `t` no es candidata):
        jueves–domingo → su propia semana; el lunes … primer día hábil (inclusive) de una semana
        → el finde de la semana ANTERIOR.

        Los días entre el lunes y el primer día hábil (festivos/mantenimientos que corren el primer
        hábil al martes o más allá) también pertenecen a la ventana del finde anterior: la ventana es
        un rango continuo, no solo sus extremos.
        """
        dow = t.weekday()
        if dow >= 3:  # jueves(3), viernes(4), sábado(5), domingo(6)
            return cls._lunes_de(t)
        # lunes(0), martes(1), miércoles(2): pertenecen al finde anterior mientras no se haya
        # pasado el primer día hábil de su propia semana.
        lunes_t = cls._lunes_de(t)
        if t <= cls._primer_dia_habil(lunes_t):
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
        inicio_ventana, fin_ventana, cutoff_fecha, hora, _dia = v
        if not (inicio_ventana <= t <= fin_ventana):
            return None
        naive = datetime.combine(cutoff_fecha, hora)
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
                _ini, _fin, _cutoff_fecha, _hora, dia = cls._ventana_semana(lunes)
                hora = cutoff.strftime('%H:%M')
                msg = (
                    f"Cierre de solicitudes activo: desde el {_NOMBRE_DIA.get(dia, dia)} "
                    f"{_cutoff_fecha.strftime('%d/%m/%Y')} a las {hora} la programación del fin de "
                    f"semana ya está cerrada; no se pueden enviar solicitudes para el "
                    f"{t.strftime('%d/%m/%Y')}."
                )
                return t, msg
        return None, None
