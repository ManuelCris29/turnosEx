from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView

from core.mixins import AdminRequiredMixin

from ..forms import RoleForm
from ..models import Role


# CRUD de Roles
class RoleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Role
    template_name = 'empleados/roles_list.html'
    context_object_name = 'roles'

    def get_queryset(self):
        # El número de empleados es el dato que hace falta para decidir si
        # editar o borrar un rol es seguro.
        return super().get_queryset().annotate(num_empleados=Count('empleadorole'))

class RoleCreateView(LoginRequiredMixin, AdminRequiredMixin, SuccessMessageMixin, CreateView):
    model = Role
    form_class = RoleForm
    template_name = 'empleados/roles_create.html'
    success_url = reverse_lazy('roles_list')
    success_message = 'Rol "%(nombre)s" creado correctamente.'

class RoleUpdateView(LoginRequiredMixin, AdminRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Role
    form_class = RoleForm
    template_name = 'empleados/roles_edit.html'
    success_url = reverse_lazy('roles_list')
    success_message = 'Rol "%(nombre)s" actualizado correctamente.'

class RoleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    """Elimina un rol.

    Los roles base (Supervisor/Explorador) NO se pueden eliminar: el permiso de
    administración y el listado de exploradores los buscan por nombre, así que
    borrarlos dejaría la operación sin supervisores o sin sancionables. El
    resto solo se puede borrar si no está asignado a nadie: la FK de
    EmpleadoRole es PROTECT, antes era CASCADE y el borrado se llevaba por
    delante las asignaciones sin avisar.
    """
    model = Role
    template_name = 'empleados/roles_confirm_delete.html'
    success_url = reverse_lazy('roles_list')

    def get(self, request, *args, **kwargs):
        bloqueo = self._bloqueo_si_protegido()
        return bloqueo or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        bloqueo = self._bloqueo_si_protegido()
        return bloqueo or super().post(request, *args, **kwargs)

    def _bloqueo_si_protegido(self):
        self.object = self.get_object()
        if self.object.es_protegido:
            messages.error(
                self.request,
                f'El rol "{self.object.nombre}" es parte de la configuración base '
                f'del sistema y no se puede eliminar.'
            )
            return redirect('roles_list')
        return None

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto['num_empleados'] = self.object.empleadorole_set.count()
        return contexto

    def form_valid(self, form):
        nombre = self.object.nombre
        try:
            respuesta = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f'No se puede eliminar el rol "{nombre}": está asignado a '
                f'{self.object.empleadorole_set.count()} empleado(s). Quítaselo '
                f'primero desde la ficha de cada empleado.'
            )
            return redirect('roles_list')
        messages.success(self.request, f'Rol "{nombre}" eliminado correctamente.')
        return respuesta
