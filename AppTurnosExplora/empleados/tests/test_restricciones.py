"""
Tests de las vistas y el formulario de restricciones.

Cubren lo que la auditoría detectó: el permiso resuelto con dos criterios
distintos (is_staff vs rol Supervisor), los filtros con basura, la restricción
indefinida y el solapamiento.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.forms import RestriccionEmpleadoForm
from empleados.models import Empleado, EmpleadoRole, RestriccionEmpleado, Role


def _empleado(username, nombre, rol, staff=False):
    user = User.objects.create_user(username=username, password='x', is_staff=staff)
    emp = Empleado.objects.create(user=user, nombre=nombre, apellido='Test',
                                  cedula=username, activo=True)
    EmpleadoRole.objects.create(empleado=emp, role=rol)
    return emp


class RestriccionesBaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_sup = Role.objects.create(nombre='Supervisor')
        cls.rol_exp = Role.objects.create(nombre='Explorador')
        cls.sup = _empleado('sup', 'Supervisora', cls.rol_sup)          # rol, sin staff
        cls.staff = _empleado('jefe', 'Jefe', cls.rol_sup, staff=True)
        cls.exp = _empleado('exp', 'Explorador', cls.rol_exp)
        cls.otro_exp = _empleado('exp2', 'Otro', cls.rol_exp)
        cls.hoy = timezone.localdate()

    def _restriccion(self, empleado, inicio_offset=0, dias=15):
        inicio = self.hoy + timedelta(days=inicio_offset)
        return RestriccionEmpleado.objects.create(
            empleado=empleado,
            fecha_inicio=inicio,
            fecha_fin=None if dias is None else inicio + timedelta(days=dias - 1),
            recomendacion='Evitar levantar peso',
            tipo_restriccion='Peso',
        )


class RestriccionFiltrosTest(RestriccionesBaseTest):
    """Un parámetro inválido se ignora; nunca debe reventar la vista."""

    def setUp(self):
        self.client.force_login(self.staff.user)

    def test_visualizar_con_empleado_no_numerico(self):
        resp = self.client.get(reverse('restricciones_visualizar'), {'empleado': 'abc'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['filtro_empleado'], '')

    def test_visualizar_con_fechas_invalidas(self):
        resp = self.client.get(reverse('restricciones_visualizar'),
                               {'fecha_desde': 'ayer', 'fecha_hasta': '32/13/2026'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['filtro_fecha_desde'], '')
        self.assertEqual(resp.context['filtro_fecha_hasta'], '')

    def test_visualizar_filtra_por_empleado_valido(self):
        self._restriccion(self.exp)
        self._restriccion(self.otro_exp)
        resp = self.client.get(reverse('restricciones_visualizar'), {'empleado': self.exp.id})
        self.assertEqual([r.empleado_id for r in resp.context['restricciones']], [self.exp.id])

    def test_visualizar_filtra_por_rango_de_fechas(self):
        self._restriccion(self.exp, inicio_offset=-60)
        reciente = self._restriccion(self.otro_exp, inicio_offset=-1)
        desde = (self.hoy - timedelta(days=10)).isoformat()
        resp = self.client.get(reverse('restricciones_visualizar'), {'fecha_desde': desde})
        self.assertEqual([r.id for r in resp.context['restricciones']], [reciente.id])

    def test_listado_con_explorador_no_numerico(self):
        resp = self.client.get(reverse('restricciones_list'), {'explorador': "1 OR 1=1"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['filtro_explorador'], '')

    def test_listado_filtra_estado_en_servidor(self):
        self._restriccion(self.exp, inicio_offset=-60, dias=15)   # finalizada
        self._restriccion(self.otro_exp, dias=15)                 # activa
        activas = self.client.get(reverse('restricciones_list'), {'estado': 'activa'})
        self.assertEqual([r.empleado_id for r in activas.context['restricciones']], [self.otro_exp.id])
        finalizadas = self.client.get(reverse('restricciones_list'), {'estado': 'finalizada'})
        self.assertEqual([r.empleado_id for r in finalizadas.context['restricciones']], [self.exp.id])

    def test_listado_estado_invalido_muestra_todas(self):
        self._restriccion(self.exp, inicio_offset=-60, dias=15)
        self._restriccion(self.otro_exp, dias=15)
        resp = self.client.get(reverse('restricciones_list'), {'estado': 'lo-que-sea'})
        self.assertEqual(resp.context['filtro_estado'], 'todos')
        self.assertEqual(len(resp.context['restricciones']), 2)

    def test_indefinida_cuenta_como_activa(self):
        self._restriccion(self.exp, inicio_offset=-100, dias=None)
        resp = self.client.get(reverse('restricciones_list'))
        self.assertEqual(resp.context['total_activos'], 1)
        self.assertEqual(resp.context['total_finalizados'], 0)


class RestriccionPermisosTest(RestriccionesBaseTest):
    """El supervisor por rol (sin staff) debe ver lo mismo que el staff."""

    def test_supervisor_no_staff_ve_todas_las_restricciones(self):
        self._restriccion(self.exp)
        self.client.force_login(self.sup.user)
        for url in (reverse('restricciones_list'), reverse('restricciones_visualizar')):
            resp = self.client.get(url)
            self.assertTrue(resp.context['es_supervisor'], url)
            self.assertEqual(len(resp.context['restricciones']), 1, url)

    def test_supervisor_no_staff_puede_filtrar_por_explorador(self):
        self._restriccion(self.exp)
        self._restriccion(self.otro_exp)
        self.client.force_login(self.sup.user)
        resp = self.client.get(reverse('restricciones_list'), {'explorador': self.exp.id})
        self.assertEqual([r.empleado_id for r in resp.context['restricciones']], [self.exp.id])

    def test_explorador_solo_ve_las_suyas(self):
        self._restriccion(self.exp)
        self._restriccion(self.otro_exp)
        self.client.force_login(self.exp.user)
        resp = self.client.get(reverse('restricciones_list'))
        self.assertFalse(resp.context['es_supervisor'])
        self.assertEqual([r.empleado_id for r in resp.context['restricciones']], [self.exp.id])

    def test_explorador_no_puede_filtrar_por_otro_empleado(self):
        self._restriccion(self.otro_exp)
        self.client.force_login(self.exp.user)
        resp = self.client.get(reverse('restricciones_visualizar'), {'empleado': self.otro_exp.id})
        self.assertEqual(len(resp.context['restricciones']), 0)

    def test_explorador_no_puede_crear(self):
        self.client.force_login(self.exp.user)
        self.assertEqual(self.client.get(reverse('restricciones_create')).status_code, 403)

    def test_supervisor_no_staff_puede_crear(self):
        self.client.force_login(self.sup.user)
        self.assertEqual(self.client.get(reverse('restricciones_create')).status_code, 200)


class RestriccionFormularioTest(RestriccionesBaseTest):

    def _datos(self, **extra):
        datos = {
            'empleado': self.exp.id,
            'fecha_inicio': self.hoy.isoformat(),
            'fecha_fin': (self.hoy + timedelta(days=14)).isoformat(),
            'recomendacion': 'Evitar levantar peso',
            'tipo_restriccion': 'Peso',
        }
        datos.update(extra)
        return datos

    def test_crea_restriccion_con_rango(self):
        form = RestriccionEmpleadoForm(data=self._datos())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().fecha_fin, self.hoy + timedelta(days=14))

    def test_fecha_fin_obligatoria_si_no_es_indefinida(self):
        form = RestriccionEmpleadoForm(data=self._datos(fecha_fin=''))
        self.assertFalse(form.is_valid())
        self.assertIn('fecha_fin', form.errors)

    def test_indefinida_no_exige_fecha_fin(self):
        form = RestriccionEmpleadoForm(data=self._datos(fecha_fin='', indefinida='on'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().fecha_fin)

    def test_indefinida_ignora_la_fecha_fin_escrita(self):
        form = RestriccionEmpleadoForm(data=self._datos(indefinida='on'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().fecha_fin)

    def test_editar_indefinida_marca_el_check(self):
        restriccion = self._restriccion(self.exp, dias=None)
        form = RestriccionEmpleadoForm(instance=restriccion)
        self.assertTrue(form.fields['indefinida'].initial)

    def test_fecha_fin_anterior_al_inicio(self):
        form = RestriccionEmpleadoForm(
            data=self._datos(fecha_fin=(self.hoy - timedelta(days=1)).isoformat())
        )
        self.assertFalse(form.is_valid())
        self.assertIn('fecha_fin', form.errors)

    def test_rechaza_solapamiento(self):
        self._restriccion(self.exp, inicio_offset=0, dias=15)
        form = RestriccionEmpleadoForm(
            data=self._datos(fecha_inicio=(self.hoy + timedelta(days=5)).isoformat(),
                             fecha_fin=(self.hoy + timedelta(days=30)).isoformat())
        )
        self.assertFalse(form.is_valid())
        self.assertIn('se solapa', ' '.join(form.non_field_errors()))

    def test_solapamiento_contra_indefinida(self):
        self._restriccion(self.exp, inicio_offset=-10, dias=None)
        form = RestriccionEmpleadoForm(data=self._datos())
        self.assertFalse(form.is_valid())

    def test_permite_rango_sin_solape(self):
        self._restriccion(self.exp, inicio_offset=-60, dias=15)
        form = RestriccionEmpleadoForm(data=self._datos())
        self.assertTrue(form.is_valid(), form.errors)

    def test_solapamiento_solo_afecta_al_mismo_empleado(self):
        self._restriccion(self.otro_exp, inicio_offset=0, dias=15)
        form = RestriccionEmpleadoForm(data=self._datos())
        self.assertTrue(form.is_valid(), form.errors)

    def test_editar_no_choca_consigo_misma(self):
        restriccion = self._restriccion(self.exp)
        form = RestriccionEmpleadoForm(
            data=self._datos(fecha_inicio=restriccion.fecha_inicio.isoformat(),
                             fecha_fin=restriccion.fecha_fin.isoformat()),
            instance=restriccion,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_empleado_inactivo_no_es_seleccionable(self):
        Empleado.objects.filter(pk=self.otro_exp.pk).update(activo=False)
        form = RestriccionEmpleadoForm()
        self.assertNotIn(self.otro_exp, form.fields['empleado'].queryset)
        self.assertIn(self.exp, form.fields['empleado'].queryset)

    def test_editar_conserva_al_empleado_inactivo(self):
        restriccion = self._restriccion(self.otro_exp)
        Empleado.objects.filter(pk=self.otro_exp.pk).update(activo=False)
        form = RestriccionEmpleadoForm(instance=restriccion)
        self.assertIn(self.otro_exp, form.fields['empleado'].queryset)
