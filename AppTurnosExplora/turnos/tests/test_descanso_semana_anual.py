"""
Tests de la planeación ANUAL de descansos de semana (DescansoSemanaService).

Cubren los tres fallos detectados en la auditoría:
  1. Guardar el año no debe chocar con descansos de otro motivo (unicidad fecha+jornada).
  2. La precarga del calendario solo debe traer el motivo que gestiona la pantalla.
  3. No se puede alterar el descanso de un día con solicitudes aprobadas.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User

from empleados.models import Empleado, Jornada
from turnos.models import DescansoSemanaManual, DiaEspecial
from turnos.services.descanso_semana_service import (
    DescansoSemanaService, DescansoSemanaConflicto,
)


def _lunes_del_anio(anio, semanas=10):
    """Un lunes cualquiera del año dado (para no depender de la fecha de hoy)."""
    d = date(anio, 1, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d + timedelta(weeks=semanas)


class DescansoSemanaAnualTest(TestCase):

    ANIO = 2030

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.lunes = _lunes_del_anio(self.ANIO)
        self.martes = self.lunes + timedelta(days=1)
        self.viernes = self.lunes + timedelta(days=4)

    # --- 1. convivencia con descansos de otro motivo -------------------------
    def test_guardar_anual_no_rompe_con_descanso_de_otro_motivo(self):
        """Antes esto lanzaba IntegrityError: el delete solo borraba 'temporada'."""
        DescansoSemanaManual.objects.create(
            fecha=self.martes, jornada=self.am, motivo='otro', activo=True
        )
        n = DescansoSemanaService.guardar_anual(
            self.ANIO, {self.martes.isoformat(): ['AM', 'PM']}
        )
        # AM ya lo cubre el descanso individual: solo se crea PM.
        self.assertEqual(n, 1)
        self.assertEqual(
            DescansoSemanaManual.objects.filter(fecha=self.martes, jornada=self.am).count(), 1
        )
        self.assertTrue(
            DescansoSemanaManual.objects.filter(
                fecha=self.martes, jornada=self.pm, motivo='temporada').exists()
        )
        # El individual conserva su motivo (la pantalla anual no se lo apropia).
        self.assertEqual(
            DescansoSemanaManual.objects.get(fecha=self.martes, jornada=self.am).motivo, 'otro'
        )

    def test_descanso_de_otro_motivo_no_se_borra_al_reprogramar(self):
        DescansoSemanaManual.objects.create(
            fecha=self.viernes, jornada=self.pm, motivo='festivo', activo=True
        )
        DescansoSemanaService.guardar_anual(self.ANIO, {})
        self.assertTrue(
            DescansoSemanaManual.objects.filter(fecha=self.viernes, jornada=self.pm).exists()
        )

    # --- 2. precarga por motivo ---------------------------------------------
    def test_descansos_anual_solo_trae_el_motivo_gestionado(self):
        DescansoSemanaManual.objects.create(fecha=self.martes, jornada=self.am, motivo='temporada')
        DescansoSemanaManual.objects.create(fecha=self.viernes, jornada=self.pm, motivo='otro')
        pre = DescansoSemanaService.descansos_anual(self.ANIO)
        self.assertEqual(pre, {self.martes.isoformat(): ['AM']})
        otros = DescansoSemanaService.descansos_anual_otros_motivos(self.ANIO)
        self.assertEqual(otros, {self.viernes.isoformat(): ['PM']})

    def test_guardar_anual_ignora_findes_y_otros_anios(self):
        sabado = self.lunes + timedelta(days=5)
        otro_anio = date(self.ANIO + 1, 3, 4)  # lunes o no, da igual: año distinto
        n = DescansoSemanaService.guardar_anual(self.ANIO, {
            sabado.isoformat(): ['AM'],
            otro_anio.isoformat(): ['AM'],
            self.martes.isoformat(): ['PM'],
        })
        self.assertEqual(n, 1)
        self.assertEqual(DescansoSemanaManual.objects.count(), 1)

    # --- 3. bloqueo por solicitudes aprobadas -------------------------------
    def _crear_solicitud_aprobada(self, fecha):
        from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
        tipo = TipoSolicitudCambio.objects.create(
            nombre='CAMBIO DESCANSO', codigo_estrategia='CAMBIO_DESCANSO', activo=True
        )
        u1 = User.objects.create_user('sol_dsa', password='x', email='s@s.com')
        u2 = User.objects.create_user('rec_dsa', password='x', email='r@r.com')
        e1 = Empleado.objects.create(user=u1, nombre='S', apellido='X', cedula='9001',
                                     email='s@s.com', activo=True)
        e2 = Empleado.objects.create(user=u2, nombre='R', apellido='X', cedula='9002',
                                     email='r@r.com', activo=True)
        return SolicitudCambio.objects.create(
            explorador_solicitante=e1, explorador_receptor=e2, tipo_cambio=tipo,
            fecha_cambio_turno=fecha, estado='aprobada',
        )

    def test_fecha_con_solicitud_aprobada_queda_bloqueada(self):
        self._crear_solicitud_aprobada(self.martes)
        bloqueadas = DescansoSemanaService.fechas_bloqueadas_por_solicitud(self.ANIO)
        self.assertIn(self.martes.isoformat(), bloqueadas)

    def test_no_se_puede_borrar_el_descanso_de_un_dia_con_solicitud_aprobada(self):
        DescansoSemanaManual.objects.create(fecha=self.martes, jornada=self.am, motivo='temporada')
        self._crear_solicitud_aprobada(self.martes)
        with self.assertRaises(DescansoSemanaConflicto):
            DescansoSemanaService.guardar_anual(self.ANIO, {})
        # Nada se borró: la transacción se abortó antes de tocar la base.
        self.assertTrue(
            DescansoSemanaManual.objects.filter(fecha=self.martes, jornada=self.am).exists()
        )

    def test_se_puede_reprogramar_si_el_dia_bloqueado_no_cambia(self):
        DescansoSemanaManual.objects.create(fecha=self.martes, jornada=self.am, motivo='temporada')
        self._crear_solicitud_aprobada(self.martes)
        n = DescansoSemanaService.guardar_anual(self.ANIO, {
            self.martes.isoformat(): ['AM'],      # igual que está: permitido
            self.viernes.isoformat(): ['PM'],     # día libre: se puede añadir
        })
        self.assertEqual(n, 2)

    # --- 4. los días de temporada SÍ se pueden programar ---------------------
    def test_se_puede_programar_el_descanso_en_un_dia_de_temporada(self):
        """La pantalla anual existe justamente para elegir qué día descansa en temporada."""
        DiaEspecial.objects.create(
            fecha=self.martes, tipo='temporada', es_temporada=True, activo=True
        )
        DiaEspecial.objects.create(
            fecha=self.viernes, tipo='temporada', es_temporada=True, activo=True
        )
        n = DescansoSemanaService.guardar_anual(self.ANIO, {
            self.martes.isoformat(): ['AM'],
            self.viernes.isoformat(): ['PM'],
        })
        self.assertEqual(n, 2)
        self.assertTrue(DescansoSemanaManual.objects.filter(
            fecha=self.martes, jornada=self.am, motivo='temporada').exists())
        self.assertTrue(DescansoSemanaManual.objects.filter(
            fecha=self.viernes, jornada=self.pm, motivo='temporada').exists())
        self.assertEqual(DescansoSemanaService.descansos_anual(self.ANIO), {
            self.martes.isoformat(): ['AM'],
            self.viernes.isoformat(): ['PM'],
        })

    def test_findes_con_solicitud_no_bloquean(self):
        """El descanso de semana es lun-vie: un finde aprobado no afecta a esta pantalla."""
        sabado = self.lunes + timedelta(days=5)
        self._crear_solicitud_aprobada(sabado)
        self.assertEqual(DescansoSemanaService.fechas_bloqueadas_por_solicitud(self.ANIO), set())
