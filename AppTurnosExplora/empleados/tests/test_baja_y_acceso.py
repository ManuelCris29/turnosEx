"""Dar de baja a un empleado le CORTA el acceso. Antes no lo hacia.

POR QUE EXISTE ESTE FICHERO
---------------------------
Se descubrio por un sintoma menor: un usuario dado de baja siguio recibiendo
correos de recuperacion de contraseña. Al mirarlo aparecieron dos fallos, y el
segundo es el grave:

  1. `EmpleadoDeleteView` era un `DeleteView` sobre `Empleado`. El OneToOne
     `Empleado.user` cascadea en un solo sentido (User -> Empleado), asi que
     borrar la ficha dejaba la cuenta viva y activa.
  2. `Empleado.activo` NO bloqueaba el acceso. Un empleado marcado como inactivo
     entraba igual y llegaba al dashboard; la casilla solo filtraba listados.

Medicion previa al arreglo, ejecutada contra la base de desarrollo:

    empleado "eliminado"        -> POST /login = 302 /dashboard/, dashboard = 200
    empleado con activo=False   -> POST /login = 302 /dashboard/, dashboard = 200

Los dos caminos terminaban en un acceso concedido. Estos tests son lo que impide
que vuelvan a abrirse: son de control de acceso, no de interfaz, y su valor esta
en que fallen si alguien deshace la sincronizacion de `Empleado.save()`.

Nota: `SERVER_NAME='127.0.0.1'` porque ALLOWED_HOSTS no incluye 'testserver'.
"""
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from empleados.models import Empleado, EmpleadoRole, Role

CLAVE = 'Clave.De.Prueba.1'


