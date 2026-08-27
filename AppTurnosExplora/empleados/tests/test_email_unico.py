"""
El correo del empleado existe UNA sola vez, en su cuenta.

Antes estaba duplicado en `Empleado.email` y `User.email`, sin nada que los
mantuviera iguales. Se separaban por dos caminos: editar la ficha solo escribía
la copia del `Empleado`, y dar de alta a alguien sobre una cuenta ya existente
dejaba en el `User` el correo de su vida anterior. El efecto era silencioso —
los avisos de solicitudes salían a un buzón y el restablecimiento de contraseña
de Django, que lee del `User`, a otro.

La migración 0010 borró la columna y dejó `Empleado.email` como propiedad. Estas
pruebas fijan la invariante que hace innecesaria cualquier sincronización: no hay
forma de escribir uno sin escribir el otro, porque son el mismo dato.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from empleados.models import Empleado


class EmailUnicoTestCase(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.jornada = crear_jornada('AM')
        self.empleado = crear_empleado('Wal', 'Ter', jornada=self.jornada, sala=self.sala)

    def test_el_email_se_lee_de_la_cuenta(self):
        self.empleado.user.email = 'leido@test.local'
        self.empleado.user.save(update_fields=['email'])
        self.assertEqual(Empleado.objects.get(pk=self.empleado.pk).email, 'leido@test.local')

    def test_asignar_el_email_escribe_en_la_cuenta(self):
        self.empleado.email = 'escrito@test.local'
        self.empleado.user.save(update_fields=['email'])
        self.empleado.user.refresh_from_db()
        self.assertEqual(self.empleado.user.email, 'escrito@test.local')

    def test_ya_no_es_una_columna_de_empleado(self):
        """
        Si alguien vuelve a añadir el campo al modelo, la duplicación regresa y
        con ella el fallo silencioso. Esto se pone rojo antes de que pase.
        """
        columnas = {f.name for f in Empleado._meta.get_fields()}
        self.assertNotIn('email', columnas)

    def test_asignarlo_sin_cuenta_falla_en_vez_de_perderse(self):
        """Aceptar el valor y descartarlo al guardar sería peor que fallar aquí."""
        with self.assertRaises(ValueError):
            Empleado(nombre='Sin', apellido='Cuenta').email = 'x@test.local'

    def test_un_empleado_nuevo_toma_el_email_de_su_cuenta(self):
        cuenta = User.objects.create_user('nuevo.emp', password='x', email='alta@test.local')
        empleado = Empleado.objects.create(
            user=cuenta, nombre='Al', apellido='Ta', cedula='9999123', activo=True)
        self.assertEqual(empleado.email, 'alta@test.local')
