"""
Pruebas de la configuración de la conexión a la base (config/settings.py).

No prueban Django, prueban DECISIONES de despliegue que son fáciles de deshacer
sin querer al tocar settings.py, y cuyo efecto no se ve en desarrollo:

  - CONN_MAX_AGE sin CONN_HEALTH_CHECKS produce 500 intermitentes en producción
    cuando RDS cierra o conmuta una conexión reutilizada.
  - Quitar la verificación del certificado convierte el TLS en decorativo:
    la conexión iría cifrada contra cualquiera que se haga pasar por la base.
"""
import importlib

from django.conf import settings
from django.test import override_settings

from core.checks import tls_hacia_la_base_en_produccion


class TestConexionPersistente:

    def test_conn_health_checks_activo(self):
        """
        Acompañante obligatorio de CONN_MAX_AGE.

        Sin él, una conexión reutilizada que murió (timeout de MySQL, failover de
        RDS) se usaría igualmente y la petición fallaría.
        """
        assert settings.DATABASES['default']['CONN_HEALTH_CHECKS'] is True

    def test_conn_max_age_definido(self):
        valor = settings.DATABASES['default']['CONN_MAX_AGE']

        assert isinstance(valor, int)
        assert valor >= 0

    def test_desarrollo_no_reutiliza_conexiones(self):
        """En dev el valor por defecto es 0: el comportamiento de siempre."""
        assert settings.IS_PRODUCTION is False
        assert settings.DATABASES['default']['CONN_MAX_AGE'] == 0


class TestTLSHaciaLaBase:

    def test_desarrollo_sin_tls(self):
        """Base local: sin certificado, sin TLS. No debe exigirse en dev."""
        assert settings.DATABASES['default']['OPTIONS'] == {}

    def test_con_ca_se_cifra_y_se_verifica(self, monkeypatch):
        """
        Con DB_SSL_CA no basta con cifrar: hay que verificar identidad.

        Se recarga settings con la variable puesta para comprobar las tres claves
        que PyMySQL necesita.
        """
        monkeypatch.setenv('DB_SSL_CA', '/app/certs/rds-ca-global.pem')

        from config import settings as modulo
        recargado = importlib.reload(modulo)
        try:
            opciones = recargado.DATABASES['default']['OPTIONS']

            assert opciones['ssl_ca'] == '/app/certs/rds-ca-global.pem'
            assert opciones['ssl_verify_cert'] is True
            assert opciones['ssl_verify_identity'] is True
        finally:
            monkeypatch.delenv('DB_SSL_CA')
            importlib.reload(modulo)

    @override_settings(IS_PRODUCTION=True,
                       DATABASES={'default': {'OPTIONS': {}}})
    def test_aviso_si_produccion_sin_tls(self):
        avisos = tls_hacia_la_base_en_produccion(None)

        assert len(avisos) == 1
        assert avisos[0].id == 'core.W002'

    @override_settings(IS_PRODUCTION=True,
                       DATABASES={'default': {'OPTIONS': {'ssl_ca': '/certs/ca.pem'}}})
    def test_sin_aviso_si_produccion_con_tls(self):
        assert tls_hacia_la_base_en_produccion(None) == []

    @override_settings(IS_PRODUCTION=False,
                       DATABASES={'default': {'OPTIONS': {}}})
    def test_sin_aviso_en_desarrollo(self):
        assert tls_hacia_la_base_en_produccion(None) == []
