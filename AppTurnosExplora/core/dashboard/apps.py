from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.dashboard'

    def ready(self):
        # Registra las comprobaciones de despliegue del proyecto (core/checks.py).
        # Viven en `core`, que no es una app instalable por sí misma, así que se
        # enganchan desde aquí: dashboard es la app que más depende de la caché.
        from core import checks  # noqa: F401
