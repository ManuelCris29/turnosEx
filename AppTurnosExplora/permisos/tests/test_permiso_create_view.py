"""
`permisos/views.py` estaba al 50 %, y el hueco más grande (líneas 199-271) era
justo el camino de CREACIÓN de un permiso especial.

Ese camino no es un formulario cualquiera: antes de guardar aplica cuatro reglas
de negocio, y ninguna estaba cubierta.

  1. Una sanción activa impide pedir permisos (y la sanción por deuda de doblada
     vencida se genera sola al entrar).
  2. Solo se puede pedir permiso en un día que SE TRABAJA. La comprobación usa
     `TurnoService.estado_dia`, la fuente de verdad con todas las capas, no la
     jornada base — pedirlo en un día de descanso no tiene sentido, porque no hay
     hueco que cubrir.
  3. El cierre semanal bloquea fechas de un fin de semana ya cerrado.
  4. Sin supervisor asignado el permiso se crea igual, pero avisando: si se
     bloqueara, nadie podría pedir permiso mientras administración no complete
     el organigrama.

Los tests van por la VISTA (cliente HTTP) y no por el formulario, porque tres de
las cuatro reglas viven en `form_valid`/`dispatch` y no en el form.
"""
from datetime import date, timedelta

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from permisos.models import PermisoEspecial
from turnos.models import DiaEspecial
from turnos.services.turno_service import TurnoService


class PermisoCreateTestCase(TestCase):
    url = None  # se resuelve en setUp

    def setUp(self):
        self.url = reverse('permisos_especiales_create')
        self.sala = crear_sala()
        self.supervisor = crear_empleado('Supi', 'Visor', jornada=crear_jornada('AM'),
                                         sala=self.sala)
        self.empleado = crear_empleado('Empe', 'Leado', jornada=crear_jornada('AM'),
                                       sala=self.sala, supervisor=self.supervisor)
        self.client.force_login(self.empleado.user)

    def _dia_que_trabaja(self):
        """
        Busca una fecha futura en la que el explorador realmente trabaje.

        No se puede fijar una fecha a mano: si ese día cayera en descanso por la
        rotación, el test fallaría por el motivo equivocado. Se pregunta a la misma
        fuente de verdad que usa la vista.
        """
        d = date.today() + timedelta(days=7)
        for _ in range(21):
            if TurnoService.estado_dia(self.empleado, d).get('trabaja'):
                return d
            d += timedelta(days=1)
        self.skipTest('No se encontró ningún día trabajado en las 3 semanas siguientes')

    def _dia_que_descansa(self):
        d = date.today() + timedelta(days=7)
        for _ in range(21):
            if not TurnoService.estado_dia(self.empleado, d).get('trabaja'):
                return d
            d += timedelta(days=1)
        self.skipTest('No se encontró ningún día de descanso en las 3 semanas siguientes')

    def _datos(self, fecha):
        return {
            'fecha': fecha.strftime('%Y-%m-%d'),
            'tiempo': '2.0',
            'tipo': 'PERSONAL',
            'especificacion': 'Entrada 1:30 pm',
            'motivo': 'Diligencia personal',
        }

    def _mensajes(self, respuesta):
        return [str(m) for m in get_messages(respuesta.wsgi_request)]


class TestCreacionCorrecta(PermisoCreateTestCase):

    def test_crea_el_permiso_en_estado_pendiente(self):
        fecha = self._dia_que_trabaja()

        respuesta = self.client.post(self.url, self._datos(fecha))

        permiso = PermisoEspecial.objects.get(empleado=self.empleado)
        assert permiso.estado == 'PENDIENTE'
        assert permiso.fecha_inicio == fecha
        assert permiso.fecha_fin == fecha, 'un permiso puntual empieza y acaba el mismo día'
        assert permiso.es_permanente is False
        assert respuesta.status_code == 302

    def test_asigna_el_supervisor_del_empleado(self):
        """
        El supervisor se copia AL CREAR, no se resuelve al aprobar. Si el empleado
        cambia de supervisor después, el permiso conserva a quien debía aprobarlo.
        """
        self.client.post(self.url, self._datos(self._dia_que_trabaja()))

        assert PermisoEspecial.objects.get().supervisor == self.supervisor

    def test_avisa_de_a_quien_se_notifico(self):
        respuesta = self.client.post(self.url, self._datos(self._dia_que_trabaja()),
                                     follow=True)

        assert any('Supi' in m for m in self._mensajes(respuesta))


