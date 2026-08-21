"""
Red de seguridad para la RESOLUCIÓN de un permiso especial.

La Fase 3 midió `permisos/views.py` esperando un God Object y encontró otra cosa:
25 vistas de tamaño normal (la mayor, 97 líneas) pero con los caminos de decisión
sin una sola prueba. Al 61 % de cobertura, los tres huecos mayores estaban justo
donde el permiso cambia de estado:

  * `PermisoEspecialAprobarView`       — el supervisor aprueba o rechaza (views.py:311)
  * `PermisoEspecialResolverEmailView` — se resuelve desde el enlace del correo, SIN
                                         sesión iniciada, solo con un token firmado
                                         (views.py:348)

El segundo importa más de lo que parece: es una vía de autorización paralela al
login. Si el token dejara de comprobarse, cualquiera con la URL resolvería
permisos ajenos, y hasta hoy nada lo vigilaba.

Los tests van por el cliente HTTP y no llamando a la vista a mano: la
comprobación de supervisor vive en `_es_supervisor` y el token viaja en la propia
URL, así que invocar el método directamente saltaría lo que se quiere proteger.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from permisos.models import PermisoEspecial
from permisos.services import PermisoNotificacionService


class ResolucionPermisoTestCase(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.supervisor = crear_empleado('Supi', 'Visor', jornada=crear_jornada('AM'),
                                         sala=self.sala)
        self.supervisor.user.is_staff = True
        self.supervisor.user.save()
        self.empleado = crear_empleado('Empe', 'Leado', jornada=crear_jornada('AM'),
                                       sala=self.sala, supervisor=self.supervisor)

    def _permiso(self, **kwargs):
        f = date.today() + timedelta(days=7)
        datos = dict(empleado=self.empleado, tipo='PERSONAL', fecha_inicio=f,
                     fecha_fin=f, tiempo=2, motivo='Cita médica', estado='PENDIENTE')
        datos.update(kwargs)
        return PermisoEspecial.objects.create(**datos)

    # ------------------------------------------------------------- supervisor

    def test_el_supervisor_aprueba_y_queda_registrado_quien_y_cuando(self):
        permiso = self._permiso()
        self.client.force_login(self.supervisor.user)

        r = self.client.post(reverse('permisos_especiales_aprobar', args=[permiso.id]),
                             {'accion': 'aprobar', 'comentario': 'Adelante'})

        self.assertEqual(r.status_code, 302)
        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'APROBADO')
        self.assertEqual(permiso.supervisor, self.supervisor)
        self.assertEqual(permiso.comentario_supervisor, 'Adelante')
        # `fecha_aprobacion` NO es decorativa: de ella cuelga el plazo de 24 h para
        # pedir la cancelación (ver el comentario del propio modelo). Si se quedara
        # en None, la ventana de cancelación se calcularía sobre nada.
        self.assertIsNotNone(permiso.fecha_aprobacion)

    def test_al_rechazar_no_se_sella_fecha_de_aprobacion(self):
        permiso = self._permiso()
        self.client.force_login(self.supervisor.user)

        self.client.post(reverse('permisos_especiales_aprobar', args=[permiso.id]),
                         {'accion': 'rechazar', 'comentario': 'No procede'})

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'RECHAZADO')
        self.assertIsNone(permiso.fecha_aprobacion)

    def test_quien_no_es_supervisor_no_resuelve_nada(self):
        permiso = self._permiso()
        self.client.force_login(self.empleado.user)

        r = self.client.post(reverse('permisos_especiales_aprobar', args=[permiso.id]),
                             {'accion': 'aprobar', 'comentario': 'Me lo apruebo yo'})

        self.assertEqual(r.status_code, 302)  # navegador: mensaje + redirect
        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'PENDIENTE')

    def test_el_comentario_es_obligatorio(self):
        """Una decisión sin motivo escrito deja al explorador sin saber por qué."""
        permiso = self._permiso()
        self.client.force_login(self.supervisor.user)

        self.client.post(reverse('permisos_especiales_aprobar', args=[permiso.id]),
                         {'accion': 'aprobar', 'comentario': '   '})

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'PENDIENTE')

    def test_un_permiso_ya_resuelto_no_se_vuelve_a_resolver(self):
        """
        Sin esto, el supervisor que refresca la página o pulsa dos veces convertiría
        un RECHAZADO en APROBADO sin darse cuenta.
        """
        permiso = self._permiso(estado='RECHAZADO')
        self.client.force_login(self.supervisor.user)

        self.client.post(reverse('permisos_especiales_aprobar', args=[permiso.id]),
                         {'accion': 'aprobar', 'comentario': 'Reconsiderado'})

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'RECHAZADO')

    # ------------------------------------------------------------ desde email

    def _token(self, permiso):
        return PermisoNotificacionService.generar_token(permiso.id, self.supervisor.id)

    def test_el_enlace_del_correo_aprueba_sin_iniciar_sesion(self):
        permiso = self._permiso()

        r = self.client.get(reverse('permisos_especiales_aprobar_email',
                                    args=[permiso.id, self._token(permiso)]))

        self.assertEqual(r.status_code, 200)
        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'APROBADO')
        self.assertEqual(permiso.supervisor, self.supervisor)
        self.assertIsNotNone(permiso.fecha_aprobacion)

    def test_la_misma_url_con_la_ruta_de_rechazo_rechaza(self):
        permiso = self._permiso()

        self.client.get(reverse('permisos_especiales_rechazar_email',
                                args=[permiso.id, self._token(permiso)]))

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'RECHAZADO')

    def test_un_token_invalido_no_resuelve_el_permiso(self):
        """
        El control central de esta vía: es la ÚNICA barrera, porque aquí no hay
        sesión que comprobar.
        """
        permiso = self._permiso()

        r = self.client.get(reverse('permisos_especiales_aprobar_email',
                                    args=[permiso.id, 'token-inventado']))

        self.assertEqual(r.status_code, 403)
        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'PENDIENTE')

    def test_el_token_de_un_permiso_no_sirve_para_otro(self):
        """
        Un token válido, pero ajeno. Si la firma no incluyera el id del permiso, un
        supervisor podría reutilizar su enlace para resolver cualquier otro.
        """
        permiso = self._permiso()
        otro = self._permiso(motivo='Otro asunto')

        r = self.client.get(reverse('permisos_especiales_aprobar_email',
                                    args=[otro.id, self._token(permiso)]))

        self.assertEqual(r.status_code, 403)
        otro.refresh_from_db()
        self.assertEqual(otro.estado, 'PENDIENTE')

    def test_reabrir_el_enlace_no_cambia_lo_ya_resuelto(self):
        """
        Los enlaces del correo se pulsan dos veces a menudo. La segunda vez debe
        mostrar el resultado, no reescribirlo.
        """
        permiso = self._permiso(estado='RECHAZADO')

        r = self.client.get(reverse('permisos_especiales_aprobar_email',
                                    args=[permiso.id, self._token(permiso)]))

        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['ya_resuelto'])
        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'RECHAZADO')
