"""
Test de la guardia de orden (LIFO) al cancelar.

Si hay dos cambios aprobados sobre el mismo (persona, día), cancelar el MÁS VIEJO debe
bloquearse (revertirlo pisaría al más nuevo). Hay que cancelar primero el más reciente.
"""
import json
from datetime import date, timedelta

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from solicitudes.views.aprobacion_views import CancelarSolicitudView, ResponderCancelacionView
from solicitudes.models import DeudaCorporativa, DobladaDetalle
from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
from solicitudes.tests.test_matriz_dobladas import (
    MatrizDobladasTestCase, FECHA_CESION, FECHA_PAGO,
)


class CancelacionLIFOTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.factory = RequestFactory()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala', activo=True)

        def _emp(username, ced, jor):
            u = User.objects.create_user(username=username, password='x')
            e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
            AsignarJornadaExplorador.objects.create(explorador=e, jornada=jor, fecha_inicio=date(2025, 1, 1))
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
            return e

        self.mariana = _emp('mariana', '1', self.am)
        self.jhon = _emp('jhon', '2', self.pm)
        self.carlos = _emp('carlos', '3', self.pm)

        d = timezone.localdate() + timedelta(days=3)
        while d.weekday() != 2:
            d += timedelta(days=1)
        self.x = d
        # Turnos reales en X (estado "ya aplicado").
        Turno.objects.create(explorador=self.mariana, fecha=self.x, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.jhon, fecha=self.x, jornada=self.pm, sala=self.sala)
        Turno.objects.create(explorador=self.carlos, fecha=self.x, jornada=self.pm, sala=self.sala)

        xi = self.x.isoformat()
        ahora = timezone.now()
        # A: Mariana↔Jhon, aprobada hace 10 min.
        self.A = SolicitudCambio.objects.create(
            explorador_solicitante=self.mariana, explorador_receptor=self.jhon,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.x, estado='aprobada',
            fecha_resolucion=ahora - timedelta(minutes=10), comentario='A',
            snapshot_turnos_previos={
                f"{self.mariana.id}:{xi}": [{'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
                f"{self.jhon.id}:{xi}": [{'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
            })
        # B: Mariana↔Carlos, aprobada hace 2 min (MÁS RECIENTE), comparte Mariana en X.
        self.B = SolicitudCambio.objects.create(
            explorador_solicitante=self.mariana, explorador_receptor=self.carlos,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.x, estado='aprobada',
            fecha_resolucion=ahora - timedelta(minutes=2), comentario='B',
            snapshot_turnos_previos={
                f"{self.mariana.id}:{xi}": [{'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
                f"{self.carlos.id}:{xi}": [{'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
            })

    def _pedir(self, solicitud, quien):
        """El solicitante pide la cancelación. Esto NO cancela: abre la petición."""
        req = self.factory.post(f'/solicitudes/cancelar-solicitud/{solicitud.id}/',
                                {'motivo': 'Me surgió un imprevisto.'})
        req.user = quien.user
        resp = CancelarSolicitudView.as_view()(req, solicitud_id=solicitud.id)
        return resp.status_code, json.loads(resp.content)

    def _responder(self, solicitud, receptor, accion='aprobar'):
        """El receptor responde. Aprobar es lo único que revierte los turnos."""
        req = self.factory.post(f'/solicitudes/cancelar-solicitud/{solicitud.id}/responder/',
                                {'accion': accion, 'comentario_respuesta': 'De acuerdo.'})
        req.user = receptor.user
        resp = ResponderCancelacionView.as_view()(req, solicitud_id=solicitud.id)
        return resp.status_code, json.loads(resp.content)

    def _cancelar(self, solicitud, quien):
        """
        Ciclo completo de cancelación: el solicitante la pide y el receptor la aprueba.

        Las guardias (LIFO, integridad) se comprueban en los DOS pasos, así que un bloqueo
        puede aparecer en cualquiera de ellos; se devuelve el primero que falle.
        """
        code, body = self._pedir(solicitud, quien)
        if code != 200:
            return code, body
        solicitud.refresh_from_db()
        return self._responder(solicitud, solicitud.explorador_receptor)

    def test_la_cancelacion_registra_su_propia_hora(self):
        """
        Cancelar debe dejar la hora REAL de la cancelación, y no puede pisar la de aprobación.

        Antes no se guardaba en ninguna parte: `fecha_resolucion` conservaba la hora de la
        aprobación y el correo de cancelación la mostraba rotulada como "Fecha de Cancelación",
        así que informaba una hora anterior a la real (hasta lo que durase la ventana).
        Y `fecha_resolucion` no se puede reutilizar: de ella se miden el plazo para pedir la
        cancelación y el orden de la guardia LIFO.
        """
        aprobacion = self.B.fecha_resolucion
        antes = timezone.now()

        code, body = self._cancelar(self.B, self.mariana)
        self.assertEqual(code, 200, body)

        self.B.refresh_from_db()
        self.assertIsNotNone(self.B.fecha_cancelacion, 'la cancelación no dejó hora')
        self.assertGreaterEqual(self.B.fecha_cancelacion, antes)
        self.assertEqual(self.B.fecha_resolucion, aprobacion,
                         'la hora de aprobación no puede sobrescribirse: de ella dependen el '
                         'plazo para pedir la cancelación y la guardia LIFO')

    def test_lifo(self):
        # Cancelar A (el viejo) → bloqueado por existir B más reciente sobre Mariana en X.
        code, body = self._cancelar(self.A, self.mariana)
        self.assertEqual(code, 400)
        self.assertEqual(body.get('code'), 'cambio_mas_reciente')
        self.A.refresh_from_db()
        self.assertEqual(self.A.estado, 'aprobada')  # sigue viva

        # Cancelar B (el más reciente) → permitido.
        code, body = self._cancelar(self.B, self.mariana)
        self.assertEqual(code, 200, body)
        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'cancelada')

        # Ahora sí, cancelar A → permitido (ya no hay posteriores aprobadas).
        code, body = self._cancelar(self.A, self.mariana)
        self.assertEqual(code, 200, body)
        self.A.refresh_from_db()
        self.assertEqual(self.A.estado, 'cancelada')


    def test_pedir_cancelacion_no_cancela_nada(self):
        """
        Pedir la cancelación de una APROBADA deja el cambio vigente.

        Es el núcleo del acuerdo: los turnos del receptor ya se movieron con su visto bueno, así
        que el solicitante no puede deshacerlos por su cuenta. Hasta que el receptor responda,
        todo sigue exactamente como estaba.
        """
        code, body = self._pedir(self.B, self.mariana)
        self.assertEqual(code, 200, body)

        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'aprobada', 'el cambio debe seguir vigente')
        self.assertEqual(self.B.cancelacion_estado, 'pendiente')
        self.assertIsNone(self.B.fecha_cancelacion)
        self.assertEqual(self.B.cancelacion_solicitada_por_id, self.mariana.id)

    def test_pedir_cancelacion_sin_motivo_se_rechaza(self):
        """
        El motivo es obligatorio en todas las acciones que mueven turnos.

        Es lo único que le llega al receptor explicando por qué le piden deshacer un cambio
        que ya aceptó, así que se valida en el servidor: quitar el `required` del formulario
        no debe bastar para saltárselo.
        """
        req = self.factory.post(f'/solicitudes/cancelar-solicitud/{self.B.id}/', {'motivo': '   '})
        req.user = self.mariana.user
        resp = CancelarSolicitudView.as_view()(req, solicitud_id=self.B.id)
        body = json.loads(resp.content)

        self.assertEqual(resp.status_code, 400, body)
        self.assertEqual(body.get('code'), 'comentario_requerido')
        self.B.refresh_from_db()
        self.assertFalse(self.B.cancelacion_estado, 'no debe quedar petición abierta')

    def test_responder_cancelacion_sin_comentario_se_rechaza(self):
        """Misma regla para quien responde: aprobar o rechazar exige decir por qué."""
        self._pedir(self.B, self.mariana)

        req = self.factory.post(f'/solicitudes/cancelar-solicitud/{self.B.id}/responder/',
                                {'accion': 'aprobar'})
        req.user = self.B.explorador_receptor.user
        resp = ResponderCancelacionView.as_view()(req, solicitud_id=self.B.id)
        body = json.loads(resp.content)

        self.assertEqual(resp.status_code, 400, body)
        self.assertEqual(body.get('code'), 'comentario_requerido')
        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'aprobada', 'el cambio sigue vigente')

    def test_solo_el_receptor_puede_responder(self):
        """Un tercero no decide sobre un acuerdo que no es suyo."""
        self._pedir(self.B, self.mariana)
        code, body = self._responder(self.B, self.jhon)
        self.assertEqual(code, 403, body)

        self.B.refresh_from_db()
        self.assertEqual(self.B.cancelacion_estado, 'pendiente')

    def test_receptor_rechaza_y_el_cambio_queda_firme(self):
        """
        Rechazar cierra el asunto: el cambio sigue vigente y no se vuelve a pedir.

        Si se pudiera reintentar, el receptor quedaría expuesto a que le insistan hasta que ceda;
        la salida es un cambio nuevo o la cancelación del supervisor.
        """
        self._pedir(self.B, self.mariana)
        code, body = self._responder(self.B, self.carlos, accion='rechazar')
        self.assertEqual(code, 200, body)

        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'aprobada')
        self.assertEqual(self.B.cancelacion_estado, 'rechazada')

        # Y no se puede volver a pedir.
        code, body = self._pedir(self.B, self.mariana)
        self.assertEqual(code, 400, body)
        self.assertEqual(body.get('code'), 'cancelacion_cerrada')

    def test_receptor_aprueba_y_se_revierte(self):
        """Aprobar es lo único que cancela y revierte."""
        self._pedir(self.B, self.mariana)
        code, body = self._responder(self.B, self.carlos)
        self.assertEqual(code, 200, body)

        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'cancelada')
        self.assertEqual(self.B.cancelacion_estado, 'aprobada')
        self.assertEqual(self.B.cancelacion_respondida_por_id, self.carlos.id)

    def test_la_peticion_caduca_si_el_receptor_no_responde(self):
        """
        Pasado el plazo, el silencio del receptor deja el cambio firme.

        Lo contrario —que caducara cancelando— haría que ignorar la notificación le costara el
        turno que había aceptado.
        """
        from core.constants import VENTANA_RESPONDER_CANCELACION_HORAS

        self._pedir(self.B, self.mariana)
        self.B.refresh_from_db()
        SolicitudCambio.objects.filter(id=self.B.id).update(
            cancelacion_solicitada_en=(timezone.now()
                                       - timedelta(hours=VENTANA_RESPONDER_CANCELACION_HORAS + 1))
        )

        code, body = self._responder(self.B, self.carlos)
        self.assertEqual(code, 400, body)

        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'aprobada', 'el cambio queda firme')
        self.assertEqual(self.B.cancelacion_estado, 'caducada')

    def test_no_se_puede_pedir_pasado_el_plazo_del_solicitante(self):
        """El solicitante tiene 24 h desde la aprobación; después es cosa del supervisor."""
        from core.constants import VENTANA_PEDIR_CANCELACION_HORAS

        SolicitudCambio.objects.filter(id=self.B.id).update(
            fecha_resolucion=(timezone.now()
                              - timedelta(hours=VENTANA_PEDIR_CANCELACION_HORAS + 1))
        )
        self.B.refresh_from_db()

        code, body = self._pedir(self.B, self.mariana)
        self.assertEqual(code, 400, body)
        self.assertEqual(body.get('code'), 'ventana_expirada')

        self.B.refresh_from_db()
        self.assertEqual(self.B.cancelacion_estado, '')


class CancelacionDesdeGestionTest(MatrizDobladasTestCase):
    """
    La cancelación del SUPERVISOR desde gestión, con sus cuatro casuísticas.

    Antes solo cambiaba el estado: la solicitud quedaba "cancelada" pero los turnos seguían
    aplicados, así que el horario mostraba un intercambio que ya no existía.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        from empleados.models import CompetenciaEmpleado
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)
        self.uc = CancelarSolicitudUseCase()

    def _doblada_aplicada(self, fecha_cesion=None, fecha_pago=None):
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy
        datos = self._datos(tipo_cambio=self.tipo_doblada)
        if fecha_cesion:
            datos['fecha_cambio_turno'] = str(fecha_cesion)
        if fecha_pago:
            datos['fecha_pago'] = str(fecha_pago)
        strat = DobladaStrategy()
        sol, msg = strat.crear_solicitud(datos)
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related('doblada', 'tipo_cambio').get(id=sol.id)
        ok, m = strat.aplicar_cambios(sol)
        self.assertTrue(ok, m)
        return sol

    def test_pendiente_solo_cambia_el_estado(self):
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy
        sol, msg = DobladaStrategy().crear_solicitud(
            self._datos(tipo_cambio=self.tipo_doblada))
        self.assertIsNotNone(sol, msg)
        ok, m = self.uc.execute_supervisor(sol.id, self.emisor)
        self.assertTrue(ok, m)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'cancelada')

    def test_aprobada_sin_cumplir_revierte_los_turnos(self):
        """El caso que estaba roto: se cancelaba y los turnos se quedaban puestos."""
        sol = self._doblada_aplicada()
        self.assertTrue(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).exists(),
                        'sanity: la doblada debe estar aplicada')

        ok, m = self.uc.execute_supervisor(sol.id, self.emisor)
        self.assertTrue(ok, m)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'cancelada')
        self.assertIn('restaurados', m)
        # El receptor ya no está doblado en la fecha de cesión.
        jornadas = sorted(t.jornada.nombre.upper() for t in
                          Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION)
                          .select_related('jornada'))
        self.assertNotEqual(jornadas, ['AM', 'PM'], 'la doblada debió revertirse')
        # Y no quedan deudas vivas.
        self.assertFalse(DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').exists())

    def test_cumplida_a_medias_se_bloquea(self):
        """
        Un día ya pasó y otro no: revertir borraría lo trabajado y no revertir dejaría el horario
        descuadrado. Se bloquea y se explica la salida.
        """
        sol = self._doblada_aplicada()
        # Simulamos que la cesión ya ocurrió moviéndola al pasado. Hay que limpiar el snapshot:
        # es la fuente preferida de "qué días tocó" y seguiría apuntando a las fechas originales.
        ayer = timezone.localdate() - timedelta(days=1)
        SolicitudCambio.objects.filter(id=sol.id).update(fecha_cambio_turno=ayer)
        sol.doblada.snapshot_turnos_previos = None
        sol.doblada.save(update_fields=['snapshot_turnos_previos'])
        sol.refresh_from_db()

        ok, m = self.uc.execute_supervisor(sol.id, self.emisor)
        self.assertFalse(ok, 'no debe poder cancelarse a medias')
        self.assertIn('ya se cumplió en parte', m)
        self.assertIn('Reprogramar', m)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'aprobada', 'la solicitud debe quedar intacta')

    def test_totalmente_cumplida_se_cancela_sin_reescribir_el_historial(self):
        sol = self._doblada_aplicada()
        ayer = timezone.localdate() - timedelta(days=1)
        anteayer = ayer - timedelta(days=1)
        SolicitudCambio.objects.filter(id=sol.id).update(fecha_cambio_turno=anteayer)
        sol.doblada.fecha_pago = ayer
        sol.doblada.save(update_fields=['fecha_pago'])
        # El snapshot manda sobre las fechas, así que se limpia para que la guardia mire las fechas.
        sol.doblada.snapshot_turnos_previos = None
        sol.doblada.save(update_fields=['snapshot_turnos_previos'])
        sol.refresh_from_db()

        turnos_antes = Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count()
        ok, m = self.uc.execute_supervisor(sol.id, self.emisor)
        self.assertTrue(ok, m)
        self.assertIn('historial', m)
        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'cancelada')
        self.assertEqual(
            Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(), turnos_antes,
            'los días ya trabajados no se tocan')

    def test_respeta_la_guardia_lifo(self):
        """Si hay un cambio más reciente sobre el mismo día, el supervisor tampoco puede pisarlo."""
        sol = self._doblada_aplicada()
        posterior = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, comentario='posterior',
            fecha_cambio_turno=FECHA_CESION, estado='aprobada',
            fecha_resolucion=timezone.now() + timedelta(minutes=5))
        DobladaDetalle.objects.create(
            solicitud=posterior, fecha_pago=FECHA_PAGO, minutos_deuda=30,
            tipo_cesion='cesion_completa', empleado_receptor=self.receptor)

        ok, m = self.uc.execute_supervisor(sol.id, self.emisor)
        self.assertFalse(ok)
        self.assertIn('más reciente', m)

    def test_el_boton_de_gestion_revierte_de_verdad(self):
        """
        Cubre el CABLEADO, no solo el caso de uso: la vista de gestión antes solo cambiaba el
        estado y dejaba los turnos puestos. Se ejerce la vista tal cual la usa el supervisor.
        """
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from solicitudes.views.gestion_solicitudes import GestionCancelarSolicitudView

        sol = self._doblada_aplicada()
        self.assertTrue(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).exists())

        self.emisor.user.is_staff = True
        self.emisor.user.save(update_fields=['is_staff'])

        req = RequestFactory().post(f'/solicitudes/gestion-solicitudes/{sol.id}/cancelar/')
        req.user = self.emisor.user
        req.session = {}
        req._messages = FallbackStorage(req)
        GestionCancelarSolicitudView.as_view()(req, solicitud_id=sol.id)

        sol.refresh_from_db()
        self.assertEqual(sol.estado, 'cancelada')
        jornadas = sorted(t.jornada.nombre.upper() for t in
                          Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION)
                          .select_related('jornada'))
        self.assertNotEqual(jornadas, ['AM', 'PM'],
                            'la vista debe revertir los turnos, no solo marcar el estado')

    def _post_gestion(self, vista, sol_id, next_url=None):
        """Ejerce una vista de gestión como lo hace el supervisor, y devuelve los mensajes."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        self.emisor.user.is_staff = True
        self.emisor.user.save(update_fields=['is_staff'])

        datos = {'next': next_url} if next_url else {}
        req = RequestFactory().post(f'/solicitudes/gestion-solicitudes/{sol_id}/x/', datos)
        req.user = self.emisor.user
        req.session = {}
        req._messages = FallbackStorage(req)
        resp = vista.as_view()(req, solicitud_id=sol_id)
        return resp, [str(m) for m in req._messages]

    def _mover_al_pasado(self, sol):
        """Deja la solicitud enteramente en días ya trabajados."""
        ayer = timezone.localdate() - timedelta(days=1)
        anteayer = ayer - timedelta(days=1)
        SolicitudCambio.objects.filter(id=sol.id).update(fecha_cambio_turno=anteayer)
        sol.doblada.fecha_pago = ayer
        # El snapshot manda sobre las fechas; se limpia para que la guardia mire las fechas.
        sol.doblada.snapshot_turnos_previos = None
        sol.doblada.save(update_fields=['fecha_pago', 'snapshot_turnos_previos'])
        sol.refresh_from_db()

    def test_no_se_puede_eliminar_una_solicitud_ya_trabajada(self):
        """
        Regresión: eliminar destruía lo que cancelar protege. En una solicitud ya cumplida,
        `execute_supervisor` devuelve OK sin revertir (conserva los turnos y deja el registro
        explicándolos), y la vista tomaba ese OK como permiso para BORRAR la fila — los turnos
        se quedaban puestos y sin nada que dijera de dónde salían.
        """
        from solicitudes.views.gestion_solicitudes import GestionEliminarSolicitudView

        sol = self._doblada_aplicada()
        self._mover_al_pasado(sol)
        turnos_antes = Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count()

        _, msgs = self._post_gestion(GestionEliminarSolicitudView, sol.id)

        self.assertTrue(SolicitudCambio.objects.filter(id=sol.id).exists(),
                        'la solicitud que explica esos turnos no puede desaparecer')
        self.assertEqual(
            Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(),
            turnos_antes, 'los días ya trabajados no se tocan')
        self.assertTrue(any('ya se trabajaron' in m for m in msgs), msgs)

    def test_eliminar_una_no_cumplida_revierte_y_borra(self):
        from solicitudes.views.gestion_solicitudes import GestionEliminarSolicitudView

        sol = self._doblada_aplicada()
        self._post_gestion(GestionEliminarSolicitudView, sol.id)

        self.assertFalse(SolicitudCambio.objects.filter(id=sol.id).exists())
        jornadas = sorted(t.jornada.nombre.upper() for t in
                          Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION)
                          .select_related('jornada'))
        self.assertNotEqual(jornadas, ['AM', 'PM'], 'debe revertir antes de borrar')

    def test_cancelar_avisa_a_las_partes_con_el_nombre_del_supervisor(self):
        from solicitudes.models import Notificacion
        from solicitudes.views.gestion_solicitudes import GestionCancelarSolicitudView

        sol = self._doblada_aplicada()
        self._post_gestion(GestionCancelarSolicitudView, sol.id)

        avisos = Notificacion.objects.filter(solicitud=sol, titulo__icontains='supervisor')
        destinatarios = set(avisos.values_list('destinatario_id', flat=True))
        self.assertEqual(destinatarios, {self.emisor.id, self.receptor.id},
                         'ambas partes deben enterarse')
        self.assertIn(self.emisor.nombre, avisos.first().mensaje,
                      'el aviso debe decir QUIÉN lo canceló')

    def test_el_aviso_de_eliminacion_sobrevive_al_borrado(self):
        """El FK a la solicitud es CASCADE: si se vincula, el aviso se borra con ella."""
        from solicitudes.models import Notificacion
        from solicitudes.views.gestion_solicitudes import GestionEliminarSolicitudView

        sol = self._doblada_aplicada()
        self._post_gestion(GestionEliminarSolicitudView, sol.id)

        avisos = Notificacion.objects.filter(titulo__icontains='eliminada')
        self.assertEqual(avisos.count(), 2, 'un aviso por parte, y deben seguir existiendo')
        self.assertIn(f'#{sol.id}', avisos.first().mensaje)
        self.assertIn(self.emisor.nombre, avisos.first().mensaje)

    def test_next_externo_no_saca_de_la_aplicacion(self):
        """`next` lo controla el cliente: sin validar era un open redirect."""
        from solicitudes.views.gestion_solicitudes import GestionCancelarSolicitudView

        sol = self._doblada_aplicada()
        resp, _ = self._post_gestion(GestionCancelarSolicitudView, sol.id,
                                     next_url='https://sitio-externo.example/x')

        self.assertNotIn('sitio-externo', resp['Location'])
        self.assertIn('gestion-solicitudes', resp['Location'])

    def test_next_interno_se_respeta(self):
        from solicitudes.views.gestion_solicitudes import GestionCancelarSolicitudView

        sol = self._doblada_aplicada()
        destino = '/solicitudes/gestion-solicitudes/?estado=aprobada'
        resp, _ = self._post_gestion(GestionCancelarSolicitudView, sol.id, next_url=destino)
        self.assertEqual(resp['Location'], destino)
