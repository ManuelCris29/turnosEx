from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView

from core.mixins import AdminRequiredMixin

from ..models import Sala


# CRUD de Salas
class SalaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Sala
    template_name = 'empleados/salas_list.html'
    context_object_name = 'salas'

class SalaCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Sala
    template_name = 'empleados/salas_create.html'
    fields = ['nombre', 'activo']
    success_url = '/empleados/salas/'

class SalaUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Sala
    template_name = 'empleados/salas_edit.html'
    fields = ['nombre', 'activo']
    success_url = '/empleados/salas/'

class SalaDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Sala
    template_name = 'empleados/salas_confirm_delete.html'
    success_url = '/empleados/salas/'
