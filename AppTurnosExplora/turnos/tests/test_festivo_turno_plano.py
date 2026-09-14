"""
Un `Turno` PLANO (sin `tipo_cambio`) en un FESTIVO entre semana no puede tapar una
solicitud aprobada.

EL HUECO QUE CIERRA
-------------------
Dos capas decidían por separado qué turno cuenta como "la realidad del día":

  · L5 (festivo) solo respetaba los turnos CON `tipo_cambio` — la regla del festivo manda
    sobre el horario predeterminado, y solo un cambio explícito gana.
  · La guarda de realidad de `DescansoPorSolicitudService` contaba CUALQUIER turno activo.

Con un turno plano en un festivo entre semana las dos se anulaban: la guarda silenciaba la
L2 y la L5 descartaba ese mismo turno, así que la solicitud aprobada desaparecía y mandaba
la rotación del festivo. El trato salía AL REVÉS — el acreedor doblando el día en que le
pagan, el deudor que debía cubrirlo descansando— tanto en el reporte del supervisor como en
Mis Turnos, que comparten las mismas capas.

Y el turno plano en un festivo no es un caso raro: es el horario importado de siempre, y es
lo que deja restaurado la cancelación de otra solicitud (el snapshot previo guarda el turno
tal y como estaba, sin `tipo_cambio`).

El criterio vive ahora en `turnos.services.turno_vigente.turno_manda_en`, que usan las dos.
"""
from datetime import date

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from empleados.models import Empleado
from solicitudes.models import DobladaDetalle, SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
from turnos.models import (
    AsignacionEspecialManual,
    AsignarJornadaExplorador,
    DiaEspecial,
    Jornada,
    Sala,
    Turno,
)
from turnos.services.reporte_dia_service import ReporteDiaService
from turnos.services.turno_service import TurnoService

FESTIVO = date(2026, 4, 3)      # viernes santo: festivo ENTRE SEMANA
CESION = date(2026, 4, 1)       # miércoles


