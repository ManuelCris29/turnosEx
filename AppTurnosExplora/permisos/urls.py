from django.urls import path
from .views import (
    PermisosEspecialesView, BeneficiosView,
    PermisoEspecialListView, PermisoEspecialCreateView, 
    PermisoEspecialUpdateView, PermisoEspecialDeleteView
)

# A medida que vayas creando las vistas para la app de permisos,
# deberás agregarlas aquí.
urlpatterns = [
    path('', PermisosEspecialesView.as_view(), name='permisos_especiales'),
    path('beneficios/', BeneficiosView.as_view(), name='beneficios'),
    path('permisos-especiales/', PermisoEspecialListView.as_view(), name='permisos_especiales_list'),
    path('permisos-especiales/create/', PermisoEspecialCreateView.as_view(), name='permisos_especiales_create'),
    path('permisos-especiales/edit/<int:pk>/', PermisoEspecialUpdateView.as_view(), name='permisos_especiales_edit'),
    path('permisos-especiales/delete/<int:pk>/', PermisoEspecialDeleteView.as_view(), name='permisos_especiales_delete'),
] 