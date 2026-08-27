"""
REVERSIÓN al cancelar el permiso de MEDIA JORNADA TEMPORADA.

Es la quinta opción del formulario de Cambio de Día de Descanso, pero NO es una solicitud de
cambio: va por la app `permisos` y tiene su propio camino de cancelación
(`PermisoMediaJornadaCancelView` → `PermisoMediaJornadaService.revertir`). Por eso las pruebas de
reversión de `solicitudes/tests/test_cambio_descanso_revert_semana.py` no la cubren, y hasta ahora
nadie comprobaba que al cancelarla los turnos volvieran a su sitio.

Semana de temporada usada:
    martes -> descansa PM  => el empleado (PM) DESCANSA        -> día de compensación
    jueves -> descansa AM  => el empleado (PM) trabaja COMPLETO -> día de trabajo partido
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado, Jornada, Sala
from permisos.models import PermisoEspecial
from permisos.services import PermisoMediaJornadaService
from turnos.models import AsignarJornadaExplorador, DescansoSemanaManual, Turno


class MediaJornadaRevertTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala MJ', activo=True)

        self.user = User.objects.create_user('mj.revert', password='x')
        self.emp = Empleado.objects.create(user=self.user, nombre='Media', apellido='Revert',
                                           cedula='7702', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.emp, jornada=self.pm,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=self.emp, sala=self.sala)

        hoy = timezone.localdate()
        lunes = hoy + timedelta(days=7 - hoy.weekday() + 7)
        self.f_comp = lunes + timedelta(days=1)     # martes: descansa PM  -> su día libre
        self.f_trabajo = lunes + timedelta(days=3)  # jueves: descansa AM  -> su día completo
        DescansoSemanaManual.objects.create(fecha=self.f_comp, jornada=self.pm, activo=True)
        DescansoSemanaManual.objects.create(fecha=self.f_trabajo, jornada=self.am, activo=True)

        self.client = Client()
        self.client.force_login(self.user)

        # Quien responde la petición de cancelación: `es_supervisor()` acepta is_staff.
        self.user_supervisor = User.objects.create_user('mj.supervisor', password='x', is_staff=True)
        self.client_supervisor = Client()
        self.client_supervisor.force_login(self.user_supervisor)

    # ------------------------------------------------------------------ utils
    def _estado(self):
        return {
            f: sorted((t.jornada.nombre.upper(), t.tipo_cambio or '', t.sala_id)
                      for t in Turno.objects.filter(explorador=self.emp, fecha=f)
                                            .select_related('jornada'))
            for f in (self.f_trabajo, self.f_comp)
        }

    def _crear_aprobado(self):
        permiso = PermisoEspecial.objects.create(
            empleado=self.emp,
            tipo='MEDIA_JORNADA_TEMPORADA',
            fecha_inicio=self.f_trabajo,
            fecha_fin=self.f_trabajo,
            fecha_compensacion=self.f_comp,
            jornada_trabaja='AM',
            especificacion='Prueba de reversión',
            tiempo=0,
            estado='APROBADO',
        )
        PermisoMediaJornadaService.aplicar(permiso)
        return PermisoEspecial.objects.get(pk=permiso.pk)

    def _cancelar(self):
        """
        Ciclo completo: el dueño pide la cancelación y el supervisor la aprueba.

        Un permiso aprobado ya movió turnos, así que el dueño no lo deshace solo: aquí la
        contraparte es el supervisor, porque el permiso no tiene receptor.
        """
        self.client.post(
            reverse('permisos_media_jornada_cancelar', args=[self.permiso.pk]),
            {'motivo': 'Me surgió un imprevisto.'},
        )
        return self.client_supervisor.post(
            reverse('permisos_media_jornada_cancelar_responder', args=[self.permiso.pk]),
            {'accion': 'aprobar', 'comentario': 'De acuerdo.'},
        )

    # ------------------------------------------------------------------ tests
    def test_cancelar_restaura_los_turnos_previos(self):
        # Turnos reales previos: sin ellos el estado de partida está vacío y el test no
        # distinguiría restaurar de simplemente borrar lo creado.
        for jornada in (self.am, self.pm):
            Turno.objects.create(explorador=self.emp, fecha=self.f_trabajo,
                                 jornada=jornada, sala=self.sala)
        previo = self._estado()

        self.permiso = self._crear_aprobado()
        self.assertNotEqual(self._estado(), previo,
                            'Aplicar el permiso no cambió nada: el test no probaría el revert.')

        self._cancelar()
        self.assertEqual(PermisoEspecial.objects.get(pk=self.permiso.pk).estado, 'CANCELADO')
        self.assertEqual(self._estado(), previo,
                         'Los turnos no volvieron a su estado previo al cancelar el permiso.')

    def test_cancelar_no_deja_turnos_de_permiso(self):
        self.permiso = self._crear_aprobado()
        self.assertTrue(Turno.objects.filter(explorador=self.emp, tipo_cambio='PERMISO').exists())
        self._cancelar()
        self.assertFalse(
            Turno.objects.filter(explorador=self.emp, tipo_cambio='PERMISO').exists(),
            'Quedaron turnos de PERMISO tras cancelar: esos días siguen partidos.',
        )

    def test_no_se_puede_cancelar_si_otro_cambio_toco_esos_dias(self):
        """
        La guarda propia de este permiso (`puede_revertir_limpio`) es lo único que lo protege:
        su `revertir` restaura el snapshot sin reconciliar lo colateral, así que si otro cambio
        ya tocó esos días, cancelar los borraría en silencio. Debe bloquearse.
        """
        self.permiso = self._crear_aprobado()
        Turno.objects.filter(explorador=self.emp, fecha=self.f_trabajo).update(tipo_cambio='CT')

        self._cancelar()
        self.assertEqual(PermisoEspecial.objects.get(pk=self.permiso.pk).estado, 'APROBADO',
                         'Debía bloquearse la cancelación: otro cambio ya tocó esos días.')
