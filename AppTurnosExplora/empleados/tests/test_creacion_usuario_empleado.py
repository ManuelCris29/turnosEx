"""
Alta de usuario + empleado: la pantalla con la que un administrador crea cuentas.

POR QUE EXISTE ESTE FICHERO
El formulario no tenia NINGUN test. Al medirlo aparecieron cinco caminos rotos:
cuatro terminaban en un 500 por IntegrityError y uno -el peor- respondia
"creados correctamente" habiendo descartado en silencio la contrasena escrita.

Medicion previa al arreglo (`EmpleadoUsuarioForm` sin validar la cuenta):

    A  sin usuario existente y sin username  -> 500  ValueError: The given username must be set
    B  usuario existente + contrasena nueva  -> 302  y check_password(nueva) = False
    C  username repetido                     -> 500  IntegrityError 1062 auth_user.username
    D  usuario existente que YA tiene empleado -> 500 IntegrityError 1062 empleado.user_id
    E  cedula repetida                       -> 500  IntegrityError 1062 empleado.cedula

Las cinco se validan ahora en el formulario, que es donde Django quiere la
validacion entre campos: se responde 200 con el error junto al campo y sin
tocar la base. Las restricciones UNIQUE siguen ahi como ultima defensa.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from empleados.models import Empleado, EmpleadoRole, Role

URL = '/empleados/create_usuario_empleado/'


class BaseAlta(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.jornada = crear_jornada('AM')
        self.admin = crear_empleado('Admin', 'Uno', jornada=self.jornada, sala=self.sala)
        self.admin.user.is_superuser = True
        self.admin.user.is_staff = True
        self.admin.user.save()
        rol_admin, _ = Role.objects.get_or_create(nombre='Administrador')
        EmpleadoRole.objects.create(empleado=self.admin, role=rol_admin)
        self.client.force_login(self.admin.user)
        self.rol, _ = Role.objects.get_or_create(nombre='Explorador')

    def enviar(self, **cambios):
        datos = {
            'nombre': 'Nuevo', 'apellido': 'Empleado', 'cedula': '1122334455',
            'email': 'nuevo@ejemplo.com', 'activo': 'on',
            'roles': [self.rol.id], 'salas': [self.sala.id], 'jornada': self.jornada.id,
            'username': 'nuevo.usuario', 'password': 'Clave.Segura.1',
        }
        datos.update(cambios)
        return self.client.post(URL, datos)

    def errores(self, respuesta):
        return respuesta.context['form'].errors


class AltaCorrectaTestCase(BaseAlta):
    """Los dos caminos buenos siguen funcionando: no se endurece de mas."""

    def test_crea_usuario_nuevo_y_empleado(self):
        r = self.enviar()

        self.assertEqual(r.status_code, 302)
        user = User.objects.get(username='nuevo.usuario')
        self.assertTrue(user.check_password('Clave.Segura.1'),
                        'la contrasena escrita debe quedar realmente guardada')
        self.assertTrue(Empleado.objects.filter(user=user, cedula='1122334455').exists())

    def test_reutiliza_un_usuario_existente_sin_empleado(self):
        # Caso legitimo: la cuenta ya existe (por ejemplo del directorio) y solo
        # falta darle su ficha de empleado.
        u = User.objects.create_user(username='ya.tiene.cuenta', password='LaSuya.1')

        r = self.enviar(usuario_existente=u.id, username='', password='')

        self.assertEqual(r.status_code, 302)
        self.assertTrue(Empleado.objects.filter(user=u).exists())
        u.refresh_from_db()
        self.assertTrue(u.check_password('LaSuya.1'), 'no debe tocarse su contrasena')


class AltaRechazadaTestCase(BaseAlta):
    """Los cinco caminos que antes reventaban o mentian."""

    def _rechaza(self, respuesta, campo):
        self.assertEqual(respuesta.status_code, 200,
                         'debe volver al formulario, no redirigir ni reventar')
        self.assertIn(campo, self.errores(respuesta))

    def test_A_sin_usuario_existente_exige_username_y_password(self):
        # Antes: 500. `User.objects.create_user` lanza ValueError con username vacio.
        r = self.enviar(username='', password='')

        self._rechaza(r, 'username')
        self.assertIn('password', self.errores(r))
        self.assertEqual(Empleado.objects.filter(cedula='1122334455').count(), 0)

    def test_B_usuario_existente_con_contrasena_escrita_NO_se_traga_el_dato(self):
        """
        El fallo mas caro de los cinco, porque no parecia un fallo.

        La vista, si hay usuario existente, ignora username y password por
        completo. El administrador escribia una contrasena, leia "Usuario y
        empleado creados correctamente", y la cuenta conservaba la contrasena
        vieja. Nadie se entera hasta que la persona no puede entrar.

        Ahora se rechaza pidiendo que vacie esos campos: mejor un aviso molesto
        que un exito falso.
        """
        u = User.objects.create_user(username='veterano', password='Vieja.1')

        r = self.enviar(usuario_existente=u.id, username='otro', password='Nueva.2')

        self._rechaza(r, 'username')
        u.refresh_from_db()
        self.assertTrue(u.check_password('Vieja.1'))
        self.assertFalse(u.check_password('Nueva.2'))
        self.assertFalse(Empleado.objects.filter(user=u).exists(),
                         'no debe crearse el empleado con la peticion rechazada')

    def test_C_username_repetido_da_error_de_campo_y_no_IntegrityError(self):
        User.objects.create_user(username='repetido', password='x')

        r = self.enviar(username='repetido')

        self._rechaza(r, 'username')

    def test_D_usuario_existente_que_ya_tiene_empleado(self):
        # Empleado.user es OneToOne: un segundo empleado sobre el mismo usuario
        # rompia la restriccion UNIQUE y salia como 500.
        r = self.enviar(usuario_existente=self.admin.user.id, username='', password='')

        self._rechaza(r, 'usuario_existente')

    def test_E_cedula_repetida_da_error_de_campo_y_no_IntegrityError(self):
        r = self.enviar(cedula=self.admin.cedula)

        self._rechaza(r, 'cedula')
        self.assertFalse(User.objects.filter(username='nuevo.usuario').exists(),
                         'si el alta se rechaza, tampoco debe quedar el usuario suelto')


class NoSeRompeLoQueYaValidabaTestCase(BaseAlta):
    """El clean() anterior exigia sala y jornada a los no supervisores."""

    def test_no_supervisor_sigue_necesitando_sala_y_jornada(self):
        r = self.enviar(salas=[], jornada='')

        self.assertEqual(r.status_code, 200)
        self.assertIn('salas', self.errores(r))
        self.assertIn('jornada', self.errores(r))

    def test_supervisor_sigue_exento_de_sala_y_jornada(self):
        rol_sup, _ = Role.objects.get_or_create(nombre=Role.SUPERVISOR)

        r = self.enviar(roles=[rol_sup.id], salas=[], jornada='')

        self.assertEqual(r.status_code, 302)