class TestReglaDiaTrabajado(PermisoCreateTestCase):
    """Regla 2: solo se pide permiso en un día que se trabaja."""

    def test_rechaza_un_dia_de_descanso(self):
        fecha = self._dia_que_descansa()

        respuesta = self.client.post(self.url, self._datos(fecha))

        assert PermisoEspecial.objects.count() == 0
        assert respuesta.status_code == 200, 'se re-muestra el formulario con el error'
        assert 'fecha' in respuesta.context['form'].errors

    def test_el_mensaje_explica_por_que(self):
        respuesta = self.client.post(self.url, self._datos(self._dia_que_descansa()))

        error = ' '.join(respuesta.context['form'].errors['fecha'])
        assert 'descanso' in error.lower()


class TestReglaSancion(PermisoCreateTestCase):
    """
    Regla 1: una sanción activa impide pedir permisos, y el corte ocurre en
    `dispatch` — antes incluso de mostrar el formulario.
    """

    def _sancionar(self):
        from empleados.models import SancionEmpleado

        return SancionEmpleado.objects.create(
            explorador=self.empleado,
            fecha_inicio=date.today() - timedelta(days=1),
            fecha_fin=date.today() + timedelta(days=30),
            motivo='Sanción de prueba',
            supervisor=self.supervisor,
        )

    def test_un_empleado_sancionado_no_puede_abrir_el_formulario(self):
        self._sancionar()

        respuesta = self.client.get(self.url)

        assert respuesta.status_code == 302
        assert reverse('permisos_especiales_list') in respuesta.url

    def test_un_empleado_sancionado_no_puede_crear_aunque_haga_post(self):
        """
        El corte está en `dispatch`, así que también protege el POST directo: un
        bloqueo que solo escondiera el formulario no serviría de nada.
        """
        self._sancionar()

        self.client.post(self.url, self._datos(self._dia_que_trabaja()))

        assert PermisoEspecial.objects.count() == 0


class TestSinSupervisor(TestCase):
    """
    Regla 4: sin supervisor el permiso SE CREA igual, con aviso. Bloquearlo dejaría
    a la gente sin poder pedir permiso por un hueco del organigrama.
    """

    def setUp(self):
        self.sala = crear_sala()
        self.empleado = crear_empleado('Huer', 'Fano', jornada=crear_jornada('AM'),
                                       sala=self.sala)  # sin supervisor
        self.client.force_login(self.empleado.user)

    def test_se_crea_pero_avisa(self):
        fecha = date.today() + timedelta(days=7)
        for _ in range(21):
            if TurnoService.estado_dia(self.empleado, fecha).get('trabaja'):
                break
            fecha += timedelta(days=1)
        else:
            self.skipTest('sin día trabajado disponible')

        respuesta = self.client.post(reverse('permisos_especiales_create'), {
            'fecha': fecha.strftime('%Y-%m-%d'),
            'tiempo': '2.0',
            'tipo': 'PERSONAL',
            'especificacion': 'x',
            'motivo': 'y',
        }, follow=True)

        assert PermisoEspecial.objects.count() == 1
        assert PermisoEspecial.objects.get().supervisor is None
        mensajes = [str(m) for m in get_messages(respuesta.wsgi_request)]
        assert any('supervisor' in m.lower() for m in mensajes)


class TestDiaNoLaborablePorDiaEspecial(PermisoCreateTestCase):
    """
    `_dia_no_laborable` se apoya en `estado_dia`, que mira TODAS las capas. Un día
    de mantenimiento no se trabaja, así que tampoco se puede pedir permiso en él
    aunque la jornada base diga que sí.
    """

    def test_un_dia_de_mantenimiento_no_admite_permiso(self):
        fecha = self._dia_que_trabaja()
        DiaEspecial.objects.create(fecha=fecha, tipo='mantenimiento', activo=True)

        respuesta = self.client.post(self.url, self._datos(fecha))

        assert PermisoEspecial.objects.count() == 0
        assert respuesta.status_code == 200
