"""
Quién puede editar la ficha de un explorador.

La auditoría de la Fase 4 (CSP) encontró que `EmpleadoEditView` solo llevaba
`LoginRequiredMixin`, mientras sus tres vistas hermanas —borrar, crear usuario y
asignar roles— sí llevaban `AdminRequiredMixin`. Con eso, cualquier explorador
con sesión podía hacer POST a /empleados/edit/<id>/ y reescribir la ficha de
cualquier compañero.

Se comprobó ejecutándolo antes de arreglarlo: la petición devolvía 302 y el
nombre de la víctima quedaba con el contenido enviado por el atacante.

Dos daños distintos, y el segundo es el que no se ve:

  1. Directo: cambiar la cédula, el email o el supervisor de otro; o poner su
     `activo` en False y dejarlo fuera del sistema.
  2. Encadenado: el nombre se interpola SIN escapar en varios `innerHTML` del
     formulario de cambio de descanso, así que un nombre con
     `<img src=x onerror=...>` se ejecuta en el navegador de quien abra ese
     formulario. La CSP no lo frena: `script-src` lleva 'unsafe-inline'.

El permiso elegido es "administración y supervisores", que es exactamente lo que
significa `AdminRequiredMixin` en este proyecto (`core/mixins.py`: staff O rol
Supervisor exacto). No se acota al supervisor a su propio equipo porque el resto
del sistema tampoco lo hace: `es_supervisor(user)` da alcance completo en
restricciones, sanciones y consolidado. Acotarlo solo aquí sería una regla nueva
e inconsistente.
"""
from django.test import TestCase
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala

PAYLOAD = '<img src=x onerror=alert(1)>'


class PermisosEdicionEmpleadoTestCase(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.jornada = crear_jornada('AM')
        self.victima = crear_empleado('Vic', 'Tima', jornada=self.jornada, sala=self.sala)

    def _datos(self, nombre='Nuevo'):
        return {
            'nombre': nombre,
            'apellido': 'Tima',
            'cedula': self.victima.cedula,
            'email': self.victima.email or 'v@test.local',
            'activo': 'on',
            'jornada': self.jornada.id,
        }

    def _editar(self, como):
        self.client.force_login(como.user)
        return self.client.post(reverse('empleado_edit', args=[self.victima.id]),
                                self._datos(PAYLOAD))

    def test_un_explorador_no_puede_editar_la_ficha_de_otro(self):
        """El agujero concreto que se cerró. Si esto se pone rojo, volvió."""
        atacante = crear_empleado('Ata', 'Cante', jornada=self.jornada, sala=self.sala)

        r = self._editar(atacante)

        self.assertNotEqual(r.status_code, 302, 'la edición fue aceptada')
        self.victima.refresh_from_db()
        self.assertEqual(self.victima.nombre, 'Vic')

    def test_un_explorador_tampoco_puede_editar_su_propia_ficha(self):
        """
        La cédula, el email y el campo `activo` son datos de administración. Si el
        explorador pudiera tocarlos, además volvería a tener el control de su
        propio nombre, que es lo que llega sin escapar a los `innerHTML`.
        """
        self.client.force_login(self.victima.user)

        self.client.post(reverse('empleado_edit', args=[self.victima.id]),
                         self._datos(PAYLOAD))

        self.victima.refresh_from_db()
        self.assertEqual(self.victima.nombre, 'Vic')

    def test_el_supervisor_si_edita(self):
        """La otra mitad: cerrar la puerta no puede dejar fuera a quien debe entrar."""
        supervisor = crear_empleado('Supi', 'Visor', jornada=self.jornada, sala=self.sala)
        supervisor.user.is_staff = True
        supervisor.user.save()
        self.client.force_login(supervisor.user)

        r = self.client.post(reverse('empleado_edit', args=[self.victima.id]),
                             self._datos('Victoria'))

        self.assertEqual(r.status_code, 302)
        self.victima.refresh_from_db()
        self.assertEqual(self.victima.nombre, 'Victoria')

    def test_sin_sesion_no_se_edita(self):
        r = self.client.post(reverse('empleado_edit', args=[self.victima.id]),
                             self._datos(PAYLOAD))

        self.assertIn(r.status_code, (302, 403))
        self.victima.refresh_from_db()
        self.assertEqual(self.victima.nombre, 'Vic')
        if r.status_code == 302:
            # El login de este proyecto vive en la raíz, no en /login.
            self.assertIn('next=', r.url)
