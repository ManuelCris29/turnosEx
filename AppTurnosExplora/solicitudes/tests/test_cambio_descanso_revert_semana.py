"""
REVERSIÓN al cancelar, para las opciones de CAMBIO DESCANSO de ENTRE SEMANA (temporada).

Por qué existe este archivo: el único revert de CAMBIO DESCANSO que estaba cubierto era el de
FIN DE SEMANA (`test_cambio_descanso.py::CDAplicacionTest::test_revert_restaura_estado_previo`).
Las cuatro sub-modalidades de entre semana no tenían ni una prueba de cancelación, y cada una se
aplica con una función distinta (`aplicar_entre_semana`, `aplicar_semana_jornadas_partidas`,
`aplicar_semana_cobertura`, `aplicar_semana_cambio_doblada`) aunque todas compartan el mismo
`revertir`. Podían romperse en silencio.

Qué se fija aquí:
  1. Tras cancelar, los turnos de AMBOS exploradores vuelven EXACTAMENTE al estado previo — no
     solo la jornada: también el `tipo_cambio` y la sala (restaurar 'AM' pero con el tipo_cambio
     equivocado dejaría el día contando como un cambio que ya no existe).
  2. Se cancela por la PUERTA REAL (`CancelarSolicitudUseCase.execute`), no llamando a
     `revertir()` a mano: así se ejercitan también la ventana de 30 min, `bloqueo_lifo` y
     `bloqueo_integridad`, que es el camino que recorre el usuario desde la pantalla.
  3. La regla de los 30 minutos en temporada: el día COMPLETO de temporada NO genera deuda (quien
     lo trabaja ya parte de AM+PM, no dobla sobre su jornada). De las cuatro opciones, SOLO
     `cobertura_misma_semana` puede generarla, y al cancelar debe quedar anulada.
     Ver `docs/05-referencia/solicitudes/REGLAS_NEGOCIO_SOLICITUDES.md:578,590`.

La semana de prueba (temporada) queda así:
    martes  -> descansa PM  => el solicitante (PM) DESCANSA ; el receptor (AM) trabaja COMPLETO
    jueves  -> descansa AM  => el receptor (AM) DESCANSA    ; el solicitante (PM) trabaja COMPLETO
    miércoles -> día normal => cada uno su jornada base (AM el receptor, PM el solicitante)

OJO con las fechas, que no son las mismas en todas las opciones:
  - `intercambio_dia` intercambia los DESCANSOS  -> cesión = martes (mi descanso).
  - las otras tres parten de mi DÍA COMPLETO     -> cesión = jueves.
"""
from datetime import timedelta

from django.utils import timezone

from solicitudes.models import SolicitudCambio, DeudaCorporativa
from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
from solicitudes.tests.helpers_cancelacion import cancelar_con_acuerdo
from turnos.models import Turno, DescansoSemanaManual

from .test_cambio_descanso import CDBaseTest


class CDSemanaRevertBase(CDBaseTest):
    """Semana de temporada futura + utilidades para comparar el estado antes/después."""

    def setUp(self):
        super().setUp()
        hoy = timezone.localdate()
        # Lunes de la semana siguiente a la próxima: siempre futuro, aunque hoy sea viernes.
        lunes = hoy + timedelta(days=7 - hoy.weekday() + 7)
        self.d_desc_sol = lunes + timedelta(days=1)   # martes: descansa PM (el solicitante)
        self.d_normal = lunes + timedelta(days=2)     # miércoles: día corriente de la semana
        self.d_desc_rec = lunes + timedelta(days=3)   # jueves: descansa AM (el receptor)
        DescansoSemanaManual.objects.create(fecha=self.d_desc_sol, jornada=self.pm, activo=True)
        DescansoSemanaManual.objects.create(fecha=self.d_desc_rec, jornada=self.am, activo=True)

    # ---------------------------------------------------------------- helpers
    def _turnos_reales(self, emp, fecha, jornadas, tipo_cambio=None):
        """
        Deja a `emp` con filas `Turno` REALES en `fecha` (por defecto sin `tipo_cambio`, como un
        horario importado).

        Hace falta para que el test DISCRIMINE. En una semana de temporada limpia no hay filas
        `Turno`: el estado es virtual. Con el estado previo vacío, restaurar el snapshot y el
        camino de respaldo de `revertir` (borrar los turnos 'CAMBIO DESCANSO') dan el mismo
        resultado, así que el test pasaría aunque la restauración estuviera rota. Con turnos
        previos reales, borrarlos ya no basta: solo el snapshot puede devolverlos.
        """
        jc = {'AM': self.am, 'PM': self.pm}
        for nombre in jornadas:
            Turno.objects.create(explorador=emp, fecha=fecha, jornada=jc[nombre],
                                 sala=self.sala, tipo_cambio=tipo_cambio)

    def _estado(self, fechas):
        """
        Huella completa del estado de los DOS exploradores en `fechas`.

        Se compara (jornada, tipo_cambio, sala) y no solo la jornada: devolver la jornada correcta
        con el `tipo_cambio` de un cambio ya cancelado dejaría el día mintiendo sobre su origen.
        """
        out = {}
        for emp in (self.solicitante, self.receptor):
            for f in fechas:
                out[(emp.id, f)] = sorted(
                    (t.jornada.nombre.upper(), t.tipo_cambio or '', t.sala_id)
                    for t in Turno.objects.filter(explorador=emp, fecha=f).select_related('jornada')
                )
        return out

    def _aprobar_y_aplicar(self, sol):
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save(update_fields=['estado', 'fecha_resolucion'])
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, f'aplicar_cambios falló: {msg}')
        return SolicitudCambio.objects.select_related('doblada').get(id=sol.id)

    def _cancelar(self, sol):
        """
        Cancela como se hace desde la pantalla: el explorador la pide y su compañero la aprueba
        (con todas sus guardas).
        """
        ok, msg = cancelar_con_acuerdo(sol, self.solicitante)
        self.assertTrue(ok, f'La cancelación fue rechazada: {msg}')
        return msg

    def _ciclo(self, fechas, **datos):
        """
        Crea → aprueba → aplica → cancela, y comprueba que se vuelve al estado previo.

        Comprueba también que el estado CAMBIÓ al aplicar: sin eso, un `aplicar_cambios` que no
        hiciera nada pasaría el test de reversión sin probar absolutamente nada.
        """
        previo = self._estado(fechas)
        sol = self._aprobar_y_aplicar(self._crear(**datos))
        self.assertNotEqual(self._estado(fechas), previo,
                            'Aplicar la solicitud no cambió nada: el test no probaría el revert.')
        self._cancelar(sol)
        posterior = self._estado(fechas)
        for clave in previo:
            emp_id, fecha = clave
            self.assertEqual(
                posterior[clave], previo[clave],
                f'El explorador {emp_id} no volvió a su estado previo el {fecha}: '
                f'antes={previo[clave]} después={posterior[clave]}',
            )
        return sol


