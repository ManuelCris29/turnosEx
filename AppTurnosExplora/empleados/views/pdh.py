import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import DeleteView

from core.mixins import AdminRequiredMixin
from permisos.models import PDH

from ..forms import PDHForm
from ..models import Empleado

logger = logging.getLogger(__name__)


# CRUD de PDH (Pago de Horas)
class PDHListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Administración: el supervisor/admin ve y gestiona todos los pagos de horas."""
    model = PDH
    template_name = 'empleados/pdh_list.html'
    context_object_name = 'pdhs'
    paginate_by = 25

    def get_queryset(self):
        qs = (
            PDH.objects.filter(tipo_registro='pago_horas')
            .select_related('explorador', 'supervisor')
            .order_by('-fecha', '-id')
        )
        explorador = self.request.GET.get('explorador')
        if explorador and explorador.isdigit():
            qs = qs.filter(explorador_id=int(explorador))
        desde = parse_date(self.request.GET.get('desde') or '')
        if desde:
            qs = qs.filter(fecha__gte=desde)
        hasta = parse_date(self.request.GET.get('hasta') or '')
        if hasta:
            qs = qs.filter(fecha__lte=hasta)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
        context['filtros'] = {
            'explorador': self.request.GET.get('explorador') or '',
            'desde': self.request.GET.get('desde') or '',
            'hasta': self.request.GET.get('hasta') or '',
        }
        # Para conservar los filtros al cambiar de página.
        qs = self.request.GET.copy()
        qs.pop('page', None)
        context['querystring'] = qs.urlencode()
        return context


class DeudasPendientesExploradorView(LoginRequiredMixin, AdminRequiredMixin, View):
    """AJAX: devuelve las deudas pendientes (dobladas + permisos) de un explorador."""
    def get(self, request):
        from permisos.pago_horas_service import PagoHorasService
        explorador_id = request.GET.get('explorador_id')
        if not explorador_id or not explorador_id.isdigit():
            return JsonResponse({'success': False, 'deudas': [], 'total_horas': 0})
        try:
            emp = Empleado.objects.get(id=int(explorador_id))
        except Empleado.DoesNotExist:
            return JsonResponse({'success': False, 'deudas': [], 'total_horas': 0})
        grupos = PagoHorasService.deudas_pendientes(emp)
        # `fecha` es un objeto date y no viaja a JSON; la pantalla usa `fecha_str`.
        data = [
            {**g, 'items': [{k: v for k, v in it.items() if k != 'fecha'}
                            for it in g['items']]}
            for g in grupos
        ]
        total = round(sum(g['horas_pendientes'] for g in grupos), 2)
        return JsonResponse({'success': True, 'meses': data, 'total_horas': total})


class PDHCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Registra un Pago de Horas apuntando a deudas concretas. El supervisor elige el
    explorador, marca las deudas (dobladas/permisos) que paga y se crea el PDH con las
    horas = suma de lo seleccionado.
    """
    template_name = 'empleados/pdh_create.html'

    def get(self, request):
        return render(request, self.template_name, self._context())

    def _context(self, datos=None):
        return {
            'exploradores': Empleado.objects.filter(activo=True).order_by('nombre', 'apellido'),
            'datos': datos or {'explorador': '', 'fecha': '', 'comentario': '', 'deudas': []},
        }

    def _error(self, request, mensaje, datos):
        """
        Re-renderiza el formulario con el error y lo que el usuario ya había escrito.
        Con `redirect` el mensaje se perdía y además se vaciaba la selección.
        """
        messages.error(request, mensaje)
        return render(request, self.template_name, self._context(datos))

    def post(self, request):
        from permisos.pago_horas_service import PagoHorasService
        explorador_id = request.POST.get('explorador', '')
        fecha_str = request.POST.get('fecha', '')
        comentario = (request.POST.get('comentario') or '').strip()
        keys = request.POST.getlist('deudas')
        # Importes de los pagos PARCIALES: llegan como `horas_permisomes:<id>`. Lo que no
        # venga se abona íntegro, que es el caso corriente.
        importes = {
            campo[len('horas_'):]: valor
            for campo, valor in request.POST.items()
            if campo.startswith('horas_permisomes:')
        }
        datos = {'explorador': explorador_id, 'fecha': fecha_str,
                 'comentario': comentario, 'deudas': keys}

        supervisor = getattr(request.user, 'empleado', None)
        if supervisor is None:
            return self._error(
                request,
                'Tu usuario no tiene una ficha de empleado asociada, así que no puede figurar '
                'como líder que autoriza el pago. Contacta con administración.',
                datos,
            )

        if not explorador_id or not fecha_str:
            return self._error(request, 'Selecciona el explorador y la fecha de pago.', datos)
        if not explorador_id.isdigit():
            return self._error(request, 'Explorador no válido.', datos)
        fecha = parse_date(fecha_str)
        if fecha is None:
            return self._error(request, 'La fecha de pago no es válida.', datos)
        try:
            explorador = Empleado.objects.get(id=int(explorador_id))
        except Empleado.DoesNotExist:
            return self._error(request, 'Explorador no válido.', datos)
        if not comentario:
            return self._error(request, 'Escribe una nota explicando el pago.', datos)

        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=supervisor,
            explorador=explorador,
            fecha=fecha,
            keys=keys,
            comentario=comentario,
            importes=importes,
        )
        if error:
            return self._error(request, error, datos)

        saldadas = pdh.deudas_pagadas.count() + pdh.detalles_permiso_mes.count()
        messages.success(
            request,
            f'Pago de {pdh.horas} h registrado para {explorador.nombre} {explorador.apellido}. '
            f'Se saldaron {saldadas} deuda(s) y se descuenta de su consolidado.'
        )
        # Ya no puede LEVANTAR nada —la sanción se cumple entera—, pero sigue haciendo
        # falta: si el pago fue parcial y el mes sigue con saldo vencido, la sanción que
        # corresponda debe nacer ahora y no esperar al cron de mañana.
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

    @transaction.atomic
    def form_valid(self, form):
        # Solo se editan fecha/comentario; las horas y deudas vinculadas no cambian aquí
        # (para cambiar las deudas pagadas, se borra el pago y se vuelve a registrar).
        from permisos.pago_horas_service import PagoHorasService
        form.instance.tipo_registro = 'pago_horas'
        resp = super().form_valid(form)
        # La fecha del pago manda: las deudas que salda deben decir lo mismo.
        PagoHorasService.sincronizar_fecha_pago(self.object)
        return resp

class PDHDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = PDH
    template_name = 'empleados/pdh_confirm_delete.html'
    success_url = '/empleados/pdh/'

    @transaction.atomic
    def form_valid(self, form):
        # Al borrar el pago, reactivar las deudas que saldaba (vuelven a pendientes).
        # Todo en una transacción: si el DELETE falla tras revertir, las deudas quedarían
        # reactivadas con el PDH todavía vivo y se contarían dos veces.
        from permisos.pago_horas_service import PagoHorasService
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
        pdh = self.object
        explorador = pdh.explorador
        PagoHorasService.revertir_pago(pdh)
        resp = super().form_valid(form)

        # Fuera de la transacción: un fallo aquí no debe romper el borrado ya confirmado
        # (una excepción de BD dentro del atomic lo dejaría inservible aunque la capturemos).
        def _sancion():
            try:
                DeudaCorporativaService.gestionar_sancion_por_deuda(explorador)
            except Exception:
                logger.warning("Error gestionando sanción por deuda tras borrar pago (explorador=%s)",
                               explorador.id, exc_info=True)
        transaction.on_commit(_sancion)
        return resp


