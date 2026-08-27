from django.urls import path

from .views import (
    BeneficiosView,
    MediaJornadaTemporadaCreateView,
    PermisoEspecialAprobarView,
    PermisoEspecialCreateView,
    PermisoEspecialDeleteView,
    PermisoEspecialListView,
    PermisoEspecialPermanenteCreateView,
    PermisoEspecialResolverEmailView,
    PermisoMediaJornadaCancelResponderView,
    PermisoMediaJornadaCancelView,
    PermisosEspecialesView,
)

urlpatterns = [
    path('', PermisosEspecialesView.as_view(), name='permisos_especiales'),
    path('beneficios/', BeneficiosView.as_view(), name='beneficios'),
    path('permisos-especiales/', PermisoEspecialListView.as_view(), name='permisos_especiales_list'),
    path('permisos-especiales/create/', PermisoEspecialCreateView.as_view(), name='permisos_especiales_create'),
    path('permisos-especiales/permanente/create/', PermisoEspecialPermanenteCreateView.as_view(), name='permisos_especiales_permanente_create'),
    path('permisos-especiales/<int:pk>/aprobar/', PermisoEspecialAprobarView.as_view(), name='permisos_especiales_aprobar'),
    path('permisos-especiales/<int:pk>/aprobar-email/<str:token>/',
         PermisoEspecialResolverEmailView.as_view(accion='aprobar'), name='permisos_especiales_aprobar_email'),
    path('permisos-especiales/<int:pk>/rechazar-email/<str:token>/',
         PermisoEspecialResolverEmailView.as_view(accion='rechazar'), name='permisos_especiales_rechazar_email'),
    path('permisos-especiales/delete/<int:pk>/', PermisoEspecialDeleteView.as_view(), name='permisos_especiales_delete'),
    path('permisos-especiales/media-jornada/create/', MediaJornadaTemporadaCreateView.as_view(),
         name='permisos_media_jornada_create'),
    path('permisos-especiales/media-jornada/<int:pk>/cancelar/', PermisoMediaJornadaCancelView.as_view(),
         name='permisos_media_jornada_cancelar'),
    # El supervisor aprueba o rechaza la cancelación de un permiso ya aprobado.
    path('permisos-especiales/media-jornada/<int:pk>/cancelar/responder/',
         PermisoMediaJornadaCancelResponderView.as_view(),
         name='permisos_media_jornada_cancelar_responder'),
]
