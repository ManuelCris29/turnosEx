from django.urls import path

from .views import (
    LoginFormView,
    LogoutUserView,
    PasswordChangeDoneSWALPView,
    PasswordChangeSWALPView,
    PasswordResetCompleteSWALPView,
    PasswordResetConfirmSWALPView,
    PasswordResetDoneSWALPView,
    PasswordResetSWALPView,
)

# Las rutas se declaran una a una en vez de con `include('django.contrib.auth.urls')`
# porque ese include trae también su propio `login`/`logout`, que chocarían con las
# vistas propias de arriba. Los NOMBRES sí son los estándar de Django: así
# `{% url 'password_reset' %}` y los enlaces que genera PasswordResetForm siguen
# funcionando sin configuración extra.
urlpatterns = [
    path('', LoginFormView.as_view(), name='login'),
    path('logout/', LogoutUserView.as_view(), name='logout'),

    # Cambiar mi contraseña (con sesión iniciada)
    path('password/cambiar/', PasswordChangeSWALPView.as_view(), name='password_change'),
    path('password/cambiar/listo/', PasswordChangeDoneSWALPView.as_view(), name='password_change_done'),

    # Recuperar contraseña olvidada (público)
    path('password/recuperar/', PasswordResetSWALPView.as_view(), name='password_reset'),
    path('password/recuperar/enviado/', PasswordResetDoneSWALPView.as_view(), name='password_reset_done'),
    path(
        'password/recuperar/<uidb64>/<token>/',
        PasswordResetConfirmSWALPView.as_view(),
        name='password_reset_confirm',
    ),
    path('password/recuperar/listo/', PasswordResetCompleteSWALPView.as_view(), name='password_reset_complete'),
]
