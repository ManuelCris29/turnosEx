from django.urls import path
from .views import PermisosEspecialesView, BeneficiosView

# A medida que vayas creando las vistas para la app de permisos,
# deberás agregarlas aquí.
urlpatterns = [
    path('', PermisosEspecialesView.as_view(), name='permisos_especiales'),
    path('beneficios/', BeneficiosView.as_view(), name='beneficios'),
] 