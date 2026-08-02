"""
Endpoints de salud para el balanceador de carga (ALB / App Runner / ECS).

Existen DOS, y la distinción importa:

  /health/       LIVENESS  — "¿el proceso responde?". No toca la base de datos.
                 Es el que debe apuntar el health check del balanceador.

  /health/ready/ READINESS — "¿además puede trabajar?". Verifica la conexión a
                 la base. Útil para comprobar un despliegue a mano o desde un
                 script, NO para el health check del ALB.

Por qué liveness no consulta la base: si el ALB comprueba la salud contra un
endpoint que toca RDS y la base tiene un hipo de 30 segundos, el ALB da por
muertas TODAS las tareas, las mata y las reemplaza. Los contenedores nuevos se
encuentran la misma base con problemas y el ciclo se repite: un incidente
recuperable de base de datos se convierte en una caída total de la aplicación.
Liveness responde por el proceso; de la base responde readiness.

Ninguno requiere autenticación (el ALB no puede iniciar sesión) y ninguno
devuelve información del sistema: solo un estado.
"""
import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
@never_cache
def health(request):
    """Liveness: el proceso está vivo y sirviendo. Sin base de datos, sin sesión."""
    return JsonResponse({'status': 'ok'})


@require_GET
@never_cache
def readiness(request):
    """Readiness: además de vivo, alcanza la base de datos. 503 si no."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        logger.error('Readiness: la base de datos no responde', exc_info=True)
        return JsonResponse({'status': 'error', 'database': 'unavailable'}, status=503)

    return JsonResponse({'status': 'ok', 'database': 'ok'})
