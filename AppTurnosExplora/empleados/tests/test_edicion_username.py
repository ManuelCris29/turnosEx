"""
El `username` y el `email` de la cuenta se corrigen desde la edición del empleado.

Antes no: el formulario es un `ModelForm` de `Empleado` y el `username` vive en
el `User` enlazado, así que un usuario mal escrito al crear el explorador solo
se arreglaba entrando al admin de Django. Ahora el campo se declara a mano y se
persiste sobre el `User` en `save()`.

Lo que estas pruebas fijan es el borde: que se guarde de verdad en la cuenta
(no solo en la ficha), que no se pueda pisar el usuario de otro, y que guardar
sin tocar el campo no se acuse a sí mismo de duplicado.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala


class EdicionUsernameTestCase(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.jornada = crear_jornada('AM')
        self.empleado = crear_empleado('Wal', 'Ter', jornada=self.jornada, sala=self.sala)
        self.admin = crear_empleado('Ad', 'Min', jornada=self.jornada, sala=self.sala)
        self.admin.user.is_staff = True
        self.admin.user.save(update_fields=['is_staff'])
        self.client.force_login(self.admin.user)

    def _post(self, username, email=None):
        return self.client.post(reverse('empleado_edit', args=[self.empleado.id]), {
            'nombre': self.empleado.nombre,
            'apellido': self.empleado.apellido,
            'cedula': self.empleado.cedula,
            'username': username,
            'email': email or self.empleado.email or 'w@test.local',
            'activo': 'on',
            'jornada': self.jornada.id,
        })

    def test_el_campo_llega_precargado_con_el_usuario_actual(self):
        resp = self.client.get(reverse('empleado_edit', args=[self.empleado.id]))
        form = resp.context['form']
        self.assertEqual(
            form.get_initial_for_field(form.fields['username'], 'username'),
            self.empleado.user.username,
        )

    def test_cambiar_el_username_lo_guarda_en_la_cuenta(self):
        self._post('walter.nuevo')
        self.empleado.user.refresh_from_db()
        self.assertEqual(self.empleado.user.username, 'walter.nuevo')

    def test_no_se_puede_tomar_el_username_de_otro(self):
        otro = crear_empleado('Otr', 'Ito', jornada=self.jornada, sala=self.sala)
        anterior = self.empleado.user.username
        resp = self._post(otro.user.username)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('username', resp.context['form'].errors)
        self.empleado.user.refresh_from_db()
        self.assertEqual(self.empleado.user.username, anterior)

    def test_guardar_sin_tocar_el_username_no_se_marca_duplicado(self):
        """Sin excluir el propio User, la comprobación de unicidad se acusaría a sí misma."""
        resp = self._post(self.empleado.user.username)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(User.objects.filter(username=self.empleado.user.username).exists())

    def test_cambiar_el_email_lo_guarda_en_la_cuenta(self):
        """
        El email se edita desde la ficha pero se guarda en la cuenta, que es
        donde vive desde la migracion 0010. Antes habia una copia en
        `Empleado.email` y el restablecimiento de contrasena de Django —que sale
        del `User`— seguia yendo al buzon antiguo.
        """
        self._post(self.empleado.user.username, email='nuevo@test.local')
        self.empleado.refresh_from_db()
        self.empleado.user.refresh_from_db()
        self.assertEqual(self.empleado.user.email, 'nuevo@test.local')
        self.assertEqual(self.empleado.email, 'nuevo@test.local')

    def test_el_campo_email_llega_precargado_desde_la_cuenta(self):
        resp = self.client.get(reverse('empleado_edit', args=[self.empleado.id]))
        form = resp.context['form']
        self.assertEqual(
            form.get_initial_for_field(form.fields['email'], 'email'),
            self.empleado.user.email,
        )
