"""
Configuración del cierre semanal de solicitudes (panel del supervisor).

- Config por defecto (toggle + día + hora) que aplica a todas las semanas.
- Overrides por semana: ajustar/deshabilitar el cierre de una semana puntual.
"""
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, redirect
from django.views import View

from core.mixins import AdminRequiredMixin
from ..models import CierreSolicitudesConfig, CierreSemanaOverride, DIA_CIERRE_CHOICES
from ..services.cierre_solicitudes_service import CierreSolicitudesService as CS
from core.utils.date_utils import DateUtils

N_SEMANAS = 8


def _parse_hora(s, default=time(14, 0)):
    try:
        return datetime.strptime(s, '%H:%M').time()
    except (ValueError, TypeError):
        return default


class CierreConfigView(LoginRequiredMixin, AdminRequiredMixin, View):
    template_name = 'solicitudes/cierre_config.html'

    def _semanas(self):
        """Las próximas N semanas con su cierre EFECTIVO (default u override)."""
        hoy = date.today()
        lunes0 = hoy - timedelta(days=hoy.weekday())
        filas = []
        for i in range(N_SEMANAS):
            lunes = lunes0 + timedelta(days=7 * i)
            ov = CierreSemanaOverride.objects.filter(semana_lunes=lunes).first()
            hab, dia, hora = CS._config_efectiva(lunes)
            v = CS._ventana_semana(lunes)
            filas.append({
                'lunes': lunes, 'domingo': lunes + timedelta(days=6),
                'override': ov, 'habilitado': hab, 'dia': dia, 'hora': hora,
                'dia_cierre_fecha': v[0] if v else None,   # inicio de la ventana
                'primer_habil': v[1] if v else None,       # fin de la ventana
                'cutoff_fecha': v[2] if v else None,       # día en que se activa el bloqueo
            })
        return filas

    def get(self, request):
        cfg = CierreSolicitudesConfig.obtener()
        return render(request, self.template_name, {
            'cfg': cfg, 'semanas': self._semanas(), 'dias_choices': DIA_CIERRE_CHOICES,
        })

    def post(self, request):
        accion = request.POST.get('accion')
        if accion == 'default':
            cfg = CierreSolicitudesConfig.obtener()
            cfg.habilitado = request.POST.get('habilitado') == 'on'
            cfg.dia_cierre = request.POST.get('dia_cierre') or cfg.dia_cierre
            cfg.hora_cierre = _parse_hora(request.POST.get('hora_cierre'), cfg.hora_cierre)
            cfg.save()
            messages.success(request, 'Configuración por defecto del cierre guardada.')
        elif accion == 'override':
            try:
                lunes = DateUtils.parse_date(request.POST.get('semana_lunes'))
            except (ValueError, TypeError):
                messages.error(request, 'Semana inválida.')
                return redirect('solicitudes:cierre_config')
            # El override se busca siempre por el LUNES de la semana: normalizar para no crear
            # ajustes huérfanos que `_config_efectiva` nunca encontraría.
            lunes -= timedelta(days=lunes.weekday())
            ov, _ = CierreSemanaOverride.objects.get_or_create(semana_lunes=lunes)
            ov.habilitado = request.POST.get('habilitado') == 'on'
            ov.dia_cierre = request.POST.get('dia_cierre') or ov.dia_cierre
            ov.hora_cierre = _parse_hora(request.POST.get('hora_cierre'), ov.hora_cierre)
            ov.save()
            messages.success(request, f'Ajuste guardado para la semana del {lunes.strftime("%d/%m/%Y")}.')
        elif accion == 'quitar_override':
            try:
                lunes = DateUtils.parse_date(request.POST.get('semana_lunes'))
                lunes -= timedelta(days=lunes.weekday())
                CierreSemanaOverride.objects.filter(semana_lunes=lunes).delete()
                messages.success(request, 'Ajuste de semana eliminado (vuelve al valor por defecto).')
            except (ValueError, TypeError):
                pass
        return redirect('solicitudes:cierre_config')
