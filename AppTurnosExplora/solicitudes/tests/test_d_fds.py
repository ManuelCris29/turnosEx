"""
Tests para D FDS (Doblada de Fin de Semana).

Cubren validación y aplicación:
- El solicitante cede su día del finde a un compañero del grupo contrario.
- En la cesión: receptor dobla (AM+PM), solicitante descansa.
- En el pago (otro finde del mismo mes): solicitante dobla (AM+PM), receptor descansa.
- Deudas: entre exploradores + corporativa 30 min por cada día doblado.

Las fechas se calculan dinámicamente (nunca hardcodeadas en el pasado).
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import (
    SolicitudCambio, TipoSolicitudCambio, DobladaDetalle,
    DeudaExplorador, DeudaCorporativa,
)
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from solicitudes.services.strategies.d_fds_strategy import DFDSStrategy


def _findes_de_mes(anio, mes):
    """Lista [(fecha, grupo_que_trabaja)] de todos los días de finde del mes."""
    d = date(anio, mes, 1)
    res = []
    while d.month == mes:
        if d.weekday() in (5, 6):
            res.append((d, AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(d)))
        d += timedelta(days=1)
    return res


def _fechas_fds(grupo_solicitante, grupo_receptor):
    """
    Devuelve (cesion, pago) en un mismo mes futuro y del MISMO día de la semana
    (sáb→sáb o dom→dom), conforme a la regla: si cedes un domingo, devuelves un domingo.
    - cesion: día de finde donde trabaja el grupo del solicitante.
    - pago: otro día de finde del MISMO día de semana (mismo mes) donde trabaja el receptor.
    """
    hoy = timezone.now().date()
    # Empezar dos meses adelante para asegurar futuro y margen.
    anio, mes = hoy.year, hoy.month
    for _ in range(2):
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    for _ in range(6):  # buscar en meses sucesivos por si acaso
        findes = _findes_de_mes(anio, mes)
        # Probar por cada tipo de día (sábado=5, domingo=6) un par cesión/pago del mismo tipo.
        for wd in (5, 6):
            dias = [f for f, _g in findes if f.weekday() == wd and f > hoy]
            ces = next((f for f in dias if AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == grupo_solicitante), None)
            pago = next((f for f in dias if AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == grupo_receptor and f != ces), None)
            if ces and pago:
                return ces, pago
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    raise AssertionError("No se hallaron fechas de finde válidas para la prueba")


class DFDSBaseTest(TestCase):
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='D FDS')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala FDS', activo=True)

        # Solicitante PM, receptor AM (grupos contrarios)
        self.u_sol = User.objects.create_user(username='sol.fds', password='x')
        self.solicitante = Empleado.objects.create(user=self.u_sol, nombre='Sol', apellido='Uno', cedula='111', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.solicitante, jornada=self.pm, fecha_inicio=date(2025, 1, 1))

        self.u_rec = User.objects.create_user(username='rec.fds', password='x')
        self.receptor = Empleado.objects.create(user=self.u_rec, nombre='Rec', apellido='Dos', cedula='222', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.receptor, jornada=self.am, fecha_inicio=date(2025, 1, 1))

        # Sala (especialidad) de ambos vía competencia — necesaria para crear turnos de doblada
        CompetenciaEmpleado.objects.create(empleado=self.solicitante, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.receptor, sala=self.sala)

        self.strat = DFDSStrategy()
        self.ces, self.pago = _fechas_fds('PM', 'AM')

    def _datos(self, **over):
        d = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'tipo_cambio': self.tipo,
            'comentario': 'Prueba',
            'fecha_cambio_turno': self.ces.strftime('%Y-%m-%d'),
            'fecha_pago': self.pago.strftime('%Y-%m-%d'),
            'fecha_creacion_solicitud': timezone.now().date(),
        }
        d.update(over)
        return d


class DFDSValidacionTest(DFDSBaseTest):
    def test_caso_valido(self):
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, msg)

    def test_revalidacion_para_aprobar_ok(self):
        # Una D FDS válida debe re-validar True al aprobar (no bloquear aprobaciones válidas).
        sol, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        ok, m = self.strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)

    def test_mismo_empleado_rechazado(self):
        ok, msg = self.strat.validar_solicitud(self._datos(explorador_receptor=self.solicitante))
        self.assertFalse(ok)

    def test_mismo_grupo_rechazado(self):
        # Receptor PM (mismo grupo que solicitante)
        u = User.objects.create_user(username='rec.pm', password='x')
        rec_pm = Empleado.objects.create(user=u, nombre='RecPM', apellido='Tres', cedula='333', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=rec_pm, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        ok, msg = self.strat.validar_solicitud(self._datos(explorador_receptor=rec_pm))
        self.assertFalse(ok)
        self.assertIn('grupo contrario', msg)

    def test_cesion_entre_semana_rechazada(self):
        lunes = self.ces
        while lunes.weekday() != 0:
            lunes += timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_cambio_turno=lunes.strftime('%Y-%m-%d')))
        self.assertFalse(ok)

    def test_pago_distinto_dia_rechazado(self):
        # Regla del mismo día: si cedes un sábado, el pago debe ser sábado (y viceversa).
        opp_wd = 6 if self.ces.weekday() == 5 else 5
        cand = None
        d = date(self.ces.year, self.ces.month, 1)
        while d.month == self.ces.month:
            if d.weekday() == opp_wd and d > timezone.now().date() and d != self.ces:
                cand = d
                break
            d += timedelta(days=1)
        self.assertIsNotNone(cand, "No se encontró un finde del día opuesto para la prueba")
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_pago=cand.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('debe ser un', msg.lower())

    def test_pago_otro_mes_rechazado(self):
        # Avanzar al mes siguiente, primer día del MISMO tipo que la cesión (sáb/dom),
        # para que dispare la regla de "mismo mes" y no la de "mismo día".
        m = self.pago.month
        d = date(self.pago.year + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        while d.weekday() != self.ces.weekday():
            d += timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_pago=d.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('mismo mes', msg.lower())


class DFDSAplicacionTest(DFDSBaseTest):
    def _crear_y_aplicar(self):
        sol, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related('doblada', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        return sol

    def _jornadas(self, emp, fecha):
        return sorted(t.jornada.nombre.upper() for t in Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada'))

    def test_aplicacion_turnos(self):
        self._crear_y_aplicar()
        # Favor: receptor dobla cesión, solicitante descansa
        self.assertEqual(self._jornadas(self.receptor, self.ces), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.solicitante, self.ces), [])
        # Pago: solicitante dobla, receptor descansa
        self.assertEqual(self._jornadas(self.solicitante, self.pago), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.receptor, self.pago), [])

    def test_deudas_generadas(self):
        sol = self._crear_y_aplicar()
        # Deuda entre exploradores: solicitante deudor, receptor acreedor
        de = DeudaExplorador.objects.filter(solicitud_origen=sol)
        self.assertEqual(de.count(), 1)
        self.assertEqual(de.first().deudor_id, self.solicitante.id)
        self.assertEqual(de.first().acreedor_id, self.receptor.id)
        # Corporativa: en D FDS la cesión y el pago caen en fin de semana, y los fines de
        # semana NO generan deuda de 30 min (solo se debe al cambiar un sábado por un día
        # de semana). Por lo tanto no debe generarse ninguna deuda corporativa.
        dc = DeudaCorporativa.objects.filter(solicitud_origen=sol)
        self.assertEqual(dc.count(), 0)

    def test_revert_restaura_y_cancela_deudas(self):
        from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService
        sol = self._crear_y_aplicar()
        # Tras aplicar: receptor dobla cesión, solicitante dobla pago; hay deuda vigente.
        self.assertEqual(self._jornadas(self.receptor, self.ces), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.solicitante, self.pago), ['AM', 'PM'])
        self.assertTrue(DeudaExplorador.objects.filter(solicitud_origen=sol)
                        .exclude(estado='cancelada').exists())
        # Revertir → turnos vuelven a vacío (findes virtuales) y deudas canceladas.
        DFDSAplicacionService.revertir(sol)
        self.assertEqual(self._jornadas(self.receptor, self.ces), [])
        self.assertEqual(self._jornadas(self.solicitante, self.pago), [])
        self.assertEqual(self._jornadas(self.solicitante, self.ces), [])
        self.assertEqual(self._jornadas(self.receptor, self.pago), [])
        self.assertFalse(DeudaExplorador.objects.filter(solicitud_origen=sol)
                         .exclude(estado='cancelada').exists())
