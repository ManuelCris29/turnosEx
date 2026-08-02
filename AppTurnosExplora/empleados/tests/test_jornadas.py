"""
Tests del CRUD de jornadas (/empleados/jornadas/).

Cubren lo que la auditoría detectó: el borrado en cascada que arrastraba el
historial de turnos, el renombrado libre que rompía los servicios que buscan
la jornada por nombre literal, los duplicados y el horario incoherente.
"""
from datetime import date

from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from empleados.forms import JornadaForm
from empleados.models import Empleado, EmpleadoRole, Jornada, Role, Sala
from turnos.models import Turno


class JornadasBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_sup = Role.objects.create(nombre='Supervisor')
        user = User.objects.create_user(username='sup', password='x')
        cls.sup = Empleado.objects.create(user=user, nombre='Supervisora',
                                          apellido='Test', cedula='sup', activo=True)
        EmpleadoRole.objects.create(empleado=cls.sup, role=cls.rol_sup)

        cls.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        cls.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')

    def setUp(self):
        self.client.force_login(self.sup.user)


class JornadaFormTest(JornadasBaseTest):
    def test_nombre_duplicado_rechazado(self):
        """Dos 'AM' romperían los Jornada.objects.get(nombre='AM') de los servicios."""
        form = JornadaForm(data={'nombre': 'AM', 'hora_inicio': '07:00', 'hora_fin': '13:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_nombre_libre_rechazado(self):
        """Renombrar a algo distinto de AM/PM dejaría los servicios sin jornada."""
        form = JornadaForm(data={'nombre': 'Maña', 'hora_inicio': '07:00', 'hora_fin': '13:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_hora_fin_anterior_a_inicio_rechazada(self):
        form = JornadaForm(instance=self.am,
                           data={'nombre': 'AM', 'hora_inicio': '14:00', 'hora_fin': '06:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('hora_fin', form.errors)

    def test_horas_iguales_rechazadas(self):
        form = JornadaForm(instance=self.am,
                           data={'nombre': 'AM', 'hora_inicio': '06:00', 'hora_fin': '06:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('hora_fin', form.errors)

    def test_solapamiento_con_otra_jornada_rechazado(self):
        """AM 06:00-16:00 pisaría las dos primeras horas de PM."""
        form = JornadaForm(instance=self.am,
                           data={'nombre': 'AM', 'hora_inicio': '06:00', 'hora_fin': '16:00'})
        self.assertFalse(form.is_valid())
        self.assertIn('hora_inicio', form.errors)

    def test_edicion_valida_aceptada(self):
        form = JornadaForm(instance=self.am,
                           data={'nombre': 'AM', 'hora_inicio': '07:00', 'hora_fin': '14:00'})
        self.assertTrue(form.is_valid(), form.errors)


class JornadaBorradoTest(JornadasBaseTest):
    def test_jornadas_base_no_se_pueden_borrar(self):
        resp = self.client.post(reverse('jornadas_delete', args=[self.am.id]), follow=True)
        self.assertTrue(Jornada.objects.filter(pk=self.am.pk).exists())
        self.assertContains(resp, 'no se puede eliminar')

    def test_get_de_confirmacion_tambien_bloqueado(self):
        resp = self.client.get(reverse('jornadas_delete', args=[self.pm.id]), follow=True)
        self.assertRedirects(resp, reverse('jornadas_list'))
        self.assertTrue(Jornada.objects.filter(pk=self.pm.pk).exists())

    def test_borrado_no_arrastra_turnos(self):
        """El fallo original: borrar la jornada borraba en cascada los turnos."""
        # Se salta el form a propósito (choices no se validan en BD): simula una
        # jornada extra heredada, la única que el sistema permite intentar borrar.
        extra = Jornada.objects.create(nombre='XX', hora_inicio='22:00:00', hora_fin='23:00:00')
        sala = Sala.objects.create(nombre='Sala 1')
        turno = Turno.objects.create(explorador=self.sup, fecha=date(2026, 1, 5),
                                     jornada=extra, sala=sala)

        with self.assertRaises(ProtectedError):
            extra.delete()

        self.assertTrue(Turno.objects.filter(pk=turno.pk).exists())

    def test_borrado_de_jornada_con_turnos_da_mensaje(self):
        extra = Jornada.objects.create(nombre='XX', hora_inicio='22:00:00', hora_fin='23:00:00')
        sala = Sala.objects.create(nombre='Sala 1')
        Turno.objects.create(explorador=self.sup, fecha=date(2026, 1, 5),
                             jornada=extra, sala=sala)

        resp = self.client.post(reverse('jornadas_delete', args=[extra.id]), follow=True)
        self.assertTrue(Jornada.objects.filter(pk=extra.pk).exists())
        self.assertContains(resp, 'No se puede eliminar')


class JornadaVistasTest(JornadasBaseTest):
    def test_listado_marca_las_protegidas_y_oculta_borrar(self):
        resp = self.client.get(reverse('jornadas_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Base')
        self.assertNotContains(resp, reverse('jornadas_delete', args=[self.am.id]))

    def test_edicion_muestra_mensaje_de_exito(self):
        resp = self.client.post(reverse('jornadas_edit', args=[self.am.id]),
                                {'nombre': 'AM', 'hora_inicio': '07:00', 'hora_fin': '14:00'},
                                follow=True)
        self.assertContains(resp, 'actualizada correctamente')
        self.am.refresh_from_db()
        self.assertEqual(self.am.hora_inicio.strftime('%H:%M'), '07:00')

    def test_errores_del_formulario_se_muestran(self):
        resp = self.client.post(reverse('jornadas_edit', args=[self.am.id]),
                                {'nombre': 'AM', 'hora_inicio': '14:00', 'hora_fin': '06:00'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'debe ser posterior')

    def test_requiere_permiso(self):
        self.client.logout()
        user = User.objects.create_user(username='exp', password='x')
        Empleado.objects.create(user=user, nombre='Exp', apellido='T', cedula='exp', activo=True)
        self.client.force_login(user)
        resp = self.client.get(reverse('jornadas_list'))
        self.assertIn(resp.status_code, (302, 403))
