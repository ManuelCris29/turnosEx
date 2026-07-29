"""
Permiso de MEDIA JORNADA TEMPORADA (sub-tipo del formulario de Cambio de Día de Descanso).

Este permiso llega por su propio endpoint, así que el gate del orquestador de solicitudes NO lo
cubre: las validaciones de días pasados y de cierre semanal tienen que estar aquí. Estos tests
cubren justo eso; el resto del flujo (día completo de temporada, compensación) vive en la vista.
"""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado
from solicitudes.models import CierreSolicitudesConfig


class MediaJornadaTemporadaGatesTest(TestCase):
    def setUp(self):
        u = User.objects.create_user('mj.temp', password='x')
        self.emp = Empleado.objects.create(user=u, nombre='Media', apellido='Jornada',
                                           cedula='7701', activo=True)
        self.client = Client()
        self.client.force_login(u)
        self.url = reverse('permisos_media_jornada_create')

    @staticmethod
    def _lunes_futuro(semanas=1):
        hoy = timezone.localdate()
        d = hoy + timedelta(days=1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        return d + timedelta(days=7 * (semanas - 1))

    def _post(self, f_trabajo, f_comp):
        return self.client.post(self.url, {
            'fecha_trabajo': f_trabajo.strftime('%Y-%m-%d'),
            'fecha_compensacion': f_comp.strftime('%Y-%m-%d'),
            'jornada_trabaja': 'AM',
            'motivo': 'Prueba',
        })

    def test_dia_pasado_rechazado(self):
        """Antes no había ningún control contra `hoy`: se podía pedir un lunes ya pasado."""
        hoy = timezone.localdate()
        lunes_pasado = hoy - timedelta(days=hoy.weekday() + 7)
        r = self._post(lunes_pasado, lunes_pasado + timedelta(days=2))
        self.assertEqual(r.status_code, 400)
        self.assertIn('pasados', r.json().get('error', ''))

    def test_cierre_semanal_bloquea(self):
        """Con el cierre activo, este endpoint no puede ser una puerta trasera.

        Busca con el propio servicio un día lun-vie que YA esté bloqueado y siga siendo futuro
        (la ventana del fin de semana en curso), para no depender del día en que se corra.
        """
        from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService as CS
        cfg = CierreSolicitudesConfig.obtener()
        cfg.habilitado = True
        cfg.dia_cierre = 'jueves'
        cfg.hora_cierre = time(0, 1)
        cfg.save()

        hoy = timezone.localdate()
        objetivo = next((hoy + timedelta(days=i) for i in range(0, 10)
                         if (hoy + timedelta(days=i)).weekday() < 5
                         and CS.fecha_bloqueada(hoy + timedelta(days=i))), None)
        if objetivo is None:
            self.skipTest('Hoy no hay ningún día lun-vie futuro dentro de una ventana ya cerrada.')

        r = self._post(objetivo, objetivo)
        self.assertEqual(r.status_code, 400)
        self.assertIn('Cierre de solicitudes', r.json().get('error', ''))

    def test_cierre_deshabilitado_no_bloquea_por_cierre(self):
        """Sin cierre activo, la petición avanza más allá del gate (falla luego por temporada)."""
        cfg = CierreSolicitudesConfig.obtener()
        cfg.habilitado = False
        cfg.save()
        lunes = self._lunes_futuro()
        r = self._post(lunes, lunes + timedelta(days=2))
        self.assertEqual(r.status_code, 400)
        self.assertNotIn('Cierre de solicitudes', r.json().get('error', ''))