class CDIntercambioDiaRevertTest(CDSemanaRevertBase):
    """«Intercambiar el día»: cada uno toma el descanso del otro. Sin deuda."""

    def test_revert_restaura_estado_previo(self):
        # El receptor (AM) trabaja el martes COMPLETO por temporada, aquí con turnos reales de
        # horario importado. El intercambio se los borra; solo el snapshot puede devolverlos.
        self._turnos_reales(self.receptor, self.d_desc_sol, ('AM', 'PM'))
        self._ciclo(
            [self.d_desc_sol, self.d_desc_rec],
            fecha_cambio_turno=self.d_desc_sol.strftime('%Y-%m-%d'),
            fecha_pago=self.d_desc_rec.strftime('%Y-%m-%d'),
            submodalidad_semana='intercambio_dia',
        )

    def test_no_genera_deuda(self):
        """El día completo de temporada no genera los 30 min: nadie dobla sobre su jornada."""
        self._aprobar_y_aplicar(self._crear(
            fecha_cambio_turno=self.d_desc_sol.strftime('%Y-%m-%d'),
            fecha_pago=self.d_desc_rec.strftime('%Y-%m-%d'),
            submodalidad_semana='intercambio_dia',
        ))
        self.assertFalse(DeudaCorporativa.objects.filter(estado='activa').exists())


class CDJornadasPartidasRevertTest(CDSemanaRevertBase):
    """«Jornadas partidas»: cada uno una media jornada los DOS días completos. Sin deuda."""

    def test_revert_restaura_estado_previo(self):
        # Turnos reales previos en los dos días completos: al partir las jornadas se reemplazan
        # por una sola cada uno, así que el revert tiene que reconstruir AM+PM.
        self._turnos_reales(self.receptor, self.d_desc_sol, ('AM', 'PM'))
        self._turnos_reales(self.solicitante, self.d_desc_rec, ('AM', 'PM'))
        self._ciclo(
            [self.d_desc_sol, self.d_desc_rec],
            # La cesión es MI día completo (jueves); el pago, el del compañero (martes).
            fecha_cambio_turno=self.d_desc_rec.strftime('%Y-%m-%d'),
            fecha_pago=self.d_desc_sol.strftime('%Y-%m-%d'),
            submodalidad_semana='jornadas_partidas',
            jornada_cedida='AM',
        )

    def test_no_genera_deuda(self):
        self._aprobar_y_aplicar(self._crear(
            fecha_cambio_turno=self.d_desc_rec.strftime('%Y-%m-%d'),
            fecha_pago=self.d_desc_sol.strftime('%Y-%m-%d'),
            submodalidad_semana='jornadas_partidas',
            jornada_cedida='AM',
        ))
        self.assertFalse(DeudaCorporativa.objects.filter(estado='activa').exists())