@override_settings(AXES_ENABLED=False)
class BaseBaja(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.jornada = crear_jornada('AM')

        self.admin = crear_empleado('Admin', 'Uno', jornada=self.jornada, sala=self.sala)
        self.admin.user.is_staff = True
        self.admin.user.is_superuser = True
        self.admin.user.save()
        rol_admin, _ = Role.objects.get_or_create(nombre='Administrador')
        EmpleadoRole.objects.create(empleado=self.admin, role=rol_admin)

        self.empleado = crear_empleado('Ana', 'Perez', jornada=self.jornada, sala=self.sala)
        self.empleado.user.set_password(CLAVE)
        self.empleado.user.save()

        self.client = self.client_class(SERVER_NAME='127.0.0.1')
        self.client.force_login(self.admin.user)

    def puede_entrar(self, usuario):
        """Intenta un login real y dice si quedo sesion iniciada."""
        cliente = self.client_class(SERVER_NAME='127.0.0.1')
        cliente.post(reverse('login'), {'username': usuario.username, 'password': CLAVE})
        return '_auth_user_id' in cliente.session


class SincronizacionActivoTestCase(BaseBaja):
    """`Empleado.activo` y `User.is_active` no pueden divergir."""

    def test_marcar_la_ficha_inactiva_revoca_el_acceso(self):
        # El fallo original: esta persona entraba igual.
        self.assertTrue(self.puede_entrar(self.empleado.user))

        self.empleado.activo = False
        self.empleado.save()

        self.empleado.user.refresh_from_db()
        self.assertFalse(self.empleado.user.is_active)
        self.assertFalse(self.puede_entrar(self.empleado.user),
                         'un empleado inactivo NO debe poder entrar')

    def test_reactivar_la_ficha_devuelve_el_acceso(self):
        self.empleado.activo = False
        self.empleado.save()

        self.empleado.activo = True
        self.empleado.save()

        self.empleado.user.refresh_from_db()
        self.assertTrue(self.empleado.user.is_active)
        self.assertTrue(self.puede_entrar(self.empleado.user))

    def test_un_empleado_nuevo_inactivo_nace_sin_acceso(self):
        """La sincronizacion tambien vale en el alta, no solo al editar."""
        nuevo = crear_empleado('Baja', 'Directa', activo=False)

        nuevo.user.refresh_from_db()
        self.assertFalse(nuevo.user.is_active)


class BajaEmpleadoTestCase(BaseBaja):
    """La pantalla de baja sustituye a la de eliminar."""

    def url(self):
        return reverse('empleado_baja', args=[self.empleado.id])

    def test_la_baja_corta_el_acceso_y_conserva_la_ficha(self):
        r = self.client.post(self.url())

        self.assertRedirects(r, reverse('empleados'))
        self.empleado.refresh_from_db()
        self.assertFalse(self.empleado.activo)
        self.assertTrue(Empleado.objects.filter(pk=self.empleado.pk).exists(),
                        'la ficha se conserva: el historial no se destruye')
        self.assertTrue(User.objects.filter(pk=self.empleado.user_id).exists(),
                        'la cuenta tampoco se borra, solo se desactiva')
        self.assertFalse(self.puede_entrar(self.empleado.user))

    def test_la_baja_cierra_las_sesiones_ya_abiertas(self):
        """Quien esta dentro en ese momento debe salir, no esperar a reintentar."""
        suya = self.client_class(SERVER_NAME='127.0.0.1')
        suya.force_login(self.empleado.user)
        self.assertEqual(suya.get(reverse('dashboard')).status_code, 200)

        self.client.post(self.url())

        self.assertEqual(suya.get(reverse('dashboard')).status_code, 302)

    def test_un_empleado_de_baja_no_recibe_enlace_de_recuperacion(self):
        """El sintoma por el que se descubrio todo esto."""
        from django.core import mail

        self.empleado.user.email = 'ana.baja@ejemplo.com'
        self.empleado.user.save()
        self.client.post(self.url())
        mail.outbox = []

        publico = self.client_class(SERVER_NAME='127.0.0.1')
        publico.post(reverse('password_reset'), {'email': 'ana.baja@ejemplo.com'})

        self.assertEqual(len(mail.outbox), 0,
                         'PasswordResetForm filtra is_active: sin acceso, sin enlace')

    def test_no_puedo_darme_de_baja_a_mi_mismo(self):
        # Dejaria la pantalla sin administrador y expulsaria a quien pulsa.
        r = self.client.post(reverse('empleado_baja', args=[self.admin.id]))

        self.assertRedirects(r, reverse('empleados'))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.activo)

    def test_un_explorador_no_puede_dar_de_baja_a_nadie(self):
        otro = crear_empleado('Curioso', 'Dos', jornada=self.jornada, sala=self.sala)
        cliente = self.client_class(SERVER_NAME='127.0.0.1')
        cliente.force_login(otro.user)

        r = cliente.post(self.url())

        self.assertIn(r.status_code, (302, 403))
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)


class ReingresoTestCase(BaseBaja):
    """Deshacer una baja sin pasar por /admin/."""

    def test_el_reingreso_devuelve_el_acceso(self):
        self.client.post(reverse('empleado_baja', args=[self.empleado.id]))
        self.assertFalse(self.puede_entrar(self.empleado.user))

        r = self.client.post(reverse('empleado_reingreso', args=[self.empleado.id]))

        self.assertRedirects(r, reverse('empleados'))
        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.activo)
        self.assertTrue(self.puede_entrar(self.empleado.user))

    def test_un_explorador_no_puede_reingresar_a_nadie(self):
        self.client.post(reverse('empleado_baja', args=[self.empleado.id]))
        otro = crear_empleado('Curioso', 'Tres', jornada=self.jornada, sala=self.sala)
        cliente = self.client_class(SERVER_NAME='127.0.0.1')
        cliente.force_login(otro.user)

        r = cliente.post(reverse('empleado_reingreso', args=[self.empleado.id]))

        self.assertIn(r.status_code, (302, 403))
        self.empleado.refresh_from_db()
        self.assertFalse(self.empleado.activo)
