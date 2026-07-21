from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView

from core.mixins import AdminRequiredMixin

from ..models import Jornada
from ..forms import JornadaForm


# CRUD de Jornadas
class JornadaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Jornada
    template_name = 'empleados/jornadas_list.html'
    context_object_name = 'jornadas'

class JornadaCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Jornada
    form_class = JornadaForm
    template_name = 'empleados/jornadas_create.html'
    success_url = '/empleados/jornadas/'

class JornadaUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Jornada
    form_class = JornadaForm
    template_name = 'empleados/jornadas_edit.html'
    success_url = '/empleados/jornadas/'

class JornadaDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Jornada
    template_name = 'empleados/jornadas_confirm_delete.html'
    success_url = '/empleados/jornadas/'