class CDCoberturaRevertTest(CDSemanaRevertBase):
    """
    «Que me cubran mi día»: el compañero cubre una jornada de mi día completo y yo se la devuelvo
    otro día de la MISMA semana.

    Es la ÚNICA de las cuatro que puede generar los 30 minutos, y aquí los genera a propósito: el
    pago cae en un día corriente (miércoles) donde el solicitante ya trabaja su PM, así que al
    cubrir el AM del compañero queda doblado sobre su propia jornada.
    """

    DATOS = dict(
        submodalidad_semana='cobertura_misma_semana',
        tipo_cesion='cesion_parcial_am',
        jornada_cedida='AM',
        jornada_cubre_en_pago='AM',
    )

    def _datos_cobertura(self):
        return dict(
            fecha_cambio_turno=self.d_desc_rec.strftime('%Y-%m-%d'),  # mi día completo (jueves)
            fecha_pago=self.d_normal.strftime('%Y-%m-%d'),            # pago el miércoles
            **self.DATOS,
        )

    def test_revert_restaura_estado_previo(self):
        # Mi día completo con turnos reales: la cobertura me quita el AM y deja solo el PM, así
        # que restaurar exige devolver la fila borrada, no solo limpiar las creadas.
        self._turnos_reales(self.solicitante, self.d_desc_rec, ('AM', 'PM'))
        self._ciclo([self.d_desc_rec, self.d_normal], **self._datos_cobertura())

    def test_la_deuda_de_30_min_se_anula_al_cancelar(self):
        sol = self._aprobar_y_aplicar(self._crear(**self._datos_cobertura()))
        deudas = DeudaCorporativa.objects.filter(solicitud_origen=sol)
        self.assertTrue(
            deudas.filter(estado='activa').exists(),
            'La cobertura debía generar los 30 min: el solicitante dobla sobre su propia jornada '
            'el día de pago.',
        )
        self._cancelar(sol)
        self.assertFalse(
            deudas.filter(estado='activa').exists(),
            'Al cancelar la cobertura, los 30 min deben quedar anulados: ya no dobla.',
        )


class CDCambioDobladaRevertTest(CDSemanaRevertBase):
    """
    «Cambio de doblada»: tomo la doblada real que el compañero tiene esa semana y él toma mi día
    completo de temporada. Sin deuda (los dos ya doblaban un día; solo cambia cuál).
    """

    def setUp(self):
        super().setUp()
        # El receptor necesita una doblada REAL (Turno AM+PM) en un día de la misma semana.
        for jornada in (self.am, self.pm):
            Turno.objects.create(explorador=self.receptor, fecha=self.d_normal,
                                 jornada=jornada, sala=self.sala, tipo_cambio='DOBLADA')

    def test_revert_restaura_estado_previo(self):
        self._ciclo(
            [self.d_desc_rec, self.d_normal],
            fecha_cambio_turno=self.d_desc_rec.strftime('%Y-%m-%d'),  # mi día completo (jueves)
            fecha_pago=self.d_normal.strftime('%Y-%m-%d'),            # su doblada (miércoles)
            submodalidad_semana='cambio_doblada',
        )

    def test_la_doblada_del_companero_vuelve_intacta(self):
        """
        El compañero cede una doblada que existía como Turno REAL. Restaurar solo las jornadas no
        basta: los dos turnos deben volver con su `tipo_cambio='DOBLADA'`, o el día dejaría de
        contar como la doblada que sigue vigente.
        """
        sol = self._aprobar_y_aplicar(self._crear(
            fecha_cambio_turno=self.d_desc_rec.strftime('%Y-%m-%d'),
            fecha_pago=self.d_normal.strftime('%Y-%m-%d'),
            submodalidad_semana='cambio_doblada',
        ))
        self._cancelar(sol)
        turnos = Turno.objects.filter(explorador=self.receptor, fecha=self.d_normal)
        self.assertEqual(
            sorted((t.jornada.nombre.upper(), t.tipo_cambio) for t in turnos.select_related('jornada')),
            [('AM', 'DOBLADA'), ('PM', 'DOBLADA')],
        )


class CDRevertNoDejaRastroTest(CDSemanaRevertBase):
    """La cancelación no debe dejar turnos huérfanos con `tipo_cambio='CAMBIO DESCANSO'`."""

    def test_no_quedan_turnos_de_cambio_descanso(self):
        sol = self._aprobar_y_aplicar(self._crear(
            fecha_cambio_turno=self.d_desc_sol.strftime('%Y-%m-%d'),
            fecha_pago=self.d_desc_rec.strftime('%Y-%m-%d'),
            submodalidad_semana='intercambio_dia',
        ))
        self.assertTrue(Turno.objects.filter(tipo_cambio='CAMBIO DESCANSO').exists())
        self._cancelar(sol)
        self.assertFalse(
            Turno.objects.filter(tipo_cambio='CAMBIO DESCANSO').exists(),
            'Quedaron turnos de CAMBIO DESCANSO tras cancelar: el día sigue mostrando un '
            'intercambio que ya no existe.',
        )
