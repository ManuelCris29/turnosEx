"""
Tests de `Empleado.objects.operativos()`: el pool de "companero que cubre".

Es la unica fuente de verdad de quien puede aparecer como candidato en los
formularios de solicitudes. Antes cada camino armaba su propio queryset y solo
uno filtraba algo (`is_staff`), asi que el supervisor sin cuenta de staff salia
como candidato de todos.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from core.mixins import es_supervisor
from empleados.models import Empleado, EmpleadoRole, Role


class EmpleadosOperativosTest(TestCase):

    def _crear(self, username, cedula, activo=True, is_staff=False, is_superuser=False, roles=()):
        user = User.objects.create_user(
            username=username, password='x', is_staff=is_staff, is_superuser=is_superuser
        )
        emp = Empleado.objects.create(
            user=user, nombre=username, apellido='Prueba', cedula=cedula, activo=activo
        )
        for nombre in roles:
            rol, _ = Role.objects.get_or_create(nombre=nombre)
            EmpleadoRole.objects.create(empleado=emp, role=rol)
        return emp

    def test_explorador_normal_esta(self):
        emp = self._crear('explorador', '1', roles=[Role.EXPLORADOR])
        self.assertIn(emp, Empleado.objects.operativos())

    def test_supervisor_por_rol_excluido(self):
        emp = self._crear('sup.rol', '2', roles=[Role.SUPERVISOR])
        self.assertNotIn(emp, Empleado.objects.operativos())

    def test_supervisor_por_rol_en_minusculas_excluido(self):
        # La comparacion es iexact, igual que es_supervisor: si el rol concede
        # permisos de supervisor, tampoco puede ser candidato.
        emp = self._crear('sup.min', '3', roles=['supervisor'])
        self.assertTrue(es_supervisor(emp.user))
        self.assertNotIn(emp, Empleado.objects.operativos())

    def test_staff_excluido(self):
        emp = self._crear('staff', '4', is_staff=True)
        self.assertNotIn(emp, Empleado.objects.operativos())

    def test_superusuario_excluido(self):
        emp = self._crear('root', '5', is_superuser=True)
        self.assertNotIn(emp, Empleado.objects.operativos())

    def test_inactivo_excluido(self):
        emp = self._crear('inactivo', '6', activo=False)
        self.assertNotIn(emp, Empleado.objects.operativos())

    def test_supervisor_de_sala_no_se_excluye(self):
        # "Supervisor de sala" es un explorador normal: no concede permisos
        # (ver Role y test_roles.py) y por tanto tampoco pierde candidatura.
        emp = self._crear('sala', '7', roles=['Supervisor de sala'])
        self.assertFalse(es_supervisor(emp.user))
        self.assertIn(emp, Empleado.objects.operativos())

    def test_sin_duplicados_con_varios_roles(self):
        # El join con EmpleadoRole multiplica filas; sin distinct() el mismo
        # empleado saldria dos veces en el desplegable.
        emp = self._crear('multi', '8', roles=[Role.EXPLORADOR, 'Guia'])
        self.assertEqual(list(Empleado.objects.operativos()).count(emp), 1)
