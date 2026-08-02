"""
Tests del CRUD de roles (/empleados/roles/).

Cubren lo que la auditoría detectó: la escalada de privilegios por nombres que
se confundían con "Supervisor", el borrado en cascada que dejaba a la operación
sin supervisores, el renombrado libre de roles estructurales y los duplicados.
"""
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.mixins import es_supervisor
from empleados.forms import RoleForm
from empleados.models import Empleado, EmpleadoRole, Role


class ArranqueEnBDLimpiaTest(TestCase):
    """Producción arranca sin ningún rol creado: el camino que nadie prueba.

    No hereda de RolesBaseTest a propósito — la gracia es que la BD esté vacía.
    Verifica que no hay bloqueo de arranque (para entrar a /roles/ hace falta ser
    supervisor, pero el rol Supervisor todavía no existe) y que crearlo a mano
    con la capitalización real de la BD ('SUPERVISOR') concede permisos.
    """

    def setUp(self):
        self.admin = User.objects.create_user(username='manuel.moreno', password='x', is_staff=True)
        self.client.force_login(self.admin)

    def test_flujo_completo_desde_cero(self):
        # Sin ningún rol en BD, el staff entra igual: es_supervisor() atiende
        # is_staff antes de mirar roles, y por ahí se rompe el huevo y la gallina.
        self.assertFalse(Role.objects.exists())
        self.assertEqual(self.client.get(reverse('roles_list')).status_code, 200)

        resp = self.client.post(reverse('roles_create'), {'nombre': 'SUPERVISOR'}, follow=True)
        self.assertContains(resp, 'creado correctamente')
        rol = Role.objects.get(nombre='SUPERVISOR')

        # Protegido de inmediato pese a la capitalización distinta.
        self.assertTrue(rol.es_protegido)

        user = User.objects.create_user(username='otra.sup', password='x')
        emp = Empleado.objects.create(user=user, nombre='Otra', apellido='Sup',
                                      cedula='123', activo=True)
        EmpleadoRole.objects.create(empleado=emp, role=rol)

        self.assertTrue(es_supervisor(user))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('roles_list')).status_code, 200)


class RolesBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_sup = Role.objects.create(nombre=Role.SUPERVISOR)
        cls.rol_exp = Role.objects.create(nombre=Role.EXPLORADOR)
        user = User.objects.create_user(username='sup', password='x')
        cls.sup = Empleado.objects.create(user=user, nombre='Supervisora',
                                          apellido='Test', cedula='sup', activo=True)
        EmpleadoRole.objects.create(empleado=cls.sup, role=cls.rol_sup)

    def setUp(self):
        self.client.force_login(self.sup.user)

    @staticmethod
    def _empleado_sin_rol(username='otro', cedula='otro'):
        user = User.objects.create_user(username=username, password='x')
        return Empleado.objects.create(user=user, nombre='Otro', apellido='T',
                                       cedula=cedula, activo=True)


class RolePermisoTest(RolesBaseTest):
    def test_rol_parecido_no_concede_permisos(self):
        """El fallo original: el permiso se resolvía con icontains='supervisor'."""
        falso = Role.objects.create(nombre='Sup de sala')
        empleado = self._empleado_sin_rol()
        EmpleadoRole.objects.create(empleado=empleado, role=falso)

        self.assertFalse(es_supervisor(empleado.user))

    def test_rol_supervisor_exacto_concede_permisos(self):
        self.assertTrue(es_supervisor(self.sup.user))

    def test_variante_de_mayusculas_sigue_concediendo_permisos_y_esta_protegida(self):
        """Un rol heredado como "SUPERVISOR" concede acceso: debe estar protegido."""
        # Se escribe por UPDATE porque el unique de MySQL ya es case-insensitive
        # y no deja que convivan "Supervisor" y "SUPERVISOR".
        Role.objects.filter(pk=self.rol_sup.pk).update(nombre='SUPERVISOR')
        self.rol_sup.refresh_from_db()

        self.assertTrue(es_supervisor(self.sup.user))
        self.assertTrue(self.rol_sup.es_protegido)

    def test_duplicado_por_mayusculas_rechazado_en_bd(self):
        with transaction.atomic(), self.assertRaises(IntegrityError):
            Role.objects.create(nombre='SUPERVISOR')

    def test_requiere_permiso(self):
        self.client.logout()
        empleado = self._empleado_sin_rol(username='exp', cedula='exp')
        self.client.force_login(empleado.user)
        resp = self.client.get(reverse('roles_list'))
        self.assertIn(resp.status_code, (302, 403))


