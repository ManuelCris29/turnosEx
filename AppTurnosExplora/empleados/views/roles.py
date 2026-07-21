from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView
from django.urls import reverse_lazy

from core.mixins import AdminRequiredMixin

from ..models import Role


# CRUD de Roles
class RoleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Role
    template_name = 'empleados/roles_list.html'
    context_object_name = 'roles'

class RoleCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Role
    template_name = 'empleados/roles_create.html'
    fields = ['nombre']
    success_url = reverse_lazy('roles_list')

class RoleUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Role
    template_name = 'empleados/roles_edit.html'
    fields = ['nombre']
    success_url = reverse_lazy('roles_list')

class RoleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Role
    template_name = 'empleados/roles_confirm_delete.html'
    success_url = reverse_lazy('roles_list')
