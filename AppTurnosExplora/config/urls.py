"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings

from core.health import health, readiness

urlpatterns = [
    # Salud para el balanceador. Va primero y fuera de cualquier app: debe
    # responder aunque el resto del enrutado cambie. Ver core/health.py.
    path('health/', health, name='health'),
    path('health/ready/', readiness, name='health_ready'),

    path('admin/', admin.site.urls),
    path('', include('core.login.urls')),
    path('dashboard/', include('core.dashboard.urls')),
    path('empleados/', include('empleados.urls')),
    path('turnos/', include('turnos.urls')),
    path('permisos/', include('permisos.urls')),
    path('solicitudes/', include('solicitudes.urls', namespace='solicitudes')),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
