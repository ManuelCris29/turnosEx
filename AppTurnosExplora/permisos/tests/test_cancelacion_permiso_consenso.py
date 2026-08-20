"""
Quién decide la cancelación de un permiso de MEDIA JORNADA TEMPORADA, y desde cuándo corre el plazo.

Un permiso aprobado ya movió turnos, así que su dueño no lo deshace solo: lo PIDE y lo confirma
su supervisor (aquí la contraparte es el supervisor porque el permiso no tiene receptor). Estas
pruebas cubren los tres agujeros que tenía ese control:

- el plazo de 24 h se medía contra `actualizado_en`, que es `auto_now`: cualquier guardado
  posterior reiniciaba el reloj;
- un explorador que además fuera supervisor caía en la rama de cancelación directa y se
  autoaprobaba su propio permiso;
- la respuesta solo exigía tener rol de supervisor, no ser EL supervisor de ese explorador.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado, Jornada, Sala, CompetenciaEmpleado
from core.constants import EstadoCancelacion
from permisos.models import PermisoEspecial
from permisos.services import PermisoMediaJornadaService
from turnos.models import AsignarJornadaExplorador, DescansoSemanaManual, Turno


class CancelacionPermisoConsensoTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala MJC', activo=True)

        self.jefe = self._empleado('mjc.jefe', 'Jefe', '8801', supervisor=None, staff=True)
        self.otro_jefe = self._empleado('mjc.otrojefe', 'Otro', '8802', supervisor=None, staff=True)
        self.emp = self._empleado('mjc.emp', 'Duenno', '8803', supervisor=self.jefe)
        # El jefe también es explorador con turnos: dos pruebas usan un permiso SUYO.
        for empleado in (self.emp, self.jefe):
            AsignarJornadaExplorador.objects.create(explorador=empleado, jornada=self.pm,
                                                    fecha_inicio=date(2025, 1, 1))
            CompetenciaEmpleado.objects.create(empleado=empleado, sala=self.sala)

        hoy = timezone.localdate()
        lunes = hoy + timedelta(days=7 - hoy.weekday() + 7)
        self.f_comp = lunes + timedelta(days=1)     # martes: descansa PM -> su día libre
        self.f_trabajo = lunes + timedelta(days=3)  # jueves: descansa AM -> su día completo
        DescansoSemanaManual.objects.create(fecha=self.f_comp, jornada=self.pm, activo=True)
        DescansoSemanaManual.objects.create(fecha=self.f_trabajo, jornada=self.am, activo=True)

        self.cli_emp = self._cliente(self.emp.user)
        self.cli_jefe = self._cliente(self.jefe.user)
        self.cli_otro = self._cliente(self.otro_jefe.user)

    # ------------------------------------------------------------------ utils
    def _empleado(self, username, nombre, cedula, supervisor, staff=False):
        user = User.objects.create_user(username, password='x', is_staff=staff)
        return Empleado.objects.create(user=user, nombre=nombre, apellido='MJC', cedula=cedula,
                                       activo=True, supervisor=supervisor)

    def _cliente(self, user):
        cli = Client()
        cli.force_login(user)
        return cli

    def _permiso_aprobado(self, empleado=None, supervisor=None):
        permiso = PermisoEspecial.objects.create(
            empleado=empleado or self.emp,
            supervisor=supervisor if supervisor is not None else self.jefe,
            tipo='MEDIA_JORNADA_TEMPORADA',
            fecha_inicio=self.f_trabajo,
            fecha_fin=self.f_trabajo,
            fecha_compensacion=self.f_comp,
            jornada_trabaja='AM',
            especificacion='Prueba de consenso',
            tiempo=0,
            estado='APROBADO',
            fecha_aprobacion=timezone.now(),
        )
        PermisoMediaJornadaService.aplicar(permiso)
        return PermisoEspecial.objects.get(pk=permiso.pk)

    def _pedir(self, cliente, permiso):
        return cliente.post(reverse('permisos_media_jornada_cancelar', args=[permiso.pk]),
                            {'motivo': 'Me surgió un imprevisto.'})

    def _responder(self, cliente, permiso, accion='aprobar'):
        return cliente.post(
            reverse('permisos_media_jornada_cancelar_responder', args=[permiso.pk]),
            {'accion': accion, 'comentario': 'De acuerdo.'},
        )

    # ------------------------------------------------------------------ tests
    def test_el_aviso_del_navegador_es_el_mismo_literal_que_el_del_servidor(self):
        """
        Estos textos estuvieron en tres sitios a la vez —constantes, vistas y plantillas— y se
        desincronizaban al primer retoque: la pantalla decía una cosa y el servidor otra para
        la misma falta. Ahora la plantilla los recibe del contexto; este test lo sujeta.
        """
        from core.utils.comentarios import MSG_COMENTARIO, MSG_MOTIVO

        # Aprobado y pendiente a la vez: el primero muestra el botón de cancelar (motivo) y
        # el segundo los de aprobar/rechazar (comentario). Hacen falta los dos para ver
        # ambos literales en la misma página.
        self._permiso_aprobado()
        PermisoEspecial.objects.create(
            empleado=self.emp, supervisor=self.jefe, tipo='OCASIONAL',
            fecha_inicio=self.f_trabajo, fecha_fin=self.f_trabajo,
            especificacion='Pendiente de resolver', tiempo=0, estado='PENDIENTE',
        )
        html = self.cli_jefe.get(reverse('permisos_especiales_list')).content.decode()

        self.assertIn(f'data-comentario-error="{MSG_COMENTARIO}"', html)
        self.assertIn(f'data-comentario-error="{MSG_MOTIVO}"', html)
        self.assertNotIn('(obligatorio)', html, 'la etiqueta la marca el asterisco, no el texto')

    def test_un_cliente_json_recibe_el_codigo_http_del_fallo(self):
        """
        Estas vistas nacieron como formularios: todo desenlace era un 302 a la lista, así que
        un cliente automatizado no distinguía "comentario vacío" de "cancelación aplicada".
        Quien pide JSON recibe ahora el estado real y un `code`; el navegador sigue con su
        redirect, que es lo que espera al enviar un formulario.
        """
        permiso = self._permiso_aprobado()
        r = self.cli_emp.post(
            reverse('permisos_media_jornada_cancelar', args=[permiso.pk]),
            {'motivo': '  '},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()['code'], 'comentario_requerido')

    def test_el_navegador_sigue_viendo_redirect_y_mensaje(self):
        """La misma falta, desde un formulario normal, no debe romper el flujo de siempre."""
        permiso = self._permiso_aprobado()
        r = self.cli_emp.post(
            reverse('permisos_media_jornada_cancelar', args=[permiso.pk]), {'motivo': '  '}
        )

        self.assertEqual(r.status_code, 302)
        self.assertIn('permisos', r['Location'])

    def test_pedir_cancelacion_sin_motivo_no_abre_la_peticion(self):
        """
        El motivo es obligatorio también aquí, y se valida en el servidor.

        Cancelar un permiso aprobado mueve turnos ya aplicados: el supervisor tiene que
        saber por qué se lo piden, así que un POST sin motivo no debe abrir nada.
        """
        permiso = self._permiso_aprobado()
        self.cli_emp.post(
            reverse('permisos_media_jornada_cancelar', args=[permiso.pk]), {'motivo': '  '}
        )

        permiso.refresh_from_db()
        self.assertNotEqual(permiso.cancelacion_estado, EstadoCancelacion.PENDIENTE)
        self.assertEqual(permiso.estado, 'APROBADO')

    def test_el_plazo_no_se_reinicia_al_guardar_el_permiso(self):
        """
        El plazo cuelga de `fecha_aprobacion`, no de `actualizado_en`.

        Con `actualizado_en` (auto_now) cualquier guardado posterior —un comentario del
        supervisor— devolvía al dueño 24 h nuevas para pedir la cancelación de un permiso
        aprobado hace días.
        """
        permiso = self._permiso_aprobado()
        PermisoEspecial.objects.filter(pk=permiso.pk).update(
            fecha_aprobacion=timezone.now() - timedelta(hours=48)
        )
        # Un guardado cualquiera, muy posterior a la aprobación: refresca `actualizado_en`.
        permiso.refresh_from_db()
        permiso.comentario_supervisor = 'Anotación del supervisor'
        permiso.save()

        self._pedir(self.cli_emp, permiso)

        permiso.refresh_from_db()
        self.assertEqual(permiso.cancelacion_estado, '',
                         'el plazo venció hace 24 h: el guardado no puede reabrirlo')

    def test_el_plazo_corre_desde_la_aprobacion(self):
        """Contrapartida del anterior: dentro de las 24 h, la petición sí se registra."""
        permiso = self._permiso_aprobado()

        self._pedir(self.cli_emp, permiso)

        permiso.refresh_from_db()
        self.assertEqual(permiso.cancelacion_estado, 'pendiente')
        self.assertEqual(permiso.cancelacion_solicitada_por_id, self.emp.id)

    def test_un_supervisor_no_cancela_directo_su_propio_permiso(self):
        """
        Sobre lo propio siempre se PIDE, aunque quien pulse lleve galones.

        Antes la condición miraba el rol (`es_dueno and not es_sup`), así que un explorador que
        además fuera supervisor caía en la cancelación directa y se autoaprobaba.
        """
        permiso = self._permiso_aprobado(empleado=self.jefe, supervisor=self.otro_jefe)

        self._pedir(self.cli_jefe, permiso)

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'APROBADO', 'no puede haberse cancelado solo')
        self.assertEqual(permiso.cancelacion_estado, 'pendiente')

    def test_el_dueno_no_puede_responderse_a_si_mismo(self):
        """La otra mitad de lo anterior: pedir y conceder no pueden ser la misma persona."""
        permiso = self._permiso_aprobado(empleado=self.jefe, supervisor=self.otro_jefe)
        self._pedir(self.cli_jefe, permiso)

        self._responder(self.cli_jefe, permiso)

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'APROBADO')
        self.assertEqual(permiso.cancelacion_estado, 'pendiente', 'sigue esperando a otro')

    def test_solo_responde_el_supervisor_de_ese_explorador(self):
        """
        Tener rol de supervisor no da voz sobre el permiso de cualquiera.

        El aviso se le manda al supervisor concreto, así que la decisión debe ser suya: antes
        bastaba con el rol y cualquier supervisor podía resolver por otro.
        """
        permiso = self._permiso_aprobado()
        self._pedir(self.cli_emp, permiso)

        self._responder(self.cli_otro, permiso)

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'APROBADO')
        self.assertEqual(permiso.cancelacion_estado, 'pendiente')

        # Y su supervisor sí puede.
        self._responder(self.cli_jefe, permiso)

        permiso.refresh_from_db()
        self.assertEqual(permiso.estado, 'CANCELADO')
        self.assertEqual(permiso.cancelacion_estado, 'aprobada')
        self.assertFalse(
            Turno.objects.filter(explorador=self.emp, tipo_cambio='PERMISO').exists(),
            'aprobar la cancelación debe revertir los turnos del permiso',
        )
