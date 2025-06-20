from django.shortcuts import render
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin

# Create your views here.

class PermisosEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/list.html'

class BeneficiosView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/beneficios.html'
