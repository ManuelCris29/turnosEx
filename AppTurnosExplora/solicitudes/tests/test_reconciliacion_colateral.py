"""
Reconciliación posterior a una cancelación: DÍAS COLATERALES.

Caso real que motivó estos tests (solicitud #584 en desarrollo):

  · CAMBIO DESCANSO (finde) aprobado entre J y M: cesión sábado S1, devolución domingo D0.
    Su aplicación reescribe CUATRO días (los dos findes completos): S1, D1, S0 y D0.
  · D FDS aprobada DESPUÉS entre M y R: M cede el domingo D0 y paga el domingo D1.
    Vive justo en dos de los días colaterales del cambio de descanso.
  · Se aprueba y se cancela una tercera solicitud que solo toca S1 y S0.

Al cancelar la tercera, la reconciliación re-aplicaba el CAMBIO DESCANSO (su cesión cae en S1),
y esa re-aplicación reescribía también D0 y D1 — borrando la D FDS, que seguía aprobada y era
POSTERIOR. Como D0/D1 no estaban en el conjunto de fechas afectadas, nadie la re-materializaba:
pérdida silenciosa.

La corrección cierra el conjunto de fechas afectadas antes de re-aplicar nada, de forma que la
D FDS entra en la reconciliación y se re-aplica después (orden de `fecha_resolucion`).
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio, DobladaDetalle
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from solicitudes.services.cambio_descanso_aplicacion_service import (
    CambioDescansoAplicacionService as CDS,
)
from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService
from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService


def _segundo_sabado_futuro():
    """Segundo sábado de un mes dos meses adelante (deja un finde antes y otro después)."""
    hoy = timezone.localdate()
    anio, mes = hoy.year, hoy.month + 2
    while mes > 12:
        mes -= 12
        anio += 1
    d = date(anio, mes, 1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    return d + timedelta(days=7)


class ReconciliacionColateralTest(TestCase):
    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Rec', activo=True)
        self.t_cd = TipoSolicitudCambio.objects.create(nombre='CAMBIO DESCANSO')
        self.t_fds = TipoSolicitudCambio.objects.create(nombre='D FDS')

        self.j = self._empleado('jei', self.am)   # solicitante del cambio de descanso
        self.m = self._empleado('mar', self.pm)   # receptor del CD y solicitante de la D FDS
        self.r = self._empleado('rec', self.am)   # receptor de la D FDS
        self.h = self._empleado('hon', self.pm)   # tercero de la solicitud cancelada

        # Findes: (S0, D0) y (S1, D1). S1 = sábado de cesión del cambio de descanso.
        self.s1 = _segundo_sabado_futuro()
        self.d1 = self.s1 + timedelta(days=1)
        self.s0 = self.s1 - timedelta(days=7)
        self.d0 = self.s0 + timedelta(days=1)

        ahora = timezone.now()
        # 1) CAMBIO DESCANSO aprobado PRIMERO: J cede S1, devolución D0.
        self.cd = self._solicitud(self.t_cd, self.j, self.m, self.s1, self.d0,
                                  ahora - timedelta(days=10))
        CDS.aplicar(self.cd, self.cd.doblada)

        # 2) D FDS aprobada DESPUÉS: M cede D0 (donde el CD lo hacía trabajar) y paga D1.
        self.fds = self._solicitud(self.t_fds, self.m, self.r, self.d0, self.d1,
                                   ahora - timedelta(days=1))
        DFDSAplicacionService.aplicar(self.fds, self.fds.doblada)

    def _empleado(self, slug, jornada):
        u = User.objects.create_user(username=f'{slug}.rec', password='x')
        e = Empleado.objects.create(user=u, nombre=slug, apellido='Test',
                                    cedula=f'cc-{slug}', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _solicitud(self, tipo, solicitante, receptor, fecha_cesion, fecha_pago, resolucion):
        s = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante, explorador_receptor=receptor,
            tipo_cambio=tipo, comentario='fixture', fecha_cambio_turno=fecha_cesion,
            estado='aprobada', fecha_resolucion=resolucion,
        )
        DobladaDetalle.objects.create(solicitud=s, fecha_pago=fecha_pago, minutos_deuda=0,
                                      tipo_cesion='cesion_completa', empleado_receptor=receptor)
        return SolicitudCambio.objects.select_related('doblada', 'tipo_cambio').get(pk=s.pk)

    def _jornadas(self, empleado, fecha):
        return sorted(t.jornada.nombre.upper() for t in
                      Turno.objects.filter(explorador=empleado, fecha=fecha)
                      .select_related('jornada'))

    def _reconciliar(self):
        """Simula la reconciliación de una cancelación que solo toca S1 y S0 (M y H)."""
        afectados = {(self.m.id, self.s1), (self.h.id, self.s1),
                     (self.m.id, self.s0), (self.h.id, self.s0)}
        DobladaSnapshotService.reconciliar_dobladas_aprobadas(afectados, excluir_solicitud_id=0)

    # ------------------------------------------------------------------ estado inicial
    def test_estado_inicial_es_el_de_la_d_fds(self):
        """La D FDS, al ser posterior, gana los días D0 y D1 (última aprobada gana el día)."""
        self.assertEqual(self._jornadas(self.m, self.d0), [])            # M cede: descansa
        self.assertEqual(self._jornadas(self.r, self.d0), ['AM', 'PM'])  # R cubre
        self.assertEqual(self._jornadas(self.m, self.d1), ['AM', 'PM'])  # M paga
        self.assertEqual(self._jornadas(self.r, self.d1), [])

    # -------------------------------------------------------------------- la regresión
    def test_reconciliacion_conserva_la_d_fds_en_dias_colaterales(self):
        self._reconciliar()

        # Lo que el bug rompía: el CD re-aplicado devolvía a M al trabajo el D0 y borraba su
        # pago del D1, dejando la D FDS aprobada sin efecto en ninguno de sus dos días.
        self.assertEqual(self._jornadas(self.m, self.d0), [],
                         'M debe seguir descansando el día que cedió en la D FDS')
        self.assertEqual(self._jornadas(self.r, self.d0), ['AM', 'PM'],
                         'El receptor de la D FDS debe seguir cubriendo el día cedido')
        self.assertEqual(self._jornadas(self.m, self.d1), ['AM', 'PM'],
                         'El pago de la D FDS no debe desaparecer')
        self.assertEqual(self._jornadas(self.r, self.d1), [])

    def test_reconciliacion_re_materializa_el_cambio_descanso(self):
        """El cambio de descanso sigue vigente donde la D FDS no lo pisa: trabaja S1."""
        self._reconciliar()
        self.assertEqual(self._jornadas(self.m, self.s1), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.j, self.s1), [])

    def test_reconciliacion_no_marca_reemplazada_la_solicitud_vigente(self):
        """Re-aplicar un cambio de descanso no puede cambiar el estado de otras solicitudes."""
        self._reconciliar()
        self.cd.refresh_from_db()
        self.fds.refresh_from_db()
        self.assertEqual(self.cd.estado, 'aprobada')
        self.assertEqual(self.fds.estado, 'aprobada')

    # ------------------------------------------------------------------------ caché de terceros
    def test_reconciliacion_invalida_el_cache_de_los_terceros(self):
        """
        Mis Turnos cachea el mes completo por empleado. La reconciliación reescribe turnos de
        terceros en los días colaterales, así que su mes también hay que invalidarlo: si no, siguen
        viendo el horario anterior hasta que expire el TTL (en desarrollo el caché es de proceso y
        un reinicio lo ocultaba; con Redis en producción, no).
        """
        from core.services.cache_service import CacheService

        claves = {e.id: f'turnos_mes_{e.id}_{self.s1.year}_{self.s1.month:02d}'
                  for e in (self.m, self.r, self.j, self.h)}
        for k in claves.values():
            CacheService.set(k, {'stale': True}, ttl=600)

        self._reconciliar()

        for emp, k in claves.items():
            self.assertIsNone(CacheService.get(k),
                              f'el mes cacheado del explorador {emp} quedó sin invalidar')

    # --------------------------------------------------- el refresco no adopta estados ajenos
    def test_refrescar_resultantes_solo_toca_las_reaplicadas(self):
        """
        Si una solicitud vigente NO se re-materializó, su efecto está roto y su resultante debe
        conservar lo que dejó de verdad. Refrescarlo grababa el estado ROTO como propio, y a partir
        de ahí ni la guardia de integridad ni la auditoría veían la discrepancia (pasó con la #554,
        cuyo resultante acabó afirmando que una D FDS había dejado un turno `CAMBIO DESCANSO`).
        """
        det = self.fds.doblada
        det.snapshot_turnos_resultantes = {f'{self.m.id}:{self.d1.isoformat()}': [
            {'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': 'D FDS'},
            {'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': 'D FDS'}]}
        det.save(update_fields=['snapshot_turnos_resultantes'])
        Turno.objects.filter(explorador=self.m, fecha=self.d1).delete()   # alguien lo pisó

        DobladaSnapshotService.refrescar_resultantes(
            {(self.m.id, self.d1)}, excluir_solicitud_id=0, ids_reaplicadas={self.cd.id})

        det.refresh_from_db()
        self.assertEqual(len(det.snapshot_turnos_resultantes[f'{self.m.id}:{self.d1.isoformat()}']), 2,
                         'el resultante de una solicitud que NO se re-aplicó no debe adoptar el '
                         'estado actual: es justo la discrepancia que hay que poder detectar')

    # ------------------------------------------------------------------ cierre de pares
    def test_cierre_incluye_los_dias_colaterales(self):
        afectados = {(self.m.id, self.s1)}
        cerrado = DobladaSnapshotService._cerrar_afectados(afectados, excluir_solicitud_id=0)
        # El CD aporta sus cuatro días para ambas partes; la D FDS aporta los suyos.
        for esperado in [(self.m.id, self.d0), (self.m.id, self.d1),
                         (self.r.id, self.d0), (self.r.id, self.d1),
                         (self.j.id, self.s1), (self.m.id, self.s0)]:
            self.assertIn(esperado, cerrado)

    # ------------------------------------------------------- orden global de re-aplicación
    def test_una_permanente_vieja_no_gana_el_dia_a_una_d_fds_nueva(self):
        """
        Antes se re-aplicaba en tres bloques (doblada → permanentes → CT) sin orden ENTRE ellos:
        una doblada permanente aprobada antes se re-materializaba DESPUÉS de una D FDS aprobada
        después, y le ganaba el día. La persona volvía a trabajar el día que había cedido mientras
        su sustituto también lo tenía asignado: dos personas en el mismo turno.
        """
        from solicitudes.models import DobladaPermanenteDetalle

        # Doblada permanente VIEJA: M devuelve el favor doblándose el sábado S1 (R descansa).
        s_perm = SolicitudCambio.objects.create(
            explorador_solicitante=self.m, explorador_receptor=self.h,
            tipo_cambio=TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE'),
            comentario='fixture', fecha_cambio_turno=self.s1, estado='aprobada',
            fecha_resolucion=timezone.now() - timedelta(days=30),
        )
        DobladaPermanenteDetalle.objects.create(
            solicitud=s_perm, fecha_inicio=self.s0, fecha_fin=self.s1 + timedelta(days=14),
            dias_cesion='', dias_devolucion='5', fechas_devolucion=self.s1.isoformat(),
            empleado_receptor=self.h,
            snapshot_turnos_previos={f'{self.m.id}:{self.s1.isoformat()}': [],
                                     f'{self.h.id}:{self.s1.isoformat()}': []},
        )
        # D FDS NUEVA: M cede ese mismo sábado S1 a R, que pasa a cubrirlo.
        fds2 = self._solicitud(self.t_fds, self.m, self.r, self.s1, self.s1 + timedelta(days=7),
                               timezone.now())
        DFDSAplicacionService.aplicar(fds2, fds2.doblada)
        self.assertEqual(self._jornadas(self.m, self.s1), [])
        self.assertEqual(self._jornadas(self.r, self.s1), ['AM', 'PM'])

        DobladaSnapshotService.reconciliar_dobladas_aprobadas(
            {(self.m.id, self.s1), (self.h.id, self.s1)}, excluir_solicitud_id=0)

        # Gana la D FDS, que es la última aprobada: M sigue descansando y R sigue cubriendo.
        self.assertEqual(self._jornadas(self.m, self.s1), [],
                         'la doblada permanente (más antigua) no puede recuperar el día cedido')
        self.assertEqual(self._jornadas(self.r, self.s1), ['AM', 'PM'])

    def test_candidatas_ordenadas_por_fecha_de_aprobacion(self):
        """El orden de re-aplicación es uno solo y global, sin importar el modelo de cada tipo."""
        ct = SolicitudCambio.objects.create(
            explorador_solicitante=self.m, explorador_receptor=self.h,
            tipo_cambio=TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO'),
            comentario='fixture', fecha_cambio_turno=self.s1, estado='aprobada',
            fecha_resolucion=timezone.now() - timedelta(days=20),
        )
        orden = DobladaSnapshotService._candidatas_ordenadas(
            {self.s1, self.d0, self.d1}, {self.m.id, self.h.id, self.r.id, self.j.id}, 0)
        ids = [s.id for s in orden]
        self.assertEqual(ids, [s.id for s in sorted(orden, key=lambda x: x.fecha_resolucion)])
        # El CT (hace 20 días) va antes que el cambio de descanso (hace 10) aunque viva en otro
        # modelo y antes se re-aplicara en el último bloque.
        self.assertLess(ids.index(ct.id), ids.index(self.cd.id))
        self.assertLess(ids.index(self.cd.id), ids.index(self.fds.id))

    def test_cierre_no_arrastra_el_otro_lado_de_una_doblada_normal(self):
        """
        Una DOBLADA normal se re-aplica solo por el lado que cae en las fechas afectadas, así que
        su otro lado NO es colateral: meterlo haría que la reconciliación lo re-aplicara y pisara
        cambios ajenos en un día que nadie tocó.
        """
        t_dob = TipoSolicitudCambio.objects.create(nombre='DOBLADA')
        dob = self._solicitud(t_dob, self.h, self.j, self.s1, self.s1 + timedelta(days=14),
                              timezone.now() - timedelta(days=5))
        cerrado = DobladaSnapshotService._cerrar_afectados(
            {(self.h.id, self.s1)}, excluir_solicitud_id=0)
        self.assertNotIn((self.h.id, dob.doblada.fecha_pago), cerrado)
