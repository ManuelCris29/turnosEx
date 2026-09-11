"""
`AcuerdoPorDiaService`: quién puso a esta persona a trabajar este día.

Es la fuente que alimenta el «con quién» del detalle del día en Mis Turnos. Que cada tipo
de solicitud llegue hasta ahí se comprueba de punta a punta en
`test_reflejo_mis_turnos.py`, que monta los seis trámites de verdad. Lo que se prueba AQUÍ
son las dos reglas de resolución del servicio, que no dependen de ningún tipo y que un
test de integración no puede provocar a voluntad:

  1. **La última aprobada gana el día.** Dos solicitudes vigentes pueden reclamar la misma
     fecha (ceder un día que ya trabajas por otro acuerdo es legítimo). La que manda es la
     aprobada más tarde: los acuerdos no se encadenan, el último cancela al anterior.
  2. **La realidad manda sobre el snapshot.** Un acuerdo cuyo día fue reescrito después por
     otro no puede seguir nombrando a su compañero. Sin esta guarda, el detalle del día
     atribuiría el turno a quien ya no tiene nada que ver con él.

Y la rama de **PAGO REPROGRAMADO**, que es la única del servicio que NO sale de un snapshot
—el día lo escribe el módulo de reprogramación de dobladas, no un aplicador de solicitudes—.
Por eso es también la única que puede desalinearse sin que nada la cruce con otra fuente, y
`test_reflejo_mis_turnos.py` no la alcanza: monta los seis tipos de solicitud, no una
inasistencia reprogramada por el supervisor.

Los snapshots se escriben a mano a propósito: montar dos acuerdos reales que se pisen el
mismo día exige un calendario muy concreto y dejaría el test dependiendo de la geometría
de un tipo, que es justo lo que este servicio ya no mira.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, Jornada
from solicitudes.models import ReprogramacionDiaDoblada, SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.acuerdo_por_dia_service import AcuerdoPorDiaService
from turnos.models import Sala, Turno

DIA = date(2030, 3, 6)   # miércoles lejano: ningún dato de prueba lo toca


class AcuerdoPorDiaTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Acuerdo', activo=True)
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA')

        self.yo = self._empleado('yo.acuerdo', 'Yo', 'Acuerdo', '9401')
        self.antiguo = self._empleado('ant.acuerdo', 'Ana', 'Antigua', '9402')
        self.reciente = self._empleado('rec.acuerdo', 'Rita', 'Reciente', '9403')

    def _empleado(self, username, nombre, apellido, cedula):
        user = User.objects.create_user(username=username, password='x')
        return Empleado.objects.create(user=user, nombre=nombre, apellido=apellido,
                                       cedula=cedula, activo=True)

    def _turno(self, tipo_cambio, jornada=None):
        return Turno.objects.create(explorador=self.yo, fecha=DIA, sala=self.sala,
                                    jornada=jornada or self.am, tipo_cambio=tipo_cambio)

    def _solicitud(self, companero, resuelta_hace_dias, tipo_cambio_turno):
        """Una aprobada cuyo snapshot dice que dejó a `self.yo` trabajando `DIA`."""
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=companero, explorador_receptor=self.yo,
            tipo_cambio=self.tipo, estado='aprobada',
            fecha_cambio_turno=DIA,
            fecha_resolucion=timezone.now() - timedelta(days=resuelta_hace_dias),
        )
        sol.snapshot_turnos_resultantes = {
            f'{self.yo.id}:{DIA.isoformat()}': [
                {'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': tipo_cambio_turno},
            ],
            # El otro lado queda LIBRE: lista vacía. No debe reclamar el día de nadie.
            f'{companero.id}:{DIA.isoformat()}': [],
        }
        sol.save(update_fields=['snapshot_turnos_resultantes'])
        return sol

    # ------------------------------------------------------------------ pruebas
    def test_la_ultima_aprobada_gana_el_dia(self):
        """Con dos acuerdos vigentes sobre el mismo día, el compañero es el del más reciente."""
        self._turno('DOBLADA')
        self._solicitud(self.antiguo, resuelta_hace_dias=30, tipo_cambio_turno='DOBLADA')
        self._solicitud(self.reciente, resuelta_hace_dias=1, tipo_cambio_turno='DOBLADA')

        info = AcuerdoPorDiaService.en_fecha(self.yo, DIA)
        self.assertIsNotNone(info)
        self.assertEqual(info['companero_nombre'], 'Rita Reciente',
                         'el día lo gana la solicitud aprobada más tarde')
        self.assertEqual(info['rol'], 'receptor')

    def test_un_snapshot_que_ya_no_describe_el_turno_no_reclama_el_dia(self):
        """
        El turno real es de otro tipo: el acuerdo antiguo ya no explica ese día.

        Ese día fue reescrito por algo posterior. Si el servicio no lo comprobara, la ficha
        seguiría diciendo "estás cubriendo a Ana" sobre un turno que Ana ya no le dio.
        """
        self._turno('CT')                       # la realidad: hoy es un cambio de turno
        self._solicitud(self.antiguo, resuelta_hace_dias=30, tipo_cambio_turno='DOBLADA')

        self.assertIsNone(AcuerdoPorDiaService.en_fecha(self.yo, DIA))

    def test_sin_turno_real_no_hay_acuerdo_que_contar(self):
        """Un día en el que no se trabaja no tiene "con quién": lo cuenta el lado del descanso."""
        self._solicitud(self.antiguo, resuelta_hace_dias=2, tipo_cambio_turno='DOBLADA')
        self.assertEqual(AcuerdoPorDiaService.en_rango(self.yo, DIA, DIA), {})

    def test_el_dia_libre_del_companero_no_se_le_atribuye_como_trabajado(self):
        """La lista VACÍA del snapshot significa "quedó libre", no "trabajó"."""
        self._turno('DOBLADA')
        sol = self._solicitud(self.antiguo, resuelta_hace_dias=2, tipo_cambio_turno='DOBLADA')

        # Al compañero el mismo snapshot le deja `[]` ese día.
        self.assertEqual(AcuerdoPorDiaService.en_rango(self.antiguo, DIA, DIA), {})
        # Y a quien sí trabaja se lo atribuye la misma solicitud.
        self.assertEqual(AcuerdoPorDiaService.en_fecha(self.yo, DIA)['solicitud_id'], sol.id)

    def test_una_solicitud_no_aprobada_no_cuenta(self):
        self._turno('DOBLADA')
        sol = self._solicitud(self.antiguo, resuelta_hace_dias=2, tipo_cambio_turno='DOBLADA')
        sol.estado = 'cancelada'
        sol.save(update_fields=['estado'])

        self.assertIsNone(AcuerdoPorDiaService.en_fecha(self.yo, DIA))

    def test_el_rango_no_se_sale_de_sus_bordes(self):
        """Un acuerdo del día siguiente no se cuela al pedir solo el día anterior."""
        self._turno('DOBLADA')
        self._solicitud(self.antiguo, resuelta_hace_dias=2, tipo_cambio_turno='DOBLADA')

        self.assertEqual(AcuerdoPorDiaService.en_rango(
            self.yo, DIA - timedelta(days=2), DIA - timedelta(days=1)), {})

    # ------------------------------------------------- variante BATCH
    def test_el_batch_dice_lo_mismo_que_la_version_individual(self):
        """
        `en_rango_multiple` es la implementación real y `en_rango` su atajo: si divergieran,
        el reporte del supervisor y el detalle del día contarían historias distintas del
        mismo día. Es el mismo pacto que ya tiene `DescansoPorSolicitudService`.
        """
        self._turno('DOBLADA')
        self._solicitud(self.reciente, resuelta_hace_dias=1, tipo_cambio_turno='DOBLADA')
        Turno.objects.create(explorador=self.antiguo, fecha=DIA, sala=self.sala,
                             jornada=self.pm, tipo_cambio='PAGO REPROGRAMADO')
        self._reprogramacion(self.reciente, explorador=self.antiguo)

        empleados = [self.yo, self.antiguo, self.reciente]
        batch = AcuerdoPorDiaService.en_rango_multiple(empleados, DIA, DIA)
        for emp in empleados:
            self.assertEqual(batch[emp.id],
                             AcuerdoPorDiaService.en_rango(emp, DIA, DIA),
                             f'el batch difiere del individual para {emp.nombre}')
        # Y no es un empate de diccionarios vacíos: los dos que trabajan tienen acuerdo.
        self.assertEqual(batch[self.yo.id][DIA]['companero_nombre'], 'Rita Reciente')
        self.assertEqual(batch[self.antiguo.id][DIA]['tipo_cambio'], 'PAGO REPROGRAMADO')

    def test_el_batch_no_atribuye_dias_a_quien_no_esta_en_el_lote(self):
        """
        Un snapshot habla de las DOS personas del acuerdo. Al pedir solo una, la otra no
        puede aparecer en la salida ni colarse como clave nueva.
        """
        self._turno('DOBLADA')
        self._solicitud(self.reciente, resuelta_hace_dias=1, tipo_cambio_turno='DOBLADA')

        batch = AcuerdoPorDiaService.en_rango_multiple([self.yo], DIA, DIA)
        self.assertEqual(set(batch), {self.yo.id})
        self.assertEqual(batch[self.yo.id][DIA]['companero_nombre'], 'Rita Reciente')

    def test_el_batch_sin_empleados_no_consulta_nada(self):
        with self.assertNumQueries(0):
            self.assertEqual(AcuerdoPorDiaService.en_rango_multiple([], DIA, DIA), {})

    # ------------------------------------------------- PAGO REPROGRAMADO
    def _reprogramacion(self, companero, estado='pendiente', explorador=None):
        """
        Una doblada que `explorador` (por defecto `self.yo`) no pudo cumplir y que el
        supervisor le reprogramó a `DIA`.

        El compañero sale de la doblada ORIGINAL: la reprogramación no es un acuerdo nuevo
        entre dos, solo mueve el día que ya se debía.
        """
        explorador = explorador or self.yo
        origen = SolicitudCambio.objects.create(
            explorador_solicitante=explorador, explorador_receptor=companero,
            tipo_cambio=self.tipo, estado='aprobada',
            fecha_cambio_turno=DIA - timedelta(days=14),
            fecha_resolucion=timezone.now() - timedelta(days=20),
        )
        return ReprogramacionDiaDoblada.objects.create(
            doblada_origen=origen, explorador=explorador,
            fecha_original=DIA - timedelta(days=7),
            fecha_reprogramada=DIA, estado=estado,
        )

    def test_el_pago_reprogramado_nombra_al_companero_de_la_doblada_original(self):
        self._turno('PAGO REPROGRAMADO')
        reprog = self._reprogramacion(self.antiguo)

        info = AcuerdoPorDiaService.en_fecha(self.yo, DIA)
        self.assertIsNotNone(info, 'el día reprogramado debe decir de qué doblada viene')
        self.assertEqual(info['tipo_cambio'], 'PAGO REPROGRAMADO')
        self.assertEqual(info['companero_nombre'], 'Ana Antigua')
        self.assertEqual(info['rol'], 'solicitante')
        self.assertEqual(info['solicitud_id'], reprog.doblada_origen_id)
        # La fecha relacionada es el día que NO se pudo cumplir, que es lo que se está pagando.
        self.assertEqual(info['fecha_relacionada'],
                         reprog.fecha_original.strftime('%d/%m/%Y'))

    def test_una_reprogramacion_cancelada_no_reclama_el_dia(self):
        self._turno('PAGO REPROGRAMADO')
        self._reprogramacion(self.antiguo, estado='cancelada')

        self.assertIsNone(AcuerdoPorDiaService.en_fecha(self.yo, DIA))

    def test_el_pago_reprogramado_tambien_pasa_por_la_guarda_de_realidad(self):
        """Si el día ya es de otro tipo, la reprogramación no puede seguir reclamándolo."""
        self._turno('DOBLADA')          # la realidad: hoy este día lo escribió otra cosa
        self._reprogramacion(self.antiguo)

        info = AcuerdoPorDiaService.en_fecha(self.yo, DIA)
        self.assertIsNone(info, 'la reprogramación no describe este día y no debe nombrarse')

    def test_un_acuerdo_con_snapshot_gana_a_la_reprogramacion(self):
        """
        Las dos ramas pueden reclamar el mismo día; el snapshot va primero.

        La rama de reprogramación se añade AL FINAL y solo sobre fechas que nadie reclamó
        (`if fecha in salida: continue`). Si ese orden se invirtiera, un día reescrito por una
        solicitud posterior seguiría anunciándose como pago de una doblada vieja.
        """
        self._turno('DOBLADA')
        self._solicitud(self.reciente, resuelta_hace_dias=1, tipo_cambio_turno='DOBLADA')
        self._reprogramacion(self.antiguo)

        info = AcuerdoPorDiaService.en_fecha(self.yo, DIA)
        self.assertEqual(info['companero_nombre'], 'Rita Reciente')
        self.assertEqual(info['tipo_cambio'], 'DOBLADA')
