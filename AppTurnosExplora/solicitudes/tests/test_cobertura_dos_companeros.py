"""
CAMBIO DESCANSO — cobertura de día completo con DOS compañeros.

Son dos solicitudes (AM y PM) que solo tienen sentido juntas: media cobertura dejaría al
explorador con media jornada suya sin resolver. Antes se enviaban en dos POST secuenciales desde
el navegador y, si el segundo fallaba, quedaba creada solo la de AM. Ahora van en UN POST y el
servidor las crea en una transacción: o las dos o ninguna.

Escenario de temporada usado:
- Solicitante grupo PM; los dos compañeros, grupo AM (son los que descansan el día que él cede).
- Día de cesión: descansa el grupo AM → el solicitante tiene ahí su día COMPLETO (AM+PM).
- Día de pago (misma semana): descansa el grupo PM → el solicitante está libre y cada compañero
  trabaja el día completo, así que él puede cubrirle la AM a uno y la PM al otro.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import AsignarJornadaExplorador, DescansoSemanaManual, Sala


class CoberturaDosCompanerosTest(TestCase):
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO DESCANSO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CD2', activo=True)

        self.solicitante = self._empleado('sol.cob', 'Sol', '9101', self.pm)
        self.comp_am = self._empleado('comp.am', 'CompAM', '9102', self.am)
        self.comp_pm = self._empleado('comp.pm', 'CompPM', '9103', self.am)

        # Semana de temporada futura: martes (cesión) y jueves (pago) de la próxima semana.
        hoy = timezone.localdate()
        lunes = hoy - timedelta(days=hoy.weekday()) + timedelta(days=7)
        self.cesion = lunes + timedelta(days=1)   # martes
        self.pago = lunes + timedelta(days=3)     # jueves

        # Día de cesión: descansa el grupo AM → el solicitante (PM) tiene día completo.
        DescansoSemanaManual.objects.create(fecha=self.cesion, jornada=self.am,
                                            motivo='temporada', descripcion='t', activo=True)

        self.client = Client()
        self.client.force_login(self.solicitante.user)
        self.url = reverse('solicitudes:procesar_solicitud')

    def _empleado(self, username, nombre, cedula, jornada):
        u = User.objects.create_user(username, password='x')
        e = Empleado.objects.create(user=u, nombre=nombre, apellido='Test',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _post(self, **over):
        datos = {
            'tipo_solicitud_id': self.tipo.id,
            'modo_descanso': 'semana',
            'fecha_solicitud': self.cesion.strftime('%Y-%m-%d'),
            'fecha_pago': self.pago.strftime('%Y-%m-%d'),
            'submodalidad_semana': 'cobertura_misma_semana',
            'comentarios': 'Cobertura con dos compañeros',
            'empleado_receptor': self.comp_am.id,
            'empleado_receptor_2': self.comp_pm.id,
        }
        datos.update(over)
        return self.client.post(self.url, datos)

    def _pago_es_dia_libre_del_solicitante(self):
        """Día de pago: descansa el grupo PM → el solicitante está libre y los compañeros (AM)
        trabajan el día completo, así que él puede cubrirle la AM a uno y la PM al otro."""
        DescansoSemanaManual.objects.create(fecha=self.pago, jornada=self.pm,
                                            motivo='temporada', descripcion='t', activo=True)

    # ------------------------------------------------------------------ casos
    def test_crea_las_dos_solicitudes_en_un_solo_envio(self):
        self._pago_es_dia_libre_del_solicitante()
        r = self._post()
        self.assertEqual(r.status_code, 201, r.content)

        creadas = SolicitudCambio.objects.filter(tipo_cambio=self.tipo).select_related('doblada')
        self.assertEqual(creadas.count(), 2)
        por_jornada = {s.doblada.jornada_cedida: s for s in creadas}
        self.assertEqual(set(por_jornada), {'AM', 'PM'})
        self.assertEqual(por_jornada['AM'].explorador_receptor_id, self.comp_am.id)
        self.assertEqual(por_jornada['PM'].explorador_receptor_id, self.comp_pm.id)
        for s in creadas:
            self.assertEqual(s.doblada.submodalidad_semana, 'cobertura_misma_semana')
            self.assertEqual(s.estado, 'pendiente')

    def test_si_falla_una_jornada_no_se_crea_ninguna(self):
        """Sin el descanso del grupo PM en el día de pago, los compañeros solo trabajan AM: la
        solicitud de la jornada PM no es válida. Antes quedaba creada la de AM; ahora, ninguna."""
        r = self._post()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(SolicitudCambio.objects.count(), 0,
                         'No debió quedar ninguna solicitud a medias')
        self.assertIn('PM', r.json().get('error', ''))

    def test_mismo_companero_dos_veces_rechazado(self):
        self._pago_es_dia_libre_del_solicitante()
        r = self._post(empleado_receptor_2=self.comp_am.id)
        self.assertEqual(r.status_code, 400)
        self.assertIn('distintas', r.json().get('error', ''))
        self.assertEqual(SolicitudCambio.objects.count(), 0)

    def test_companero_inexistente_rechazado(self):
        self._pago_es_dia_libre_del_solicitante()
        r = self._post(empleado_receptor_2=999999)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(SolicitudCambio.objects.count(), 0)

    def test_dia_de_pago_donde_ya_doblo_es_rechazado(self):
        """
        Si el solicitante ya trabaja AM+PM el día de pago no le queda jornada con la que pagar:
        cubrirle la jornada al compañero sería ficticio (ya iba a estar ese día completo) y no
        genera deuda (la regla exige partir de UNA sola jornada). El formulario lo avisa, pero
        el backend debe rechazarlo por su cuenta.
        """
        from turnos.models import Turno
        for jornada in (self.am, self.pm):
            Turno.objects.create(explorador=self.solicitante, fecha=self.pago,
                                 jornada=jornada, sala=self.sala)

        r = self._post(empleado_receptor_2='', tipo_cesion='cesion_parcial',
                       jornada_cedida='AM', empleado_receptor=self.comp_am.id)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn('ya trabajas esa jornada', r.json().get('error', ''))
        self.assertEqual(SolicitudCambio.objects.count(), 0)

    def test_candidatos_excluye_a_quien_no_trabaja_esa_jornada_el_dia_de_pago(self):
        """
        El desplegable y la validación deben mirar las MISMAS dos fechas. El día de pago, el
        compañero (grupo AM) trabaja AM: se le puede pagar la AM, pero no la PM. Antes el
        desplegable lo ofrecía igual para PM porque solo miraba el día de cesión, y el envío
        moría con "no hay jornada que puedas pagarle ese día".
        """
        url = reverse('solicitudes:cobertura_candidatos')
        params = {'fecha_trabajo': self.cesion.strftime('%Y-%m-%d'),
                  'fecha_pago': self.pago.strftime('%Y-%m-%d')}

        def _cand(opcion):
            r = self.client.get(url, dict(params, opcion=opcion),
                                HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(r.status_code, 200, r.content)
            data = r.json().get('data') or r.json()
            return {c['id']: c for c in data['candidatos']}[self.comp_am.id]

        am = _cand('AM')
        self.assertTrue(am['disponible'], f"Debía poder cubrir/pagar la AM: {am['motivo']}")

        pm = _cand('PM')
        self.assertFalse(pm['disponible'],
                         'No trabaja PM el día de pago: no debía ofrecerse para la PM.')
        self.assertIn('pagarle', pm['motivo'])

    def test_sin_segundo_companero_usa_el_flujo_normal(self):
        """Sin `empleado_receptor_2` no se activa el camino de pareja: sigue el flujo de siempre
        (una sola solicitud parcial), que aquí falla por no indicar la jornada cedida."""
        self._pago_es_dia_libre_del_solicitante()
        r = self._post(empleado_receptor_2='')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(SolicitudCambio.objects.count(), 0)
