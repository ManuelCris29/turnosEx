from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

# Create your views here.

class MisTurnosView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/mis_turnos.html'

class CambiosTurnoView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'

class ConsolidadoHorasView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'

class DiasEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'
