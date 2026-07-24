import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import DeleteView
from django.views import View
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse

from permisos.models import PDH
from core.mixins import AdminRequiredMixin

from ..models import Empleado
from ..forms import PDHForm

logger = logging.getLogger(__name__)


# CRUD de PDH (Pago de Horas)
class PDHListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Administración: el supervisor/admin ve y gestiona todos los pagos de horas."""
    model = PDH
    template_name = 'empleados/pdh_list.html'
    context_object_name = 'pdhs'

    def get_queryset(self):
        return (
            PDH.objects.filter(tipo_registro='pago_horas')
            .select_related('explorador', 'supervisor')
            .order_by('-fecha', '-id')
        )

class DeudasPendientesExploradorView(LoginRequiredMixin, AdminRequiredMixin, View):
    """AJAX: devuelve las deudas pendientes (dobladas + permisos) de un explorador."""
    def get(self, request):
        from permisos.pago_horas_service import PagoHorasService
        explorador_id = request.GET.get('explorador_id')
        if not explorador_id:
            return JsonResponse({'success': False, 'deudas': [], 'total_horas': 0})
        try:
            emp = Empleado.objects.get(id=explorador_id)
        except Empleado.DoesNotExist:
            return JsonResponse({'success': False, 'deudas': [], 'total_horas': 0})
        items = PagoHorasService.deudas_pendientes(emp)
        data = [{k: v for k, v in it.items() if k != 'fecha'} for it in items]
        total = round(sum(it['horas'] for it in items), 2)
        return JsonResponse({'success': True, 'deudas': data, 'total_horas': total})


class PDHCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Registra un Pago de Horas apuntando a deudas concretas. El supervisor elige el
    explorador, marca las deudas (dobladas/permisos) que paga y se crea el PDH con las
    horas = suma de lo seleccionado.
    """
    template_name = 'empleados/pdh_create.html'

    def get(self, request):
        return render(request, self.template_name, {
            'exploradores': Empleado.objects.filter(activo=True).order_by('nombre', 'apellido'),
        })

    def post(self, request):
        from permisos.pago_horas_service import PagoHorasService
        explorador_id = request.POST.get('explorador')
        fecha = request.POST.get('fecha')
        comentario = request.POST.get('comentario', '')
        keys = request.POST.getlist('deudas')

        if not explorador_id or not fecha:
            messages.error(request, 'Selecciona el explorador y la fecha de pago.')
            return redirect('pdh_create')
        try:
            explorador = Empleado.objects.get(id=explorador_id)
        except Empleado.DoesNotExist:
            messages.error(request, 'Explorador no válido.')
            return redirect('pdh_create')

        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=request.user.empleado,
            explorador=explorador,
            fecha=fecha,
            keys=keys,
            comentario=comentario,
        )
        if error:
            messages.error(request, error)
            return redirect('pdh_create')

        messages.success(
            request,
            f'Pago de {pdh.horas} h registrado para {explorador.nombre} {explorador.apellido}. '
            f'Se saldaron {len(keys)} deuda(s) y se descuenta de su consolidado.'
        )
        try:
            from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
            DeudaCorporativaService.gestionar_sancion_por_deuda(explorador)
        except Exception:
            logger.warning("Error gestionando sanción por deuda tras pago (explorador=%s)", explorador.id, exc_info=True)
        return redirect('pdh_list')

class PDHUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = PDH
    form_class = PDHForm
    template_name = 'empleados/pdh_edit.html'
    success_url = '/empleados/pdh/'

    def form_valid(self, form):
        # Solo se editan fecha/comentario; las horas y deudas vinculadas no cambian aquí
        # (para cambiar las deudas pagadas, se borra el pago y se vuelve a registrar).
        form.instance.tipo_registro = 'pago_horas'
        return super().form_valid(form)

class PDHDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = PDH
    template_name = 'empleados/pdh_confirm_delete.html'
    success_url = '/empleados/pdh/'

    def form_valid(self, form):
        # Al borrar el pago, reactivar las deudas que saldaba (vuelven a pendientes).
        from permisos.pago_horas_service import PagoHorasService
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
        pdh = self.get_object()
        explorador = pdh.explorador
        PagoHorasService.revertir_pago(pdh)
        resp = super().form_valid(form)
        try:
            DeudaCorporativaService.gestionar_sancion_por_deuda(explorador)
        except Exception:
            logger.warning("Error gestionando sanción por deuda tras borrar pago (explorador=%s)", explorador.id, exc_info=True)
        return resp


# Vistas solo visualización para Consultas Rápidas
class PDHVisualizarListView(LoginRequiredMixin, ListView):
    """Consulta: admin/supervisor ve todos los pagos; el explorador solo los suyos."""
    model = PDH
    template_name = 'empleados/pdh_visualizar_list.html'
    context_object_name = 'pdhs'

    def get_queryset(self):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService
        qs = (
            PDH.objects.filter(tipo_registro='pago_horas')
            .select_related('explorador', 'supervisor')
            .order_by('-fecha', '-id')
        )
        user = self.request.user
        if ConsolidadoHorasService.es_supervisor(user):
            return qs
        empleado = getattr(user, 'empleado', None)
        return qs.filter(explorador=empleado) if empleado else qs.none()

    def get_context_data(self, **kwargs):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService
        context = super().get_context_data(**kwargs)
        context['es_supervisor'] = ConsolidadoHorasService.es_supervisor(self.request.user)
        return context
