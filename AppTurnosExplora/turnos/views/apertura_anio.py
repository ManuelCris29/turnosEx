"""
Pantalla de APERTURA DE AÑO: el checklist de lo que el supervisor debe dejar planificado
antes de que empiece el año siguiente.

No hay nada que "marcar" aquí: cada ítem enlaza a la pantalla donde se hace el trabajo y se
pone en verde solo cuando los datos existen (ver `AperturaAnioService`).
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from core.mixins import AdminRequiredMixin
from turnos.models import AperturaAnioConfig
from turnos.services.apertura_anio_service import AperturaAnioService

__all__ = ['AperturaAnioView']


class AperturaAnioView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'turnos/apertura_anio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        anio = kwargs.get('anio') or AperturaAnioService.anio_objetivo()
        items = AperturaAnioService.estado(anio)
        completos = {i.clave for i in items if i.completo}

        # Un ítem se puede abordar cuando sus dependencias están listas. Es una guía visual,
        # no un candado: si el supervisor sabe lo que hace, puede entrar igual a la pantalla.
        for item in items:
            item.esperando = [d for d in item.depende_de if d not in completos]

        cfg = AperturaAnioConfig.obtener()
        context.update({
            'anio': anio,
            'items': items,
            'total': len(items),
            'completados': len(completos),
            'pendientes': len(items) - len(completos),
            'todo_listo': len(completos) == len(items),
            'config': cfg,
            'fecha_bloqueo': cfg.fecha_bloqueo(anio - 1),
        })
        return context
