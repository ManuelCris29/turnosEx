"""Autoservicio de contraseña: cambiarla desde el menú y recuperarla por correo.

POR QUÉ EXISTE ESTE FICHERO
---------------------------
Ni el login, ni el logout, ni la pantalla de contraseña del administrador tenían
un solo test. Al añadir dos flujos que reparten llaves de cuentas por correo, la
parte que hay que sujetar con tests no es "¿funciona?" sino las decisiones de
seguridad, que son justo las que un refactor bienintencionado deshace sin que
nada se queje:

  * que la respuesta NO delate si una cuenta existe (ni por el mensaje ni por el
    límite de peticiones),
  * que el enlace caduque pronto y sirva UNA sola vez,
  * que el límite de peticiones exista, porque axes no cubre estas pantallas,
  * que cambiar la contraseña expulse a las demás sesiones.

Estilo del repo: `django.test.TestCase` + `self.client`, sin fixtures de pytest
(ver `core/tests/factories.py` para el porqué).

La caché se fija a `locmem` y se vacía en cada `setUp`: los contadores del límite
viven en la caché, y sin limpiarlos un test arrastraría los intentos del
anterior. Con `pytest -n 4` cada worker es un proceso aparte, así que no se pisan.
"""
import re
from datetime import datetime, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.factories import crear_empleado

CACHE_DE_TEST = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-password-autoservicio',
    }
}

CLAVE_VIEJA = 'Clave.Vieja.1'
CLAVE_NUEVA = 'Clave.Nueva.7x'


