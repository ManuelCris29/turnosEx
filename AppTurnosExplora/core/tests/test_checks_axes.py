"""
Pruebas de la comprobación de despliegue de django-axes (core/checks.py).

Esta comprobación es la red que impide un fallo con consecuencias muy visibles:
salir a producción bloqueando por IP detrás de un balanceador sin contar los
proxies. En esa combinación axes ve la IP del intermediario para TODO el mundo,
así que 5 intentos fallidos de cualquier empleado dejarían fuera a la plantilla
entera durante una hora — una denegación de servicio provocada por la propia
protección contra fuerza bruta.
"""
from django.test import override_settings

from core.checks import (
    _parametros_de_bloqueo,
    axes_puede_leer_la_ip_reenviada,
    axes_ve_la_ip_real_del_cliente,
)

PROXY = ('HTTP_X_FORWARDED_PROTO', 'https')
POR_USUARIO_E_IP = ['username', 'ip_address']
SOLO_USUARIO = ['username']


class TestAxesVeLaIpRealDelCliente:

    @override_settings(IS_PRODUCTION=True, SECURE_PROXY_SSL_HEADER=PROXY,
                       AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=0)
    def test_error_si_bloquea_por_ip_tras_proxy_sin_contarlo(self):
        """La combinación peligrosa: es la que debe impedir el despliegue."""
        errores = axes_ve_la_ip_real_del_cliente(None)

        assert len(errores) == 1
        assert errores[0].id == 'core.E003'
        assert 'AXES_IPWARE_PROXY_COUNT' in errores[0].hint

    @override_settings(IS_PRODUCTION=True, SECURE_PROXY_SSL_HEADER=PROXY,
                       AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=1)
    def test_sin_error_si_los_proxies_estan_contados(self):
        """Configuración correcta para Nginx (EC2) o ALB (Fargate): un intermediario."""
        assert axes_ve_la_ip_real_del_cliente(None) == []

    @override_settings(IS_PRODUCTION=True, SECURE_PROXY_SSL_HEADER=PROXY,
                       AXES_LOCKOUT_PARAMETERS=SOLO_USUARIO,
                       AXES_IPWARE_PROXY_COUNT=0)
    def test_sin_error_si_no_bloquea_por_ip(self):
        """Sin 'ip_address' en juego, no contar proxies es irrelevante para axes."""
        assert axes_ve_la_ip_real_del_cliente(None) == []

    @override_settings(IS_PRODUCTION=True, SECURE_PROXY_SSL_HEADER=None,
                       AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=0)
    def test_sin_error_si_no_hay_proxy_delante(self):
        """Sin intermediario, Django ya ve la IP real: no hay nada que saltar."""
        assert axes_ve_la_ip_real_del_cliente(None) == []

    @override_settings(IS_PRODUCTION=False, SECURE_PROXY_SSL_HEADER=PROXY,
                       AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=0)
    def test_sin_error_en_desarrollo(self):
        """En desarrollo no hay balanceador y el check no debe estorbar."""
        assert axes_ve_la_ip_real_del_cliente(None) == []


class TestParametrosDeBloqueo:
    """
    `AXES_LOCKOUT_PARAMETERS` admite dos formas con semántica MUY distinta, y el
    check debe reconocer la IP en ambas:

      plana   ['username', 'ip_address']    -> bloquea por usuario O por IP
      anidada [['username', 'ip_address']]  -> bloquea por la PAREJA

    La anidada no frena a quien rota nombres desde una misma IP, pero para saber
    si la IP participa en la decisión ambas cuentan igual.
    """

    @override_settings(AXES_LOCKOUT_PARAMETERS=['username', 'ip_address'])
    def test_reconoce_la_forma_plana(self):
        assert _parametros_de_bloqueo() == ['username', 'ip_address']

    @override_settings(AXES_LOCKOUT_PARAMETERS=[['username', 'ip_address']])
    def test_aplana_la_forma_anidada(self):
        assert _parametros_de_bloqueo() == ['username', 'ip_address']

    @override_settings(AXES_LOCKOUT_PARAMETERS=['ip_address', ['username', 'user_agent']])
    def test_admite_las_dos_formas_mezcladas(self):
        assert _parametros_de_bloqueo() == ['ip_address', 'username', 'user_agent']

    @override_settings(AXES_LOCKOUT_PARAMETERS=[])
    def test_lista_vacia(self):
        assert _parametros_de_bloqueo() == []


class TestConfiguracionRealDelProyecto:
    """La configuración que se despliega de verdad, no una inventada por el test."""

    def test_bloquea_por_usuario_y_por_ip(self):
        """
        Si alguien vuelve a dejarlo en solo 'username', este test lo caza: con 5
        intentos por usuario y una lista de nombres, no hay límite efectivo.
        """
        from django.conf import settings

        assert 'ip_address' in _parametros_de_bloqueo()
        assert 'username' in _parametros_de_bloqueo()
        # Plana, no anidada: la anidada cuenta la pareja y no frena la rotación
        # de usuarios desde una misma IP.
        assert all(isinstance(p, str) for p in settings.AXES_LOCKOUT_PARAMETERS)

    def test_cuenta_un_proxy_en_produccion(self):
        """
        Nginx (EC2) y ALB (Fargate) son UN intermediario; ninguna de las dos
        arquitecturas candidatas contempla CloudFront. Si se añadiera un segundo,
        este número debe subir o el bloqueo por IP deja de servir.
        """
        from django.conf import settings

        assert settings.AXES_IPWARE_PROXY_COUNT in (0, 1)


