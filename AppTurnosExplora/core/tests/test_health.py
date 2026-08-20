"""
Pruebas de los endpoints de salud (core/health.py).

Lo que se protege aquí no es "que devuelvan 200": es que sigan siendo utilizables
como health check del balanceador. Si alguien los pone detrás de login, les añade
una consulta pesada o los mete bajo un prefijo que un middleware intercepta, el
ALB empezaría a considerar muertas las tareas y ECS las reiniciaría en bucle.
"""
from unittest.mock import patch

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestHealth:

    def test_liveness_responde_ok_sin_autenticacion(self, client):
        """El ALB no puede iniciar sesión: el endpoint debe ser anónimo."""
        respuesta = client.get(reverse('health'))

        assert respuesta.status_code == 200
        assert respuesta.json() == {'status': 'ok'}

    def test_liveness_no_consulta_la_base_de_datos(self, client):
        """
        Liveness responde por el proceso, no por la base.

        Si tocara RDS, una caída pasajera de la base haría que el ALB matara todas
        las tareas a la vez y convertiría un incidente recuperable en una caída
        total. `django_assert_num_queries` deja constancia de esa exigencia.
        """
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as consultas:
            respuesta = client.get(reverse('health'))

        assert respuesta.status_code == 200
        assert len(consultas) == 0

    def test_liveness_no_se_cachea(self, client):
        """Una respuesta de salud cacheada dejaría de informar del estado real."""
        respuesta = client.get(reverse('health'))

        assert 'no-cache' in respuesta.headers.get('Cache-Control', '')

    def test_readiness_ok_cuando_la_base_responde(self, client):
        respuesta = client.get(reverse('health_ready'))

        assert respuesta.status_code == 200
        assert respuesta.json() == {'status': 'ok', 'database': 'ok'}

    def test_readiness_devuelve_503_si_la_base_falla(self, client):
        """Debe distinguirse de un 200: es lo que lo hace útil al desplegar."""
        with patch('core.health.connection') as conexion:
            conexion.cursor.side_effect = Exception('base caída')
            respuesta = client.get(reverse('health_ready'))

        assert respuesta.status_code == 503
        assert respuesta.json()['database'] == 'unavailable'

    def test_solo_acepta_get(self, client):
        assert client.post(reverse('health')).status_code == 405


def test_PRUEBA_NEGATIVA_BORRAR():
    """Fallo deliberado para verificar que el CI se pone rojo. Se revierte enseguida."""
    assert 1 == 2, "prueba negativa del CI"
