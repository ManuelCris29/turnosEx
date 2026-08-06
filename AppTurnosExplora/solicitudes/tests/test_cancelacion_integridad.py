"""
Guardia de INTEGRIDAD al cancelar: el estado actual debe coincidir con lo que la solicitud dejó.

Revertir consiste en restaurar `snapshot_turnos_previos`, y eso sólo es correcto si nadie tocó
esos días desde la aprobación. La guardia LIFO no basta: sólo mira otras `SolicitudCambio`
aprobadas después, así que no ve los permisos especiales, ni las reprogramaciones, ni las
ediciones manuales/admin.

Caso que lo motivó: A y B hacen un CT. Antes de que A cancele, B cambia su turno por otra vía.
Si A cancela, la restauración escribe sobre B el turno viejo del snapshot —que B ya no tiene— y
quedan dos jornadas en conflicto.

Política: se BLOQUEA (nadie fuerza, ni el supervisor), la solicitud sigue vigente, y la salida es
solicitar un cambio de turno nuevo.
"""
import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
from solicitudes.views.aprobacion_views import CancelarSolicitudView
from turnos.models import AsignarJornadaExplorador, Sala, Turno


class CancelacionIntegridadTest(TestCase):
    """
    Escenario base: CT aprobado entre Mariana (AM) y Jhon (PM) el día X, ya aplicado.

    - `snapshot_turnos_previos`: lo que había ANTES (Mariana AM, Jhon PM).
    - `snapshot_turnos_resultantes`: lo que el CT DEJÓ (Mariana PM, Jhon AM) — lo que la guardia
      compara contra la realidad.
    """

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.factory = RequestFactory()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala', activo=True)
        self.otra_sala = Sala.objects.create(nombre='Otra', activo=True)

        def _emp(username, ced, jor, es_admin=False):
            u = User.objects.create_user(username=username, password='x', is_staff=es_admin)
            e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
            AsignarJornadaExplorador.objects.create(explorador=e, jornada=jor, fecha_inicio=date(2025, 1, 1))
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
            return e

        self.mariana = _emp('mariana', '1', self.am)
        self.jhon = _emp('jhon', '2', self.pm)
        self.supervisor = _emp('super', '9', self.am, es_admin=True)

        d = timezone.localdate() + timedelta(days=3)
        while d.weekday() != 2:
            d += timedelta(days=1)
        self.x = d
        xi = self.x.isoformat()

        # Estado YA APLICADO: el CT intercambió las jornadas.
        self.t_mariana = Turno.objects.create(
            explorador=self.mariana, fecha=self.x, jornada=self.pm, sala=self.sala, tipo_cambio='CT')
        self.t_jhon = Turno.objects.create(
            explorador=self.jhon, fecha=self.x, jornada=self.am, sala=self.sala, tipo_cambio='CT')

        self.solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.mariana, explorador_receptor=self.jhon,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.x, estado='aprobada',
            fecha_resolucion=timezone.now() - timedelta(minutes=5),
            snapshot_turnos_previos={
                f"{self.mariana.id}:{xi}": [{'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
                f"{self.jhon.id}:{xi}": [{'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
            },
            snapshot_turnos_resultantes={
                f"{self.mariana.id}:{xi}": [{'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': 'CT'}],
                f"{self.jhon.id}:{xi}": [{'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': 'CT'}],
            },
        )

    # ------------------------------------------------------------------ helpers
    def _cancelar_explorador(self, quien=None):
        req = self.factory.post(f'/solicitudes/cancelar/{self.solicitud.id}/')
        req.user = (quien or self.mariana).user
        resp = CancelarSolicitudView.as_view()(req, solicitud_id=self.solicitud.id)
        return resp.status_code, json.loads(resp.content)

    def _turnos(self, empleado):
        """Huella comparable de los turnos activos de alguien en X."""
        return {
            (t.jornada.nombre, t.sala_id, t.tipo_cambio)
            for t in Turno.objects.filter(explorador=empleado, fecha=self.x).select_related('jornada')
        }

    def _tocar_turno_de_jhon(self):
        """La contraparte cambia su turno por una vía que la guardia LIFO NO ve."""
        self.t_jhon.jornada = self.pm
        self.t_jhon.tipo_cambio = 'PERMISO'
        self.t_jhon.save()

    # ------------------------------------------------------------------ tests
    def test_caso_base_sin_interferencia_cancela_y_restaura(self):
        """Camino feliz: nadie tocó nada → cancela y restaura el estado previo."""
        code, body = self._cancelar_explorador()

        self.assertEqual(code, 200, body)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'cancelada')
        self.assertEqual(self._turnos(self.mariana), {('AM', self.sala.id, None)})
        self.assertEqual(self._turnos(self.jhon), {('PM', self.sala.id, None)})

    def test_contraparte_cambio_su_turno_bloquea_al_explorador(self):
        """El caso del usuario: Jhon ya no tiene el turno que el CT le dejó → bloqueado."""
        self._tocar_turno_de_jhon()
        antes_mariana, antes_jhon = self._turnos(self.mariana), self._turnos(self.jhon)

        code, body = self._cancelar_explorador()

        self.assertEqual(code, 400)
        self.assertEqual(body.get('code'), 'conflicto_integridad')
        # El mensaje debe nombrar a quién y qué día, y ofrecer la salida.
        self.assertIn('jhon', body['error'].lower())
        self.assertIn(self.x.strftime('%d/%m'), body['error'])
        self.assertIn('nuevo cambio de turno', body['error'])

        # La solicitud sigue VIGENTE y NINGÚN turno se tocó.
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'aprobada')
        self.assertEqual(self._turnos(self.mariana), antes_mariana)
        self.assertEqual(self._turnos(self.jhon), antes_jhon)

    def test_supervisor_tampoco_puede_forzar(self):
        """No hay bypass: forzar reintroduce exactamente el conflicto que se evita."""
        self._tocar_turno_de_jhon()

        ok, msg = CancelarSolicitudUseCase().execute_supervisor(
            self.solicitud.id, self.supervisor)

        self.assertFalse(ok)
        self.assertIn('conflicto de jornadas', msg)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'aprobada')

    def test_cambio_manual_de_sala_tambien_bloquea(self):
        """La comparación es de CONTENIDO: cubre orígenes que no están modelados."""
        self.t_jhon.sala = self.otra_sala
        self.t_jhon.save()

        code, body = self._cancelar_explorador()

        self.assertEqual(code, 400)
        self.assertEqual(body.get('code'), 'conflicto_integridad')

    def test_turno_borrado_por_otra_via_bloquea(self):
        """Si el día quedó vacío, restaurar el snapshot lo reinventaría."""
        self.t_jhon.delete()

        code, body = self._cancelar_explorador()

        self.assertEqual(code, 400)
        self.assertEqual(body.get('code'), 'conflicto_integridad')

    def test_turno_extra_en_el_dia_bloquea(self):
        """Alguien dobló a Jhon: restaurar borraría el día entero y se llevaría la doblada."""
        Turno.objects.create(
            explorador=self.jhon, fecha=self.x, jornada=self.pm, sala=self.sala,
            tipo_cambio='DOBLADA')

        code, body = self._cancelar_explorador()

        self.assertEqual(code, 400)
        self.assertEqual(body.get('code'), 'conflicto_integridad')

    def test_sin_snapshot_resultante_no_bloquea(self):
        """
        Fallback ABIERTO (a propósito, al revés que `_pares_afectados`).

        Las solicitudes anteriores a este mecanismo no tienen resultante. Bloquearlas las
        volvería incancelables en bloque; se quedan con las guardias antiguas.
        """
        SolicitudCambio.objects.filter(pk=self.solicitud.pk).update(snapshot_turnos_resultantes=None)
        self._tocar_turno_de_jhon()

        code, body = self._cancelar_explorador()

        self.assertEqual(code, 200, body)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, 'cancelada')

    def test_orden_de_los_turnos_no_afecta(self):
        """La comparación es por conjuntos: dos turnos el mismo día no dependen del orden."""
        xi = self.x.isoformat()
        Turno.objects.create(
            explorador=self.jhon, fecha=self.x, jornada=self.pm, sala=self.sala, tipo_cambio='CT')
        self.solicitud.snapshot_turnos_resultantes[f"{self.jhon.id}:{xi}"] = [
            {'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': 'CT'},
            {'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': 'CT'},
        ]
        self.solicitud.save(update_fields=['snapshot_turnos_resultantes'])

        self.assertIsNone(CancelarSolicitudUseCase().bloqueo_integridad(self.solicitud))