class TestAxesPuedeLeerLaIpReenviada:
    """
    `core.E004`: la trampa que `core.E003` no veía.

    E003 comprueba que AXES_IPWARE_PROXY_COUNT esté puesto. Pero ese ajuste puede
    estar puesto y NO HACER NADA —si falta django-ipware, o si axes no mira
    X-Forwarded-For—, con lo que E003 daba luz verde a una configuración inerte.
    Se descubrió ejecutando `manage.py verificar_ip_cliente` con la configuración
    "correcta": axes resolvía la IP del balanceador.
    """

    CABECERAS_OK = ['HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']

    @override_settings(IS_PRODUCTION=True, AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=1,
                       AXES_IPWARE_META_PRECEDENCE_ORDER=CABECERAS_OK)
    def test_sin_error_con_ipware_y_la_cabecera_correcta(self):
        assert axes_puede_leer_la_ip_reenviada(None) == []

    @override_settings(IS_PRODUCTION=True, AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=1,
                       AXES_IPWARE_META_PRECEDENCE_ORDER=('REMOTE_ADDR',))
    def test_error_si_axes_no_mira_x_forwarded_for(self):
        """El valor POR DEFECTO de axes: solo REMOTE_ADDR. Nunca vería al cliente."""
        errores = axes_puede_leer_la_ip_reenviada(None)

        assert len(errores) == 1
        assert errores[0].id == 'core.E004'
        assert 'HTTP_X_FORWARDED_FOR' in errores[0].hint

    @override_settings(IS_PRODUCTION=True, AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=0,
                       AXES_IPWARE_META_PRECEDENCE_ORDER=('REMOTE_ADDR',))
    def test_sin_error_si_no_se_declaran_proxies(self):
        """De esa combinación responde core.E003; E004 no debe duplicar el aviso."""
        assert axes_puede_leer_la_ip_reenviada(None) == []

    @override_settings(IS_PRODUCTION=True, AXES_LOCKOUT_PARAMETERS=SOLO_USUARIO,
                       AXES_IPWARE_PROXY_COUNT=1,
                       AXES_IPWARE_META_PRECEDENCE_ORDER=('REMOTE_ADDR',))
    def test_sin_error_si_no_bloquea_por_ip(self):
        assert axes_puede_leer_la_ip_reenviada(None) == []

    @override_settings(IS_PRODUCTION=False, AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=1,
                       AXES_IPWARE_META_PRECEDENCE_ORDER=('REMOTE_ADDR',))
    def test_sin_error_en_desarrollo(self):
        assert axes_puede_leer_la_ip_reenviada(None) == []

    @override_settings(IS_PRODUCTION=True, AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                       AXES_IPWARE_PROXY_COUNT=1,
                       AXES_CLIENT_IP_CALLABLE='mi.modulo.resolver_ip',
                       AXES_IPWARE_META_PRECEDENCE_ORDER=('REMOTE_ADDR',))
    def test_sin_error_con_resolutor_propio(self):
        """Un AXES_CLIENT_IP_CALLABLE sustituye a ipware entero: no hay nada que exigir."""
        assert axes_puede_leer_la_ip_reenviada(None) == []


class TestIpwareRealmenteInstalado:
    """
    El extra `django-axes[ipware]` es una dependencia REAL, no opcional: sin ella
    axes ignora todos los ajustes AXES_IPWARE_* y resuelve siempre REMOTE_ADDR.
    Si alguien lo quita de requirements.txt, este test lo caza.
    """

    def test_django_ipware_esta_disponible(self):
        import ipware.ip  # noqa: F401

    def test_axes_resuelve_la_ip_del_cliente_tras_un_proxy(self):
        """
        La comprobación de VERDAD: no que los ajustes estén, sino que la resolución
        funcione. Es la que destapó que AXES_IPWARE_PROXY_COUNT era inerte.
        """
        from django.test import RequestFactory

        from axes.helpers import get_client_ip_address

        peticion = RequestFactory().post('/login/')
        peticion.META['REMOTE_ADDR'] = '10.0.1.20'
        peticion.META['HTTP_X_FORWARDED_FOR'] = '203.0.113.45, 10.0.1.20'

        with override_settings(AXES_IPWARE_PROXY_COUNT=1,
                               AXES_IPWARE_META_PRECEDENCE_ORDER=['HTTP_X_FORWARDED_FOR',
                                                                  'REMOTE_ADDR']):
            assert get_client_ip_address(peticion) == '203.0.113.45'

    def test_el_check_detecta_si_alguien_quita_ipware(self):
        """
        La rama que motivó `core.E004`: sin django-ipware, axes ignora todos los
        ajustes AXES_IPWARE_* en silencio. Se simula la ausencia poniendo el módulo
        a None en sys.modules, que hace fallar el import con ImportError.
        """
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {'ipware.ip': None}):
            with override_settings(IS_PRODUCTION=True,
                                   AXES_LOCKOUT_PARAMETERS=POR_USUARIO_E_IP,
                                   AXES_IPWARE_PROXY_COUNT=1,
                                   AXES_IPWARE_META_PRECEDENCE_ORDER=['HTTP_X_FORWARDED_FOR',
                                                                      'REMOTE_ADDR']):
                errores = axes_puede_leer_la_ip_reenviada(None)

        assert len(errores) == 1
        assert errores[0].id == 'core.E004'
        assert 'django-ipware' in errores[0].hint
