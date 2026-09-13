"""
CRUD de horas a favor del explorador (crédito corporativo).

Espejo deliberado del CRUD de PDH (`empleados/views/pdh.py`): mismas plantillas de estilo,
mismos filtros y el mismo `AdminRequiredMixin`, que ya autoriza a staff y supervisores —los
dos perfiles que pueden reconocer horas—, así que no hace falta un permiso nuevo.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import ListView

from core.mixins import AdminRequiredMixin
from permisos.models import CreditoHoras
from permisos.services.credito_horas_service import CreditoHorasService

from ..forms import CreditoHorasForm
from ..models import Empleado

logger = logging.getLogger(__name__)


class CreditoHorasListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Todas las horas a favor registradas, con el saldo vivo de cada explorador."""
    model = CreditoHoras
    template_name = 'empleados/credito_list.html'
    context_object_name = 'creditos'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            CreditoHoras.objects
            .select_related('explorador', 'otorgado_por')
            .order_by('-fecha_hecho', '-id')
        )
        explorador = self.request.GET.get('explorador')
        if explorador and explorador.isdigit():
            qs = qs.filter(explorador_id=int(explorador))
        estado = self.request.GET.get('estado')
        if estado in dict(CreditoHoras.ESTADO_CHOICES):
            qs = qs.filter(estado=estado)
        desde = parse_date(self.request.GET.get('desde') or '')
        if desde:
            qs = qs.filter(fecha_hecho__gte=desde)
        hasta = parse_date(self.request.GET.get('hasta') or '')
        if hasta:
            qs = qs.filter(fecha_hecho__lte=hasta)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
        context['estados'] = CreditoHoras.ESTADO_CHOICES
        context['filtros'] = {
            'explorador': self.request.GET.get('explorador') or '',
            'estado': self.request.GET.get('estado') or '',
            'desde': self.request.GET.get('desde') or '',
            'hasta': self.request.GET.get('hasta') or '',
        }
        # Saldo del explorador filtrado: es el dato que se consulta antes de registrar
        # un pago, y calcularlo aquí evita tener que abrir la pantalla de PDH para verlo.
        filtro_exp = context['filtros']['explorador']
        if filtro_exp and filtro_exp.isdigit():
            emp = Empleado.objects.filter(id=int(filtro_exp)).first()
            if emp:
                context['saldo_horas'] = CreditoHorasService.horas_disponibles(emp)
        qs = self.request.GET.copy()
        qs.pop('page', None)
        context['querystring'] = qs.urlencode()
        return context


class CreditoHorasCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Reconoce horas que la corporación le debe a un explorador."""
    template_name = 'empleados/credito_create.html'

    def get(self, request):
        return render(request, self.template_name, {'form': CreditoHorasForm()})

    def post(self, request):
        form = CreditoHorasForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {'form': form})

        otorgado_por = getattr(request.user, 'empleado', None)
        if otorgado_por is None:
            messages.error(
                request,
                'Tu usuario no tiene una ficha de empleado asociada, así que no puede figurar '
                'como quien reconoce las horas. Contacta con administración.',
            )
            return render(request, self.template_name, {'form': form})

        credito, error = CreditoHorasService.otorgar(
            explorador=form.cleaned_data['explorador'],
            fecha_hecho=form.cleaned_data['fecha_hecho'],
            minutos=form.minutos,
            motivo=form.cleaned_data['motivo'],
            otorgado_por=otorgado_por,
        )
        if error:
            messages.error(request, error)
            return render(request, self.template_name, {'form': form})

        explorador = credito.explorador
        messages.success(
            request,
            f'Registradas {credito.horas_otorgadas} h a favor de {explorador.nombre} '
            f'{explorador.apellido}. Quedan {CreditoHorasService.horas_disponibles(explorador)} h '
            f'disponibles para descontar de sus deudas.'
        )
        return redirect('credito_list')


class CreditoHorasAnularView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Deja sin efecto un crédito otorgado por error.

    No hay borrado: el crédito es un reconocimiento de deuda hacia el explorador y borrarlo
    haría desaparecer el rastro de que alguien lo concedió. Se anula, igual que una sanción
    se levanta en vez de eliminarse.
    """
    template_name = 'empleados/credito_confirm_anular.html'

    def get(self, request, pk):
        credito = get_object_or_404(CreditoHoras, pk=pk)
        return render(request, self.template_name, {'credito': credito})

    def post(self, request, pk):
        credito = get_object_or_404(CreditoHoras, pk=pk)
        motivo = (request.POST.get('motivo') or '').strip()
        _, error = CreditoHorasService.anular(credito, motivo)
        if error:
            messages.error(request, error)
            return render(request, self.template_name, {'credito': credito})
        messages.success(request, f'Crédito de {credito.horas_otorgadas} h anulado.')
        return redirect('credito_list')
