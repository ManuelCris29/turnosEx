from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView

from core.mixins import AdminRequiredMixin
from core.services.cache_service import CACHE_TTL_VERY_LONG, CacheService

from ..forms import JornadaForm
from ..models import Jornada


# CRUD de Jornadas
class JornadaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Jornada
    template_name = 'empleados/jornadas_list.html'
    context_object_name = 'jornadas'

    def get_queryset(self):
        # Catálogo casi estático: se cachea 24h e invalida por señal
        # (empleados/signals.py) ante cualquier escritura de Jornada.
        qs = super().get_queryset()
        return CacheService.get_or_set('catalogo_jornadas_v1', lambda: list(qs), ttl=CACHE_TTL_VERY_LONG)

class JornadaCreateView(LoginRequiredMixin, AdminRequiredMixin, SuccessMessageMixin, CreateView):
    model = Jornada
    form_class = JornadaForm
    template_name = 'empleados/jornadas_create.html'
    success_url = reverse_lazy('jornadas_list')
    success_message = 'Jornada "%(nombre)s" creada correctamente.'

class JornadaUpdateView(LoginRequiredMixin, AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Jornada
    form_class = JornadaForm
    template_name = 'empleados/jornadas_edit.html'
    success_url = reverse_lazy('jornadas_list')
    success_message = 'Jornada "%(nombre)s" actualizada correctamente.'

class JornadaDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Elimina una jornada.

    Las jornadas base (AM/PM) NO se pueden eliminar: el motor de turnos las
    busca por nombre literal y las FK que las referencian son PROTECT, así que
    el borrado fallaría igualmente. Se bloquea antes para dar un mensaje claro.
    """
    model = Jornada
    template_name = 'empleados/jornadas_confirm_delete.html'
    success_url = reverse_lazy('jornadas_list')

    def get(self, request, *args, **kwargs):
        bloqueo = self._bloqueo_si_protegida()
        return bloqueo or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        bloqueo = self._bloqueo_si_protegida()
        return bloqueo or super().post(request, *args, **kwargs)

    def _bloqueo_si_protegida(self):
        self.object = self.get_object()
        if self.object.es_protegida:
            messages.error(
                self.request,
                f'La jornada "{self.object.nombre}" es parte de la configuración base '
                f'del sistema de turnos y no se puede eliminar.'
            )
            return redirect('jornadas_list')
        return None

    def form_valid(self, form):
        nombre = self.object.nombre
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            # Las FK de turnos son PROTECT: si la jornada tiene turnos,
            # asignaciones o descansos asociados, no se puede borrar.
            messages.error(
                self.request,
                f'No se puede eliminar la jornada "{nombre}": tiene turnos o '
                f'asignaciones asociadas. Eliminar la jornada borraría ese historial.'
            )
            return redirect('jornadas_list')
        messages.success(self.request, f'Jornada "{nombre}" eliminada correctamente.')
        return respuesta