class CapturaSnapshotResultanteTest(TestCase):
    """
    Cada tipo debe CABLEAR la captura del resultante al aplicar. Sin esto la guardia cae al
    fallback abierto y no protege nada — un fallo silencioso, por eso se testea explícitamente.
    """

    def test_todos_los_aplicadores_capturan_el_resultante(self):
        import inspect

        from solicitudes.services import (
            cambio_descanso_aplicacion_service,
            doblada_permanente_aplicacion_service,
        )
        from solicitudes.services.strategies import (
            cambio_descanso_strategy,
            cambio_turno_strategy,
            ct_permanente_strategy,
            d_fds_strategy,
            doblada_strategy,
        )

        modulos = {
            'CAMBIO TURNO': cambio_turno_strategy,
            'CT PERMANENTE': ct_permanente_strategy,
            'DOBLADA': doblada_strategy,
            'D FDS': d_fds_strategy,
            'CAMBIO DESCANSO': cambio_descanso_strategy,
            'DOBLADA PERMANENTE': doblada_permanente_aplicacion_service,
        }
        sin_captura = [
            tipo for tipo, mod in modulos.items()
            if 'capturar_snapshot_resultante' not in inspect.getsource(mod)
        ]
        self.assertEqual(
            sin_captura, [],
            f'Estos tipos aplican turnos sin capturar el snapshot resultante, así que su '
            f'cancelación no está protegida por la guardia de integridad: {sin_captura}'
        )
        # `cambio_descanso_aplicacion_service` captura desde su strategy (dispatch de sub-flujos).
        self.assertIn('snapshot_turnos_previos',
                      inspect.getsource(cambio_descanso_aplicacion_service))


