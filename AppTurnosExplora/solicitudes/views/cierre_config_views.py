"""
Configuración del cierre semanal de solicitudes (panel del supervisor).

- Config por defecto (toggle + día + hora) que aplica a todas las semanas.
- Overrides por semana: ajustar/deshabilitar el cierre de una semana puntual.
"""
from datetime import datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.views import View

from core.mixins import AdminRequiredMixin
from ..models import CierreSolicitudesConfig, CierreSemanaOverride, DIA_CIERRE_CHOICES
from ..services.cierre_solicitudes_service import CierreSolicitudesService as CS
from core.utils.date_utils import DateUtils
from django.utils import timezone

N_SEMANAS = 8

# Destino unico de todos los redirect del panel: cambiar el nombre de la ruta en
# urls.py obliga a tocar un solo sitio.
_URL_CONFIG = 'solicitudes:cierre_config'


_DIAS_VALIDOS = {v for v, _ in DIA_CIERRE_CHOICES}


def _aware(naive):
    return timezone.make_aware(naive) if timezone.is_aware(timezone.now()) else naive


def _parse_hora(s, default=time(14, 0)):
    """(hora, ok). `ok=False` cuando se cayó al valor anterior, para poder avisar al supervisor."""
    for fmt in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).time(), True
        except (ValueError, TypeError):
            continue
    return default, False


def _parse_dia(s, default):
    """El día debe estar en las choices: el servicio lo usa como clave y un valor libre lo rompería."""
    return (s, True) if s in _DIAS_VALIDOS else (default, s in (None, ''))


class CierreConfigView(LoginRequiredMixin, AdminRequiredMixin, View):
    template_name = 'solicitudes/cierre_config.html'

    def _semanas(self, cfg):
        """Las próximas N semanas con su cierre EFECTIVO (default u override)."""
        hoy = timezone.localdate()
        ahora = timezone.now()
        lunes0 = hoy - timedelta(days=hoy.weekday())
        lunes_todos = [lunes0 + timedelta(days=7 * i) for i in range(N_SEMANAS)]
        # Overrides y config se cargan de una vez: si no, cada fila dispara sus propias consultas
        # (una por `_config_efectiva` y otra por `_ventana_semana`).
        overrides = {o.semana_lunes: o
                     for o in CierreSemanaOverride.objects.filter(semana_lunes__in=lunes_todos)}
        filas = []
        for lunes in lunes_todos:
            ov = overrides.get(lunes)
            hab, dia, hora = CS._config_efectiva(lunes, ov, cfg)
            v = CS._ventana_semana(lunes, ov, cfg)
            cutoff_fecha = v[2] if v else None
            filas.append({
                'lunes': lunes, 'domingo': lunes + timedelta(days=6),
                'override': ov, 'habilitado': hab, 'dia': dia, 'hora': hora,
                'dia_cierre_fecha': v[0] if v else None,   # inicio de la ventana
                'primer_habil': v[1] if v else None,       # fin de la ventana
                'cutoff_fecha': cutoff_fecha,              # día en que se activa el bloqueo
                # Saber si el bloqueo YA está aplicándose es justo lo que necesita el supervisor
                # cuando un explorador reclama; sin esto la fila futura y la cerrada se ven igual.
                'activa_ahora': bool(v) and ahora >= _aware(datetime.combine(cutoff_fecha, v[3])),
                'vencida': bool(v) and hoy > v[1],
            })
        return filas

    def get(self, request):
        cfg = CierreSolicitudesConfig.obtener()
        return render(request, self.template_name, {
            'cfg': cfg, 'semanas': self._semanas(cfg), 'dias_choices': DIA_CIERRE_CHOICES,
        })

    def post(self, request):
        accion = request.POST.get('accion')
        if accion == 'default':
            cfg = CierreSolicitudesConfig.obtener()
            cfg.habilitado = request.POST.get('habilitado') == 'on'
            cfg.dia_cierre, dia_ok = _parse_dia(request.POST.get('dia_cierre'), cfg.dia_cierre)
            cfg.hora_cierre, hora_ok = _parse_hora(request.POST.get('hora_cierre'), cfg.hora_cierre)
            if not (dia_ok and hora_ok):
                messages.error(request, 'Día u hora de cierre inválidos: no se guardó nada.')
                return redirect(_URL_CONFIG)
            cfg.save()
            messages.success(request, 'Configuración por defecto del cierre guardada.')
        elif accion == 'override':
            try:
                lunes = DateUtils.parse_date(request.POST.get('semana_lunes'))
            except (ValueError, TypeError):
                messages.error(request, 'Semana inválida.')
                return redirect(_URL_CONFIG)
            # El override se busca siempre por el LUNES de la semana: normalizar para no crear
            # ajustes huérfanos que `_config_efectiva` nunca encontraría.
            lunes -= timedelta(days=lunes.weekday())
            # Validar ANTES del get_or_create: si no, un POST inválido dejaría creado un override
            # con los valores por defecto que el supervisor nunca pidió.
            ov = CierreSemanaOverride.objects.filter(semana_lunes=lunes).first()
            actual = ov or CierreSemanaOverride(semana_lunes=lunes)
            dia, dia_ok = _parse_dia(request.POST.get('dia_cierre'), actual.dia_cierre)
            hora, hora_ok = _parse_hora(request.POST.get('hora_cierre'), actual.hora_cierre)
            if not (dia_ok and hora_ok):
                messages.error(request, 'Día u hora de cierre inválidos: no se guardó nada.')
                return redirect(_URL_CONFIG)
            actual.habilitado = request.POST.get('habilitado') == 'on'
            actual.dia_cierre, actual.hora_cierre = dia, hora
            actual.save()
            messages.success(request, f'Ajuste guardado para la semana del {lunes.strftime("%d/%m/%Y")}.')
        elif accion == 'quitar_override':
            try:
                lunes = DateUtils.parse_date(request.POST.get('semana_lunes'))
                lunes -= timedelta(days=lunes.weekday())
                CierreSemanaOverride.objects.filter(semana_lunes=lunes).delete()
                messages.success(request, 'Ajuste de semana eliminado (vuelve al valor por defecto).')
            except (ValueError, TypeError):
                pass
        return redirect(_URL_CONFIG)
