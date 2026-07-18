"""
Tests para Cambio de Día de Descanso (modalidad fin de semana).

Cubren:
- Validación: caso válido, mismo empleado, mismo grupo, día opuesto (sáb↔dom),
  mismo mes, duplicado exacto, duplicado INVERTIDO (cesión↔pago), día ya comprometido.
- Aplicación: el intercambio deja los turnos correctos (ida y vuelta).
- Reversión: al revertir, los turnos vuelven al estado previo (fix de cancelación).

Las fechas se calculan dinámicamente desde la alternancia real (nunca hardcodeadas).
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService as A
from solicitudes.services.strategies.cambio_descanso_strategy import CambioDescansoStrategy
from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService


def _fechas_cd(grupo_sol, grupo_rec):
    """
    Devuelve (cesion, pago) para un cambio de descanso de finde, en el mismo mes futuro:
    - cesion: un SÁBADO donde trabaja el solicitante (y el receptor trabaja el domingo).
    - pago: un DOMINGO (día opuesto, otro finde) donde trabaja el solicitante (y el receptor
      trabaja el sábado).
    """
    hoy = timezone.now().date()
    anio, mes = hoy.year, hoy.month
    for _ in range(2):  # arrancar 2 meses adelante
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    for _ in range(12):
        sabados = []
        d = date(anio, mes, 1)
        while d.month == mes:
            if d.weekday() == 5:
                sabados.append(d)
            d += timedelta(days=1)
        ces = next((s for s in sabados if s > hoy
                    and A.jornada_trabaja_sabado(s) == grupo_sol
                    and A.jornada_trabaja_domingo(s) == grupo_rec), None)
        pago = None
        for s in sabados:
            dom = s + timedelta(days=1)
            if (dom.month == mes and dom > hoy and s != ces
                    and A.jornada_trabaja_domingo(s) == grupo_sol
                    and A.jornada_trabaja_sabado(s) == grupo_rec):
                pago = dom
                break
        if ces and pago:
            return ces, pago
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    raise AssertionError("No se hallaron fechas de cambio de descanso válidas para la prueba")


class CDBaseTest(TestCase):
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO DESCANSO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CD', activo=True)

        self.u_sol = User.objects.create_user(username='sol.cd', password='x')
        self.solicitante = Empleado.objects.create(user=self.u_sol, nombre='Sol', apellido='Uno', cedula='111', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.solicitante, jornada=self.pm, fecha_inicio=date(2025, 1, 1))

        self.u_rec = User.objects.create_user(username='rec.cd', password='x')
        self.receptor = Empleado.objects.create(user=self.u_rec, nombre='Rec', apellido='Dos', cedula='222', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.receptor, jornada=self.am, fecha_inicio=date(2025, 1, 1))

        CompetenciaEmpleado.objects.create(empleado=self.solicitante, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.receptor, sala=self.sala)

        self.strat = CambioDescansoStrategy()
        self.ces, self.pago = _fechas_cd('PM', 'AM')

    def _datos(self, **over):
        d = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'tipo_cambio': self.tipo,
            'comentario': 'Prueba',
            'fecha_cambio_turno': self.ces.strftime('%Y-%m-%d'),
            'fecha_pago': self.pago.strftime('%Y-%m-%d'),
        }
        d.update(over)
        return d

    def _crear(self, **over):
        sol, msg = self.strat.crear_solicitud(self._datos(**over))
        self.assertIsNotNone(sol, msg)
        return SolicitudCambio.objects.select_related('doblada', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)


class CDValidacionTest(CDBaseTest):
    def test_caso_valido(self):
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, msg)

    def test_mismo_empleado_rechazado(self):
        ok, _ = self.strat.validar_solicitud(self._datos(explorador_receptor=self.solicitante))
        self.assertFalse(ok)

    def test_mismo_grupo_rechazado(self):
        u = User.objects.create_user(username='rec.pm', password='x')
        rec_pm = Empleado.objects.create(user=u, nombre='RecPM', apellido='Tres', cedula='333', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=rec_pm, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        ok, msg = self.strat.validar_solicitud(self._datos(explorador_receptor=rec_pm))
        self.assertFalse(ok)
        self.assertIn('grupo contrario', msg)

    def test_mismo_dia_semana_rechazado(self):
        # cesión sábado, pago sábado (mismo weekday) → debe pedir el día contrario.
        otro_sabado = self.ces + timedelta(days=7)
        if otro_sabado.month != self.ces.month:
            otro_sabado = self.ces - timedelta(days=7)
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_pago=otro_sabado.strftime('%Y-%m-%d')))
        self.assertFalse(ok)

    def test_pago_otro_mes_rechazado(self):
        # un domingo del mes siguiente
        m = self.pago.month
        d = date(self.pago.year + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        while d.weekday() != 6:
            d += timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_pago=d.strftime('%Y-%m-%d')))
        self.assertFalse(ok)

    def test_duplicado_exacto_rechazado(self):
        self._crear()  # deja una pendiente
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok)

    def test_duplicado_invertido_rechazado(self):
        # Crea A (cesión=sáb, pago=dom). Intenta B con cesión/pago INVERTIDOS → mismo intercambio.
        self._crear()
        ok, msg = self.strat.validar_solicitud(self._datos(
            fecha_cambio_turno=self.pago.strftime('%Y-%m-%d'),
            fecha_pago=self.ces.strftime('%Y-%m-%d'),
        ))
        self.assertFalse(ok)
        self.assertIn('Ya enviaste', msg)

    def test_dia_comprometido_rechazado(self):
        # Si la cesión ya tiene un turno con tipo_cambio (otro cambio aplicado), se bloquea.
        Turno.objects.create(explorador=self.solicitante, fecha=self.ces, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.solicitante, fecha=self.ces, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok)


class CDAplicacionTest(CDBaseTest):
    def _crear_y_aplicar(self):
        sol = self._crear()
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        return sol

    def _jornadas(self, emp, fecha):
        return sorted(t.jornada.nombre.upper() for t in Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada'))

    def test_reconciliacion_doblada_no_corrompe_cambio_descanso(self):
        """Regresión: al revertir una doblada, la reconciliación post-revert NO debe aplicar
        lógica de DOBLADA a un CAMBIO DESCANSO (ambos comparten DobladaDetalle). Debe re-aplicarlo
        con SU propia lógica y restaurar sus turnos, sin dejar turnos DOBLADA colgados."""
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService
        self._crear_y_aplicar()
        # Estado correcto tras aplicar: el receptor trabaja AM+PM el sábado de cesión.
        self.assertEqual(self._jornadas(self.receptor, self.ces), ['AM', 'PM'])
        # Simular lo que dejaba una doblada al pisar ese día: borrar los turnos del cambio de
        # descanso y dejar un turno DOBLADA colgado.
        Turno.objects.filter(explorador=self.receptor, fecha=self.ces).delete()
        Turno.objects.create(explorador=self.receptor, fecha=self.ces, jornada=self.am,
                             sala=self.sala, tipo_cambio='DOBLADA')
        # Reconciliar como tras revertir una doblada que pagaba ese día.
        DobladaSnapshotService.reconciliar_dobladas_aprobadas(
            {(self.receptor.id, self.ces)}, excluir_solicitud_id=None)
        # El cambio de descanso quedó re-aplicado con SU lógica (AM+PM), sin DOBLADA colgada.
        turnos = list(Turno.objects.filter(explorador=self.receptor, fecha=self.ces).select_related('jornada'))
        self.assertEqual(sorted(t.jornada.nombre.upper() for t in turnos), ['AM', 'PM'])
        self.assertTrue(
            all(t.tipo_cambio == 'CAMBIO DESCANSO' for t in turnos),
            f'turnos con tipo inesperado: {[(t.jornada.nombre, t.tipo_cambio) for t in turnos]}',
        )

    def test_aplicacion_intercambio(self):
        self._crear_y_aplicar()
        otro_ces = self.ces + timedelta(days=1)   # domingo del finde de cesión
        otro_pago = self.pago - timedelta(days=1)  # sábado del finde de pago
        # Solicitante: descansa cesión/pago, trabaja los días contrarios (DOBLADA)
        self.assertEqual(self._jornadas(self.solicitante, self.ces), [])
        self.assertEqual(self._jornadas(self.solicitante, otro_ces), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.solicitante, self.pago), [])
        self.assertEqual(self._jornadas(self.solicitante, otro_pago), ['AM', 'PM'])
        # Receptor: espejo
        self.assertEqual(self._jornadas(self.receptor, self.ces), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.receptor, otro_ces), [])

    def test_revert_restaura_estado_previo(self):
        otro_ces = self.ces + timedelta(days=1)
        otro_pago = self.pago - timedelta(days=1)
        dias = [self.ces, otro_ces, self.pago, otro_pago]
        # Estado previo (findes virtuales: sin turnos reales)
        previo = {d: self._jornadas(self.solicitante, d) for d in dias}
        sol = self._crear_y_aplicar()
        # Tras aplicar, hay turnos creados
        self.assertNotEqual(self._jornadas(self.solicitante, otro_ces), previo[otro_ces])
        # Revertir → vuelve al estado previo
        CambioDescansoAplicacionService.revertir(sol)
        for d in dias:
            self.assertEqual(self._jornadas(self.solicitante, d), previo[d],
                             f"El día {d} no volvió a su estado previo tras revertir")


class CDConcurrenciaReceptorTest(CDBaseTest):
    def test_caso_b_receptor_ya_comprometido_por_otra_aprobada(self):
        # Caso B: A (solicitante -> receptor) ya APROBADA y aplicada. Un SEGUNDO solicitante del
        # mismo grupo intenta el MISMO receptor el mismo finde -> debe bloquearse (el receptor ya
        # quedó comprometido). Cubre el escenario de dos solicitantes hacia el mismo compañero.
        solA = self._crear()
        solA.estado = 'aprobada'
        solA.fecha_resolucion = timezone.now()
        solA.save()
        ok, msg = self.strat.aplicar_cambios(solA)
        self.assertTrue(ok, msg)

        u = User.objects.create_user(username='sol2.cd', password='x')
        sol2 = Empleado.objects.create(user=u, nombre='Sol2', apellido='PM', cedula='999', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=sol2, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=sol2, sala=self.sala)

        ok2, msg2 = self.strat.validar_solicitud(self._datos(explorador_solicitante=sol2))
        self.assertFalse(ok2, f"B debió bloquearse (receptor ya comprometido por A). msg={msg2}")


class CDRevalidacionTest(CDBaseTest):
    def test_revalidacion_ok_no_se_autobloquea_por_duplicado(self):
        # La solicitud existe (pendiente). Al re-validar para aprobar NO debe verse a sí
        # misma como "duplicado pendiente".
        sol = self._crear()
        ok, msg = self.strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, msg)

    def test_revalidacion_falla_si_la_cesion_quedo_comprometida(self):
        # Entre el envío y la aprobación, el día de cesión quedó comprometido por otra gestión.
        sol = self._crear()
        Turno.objects.create(explorador=self.solicitante, fecha=self.ces, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.solicitante, fecha=self.ces, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        ok, msg = self.strat.revalidar_para_aprobar(sol)
        self.assertFalse(ok, "Debió rechazar la aprobación: el día ya no es válido")