class FestivoConTurnoPlanoTest(TestCase):
    """El festivo en que a alguien le PAGAN una doblada, con un turno plano de por medio."""

    @classmethod
    def setUpTestData(cls):
        cls.am = Jornada.objects.get_or_create(
            nombre='AM', defaults={'hora_inicio': '06:00:00', 'hora_fin': '14:00:00'})[0]
        cls.pm = Jornada.objects.get_or_create(
            nombre='PM', defaults={'hora_inicio': '14:00:00', 'hora_fin': '22:00:00'})[0]
        cls.sala = Sala.objects.create(nombre='Sala festivo')

        def _emp(username, nombre, cedula, jornada):
            user = User.objects.create_user(username=username, password='x')
            e = Empleado.objects.create(user=user, nombre=nombre, apellido='Festivo',
                                        cedula=cedula, activo=True)
            AsignarJornadaExplorador.objects.create(
                explorador=e, jornada=jornada, fecha_inicio=date(2026, 1, 1))
            return e

        cls.deudor = _emp('fest.deudor', 'Deudor', '99101', cls.am)
        cls.acreedor = _emp('fest.acreedor', 'Acreedor', '99102', cls.pm)

        # El festivo y su alternancia publicada: ese día DOBLA el grupo PM (el del acreedor).
        DiaEspecial.objects.create(fecha=FESTIVO, tipo='festivo', activo=True)
        AsignacionEspecialManual.objects.create(
            fecha=FESTIVO, jornada_trabaja=cls.pm, tipo='festivo', activo=True)

        # DOBLADA aprobada: el deudor cede el 01/04 y PAGA el 03/04 (el festivo). Ese día el
        # acreedor NO trabaja — se lo cubre el deudor.
        tipo = TipoSolicitudCambio.objects.get_or_create(nombre='DOBLADA')[0]
        cls.sol = SolicitudCambio.objects.create(
            explorador_solicitante=cls.deudor, explorador_receptor=cls.acreedor,
            tipo_cambio=tipo, estado='aprobada', fecha_cambio_turno=CESION)
        DobladaDetalle.objects.create(
            solicitud=cls.sol, fecha_pago=FESTIVO, tipo_cesion='cesion_completa',
            jornada_cedida='AM')

    def setUp(self):
        # `ReporteDiaService.reporte` y `DiaEspecial.es_festivo` cachean por fecha.
        cache.clear()

    def _columnas(self):
        rep = ReporteDiaService._reporte_bd(FESTIVO)
        return ({r['id']: r for r in rep['trabajando']},
                {r['id']: r for r in rep['descansando']})

    def test_el_turno_plano_no_tapa_la_solicitud(self):
        """EL CASO: con un turno plano en el festivo, la doblada aprobada sigue viéndose."""
        Turno.objects.create(explorador=self.acreedor, fecha=FESTIVO,
                             jornada=self.pm, sala=self.sala, tipo_cambio=None)

        trabajando, descansando = self._columnas()
        self.assertIn(
            self.acreedor.id, descansando,
            'le pagan la doblada ese festivo: el reporte debe mostrarlo descansando, no '
            f'trabajando {(trabajando.get(self.acreedor.id) or {}).get("jornada_dia")!r}')
        self.assertEqual(descansando[self.acreedor.id]['motivo'], 'paga doblada')
        self.assertEqual(descansando[self.acreedor.id]['companero']['id'], self.deudor.id)

    def test_mis_turnos_dice_lo_mismo_que_el_reporte(self):
        """Las dos pantallas comparten las capas: no pueden discrepar del mismo día."""
        Turno.objects.create(explorador=self.acreedor, fecha=FESTIVO,
                             jornada=self.pm, sala=self.sala, tipo_cambio=None)

        estado = TurnoService.estado_dia(self.acreedor, FESTIVO)
        self.assertFalse(estado['trabaja'])
        self.assertEqual(estado['fuente'], 'solicitud')
        self.assertEqual(estado['motivo'], 'paga doblada')

        # Y la variante batch (la que alimenta Mis Turnos) igual.
        batch = TurnoService.estado_rango_multiple([self.acreedor], FESTIVO, FESTIVO)
        self.assertFalse(batch[self.acreedor.id][FESTIVO]['trabaja'])

    def test_sin_turno_plano_sigue_funcionando(self):
        """Línea base: sin turnos en el festivo la capa L2 ya funcionaba, y sigue igual."""
        _, descansando = self._columnas()
        self.assertIn(self.acreedor.id, descansando)
        self.assertEqual(descansando[self.acreedor.id]['motivo'], 'paga doblada')

    def test_un_turno_CON_tipo_cambio_si_manda_sobre_la_solicitud(self):
        """Contraste: un cambio EXPLÍCITO sí gana en festivo (la última aprobada gana).

        Es la mitad del criterio que ya era correcta y que no se puede perder al cerrar la
        otra: si un turno con `tipo_cambio` dejara de mandar, un día recuperado por una
        solicitud posterior volvería a figurar como descanso.
        """
        Turno.objects.create(explorador=self.acreedor, fecha=FESTIVO,
                             jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')

        trabajando, descansando = self._columnas()
        self.assertIn(self.acreedor.id, trabajando)
        self.assertEqual(trabajando[self.acreedor.id]['jornada_dia'], 'PM')
        self.assertNotIn(self.acreedor.id, descansando)

    def test_fuera_del_festivo_cualquier_turno_manda(self):
        """La excepción es SOLO del festivo entre semana: el resto de días no cambia.

        En un día ordinario un turno plano sigue siendo realidad (L1 gana a L2), que es lo
        que impide que un día ya "descansado" quede bloqueado para siempre.
        """
        ordinario = date(2026, 4, 8)    # miércoles cualquiera, sin festivo
        sol2 = SolicitudCambio.objects.create(
            explorador_solicitante=self.deudor, explorador_receptor=self.acreedor,
            tipo_cambio=self.sol.tipo_cambio, estado='aprobada',
            fecha_cambio_turno=date(2026, 4, 6))
        DobladaDetalle.objects.create(
            solicitud=sol2, fecha_pago=ordinario, tipo_cesion='cesion_completa',
            jornada_cedida='AM')
        Turno.objects.create(explorador=self.acreedor, fecha=ordinario,
                             jornada=self.pm, sala=self.sala, tipo_cambio=None)

        self.assertIsNone(
            DescansoPorSolicitudService.en_fecha(self.acreedor, ordinario),
            'fuera del festivo un turno plano SÍ es realidad: L1 debe seguir ganando a L2')
