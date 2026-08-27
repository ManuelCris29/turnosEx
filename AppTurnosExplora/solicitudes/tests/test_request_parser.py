"""
Tests para SolicitudRequestParser.

Cubren:
- validate_required() rechaza campos faltantes por tipo
- validate_required() aprueba cuando están todos los campos
- get_fechas_del_post() extrae las fechas correctamente
"""
from django.test import TestCase

from solicitudes.services.solicitud_request_parser import SolicitudRequestParser


class ValidateRequiredTest(TestCase):

    def _post(self, **kwargs):
        """QueryDict mínimo simulado como dict con soporte de getlist."""
        class FakePost(dict):
            def getlist(self, key):
                val = self.get(key, [])
                return val if isinstance(val, list) else [val]
        return FakePost(kwargs)

    # --- CT ---
    def test_ct_sin_receptor_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('CT', self._post(
            fecha_solicitud='2027-08-01'
        ))
        self.assertFalse(ok)

    def test_ct_sin_fecha_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('CT', self._post(
            empleado_receptor='5',
        ))
        self.assertFalse(ok)

    def test_ct_completo_pasa(self):
        ok, _ = SolicitudRequestParser.validate_required('CT', self._post(
            empleado_receptor='5',
            fecha_solicitud='2027-08-01',
        ))
        self.assertTrue(ok)

    # --- DOBLADA ---
    def test_doblada_sin_fecha_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('DOBLADA', self._post(
            empleado_receptor='5',
        ))
        self.assertFalse(ok)

    def test_doblada_sin_receptor_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('DOBLADA', self._post(
            fecha_solicitud='2027-08-01',
        ))
        self.assertFalse(ok)

    def test_doblada_completa_pasa(self):
        ok, _ = SolicitudRequestParser.validate_required('DOBLADA', self._post(
            empleado_receptor='5',
            fecha_solicitud='2027-08-01',
        ))
        self.assertTrue(ok)

    # --- D FDS ---
    def test_d_fds_sin_fecha_pago_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('D FDS', self._post(
            empleado_receptor='5',
            fecha_solicitud='2027-08-02',
        ))
        self.assertFalse(ok)

    def test_d_fds_completa_pasa(self):
        ok, _ = SolicitudRequestParser.validate_required('D FDS', self._post(
            empleado_receptor='5',
            fecha_solicitud='2027-08-02',
            fecha_pago='2027-08-09',
        ))
        self.assertTrue(ok)

    # --- CT PERMANENTE ---
    def test_ct_permanente_sin_receptor_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('CT PERMANENTE', self._post(
            fecha_inicio='2027-08-01',
            fecha_fin='2027-09-01',
        ))
        self.assertFalse(ok)

    def test_ct_permanente_sin_fechas_falla(self):
        ok, _ = SolicitudRequestParser.validate_required('CT PERMANENTE', self._post(
            empleado_receptor='5',
        ))
        self.assertFalse(ok)

    def test_ct_permanente_completa_pasa(self):
        ok, _ = SolicitudRequestParser.validate_required('CT PERMANENTE', self._post(
            empleado_receptor='5',
            fecha_inicio='2027-08-01',
            fecha_fin='2027-09-01',
        ))
        self.assertTrue(ok)


class GetFechasDelPostTest(TestCase):

    def test_extrae_fecha_cambio_turno(self):
        fechas = SolicitudRequestParser.get_fechas_del_post({
            'fecha_cambio_turno': '2027-08-01',
        })
        from datetime import date
        self.assertIn(date(2027, 8, 1), fechas)

    def test_extrae_fecha_pago(self):
        fechas = SolicitudRequestParser.get_fechas_del_post({
            'fecha_cambio_turno': '2027-08-01',
            'fecha_pago': '2027-08-15',
        })
        from datetime import date
        self.assertIn(date(2027, 8, 15), fechas)

    def test_ignora_fechas_vacias(self):
        fechas = SolicitudRequestParser.get_fechas_del_post({
            'fecha_cambio_turno': '',
            'fecha_pago': None,
        })
        self.assertEqual(fechas, [])

    def test_extrae_fechas_ct_permanente(self):
        fechas = SolicitudRequestParser.get_fechas_del_post({
            'fecha_inicio': '2027-08-01',
            'fecha_fin': '2027-09-01',
        })
        from datetime import date
        self.assertIn(date(2027, 8, 1), fechas)
        self.assertIn(date(2027, 9, 1), fechas)