@override_settings(CACHES=CACHE_DE_TEST, AXES_ENABLED=False)
class BasePassword(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.empleado = crear_empleado('Ana', 'Perez')
        self.user = self.empleado.user
        self.user.email = 'ana.perez@ejemplo.com'
        self.user.set_password(CLAVE_VIEJA)
        self.user.save()

    def enlace_del_correo(self):
        """Extrae la ruta de confirmación del último correo enviado."""
        cuerpo = mail.outbox[-1].body
        encontrado = re.search(r'/password/recuperar/[^/\s]+/[^/\s]+/', cuerpo)
        self.assertIsNotNone(encontrado, f'el correo no traía enlace:\n{cuerpo}')
        return encontrado.group(0)


class CambioPasswordTestCase(BasePassword):
    """Camino de "Cambiar mi contraseña", con la sesión ya iniciada."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_cambia_la_password_con_la_actual_correcta(self):
        r = self.client.post(reverse('password_change'), {
            'old_password': CLAVE_VIEJA,
            'new_password1': CLAVE_NUEVA,
            'new_password2': CLAVE_NUEVA,
        })

        self.assertRedirects(r, reverse('password_change_done'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(CLAVE_NUEVA))

    def test_con_la_actual_incorrecta_no_cambia_nada(self):
        r = self.client.post(reverse('password_change'), {
            'old_password': 'esta-no-es',
            'new_password1': CLAVE_NUEVA,
            'new_password2': CLAVE_NUEVA,
        })

        self.assertEqual(r.status_code, 200, 'debe volver al formulario, no redirigir')
        self.assertIn('old_password', r.context['form'].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(CLAVE_VIEJA))

    def test_sin_sesion_redirige_al_login(self):
        self.client.logout()

        r = self.client.get(reverse('password_change'))

        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse('login'), r['Location'])

    def test_se_avisa_por_correo_de_que_la_password_cambio(self):
        """El aviso es lo único que delata un robo de cuenta al titular."""
        self.client.post(reverse('password_change'), {
            'old_password': CLAVE_VIEJA,
            'new_password1': CLAVE_NUEVA,
            'new_password2': CLAVE_NUEVA,
        })

        from solicitudes.models import EmailOutbox

        self.assertTrue(
            EmailOutbox.objects.filter(destinatarios__icontains=self.user.email).exists(),
            'el aviso debe quedar ENCOLADO (va por el outbox, para que se reintente)',
        )

    def test_cambiar_la_password_cierra_las_demas_sesiones(self):
        """Si cambiar la contraseña no expulsa al intruso, no sirve de nada."""
        otro_dispositivo = self.client_class()
        otro_dispositivo.force_login(self.user)
        self.assertEqual(otro_dispositivo.get(reverse('password_change')).status_code, 200)

        self.client.post(reverse('password_change'), {
            'old_password': CLAVE_VIEJA,
            'new_password1': CLAVE_NUEVA,
            'new_password2': CLAVE_NUEVA,
        })

        r = otro_dispositivo.get(reverse('password_change'))
        self.assertEqual(r.status_code, 302, 'la otra sesión debe haber caído')
        self.assertIn(reverse('login'), r['Location'])

    def test_limita_los_intentos_fallidos(self):
        """axes NO cuenta estos fallos: con una sesión robada se podría probar
        la contraseña actual sin freno."""
        datos = {
            'old_password': 'incorrecta',
            'new_password1': CLAVE_NUEVA,
            'new_password2': CLAVE_NUEVA,
        }
        for _ in range(5):
            self.client.post(reverse('password_change'), datos)

        r = self.client.post(reverse('password_change'), datos)

        self.assertContains(r, 'Demasiados intentos', status_code=200)


class ResetPasswordTestCase(BasePassword):
    """Camino público de "olvidé mi contraseña"."""

    def test_envia_el_enlace_a_un_email_conocido(self):
        r = self.client.post(reverse('password_reset'), {'email': self.user.email})

        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/password/recuperar/', mail.outbox[0].body)

    def test_con_un_email_desconocido_responde_igual_y_no_manda_nada(self):
        """No debe poderse averiguar quién tiene cuenta probando correos."""
        r = self.client.post(reverse('password_reset'), {'email': 'nadie@ejemplo.com'})

        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_el_enlace_permite_fijar_una_password_nueva(self):
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        enlace = self.enlace_del_correo()

        # Django redirige a una URL con el token en sesión antes de mostrar el
        # formulario; hay que seguir esa redirección para poder postear.
        destino = self.client.get(enlace, follow=True).redirect_chain[-1][0]
        r = self.client.post(destino, {
            'new_password1': CLAVE_NUEVA,
            'new_password2': CLAVE_NUEVA,
        })

        self.assertRedirects(r, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(CLAVE_NUEVA))

    def test_el_enlace_no_sirve_dos_veces(self):
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        enlace = self.enlace_del_correo()
        destino = self.client.get(enlace, follow=True).redirect_chain[-1][0]
        self.client.post(destino, {'new_password1': CLAVE_NUEVA, 'new_password2': CLAVE_NUEVA})

        r = self.client.get(enlace, follow=True)

        self.assertContains(r, 'caducado')

    def test_el_enlace_caduca(self):
        """La vida corta del enlace es una decisión de seguridad, no un detalle:
        el defecto de Django son TRES DÍAS, y este test es lo que impide volver a
        ese defecto sin darse cuenta.

        Se adelanta el reloj DEL VALIDADOR (`_now`) en vez de bajar
        `PASSWORD_RESET_TIMEOUT` a 0: la caducidad se mide en segundos enteros, así
        que con timeout 0 el token emitido y comprobado dentro del mismo segundo
        seguiría siendo válido y el test pasaría sin comprobar nada.
        """
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        enlace = self.enlace_del_correo()

        # Naive a propósito: `PasswordResetTokenGenerator._now` devuelve un
        # datetime sin zona y lo resta de otro igual; uno con tzinfo revienta ahí.
        pasado_el_plazo = datetime.now() + timedelta(
            seconds=settings.PASSWORD_RESET_TIMEOUT + 60
        )
        with patch.object(PasswordResetTokenGenerator, '_now', return_value=pasado_el_plazo):
            r = self.client.get(enlace, follow=True)

        self.assertContains(r, 'caducado')

    def test_el_reset_no_lo_bloquea_el_middleware_de_permisos(self):
        """Es una pantalla pública: `PermisoSesionMiddleware` no la gobierna."""
        r = self.client.get(reverse('password_reset'))

        self.assertEqual(r.status_code, 200)

    def test_limita_las_peticiones_sin_delatar_el_limite(self):
        """El hueco que axes deja abierto. Superado el límite, la respuesta debe
        ser IDÉNTICA a la del camino bueno: decir "has excedido el límite"
        revelaría por otra vía lo que Django se cuida de no revelar."""
        for _ in range(3):
            self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertEqual(len(mail.outbox), 3)

        r = self.client.post(reverse('password_reset'), {'email': self.user.email})

        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 3, 'el cuarto correo no debe salir')

    def test_limita_tambien_por_ip_con_emails_distintos(self):
        """Rotar de destinatario no debe saltarse el freno: el límite por IP es
        el que protege la reputación de remitente del dominio."""
        for n in range(5):
            User.objects.create_user(f'otro{n}', email=f'otro{n}@ejemplo.com', password='x')
            self.client.post(reverse('password_reset'), {'email': f'otro{n}@ejemplo.com'})
        self.assertEqual(len(mail.outbox), 5)

        User.objects.create_user('sexto', email='sexto@ejemplo.com', password='x')
        r = self.client.post(reverse('password_reset'), {'email': 'sexto@ejemplo.com'})

        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 5)
