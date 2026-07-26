"""
Auditoría 2026-07-26: los cinco huecos detectados al contrastar el código con
`PROTECTION_PATTERNS.md` y los principios de dominio.

Cada clase reproduce PRIMERO el fallo concreto (el test falla contra el código anterior)
y luego queda como red de seguridad. Los huecos, en orden de riesgo:

1. La reconciliación (#22) solo cubría 4 de los 6 tipos: CAMBIO TURNO y CT PERMANENTE
   quedaban fuera, y solo se disparaba al revertir una DOBLADA.
2. La guardia LIFO se desactivaba sola cuando la solicitud no tenía snapshot.
3. `reprogramacion_doblada_service` era el único llamador que no usaba el guard
   idempotente de deuda (#21).
4. El estado terminal 'reemplazada' no cancelaba deudas (la señal #23 solo miraba
   'cancelada').
5. Nada impedía que un (explorador, fecha, jornada) activo se duplicara.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado
from solicitudes.models import (
    CambioPermanenteDetalle, DeudaCorporativa, DobladaDetalle,
    SolicitudCambio, TipoSolicitudCambio,
)
from turnos.models import AsignarJornadaExplorador, Jornada, Sala, Turno


def _lunes_futuro(desde_dias=14):
    d = date.today() + timedelta(days=desde_dias)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


class HuecosTestCase(TestCase):
    """Dos exploradores con jornadas contrarias en la misma sala."""

    def setUp(self):
        cache.clear()
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Huecos', activo=True)

        u1 = User.objects.create_user(username='sol.hue', password='x')
        self.solicitante = Empleado.objects.create(
            user=u1, nombre='Sol', apellido='Hue', cedula='95001', activo=True)
        u2 = User.objects.create_user(username='rec.hue', password='x')
        self.receptor = Empleado.objects.create(
            user=u2, nombre='Rec', apellido='Hue', cedula='95002', activo=True)

        AsignarJornadaExplorador.objects.create(
            explorador=self.solicitante, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        AsignarJornadaExplorador.objects.create(
            explorador=self.receptor, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        for e in (self.solicitante, self.receptor):
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)

    def _jornadas(self, empleado, fecha):
        return {t.jornada.nombre.upper() for t in
                Turno.objects.filter(explorador=empleado, fecha=fecha).select_related('jornada')}


# ===========================================================================
# 1. La reconciliación debe cubrir los SEIS tipos, no cuatro
# ===========================================================================
class TestReconciliacionCubreTodosLosTipos(HuecosTestCase):
    """
    `restaurar_turnos_desde_snapshot` borra TODOS los turnos de (explorador, fecha) antes
    de reponer lo guardado. Si en esa fecha vivía un CAMBIO TURNO o un CT PERMANENTE
    aprobado, desaparecía sin que nada lo repusiera: la reconciliación solo conocía
    DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA PERMANENTE.

    El patrón #22 exige que todo tipo con efecto propio esté enganchado aquí.
    """

    def setUp(self):
        super().setUp()
        self.tipo_ct = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')
        self.tipo_ctp = TipoSolicitudCambio.objects.create(nombre='CT PERMANENTE')

    def _ct_aprobado(self, fecha):
        """CAMBIO TURNO aprobado y materializado: cada uno con la jornada del otro."""
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_ct, estado='aprobada', fecha_cambio_turno=fecha,
            fecha_resolucion=timezone.now() - timedelta(minutes=5), comentario='CT vigente',
            snapshot_turnos_previos={
                f"{self.solicitante.id}:{fecha.isoformat()}": [],
                f"{self.receptor.id}:{fecha.isoformat()}": [],
            },
        )
        Turno.objects.create(explorador=self.solicitante, fecha=fecha, jornada=self.pm,
                             sala=self.sala, tipo_cambio='CT')
        Turno.objects.create(explorador=self.receptor, fecha=fecha, jornada=self.am,
                             sala=self.sala, tipo_cambio='CT')
        return sol

    def _ct_permanente_aprobado(self, fecha):
        """CT PERMANENTE aprobado y materializado en `fecha`."""
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_ctp, estado='aprobada', fecha_cambio_turno=fecha,
            fecha_resolucion=timezone.now() - timedelta(minutes=5), comentario='CTP vigente',
            snapshot_turnos_previos={
                f"{self.solicitante.id}:{fecha.isoformat()}": [],
                f"{self.receptor.id}:{fecha.isoformat()}": [],
            },
        )
        CambioPermanenteDetalle.objects.create(
            solicitud=sol, fecha_inicio=fecha, fecha_fin=fecha + timedelta(days=30))
        Turno.objects.create(explorador=self.solicitante, fecha=fecha, jornada=self.pm,
                             sala=self.sala, tipo_cambio='CT PERMANENTE')
        Turno.objects.create(explorador=self.receptor, fecha=fecha, jornada=self.am,
                             sala=self.sala, tipo_cambio='CT PERMANENTE')
        return sol

    def _pisar(self, fecha):
        """Simula el efecto de restaurar el snapshot de otra solicitud: la fecha queda arrasada."""
        Turno.objects.filter(fecha=fecha).delete()

    def test_rematerializa_un_cambio_turno_vigente(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        fecha = _lunes_futuro()
        self._ct_aprobado(fecha)
        self._pisar(fecha)

        DobladaSnapshotService.reconciliar_dobladas_aprobadas(
            {(self.solicitante.id, fecha), (self.receptor.id, fecha)}, excluir_solicitud_id=0)

        self.assertEqual(self._jornadas(self.solicitante, fecha), {'PM'},
                         'el CT vigente debe re-materializarse con la jornada intercambiada')
        self.assertEqual(self._jornadas(self.receptor, fecha), {'AM'})
        self.assertEqual(
            Turno.objects.filter(fecha=fecha, tipo_cambio='CT').count(), 2,
            'los turnos repuestos deben seguir marcados como CT')

    def test_rematerializa_un_ct_permanente_vigente(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        fecha = _lunes_futuro()
        self._ct_permanente_aprobado(fecha)
        self._pisar(fecha)

        DobladaSnapshotService.reconciliar_dobladas_aprobadas(
            {(self.solicitante.id, fecha), (self.receptor.id, fecha)}, excluir_solicitud_id=0)

        self.assertEqual(self._jornadas(self.solicitante, fecha), {'PM'},
                         'el CT permanente vigente debe re-materializarse')
        self.assertEqual(self._jornadas(self.receptor, fecha), {'AM'})
        self.assertEqual(
            Turno.objects.filter(fecha=fecha, tipo_cambio='CT PERMANENTE').count(), 2)

    def test_no_rematerializa_fuera_de_las_fechas_afectadas(self):
        """La reconciliación solo toca las fechas del snapshot que se restauró."""
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        fecha = _lunes_futuro()
        otra = fecha + timedelta(days=7)
        self._ct_aprobado(fecha)
        self._pisar(fecha)

        DobladaSnapshotService.reconciliar_dobladas_aprobadas(
            {(self.solicitante.id, otra), (self.receptor.id, otra)}, excluir_solicitud_id=0)

        self.assertEqual(self._jornadas(self.solicitante, fecha), set(),
                         'no debe reponer nada en una fecha que no estaba afectada')

    def test_no_rematerializa_una_solicitud_ya_cancelada(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        fecha = _lunes_futuro()
        sol = self._ct_aprobado(fecha)
        SolicitudCambio.objects.filter(id=sol.id).update(estado='cancelada')
        self._pisar(fecha)

        DobladaSnapshotService.reconciliar_dobladas_aprobadas(
            {(self.solicitante.id, fecha), (self.receptor.id, fecha)}, excluir_solicitud_id=0)

        self.assertEqual(self._jornadas(self.solicitante, fecha), set(),
                         'una solicitud cancelada no puede revivir en la reconciliación')


class TestTodoRevertQueRestauraSnapshotReconcilia(HuecosTestCase):
    """
    La reconciliación solo se llamaba desde `revertir_doblada_aplicada` (DOBLADA). Los
    revert de D FDS, CAMBIO DESCANSO y DOBLADA PERMANENTE restauraban su snapshot —
    arrasando la fecha— sin reconciliar nada después.
    """

    def setUp(self):
        super().setUp()
        self.tipo_ct = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')

    def _ct_vigente(self, fecha):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_ct, estado='aprobada', fecha_cambio_turno=fecha,
            fecha_resolucion=timezone.now() - timedelta(minutes=5), comentario='CT vigente',
            snapshot_turnos_previos={
                f"{self.solicitante.id}:{fecha.isoformat()}": [],
                f"{self.receptor.id}:{fecha.isoformat()}": [],
            },
        )
        Turno.objects.create(explorador=self.solicitante, fecha=fecha, jornada=self.pm,
                             sala=self.sala, tipo_cambio='CT')
        Turno.objects.create(explorador=self.receptor, fecha=fecha, jornada=self.am,
                             sala=self.sala, tipo_cambio='CT')
        return sol

    def _solicitud_con_snapshot_sobre(self, tipo_nombre, fecha):
        """Solicitud aprobada cuyo snapshot cubre `fecha` (vacío: ese día no tenía nada)."""
        tipo = TipoSolicitudCambio.objects.create(nombre=tipo_nombre)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=tipo, estado='aprobada', fecha_cambio_turno=fecha,
            fecha_resolucion=timezone.now() - timedelta(minutes=2), comentario=tipo_nombre,
        )
        DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=fecha, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor,
            snapshot_turnos_previos={
                f"{self.solicitante.id}:{fecha.isoformat()}": [],
                f"{self.receptor.id}:{fecha.isoformat()}": [],
            },
        )
        return SolicitudCambio.objects.select_related('doblada').get(id=sol.id)

    def test_revertir_d_fds_reconcilia_el_ct_vigente(self):
        from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService

        fecha = _lunes_futuro()
        self._ct_vigente(fecha)
        d_fds = self._solicitud_con_snapshot_sobre('D FDS', fecha)

        DFDSAplicacionService.revertir(d_fds)

        self.assertEqual(self._jornadas(self.solicitante, fecha), {'PM'},
                         'revertir una D FDS no puede borrar un CT vigente del mismo día')

    def test_revertir_cambio_descanso_reconcilia_el_ct_vigente(self):
        from solicitudes.services.cambio_descanso_aplicacion_service import (
            CambioDescansoAplicacionService,
        )

        fecha = _lunes_futuro()
        self._ct_vigente(fecha)
        cd = self._solicitud_con_snapshot_sobre('CAMBIO DESCANSO', fecha)

        CambioDescansoAplicacionService.revertir(cd)

        self.assertEqual(self._jornadas(self.solicitante, fecha), {'PM'},
                         'revertir un cambio de descanso no puede borrar un CT vigente')


# ===========================================================================
# 2. La guardia LIFO no puede desactivarse sola por falta de snapshot
# ===========================================================================
class TestLIFOFallaCerradoSinSnapshot(HuecosTestCase):
    """
    `_pares_afectados` leía únicamente el snapshot. Una solicitud sin snapshot devolvía
    conjunto vacío y el `if mios:` saltaba la guardia entera: se podía cancelar por debajo
    de un cambio más reciente, pisándolo.
    """

    def setUp(self):
        super().setUp()
        self.tipo_ct = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')
        self.fecha = _lunes_futuro()

    def _solicitud(self, minutos_atras, snapshot=None, comentario=''):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_ct, estado='aprobada', fecha_cambio_turno=self.fecha,
            comentario=comentario, snapshot_turnos_previos=snapshot,
        )
        SolicitudCambio.objects.filter(id=sol.id).update(
            fecha_resolucion=timezone.now() - timedelta(minutes=minutos_atras))
        return SolicitudCambio.objects.get(id=sol.id)

    def test_sin_snapshot_no_se_puede_cancelar_bajo_un_cambio_mas_reciente(self):
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

        clave = f"{self.solicitante.id}:{self.fecha.isoformat()}"
        antigua = self._solicitud(10, snapshot=None, comentario='antigua sin snapshot')
        self._solicitud(2, snapshot={clave: []}, comentario='reciente')

        ok, msg = CancelarSolicitudUseCase().execute(antigua.id, self.solicitante)

        self.assertFalse(ok, 'sin snapshot la guardia debe fallar cerrado, no saltarse')
        self.assertIn('más reciente', msg)
        self.assertEqual(SolicitudCambio.objects.get(id=antigua.id).estado, 'aprobada')

    def test_sin_snapshot_y_sin_conflicto_si_se_puede_cancelar(self):
        """Fallar cerrado no puede volverse "bloquear siempre": sin conflicto real, se cancela."""
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

        sola = self._solicitud(10, snapshot=None, comentario='única sobre el día')
        ok, msg = CancelarSolicitudUseCase().execute(sola.id, self.solicitante)

        self.assertTrue(ok, msg)
        self.assertEqual(SolicitudCambio.objects.get(id=sola.id).estado, 'cancelada')

    def test_sin_snapshot_un_cambio_posterior_en_OTRO_dia_no_bloquea(self):
        """El conflicto es por (persona, día): otro día de las mismas personas no cuenta."""
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

        antigua = self._solicitud(10, snapshot=None, comentario='antigua sin snapshot')
        otra_fecha = self.fecha + timedelta(days=7)
        posterior = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_ct, estado='aprobada', fecha_cambio_turno=otra_fecha,
            comentario='reciente en otro día',
            snapshot_turnos_previos={f"{self.solicitante.id}:{otra_fecha.isoformat()}": []},
        )
        SolicitudCambio.objects.filter(id=posterior.id).update(
            fecha_resolucion=timezone.now() - timedelta(minutes=2))

        ok, msg = CancelarSolicitudUseCase().execute(antigua.id, self.solicitante)
        self.assertTrue(ok, msg)


# ===========================================================================
# 3. Reprogramación: la deuda del pago también debe usar el guard idempotente
# ===========================================================================
class TestReprogramacionUsaDeudaIdempotente(HuecosTestCase):
    """
    Era el único llamador que usaba `crear_deuda_corporativa()` cruda en vez de la variante
    idempotente. El patrón #21 dice "usa SIEMPRE las variantes idempotentes": una excepción
    sin motivo es exactamente donde vuelve a colarse el cobro doble.
    """

    def setUp(self):
        super().setUp()
        self.tipo_doblada = TipoSolicitudCambio.objects.create(nombre='DOBLADA')

    def test_no_duplica_la_deuda_del_pago_reprogramado(self):
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService

        fecha = _lunes_futuro()
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=fecha,
            fecha_resolucion=timezone.now(), comentario='doblada origen',
        )

        for _ in range(2):
            DeudaCorporativaService.crear_deuda_corporativa_idempotente(
                explorador=self.receptor, minutos=30, fecha_doblada=fecha,
                solicitud=sol, comentario='Pago reprogramado por inasistencia',
            )

        self.assertEqual(
            DeudaCorporativa.objects.filter(
                explorador=self.receptor, fecha_doblada=fecha,
                solicitud_origen=sol, estado='activa').count(), 1,
            'un día doblado son 30 min, aunque el pago se registre dos veces')

    def test_el_servicio_de_reprogramacion_no_usa_la_variante_cruda(self):
        """Guard de regresión sobre el propio código: que nadie la reintroduzca."""
        import inspect
        from solicitudes.services import reprogramacion_doblada_service as mod

        fuente = inspect.getsource(mod)
        self.assertNotIn(
            'crear_deuda_corporativa(', fuente,
            'usa crear_deuda_corporativa_idempotente(): ver patrón #21 en PROTECTION_PATTERNS.md')


# ===========================================================================
# 4. 'reemplazada' es tan terminal como 'cancelada': tampoco deja deudas vivas
# ===========================================================================
class TestReemplazadaCancelaSusDeudas(HuecosTestCase):
    """
    La señal del patrón #23 filtraba `estado != 'cancelada'`. Pero 'reemplazada' significa
    lo mismo en lo económico: sus turnos fueron pisados por una solicitud posterior. Dejar
    su deuda activa es la misma trampa que motivó el patrón — deuda viva sin doblada real.
    """

    def setUp(self):
        super().setUp()
        self.tipo_cd = TipoSolicitudCambio.objects.create(nombre='CAMBIO DESCANSO')

    def _aprobada_con_deuda(self, fecha):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_cd, estado='aprobada', fecha_cambio_turno=fecha,
            fecha_resolucion=timezone.now(), comentario='con deuda',
        )
        DeudaCorporativa.objects.create(
            explorador=self.receptor, solicitud_origen=sol, minutos=30,
            fecha_doblada=fecha, estado='activa', comentario='30 min por doblar',
        )
        return sol

    def test_al_reemplazar_la_deuda_queda_cancelada(self):
        from solicitudes.domain.estado_machine import transicionar

        fecha = _lunes_futuro()
        sol = self._aprobada_con_deuda(fecha)

        transicionar(sol, 'reemplazada')

        self.assertFalse(
            DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').exists(),
            'una solicitud reemplazada no puede dejar deuda viva')

    def test_reemplazar_una_no_toca_las_deudas_de_otra(self):
        from solicitudes.domain.estado_machine import transicionar

        fecha = _lunes_futuro()
        sol_a = self._aprobada_con_deuda(fecha)
        sol_b = self._aprobada_con_deuda(fecha + timedelta(days=7))

        transicionar(sol_a, 'reemplazada')

        self.assertTrue(
            DeudaCorporativa.objects.filter(solicitud_origen=sol_b, estado='activa').exists(),
            'reemplazar A no puede tocar la deuda de B')


# ===========================================================================
# 5. Un (explorador, fecha, jornada) activo no puede duplicarse
# ===========================================================================
class TestTurnoUnicoPorJornada(HuecosTestCase):
    """
    El invariante "un día = un conjunto de jornadas sin repetir" se sostenía solo por la
    disciplina de delete-then-create repetida en ~15 sitios. Cualquier ruta nueva que cree
    sin borrar duplicaba el turno en silencio, sin que ninguna de las tres capas de defensa
    lo notara. Ahora lo garantiza la base de datos.
    """

    def test_no_permite_dos_turnos_activos_en_la_misma_jornada(self):
        fecha = _lunes_futuro()
        Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                             jornada=self.am, sala=self.sala)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                                     jornada=self.am, sala=self.sala)

    def test_permite_las_dos_jornadas_del_mismo_dia(self):
        """Doblar (AM+PM) es legítimo: la restricción es por jornada, no por día."""
        fecha = _lunes_futuro()
        Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                             jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                             jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        self.assertEqual(self._jornadas(self.solicitante, fecha), {'AM', 'PM'})

    def test_un_anulado_no_bloquea_el_turno_activo_que_lo_sustituye(self):
        """El soft-delete debe convivir con el turno vivo: si no, anular rompería el revert."""
        fecha = _lunes_futuro()
        viejo = Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                                     jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        viejo.anulado = True
        viejo.motivo_anulacion = 'Anulado por reprogramación'
        viejo.save()

        Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                             jornada=self.am, sala=self.sala)

        self.assertEqual(Turno.objects.filter(explorador=self.solicitante, fecha=fecha).count(), 1,
                         'solo el turno activo cuenta')
        self.assertEqual(Turno.all_objects.filter(explorador=self.solicitante, fecha=fecha).count(), 2,
                         'el anulado se conserva para auditoría')

    def test_varios_anulados_pueden_coexistir(self):
        fecha = _lunes_futuro()
        for _ in range(3):
            t = Turno.objects.create(explorador=self.solicitante, fecha=fecha,
                                     jornada=self.pm, sala=self.sala)
            t.anulado = True
            t.save()
        self.assertEqual(Turno.all_objects.filter(explorador=self.solicitante, fecha=fecha).count(), 3)
