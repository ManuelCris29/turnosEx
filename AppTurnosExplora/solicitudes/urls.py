from django.urls import path
from .views import SolicitudesView

# A medida que vayas creando las vistas para la app de solicitudes,
# deberás agregarlas aquí.
urlpatterns = [
    path('', SolicitudesView.as_view(), name='solicitudes'),
] 