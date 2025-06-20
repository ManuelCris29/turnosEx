from django.urls import path
from .views import (
    EmpleadoListView, EmpleadoDetailView, EmpleadoEditView,
    RestriccionesView, SeccionesView, JornadasView, RolesView
)

urlpatterns = [
    path('', EmpleadoListView.as_view(), name='empleados'),
    path('detail/<int:pk>/', EmpleadoDetailView.as_view(), name='empleado_detail'),
    path('edit/<int:pk>/', EmpleadoEditView.as_view(), name='empleado_edit'),
    path('restricciones/', RestriccionesView.as_view(), name='restricciones'),
    path('secciones/', SeccionesView.as_view(), name='secciones'),
    path('jornadas/', JornadasView.as_view(), name='jornadas'),
    path('roles/', RolesView.as_view(), name='roles'),
    # Aquí irán más URLs conforme se vayan creando las vistas
] 