class RoleFormTest(RolesBaseTest):
    def test_nombre_ambiguo_rechazado(self):
        """"Supervisor de sala" concedía acceso total con la búsqueda parcial."""
        form = RoleForm(data={'nombre': 'Supervisor de sala'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_nombre_ambiguo_de_explorador_rechazado(self):
        form = RoleForm(data={'nombre': 'Ex-Explorador'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_duplicado_exacto_rechazado(self):
        form = RoleForm(data={'nombre': 'Supervisor'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_duplicado_por_mayusculas_rechazado(self):
        Role.objects.create(nombre='Coordinador')
        form = RoleForm(data={'nombre': 'coordinador'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_nombre_se_normaliza(self):
        form = RoleForm(data={'nombre': '  Coordinador  '})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['nombre'], 'Coordinador')

    def test_nombre_en_blanco_rechazado(self):
        form = RoleForm(data={'nombre': '   '})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_rol_protegido_no_se_renombra(self):
        form = RoleForm(instance=self.rol_sup, data={'nombre': 'Coordinador'})
        self.assertFalse(form.is_valid())
        self.assertIn('nombre', form.errors)

    def test_rol_normal_si_se_renombra(self):
        rol = Role.objects.create(nombre='Coordinador')
        form = RoleForm(instance=rol, data={'nombre': 'Jefe de turno'})
        self.assertTrue(form.is_valid(), form.errors)


class RoleBorradoTest(RolesBaseTest):
    def test_roles_base_no_se_pueden_borrar(self):
        resp = self.client.post(reverse('roles_delete', args=[self.rol_sup.id]), follow=True)
        self.assertTrue(Role.objects.filter(pk=self.rol_sup.pk).exists())
        self.assertContains(resp, 'no se puede eliminar')

    def test_get_de_confirmacion_tambien_bloqueado(self):
        resp = self.client.get(reverse('roles_delete', args=[self.rol_exp.id]), follow=True)
        self.assertRedirects(resp, reverse('roles_list'))
        self.assertTrue(Role.objects.filter(pk=self.rol_exp.pk).exists())

    def test_borrado_no_arrastra_asignaciones(self):
        """El fallo original: borrar el rol borraba en cascada los EmpleadoRole."""
        rol = Role.objects.create(nombre='Coordinador')
        empleado = self._empleado_sin_rol()
        asignacion = EmpleadoRole.objects.create(empleado=empleado, role=rol)

        with self.assertRaises(ProtectedError):
            rol.delete()

        self.assertTrue(EmpleadoRole.objects.filter(pk=asignacion.pk).exists())

    def test_borrado_de_rol_asignado_da_mensaje(self):
        rol = Role.objects.create(nombre='Coordinador')
        empleado = self._empleado_sin_rol()
        EmpleadoRole.objects.create(empleado=empleado, role=rol)

        resp = self.client.post(reverse('roles_delete', args=[rol.id]), follow=True)
        self.assertTrue(Role.objects.filter(pk=rol.pk).exists())
        self.assertContains(resp, 'No se puede eliminar')

    def test_confirmacion_avisa_de_cuantos_empleados_afecta(self):
        rol = Role.objects.create(nombre='Coordinador')
        empleado = self._empleado_sin_rol()
        EmpleadoRole.objects.create(empleado=empleado, role=rol)

        resp = self.client.get(reverse('roles_delete', args=[rol.id]))
        self.assertContains(resp, '1 empleado(s)')

    def test_rol_sin_asignaciones_se_borra(self):
        rol = Role.objects.create(nombre='Coordinador')
        resp = self.client.post(reverse('roles_delete', args=[rol.id]), follow=True)
        self.assertFalse(Role.objects.filter(pk=rol.pk).exists())
        self.assertContains(resp, 'eliminado correctamente')


class RoleVistasTest(RolesBaseTest):
    def test_listado_marca_los_protegidos_y_oculta_acciones(self):
        resp = self.client.get(reverse('roles_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Base')
        self.assertNotContains(resp, reverse('roles_delete', args=[self.rol_sup.id]))
        self.assertNotContains(resp, reverse('roles_edit', args=[self.rol_sup.id]))

    def test_listado_muestra_numero_de_empleados(self):
        resp = self.client.get(reverse('roles_list'))
        self.assertEqual(resp.context['roles'].get(pk=self.rol_sup.pk).num_empleados, 1)
        self.assertEqual(resp.context['roles'].get(pk=self.rol_exp.pk).num_empleados, 0)

    def test_creacion_muestra_mensaje_de_exito(self):
        resp = self.client.post(reverse('roles_create'), {'nombre': 'Coordinador'}, follow=True)
        self.assertContains(resp, 'creado correctamente')
        self.assertTrue(Role.objects.filter(nombre='Coordinador').exists())

    def test_edicion_muestra_mensaje_de_exito(self):
        rol = Role.objects.create(nombre='Coordinador')
        resp = self.client.post(reverse('roles_edit', args=[rol.id]),
                                {'nombre': 'Jefe de turno'}, follow=True)
        self.assertContains(resp, 'actualizado correctamente')
        rol.refresh_from_db()
        self.assertEqual(rol.nombre, 'Jefe de turno')

    def test_errores_del_formulario_se_muestran(self):
        resp = self.client.post(reverse('roles_create'), {'nombre': 'Supervisor de sala'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'se confundiría con el rol base')

    def test_renombrar_protegido_por_url_directa_se_rechaza(self):
        resp = self.client.post(reverse('roles_edit', args=[self.rol_sup.id]),
                                {'nombre': 'Coordinador'})
        self.assertEqual(resp.status_code, 200)
        self.rol_sup.refresh_from_db()
        self.assertEqual(self.rol_sup.nombre, Role.SUPERVISOR)
