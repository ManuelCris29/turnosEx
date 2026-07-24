"""
Tests del enriquecimiento del reporte del día: restricción, sanción y deuda de
doblada por reprogramación. Verifica que las claves nuevas aparezcan (o queden
None) según los datos, y un smoke test de la exportación a Excel.
"""
import io
from datetime import date, timedelta

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User

from empleados.models import (Empleado, Jornada, RestriccionEmpleado, SancionEmpleado)
from turnos.models import AsignarJornadaExplorador, Sala
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio, ReprogramacionDiaDoblada
from turnos.services.reporte_dia_service import ReporteDiaService

FECHA = date(2026, 3, 4)  # miércoles, no festivo


def _buscar(data, emp_id):
    """Encuentra el dict del empleado en trabajando o descansando."""
    for grupo in ('trabajando', 'descansando'):
        for e in data[grupo]:
            if e['id'] == emp_id:
                return e
    return None


class ReporteDiaEnriquecidoTest(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Rep', activo=True)
        self.tipo_dob = TipoSolicitudCambio.objects.create(nombre='DOBLADA', codigo_estrategia='DOBLADA', activo=True)

        def _emp(username, ced, jor, staff=False):
            u = User.objects.create_user(username=username, password='x', is_staff=staff)
            e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
            AsignarJornadaExplorador.objects.create(explorador=e, jornada=jor, fecha_inicio=date(2025, 1, 1))
            return e

        self.a = _emp('rep_a', '8001', self.am)
        self.b = _emp('rep_b', '8002', self.pm)
        self.sup = Empleado.objects.create(
            user=User.objects.create_user(username='rep_sup', password='x', is_staff=True),
            nombre='Sup', apellido='X', cedula='8003', activo=True,
        )

    # ── 1. Claves nuevas presentes y None sin datos ──────────────────────────
    def test_claves_nuevas_none_sin_datos(self):
        data = ReporteDiaService.reporte(FECHA)
        ea = _buscar(data, self.a.id)
        for k in ('restriccion', 'sancion', 'deuda_reprogramacion'):
            self.assertIn(k, ea)
            self.assertIsNone(ea[k])

    # ── 2. Restricciones ─────────────────────────────────────────────────────
    def test_restriccion_activa_y_vencida(self):
        RestriccionEmpleado.objects.create(
            empleado=self.a, fecha_inicio=FECHA - timedelta(5), fecha_fin=FECHA + timedelta(5),
            tipo_restriccion='Física', recomendacion='Sin cargas pesadas',
        )
        # Vencida para B (no debe aparecer)
        RestriccionEmpleado.objects.create(
            empleado=self.b, fecha_inicio=FECHA - timedelta(20), fecha_fin=FECHA - timedelta(1),
            tipo_restriccion='Vieja', recomendacion='ya pasó',
        )
        data = ReporteDiaService.reporte(FECHA)
        self.assertEqual(_buscar(data, self.a.id)['restriccion']['tipo'], 'Física')
        self.assertEqual(_buscar(data, self.a.id)['restriccion']['recomendacion'], 'Sin cargas pesadas')
        self.assertIsNone(_buscar(data, self.b.id)['restriccion'])

    def test_restriccion_indefinida(self):
        RestriccionEmpleado.objects.create(
            empleado=self.a, fecha_inicio=FECHA - timedelta(1), fecha_fin=None,
            tipo_restriccion='Perm', recomendacion='indefinida',
        )
        r = _buscar(ReporteDiaService.reporte(FECHA), self.a.id)['restriccion']
        self.assertIsNotNone(r)
        self.assertIsNone(r['fecha_fin'])

    # ── 3. Sanciones ─────────────────────────────────────────────────────────
    def test_sancion_activa_indefinida_y_futura(self):
        SancionEmpleado.objects.create(
            explorador=self.a, supervisor=self.sup, fecha_inicio=FECHA - timedelta(2),
            fecha_fin=None, motivo='Deuda de horas',
        )
        # Futura para B (no debe aparecer)
        SancionEmpleado.objects.create(
            explorador=self.b, supervisor=self.sup, fecha_inicio=FECHA + timedelta(5),
            fecha_fin=None, motivo='futura',
        )
        data = ReporteDiaService.reporte(FECHA)
        self.assertEqual(_buscar(data, self.a.id)['sancion']['motivo'], 'Deuda de horas')
        self.assertIsNone(_buscar(data, self.b.id)['sancion'])

    # ── 4-6. Deuda de doblada por reprogramación ─────────────────────────────
    def _reprog(self, **kwargs):
        origen = SolicitudCambio.objects.create(
            explorador_solicitante=self.a, explorador_receptor=self.b,
            tipo_cambio=self.tipo_dob, fecha_cambio_turno=FECHA - timedelta(30), estado='aprobada',
        )
        defaults = dict(doblada_origen=origen, explorador=self.a,
                        fecha_original=FECHA - timedelta(10), jornada_debida='PM', motivo='incapacidad')
        defaults.update(kwargs)
        return ReprogramacionDiaDoblada.objects.create(**defaults)

    def test_deuda_pendiente_sin_fecha(self):
        self._reprog(estado='pendiente', fecha_reprogramada=None)
        d = _buscar(ReporteDiaService.reporte(FECHA), self.a.id)['deuda_reprogramacion']
        self.assertEqual(d['estado'], 'pendiente')
        self.assertIsNone(d['fecha_reprogramada'])
        self.assertFalse(d['paga_hoy'])

    def test_deuda_paga_hoy(self):
        self._reprog(estado='pagada', fecha_reprogramada=FECHA)
        d = _buscar(ReporteDiaService.reporte(FECHA), self.a.id)['deuda_reprogramacion']
        self.assertTrue(d['paga_hoy'])

    def test_deuda_pagada_en_pasado_no_aparece(self):
        self._reprog(estado='pagada', fecha_reprogramada=FECHA - timedelta(2))
        self.assertIsNone(_buscar(ReporteDiaService.reporte(FECHA), self.a.id)['deuda_reprogramacion'])

    # ── 7. Smoke test del Excel ──────────────────────────────────────────────
    def test_excel_se_genera_con_hojas_y_headers(self):
        import openpyxl
        from turnos.api.views.reportes import ReporteDiaExcelView
        req = RequestFactory().get(f'/x?fecha={FECHA.isoformat()}')
        req.user = self.sup.user
        resp = ReporteDiaExcelView().get(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        self.assertEqual(wb.sheetnames, ['Resumen', 'Trabajan AM', 'Trabajan PM', 'Descansan'])
        headers = [wb['Trabajan AM'].cell(row=4, column=c).value for c in range(1, 10)]
        self.assertIn('¿Por qué trabaja hoy?', headers)
        self.assertIn('Restricción', headers)
        self.assertIn('Doblada pendiente', headers)
