"""
Tests de las vistas y el formulario de sanciones.

Cubren lo que la auditoría detectó: filtros con basura, el permiso resuelto con
dos criterios distintos, la sanción indefinida, el solapamiento y quién queda
registrado como supervisor.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.forms import SancionEmpleadoForm
from empleados.models import Empleado, EmpleadoRole, Role, SancionEmpleado


def _empleado(username, nombre, rol, staff=False):
    user = User.objects.create_user(username=username, password='x', is_staff=staff)
    emp = Empleado.objects.create(user=user, nombre=nombre, apellido='Test',
                                  cedula=username, activo=True)
    EmpleadoRole.objects.create(empleado=emp, role=rol)
    return emp


class SancionesBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_sup = Role.objects.create(nombre='Supervisor')
        cls.rol_exp = Role.objects.create(nombre='Explorador')
        cls.sup = _empleado('sup', 'Supervisora', cls.rol_sup)          # rol, sin staff
        cls.staff = _empleado('jefe', 'Jefe', cls.rol_sup, staff=True)
        cls.exp = _empleado('exp', 'Explorador', cls.rol_exp)
        cls.otro_exp = _empleado('exp2', 'Otro', cls.rol_exp)
        cls.hoy = timezone.localdate()

    def _sancion(self, explorador, inicio_offset=0, dias=15, supervisor=None):
        inicio = self.hoy + timedelta(days=inicio_offset)
        return SancionEmpleado.objects.create(
            explorador=explorador,
            supervisor=supervisor or self.sup,
            fecha_inicio=inicio,
            fecha_fin=None if dias is None else inicio + timedelta(days=dias - 1),
            motivo='Motivo de prueba',
        )


class SancionFiltrosTest(SancionesBaseTest):
    """Un parámetro inválido se ignora; nunca debe reventar la vista."""

    def setUp(self):
        self.client.force_login(self.staff.user)

    def test_visualizar_con_empleado_no_numerico(self):
        resp = self.client.get(reverse('sanciones_visualizar'), {'empleado': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['filtro_empleado'], '')

    def test_visualizar_con_fechas_invalidas(self):
        resp = self.client.get(reverse('sanciones_visualizar'),
                               {'fecha_desde': 'ayer', 'fecha_hasta': '32/13/2026'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['filtro_fecha_desde'], '')

    def test_visualizar_filtra_por_empleado_valido(self):
        self._sancion(self.exp)
        self._sancion(self.otro_exp)
        resp = self.client.get(reverse('sanciones_visualizar'), {'empleado': self.exp.id})
        self.assertEqual([s.explorador_id for s in resp.context['sanciones']], [self.exp.id])

    def test_listado_con_explorador_no_numerico(self):
        resp = self.client.get(reverse('sanciones_list'), {'explorador': "1 OR 1=1"})
        self.assertEqual(resp.status_code, 200)

    def test_listado_filtra_estado_en_servidor(self):
        self._sancion(self.exp, inicio_offset=-60, dias=15)   # finalizada
        self._sancion(self.otro_exp, dias=15)                 # activa
        activas = self.client.get(reverse('sanciones_list'), {'estado': 'activa'})
        self.assertEqual([s.explorador_id for s in activas.context['sanciones']], [self.otro_exp.id])
        finalizadas = self.client.get(reverse('sanciones_list'), {'estado': 'finalizada'})
        self.assertEqual([s.explorador_id for s in finalizadas.context['sanciones']], [self.exp.id])


class SancionPermisosTest(SancionesBaseTest):
    """El supervisor por rol (sin staff) debe ver lo mismo que el staff."""

    def test_supervisor_no_staff_ve_todas_las_sanciones(self):
        self._sancion(self.exp)
        self.client.force_login(self.sup.user)
        for url in (reverse('sanciones_list'), reverse('sanciones_visualizar')):
            resp = self.client.get(url)
            self.assertTrue(resp.context['es_supervisor'], url)
            self.assertEqual(len(resp.context['sanciones']), 1, url)

    def test_explorador_solo_ve_las_suyas(self):
        self._sancion(self.exp)
        self._sancion(self.otro_exp)
        self.client.force_login(self.exp.user)
        resp = self.client.get(reverse('sanciones_list'))
        self.assertFalse(resp.context['es_supervisor'])
        self.assertEqual([s.explorador_id for s in resp.context['sanciones']], [self.exp.id])

    def test_explorador_no_puede_crear(self):
        self.client.force_login(self.exp.user)
        self.assertEqual(self.client.get(reverse('sanciones_create')).status_code, 403)

    def test_usuario_sin_empleado_no_puede_crear(self):
        user = User.objects.create_user(username='fantasma', password='x', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('sanciones_create')).status_code, 403)


class SancionFormularioTest(SancionesBaseTest):

    def _datos(self, **extra):
        datos = {
            'explorador': self.exp.id,
            'fecha_inicio': self.hoy.isoformat(),
            'duracion': '15',
            'motivo': 'Llegadas tarde reiteradas',
        }
        datos.update(extra)
        return datos

    def test_supervisor_es_quien_registra(self):
        form = SancionEmpleadoForm(data=self._datos(), supervisor=self.sup)
        self.assertTrue(form.is_valid(), form.errors)
        sancion = form.save()
        self.assertEqual(sancion.supervisor_id, self.sup.id)
        self.assertEqual(sancion.fecha_fin, self.hoy + timedelta(days=14))

    def test_supervisor_no_se_puede_falsear_por_post(self):
        self.client.force_login(self.staff.user)
        self.client.post(reverse('sanciones_create'), self._datos(supervisor=self.sup.id))
        self.assertEqual(SancionEmpleado.objects.get().supervisor_id, self.staff.id)

    def test_duracion_indefinida(self):
        form = SancionEmpleadoForm(data=self._datos(duracion='indefinida'), supervisor=self.sup)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().fecha_fin)

    def test_editar_indefinida_la_conserva(self):
        sancion = self._sancion(self.exp, dias=None)
        form = SancionEmpleadoForm(instance=sancion, supervisor=self.staff)
        self.assertEqual(form.fields['duracion'].initial, 'indefinida')

    def test_editar_conserva_el_supervisor_original(self):
        sancion = self._sancion(self.exp)
        form = SancionEmpleadoForm(
            data=self._datos(fecha_inicio=sancion.fecha_inicio.isoformat()),
            instance=sancion, supervisor=self.staff,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().supervisor_id, self.sup.id)

    def test_rechaza_solapamiento(self):
        self._sancion(self.exp, inicio_offset=0, dias=15)
        form = SancionEmpleadoForm(
            data=self._datos(fecha_inicio=(self.hoy + timedelta(days=5)).isoformat()),
            supervisor=self.staff,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('se solapa', ' '.join(form.non_field_errors()))

    def test_solapamiento_contra_indefinida(self):
        self._sancion(self.exp, inicio_offset=-10, dias=None)
        form = SancionEmpleadoForm(data=self._datos(), supervisor=self.staff)
        self.assertFalse(form.is_valid())

    def test_permite_rango_contiguo_sin_solape(self):
        self._sancion(self.exp, inicio_offset=-30, dias=15)
        form = SancionEmpleadoForm(data=self._datos(), supervisor=self.staff)
        self.assertTrue(form.is_valid(), form.errors)

    def test_editar_no_choca_consigo_misma(self):
        sancion = self._sancion(self.exp)
        form = SancionEmpleadoForm(
            data=self._datos(fecha_inicio=sancion.fecha_inicio.isoformat()),
            instance=sancion, supervisor=self.sup,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_no_puede_sancionarse_a_si_mismo(self):
        EmpleadoRole.objects.create(empleado=self.sup, role=self.rol_exp)
        form = SancionEmpleadoForm(data=self._datos(explorador=self.sup.id), supervisor=self.sup)
        self.assertFalse(form.is_valid())

    def test_dias_personalizados_obligatorios(self):
        form = SancionEmpleadoForm(data=self._datos(duracion='otro'), supervisor=self.sup)
        self.assertFalse(form.is_valid())
        self.assertIn('dias_personalizado', form.errors)

    def test_explorador_inactivo_no_es_seleccionable(self):
        Empleado.objects.filter(pk=self.otro_exp.pk).update(activo=False)
        form = SancionEmpleadoForm(supervisor=self.sup)
        self.assertNotIn(self.otro_exp, form.fields['explorador'].queryset)
        self.assertIn(self.exp, form.fields['explorador'].queryset)