class SerializadorSnapshotTest(TestCase):
    """
    Previo y resultante DEBEN usar el mismo serializador. Si divergieran, la guardia vería
    conflictos donde no los hay y bloquearía cancelaciones legítimas.
    """

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.sala = Sala.objects.create(nombre='Sala', activo=True)
        u = User.objects.create_user(username='ana', password='x')
        self.ana = Empleado.objects.create(
            user=u, nombre='ana', apellido='X', cedula='7', activo=True)
        self.fecha = timezone.localdate() + timedelta(days=5)
        Turno.objects.create(
            explorador=self.ana, fecha=self.fecha, jornada=self.am, sala=self.sala, tipo_cambio='CT')

    def test_huella_del_use_case_casa_con_el_serializador(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        clave = f"{self.ana.id}:{self.fecha.isoformat()}"
        snap = DobladaSnapshotService.serializar_pares([clave])
        turno = Turno.objects.get(explorador=self.ana, fecha=self.fecha)

        self.assertEqual(
            CancelarSolicitudUseCase._huella_fila(snap[clave][0]),
            CancelarSolicitudUseCase._huella_turno(turno),
        )

    def test_clave_invalida_no_revienta(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        self.assertEqual(DobladaSnapshotService.serializar_pares(['basura', None, '1:no-fecha']), {})


class RefrescarResultantesTest(TestCase):
    """
    Tras reconciliar, los resultantes de las solicitudes vigentes se refrescan — pero SOLO en las
    fechas que la reconciliación realmente reconstruyó.

    Una doblada toca 2-3 días (cesión, pago, devolución en semana) y puede entrar al refresco por
    uno solo de ellos. Recalcular el resultante completo reescribiría también los días intactos:
    una edición externa en el día de pago quedaría adoptada como "lo que la doblada dejó", y al
    cancelar, la guardia no vería conflicto y pisaría ese cambio ajeno en silencio.
    """

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala', activo=True)
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA')

        def _emp(username, ced):
            u = User.objects.create_user(username=username, password='x')
            return Empleado.objects.create(
                user=u, nombre=username, apellido='X', cedula=ced, activo=True)

        self.yesika = _emp('yesika', '11')
        self.andres = _emp('andres', '12')

        hoy = timezone.localdate()
        self.f_cesion = hoy + timedelta(days=7)
        self.f_pago = hoy + timedelta(days=15)

        self.k_cesion = f"{self.andres.id}:{self.f_cesion.isoformat()}"
        self.k_pago = f"{self.andres.id}:{self.f_pago.isoformat()}"

        def _fila(jornada):
            return [{'jornada_nombre': jornada, 'sala_id': self.sala.id, 'tipo_cambio': 'DOBLADA'}]

        self.solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.yesika, explorador_receptor=self.andres,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.f_cesion, estado='aprobada',
            fecha_resolucion=timezone.now() - timedelta(minutes=5),
            snapshot_turnos_previos={self.k_cesion: [], self.k_pago: []},
            snapshot_turnos_resultantes={
                self.k_cesion: _fila('AM'), self.k_pago: _fila('AM')},
        )

        # Estado en BD DISTINTO del resultante en AMBOS días, por causas distintas:
        # - cesión: la reconciliación acaba de reconstruirlo (refresco legítimo).
        # - pago: alguien lo editó por fuera (discrepancia que la guardia DEBE conservar).
        for fecha in (self.f_cesion, self.f_pago):
            Turno.objects.create(explorador=self.andres, fecha=fecha, jornada=self.pm,
                                 sala=self.sala, tipo_cambio='DOBLADA')

    def test_solo_refresca_las_fechas_reconciliadas(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        DobladaSnapshotService.refrescar_resultantes(
            afectados={(self.andres.id, self.f_cesion)}, excluir_solicitud_id=0)

        self.solicitud.refresh_from_db()
        res = self.solicitud.snapshot_turnos_resultantes
        # El día reconciliado se pone al día...
        self.assertEqual(res[self.k_cesion][0]['jornada_nombre'], 'PM')
        # ...y el día que nadie tocó conserva lo que la solicitud dejó de verdad.
        self.assertEqual(
            res[self.k_pago][0]['jornada_nombre'], 'AM',
            'El resultante del día de pago se reescribió con una edición externa: la guardia de '
            'integridad ya no detectaría el conflicto y la cancelación lo pisaría en silencio.')

    def test_la_guardia_sigue_bloqueando_tras_el_refresco(self):
        """Cierre del caso completo: refrescar no debe volver cancelable lo que no lo era."""
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        DobladaSnapshotService.refrescar_resultantes(
            afectados={(self.andres.id, self.f_cesion)}, excluir_solicitud_id=0)

        self.solicitud.refresh_from_db()
        bloqueo = CancelarSolicitudUseCase().bloqueo_integridad(self.solicitud)

        self.assertIsNotNone(bloqueo)
        self.assertIn(self.f_pago.strftime('%d/%m'), bloqueo)
