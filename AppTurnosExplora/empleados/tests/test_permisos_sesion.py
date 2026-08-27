"""
Tests de los permisos de sesión (/empleados/permisos-sesion/<id>/).

Lo que protegen, en orden de importancia:

1. Que ocultar el enlace del menú no sea el único control: la URL directa
   también se niega. Es la mitad que de verdad hace de permiso.
2. Que un supervisor no pueda editarse la matriz a sí mismo (sería una
   escalada trivial: se devolvería lo que el administrador le quitó).
3. Que el catálogo no se desincronice del enrutado — un `url_name` mal escrito
   no daría error, simplemente dejaría esa pantalla sin vigilar para siempre.
"""
import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from core.permisos_sesion import sesiones_habilitadas
from core.sesiones import CODIGOS, POR_URL_NAME, SESIONES
from empleados.models import Empleado, EmpleadoRole, PermisoSesion, Role


class PermisosSesionBaseTest(TestCase):
    def setUp(self):
        self.rol_supervisor = Role.objects.create(nombre=Role.SUPERVISOR)
        self.rol_explorador = Role.objects.create(nombre=Role.EXPLORADOR)

        self.admin = self._crear('admin', '1', staff=True)
        self.supervisor = self._crear('super', '2', rol=self.rol_supervisor)
        self.explorador = self._crear('explo', '3', rol=self.rol_explorador)

    def _crear(self, username, cedula, staff=False, rol=None):
        user = User.objects.create_user(username=username, password='x', is_staff=staff)
        empleado = Empleado.objects.create(
            user=user, nombre=username, apellido='Prueba', cedula=cedula,
        )
        if rol is not None:
            EmpleadoRole.objects.create(empleado=empleado, role=rol)
        return empleado


class CatalogoTest(PermisosSesionBaseTest):
    def test_todos_los_url_names_existen(self):
        """Un nombre mal escrito deja la pantalla sin vigilancia y en silencio."""
        faltan = []
        for nombre in POR_URL_NAME:
            try:
                reverse(nombre)
            except NoReverseMatch as exc:
                # Las rutas con argumentos fallan por falta de argumentos, no
                # porque el nombre no exista: solo interesa el segundo caso.
                if 'not a valid view function or pattern name' in str(exc):
                    faltan.append(nombre)
        self.assertEqual(faltan, [], f'URLs inexistentes en core.sesiones: {faltan}')

    def test_una_url_pertenece_a_una_sola_sesion(self):
        """Si dos sesiones reclaman la misma URL, una de las dos no se aplica."""
        vistos = [n for s in SESIONES for n in s.url_names]
        self.assertEqual(len(vistos), len(set(vistos)))


class MenuSincronizadoTest(TestCase):
    """El menú y el catálogo no se pueden separar, y nadie se acuerda a los tres meses.

    El catálogo de `core.sesiones` se escribe a mano: Django no puede adivinar
    cuáles de sus cientos de rutas son "módulos del menú" y cuáles son endpoints
    AJAX. Así que añadir una pantalla al menú y olvidarse del catálogo no rompe
    nada — y eso es justo el problema: la pantalla nace fuera del sistema de
    permisos, no aparece en /empleados/permisos-sesion/ y no se le puede apagar
    a nadie, sin que ningún error lo delate.

    Este test lee `base.html` y cierra ese hueco.
    """

    #: Entradas del menú que a propósito no se pueden deshabilitar. El Dashboard
    #: es la pantalla a la que se aterriza tras entrar: apagarla dejaría al
    #: usuario sin ningún sitio al que ir.
    SIN_GUARDIA = {'dashboard'}

    @classmethod
    def _items_del_menu(cls):
        """[(url_name, codigo_de_sesion_o_None)] por cada ítem del menú lateral.

        Se lee la plantilla como texto en vez de renderizarla porque lo que se
        quiere comprobar es el CÓDIGO FUENTE del menú (¿está envuelto en un
        `{% if sesiones.X %}`?), no el HTML que sale para un usuario concreto.
        Renderizándola, un ítem sin guardia se vería exactamente igual que uno
        con guardia encendido.
        """
        from pathlib import Path

        from django.conf import settings

        ruta = Path(settings.BASE_DIR) / 'templates' / 'base.html'
        html = ruta.read_text(encoding='utf-8')

        items = []
        for bloque in re.finditer(r'<li class="nav-item">.*?</li>', html, re.S):
            url = re.search(r"\{%\s*url\s+'([^']+)'", bloque.group(0))
            if not url:
                continue  # ítems sin enlace, como el botón de plegar el menú

            # El guardia tiene que estar PEGADO al <li>, sin nada entre medias
            # salvo espacios. Se comprobó primero "el último {% if %} sin
            # {% endif %} de por medio" y no servía: un ítem nuevo colado entre
            # el `{% if %}` de otro y su <li> heredaba el guardia del vecino y
            # el test lo daba por bueno. Ese es exactamente el olvido que esto
            # tiene que cazar, así que la comprobación es literal.
            antes = html[:bloque.start()]
            pegado = re.search(r'\{%\s*if\s+sesiones\.(\w+)\s*%\}\s*$', antes)
            items.append((url.group(1), pegado.group(1) if pegado else None))
        return items

    def test_el_menu_se_lee_de_verdad(self):
        """Si el parser deja de encontrar ítems, los otros dos tests pasarían en vacío."""
        items = self._items_del_menu()
        self.assertGreaterEqual(len(items), 20, 'El parser del menú ha dejado de funcionar')

    def test_todo_item_del_menu_tiene_su_sesion(self):
        """Una pantalla nueva sin guardia es una pantalla que no puedes apagar."""
        huerfanos = [url for url, codigo in self._items_del_menu()
                     if codigo is None and url not in self.SIN_GUARDIA]
        self.assertEqual(
            huerfanos, [],
            'Estos ítems del menú no están envueltos en {% if sesiones.<codigo> %}, '
            'así que quedan fuera de los permisos de sesión. Añádelos a '
            f'core/sesiones.py y envuélvelos en base.html: {huerfanos}',
        )

    def test_los_guardias_del_menu_existen_en_el_catalogo(self):
        """Un código mal escrito en la plantilla oculta el ítem a TODO el mundo.

        `{% if sesiones.pdhh %}` no da error en Django: la variable no existe,
        evalúa a falso y la entrada del menú desaparece para todos, para siempre.
        """
        inventados = sorted({codigo for _, codigo in self._items_del_menu()
                             if codigo is not None and codigo not in CODIGOS})
        self.assertEqual(
            inventados, [],
            f'Códigos usados en base.html que no existen en core/sesiones.py: {inventados}',
        )


class DefectosTest(PermisosSesionBaseTest):
    def test_supervisor_ve_todo_por_defecto(self):
        """Sin tocar nada, la función no cambia lo que el supervisor veía antes."""
        permisos = sesiones_habilitadas(self.supervisor.user)
        self.assertTrue(all(permisos.values()))

    def test_explorador_no_ve_administracion_ni_dias_especiales(self):
        permisos = sesiones_habilitadas(self.explorador.user)
        self.assertTrue(permisos['mis_turnos'])
        self.assertTrue(permisos['consulta_sanciones'])
        # La decisión de negocio de esta función: la planificación anual no es
        # información del explorador.
        self.assertFalse(permisos['consulta_dias_especiales'])
        self.assertFalse(permisos['pdh'])

    def test_staff_no_es_recortable(self):
        """Marcar casillas a un is_staff no le quita nada: lo ve todo por diseño."""
        PermisoSesion.objects.create(empleado=self.admin, sesion='pdh', habilitado=False)
        self.assertTrue(sesiones_habilitadas(self.admin.user)['pdh'])

    def test_anonimo_no_ve_nada(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(any(sesiones_habilitadas(AnonymousUser()).values()))


class BloqueoDeUrlTest(PermisosSesionBaseTest):
    def test_supervisor_con_sesion_deshabilitada_recibe_403(self):
        self.client.force_login(self.supervisor.user)
        self.assertEqual(self.client.get(reverse('pdh_list')).status_code, 200)

        PermisoSesion.objects.create(empleado=self.supervisor, sesion='pdh', habilitado=False)
        # Ocultar el enlace no basta: quien sepa la URL entra igual si no hay guardia.
        self.assertEqual(self.client.get(reverse('pdh_list')).status_code, 403)

    def test_el_bloqueo_alcanza_a_las_pantallas_hijas(self):
        """Apagar PDH tiene que cerrar también su alta, no solo el listado."""
        PermisoSesion.objects.create(empleado=self.supervisor, sesion='pdh', habilitado=False)
        self.client.force_login(self.supervisor.user)
        self.assertEqual(self.client.get(reverse('pdh_create')).status_code, 403)

    def test_otras_sesiones_siguen_abiertas(self):
        PermisoSesion.objects.create(empleado=self.supervisor, sesion='pdh', habilitado=False)
        self.client.force_login(self.supervisor.user)
        self.assertEqual(self.client.get(reverse('jornadas_list')).status_code, 200)

    def test_sanciones_apagadas_degradan_en_vez_de_negar(self):
        """La pantalla es compartida: negarla taparía también las sanciones propias.

        Quitarle 'sanciones' a un supervisor tiene que dejarle la vista personal
        (la que ve cualquier explorador) y cerrarle la gestión, no darle un 403.
        """
        PermisoSesion.objects.create(empleado=self.supervisor, sesion='sanciones', habilitado=False)
        self.client.force_login(self.supervisor.user)

        resp = self.client.get(reverse('sanciones_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['es_supervisor'])
        # Pero el alta sí queda cerrada.
        self.assertEqual(self.client.get(reverse('sanciones_create')).status_code, 403)

    def test_restricciones_apagadas_degradan_en_vez_de_negar(self):
        PermisoSesion.objects.create(
            empleado=self.supervisor, sesion='restricciones', habilitado=False,
        )
        self.client.force_login(self.supervisor.user)

        resp = self.client.get(reverse('restricciones_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context['es_supervisor'])
        self.assertEqual(self.client.get(reverse('restricciones_create')).status_code, 403)

    def test_explorador_no_entra_a_dias_especiales_por_url(self):
        self.client.force_login(self.explorador.user)
        self.assertEqual(
            self.client.get(reverse('dias_especiales_visualizar')).status_code, 403,
        )

    def test_ajax_recibe_json_y_no_html(self):
        """El front espera un cuerpo que pueda leer; una página de error lo rompe."""
        PermisoSesion.objects.create(empleado=self.supervisor, sesion='pdh', habilitado=False)
        self.client.force_login(self.supervisor.user)
        resp = self.client.get(reverse('pdh_list'), headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(resp.status_code, 403)
        self.assertIn('error', resp.json())


class PantallaDeAdministracionTest(PermisosSesionBaseTest):
    def url(self, empleado):
        return reverse('permisos_sesion_edit', args=[empleado.id])

    def test_solo_el_staff_abre_la_pantalla(self):
        self.client.force_login(self.admin.user)
        self.assertEqual(self.client.get(self.url(self.supervisor)).status_code, 200)

    def test_supervisor_no_puede_editarse_los_permisos(self):
        """La escalada obvia: devolverse lo que el administrador le quitó."""
        self.client.force_login(self.supervisor.user)
        self.assertEqual(self.client.get(self.url(self.supervisor)).status_code, 403)
        resp = self.client.post(self.url(self.supervisor), {'sesiones': ['pdh']})
        self.assertEqual(resp.status_code, 403)

    def test_guardar_persiste_marcadas_y_desmarcadas(self):
        self.client.force_login(self.admin.user)
        self.client.post(self.url(self.supervisor), {'sesiones': ['pdh', 'sanciones']})

        permisos = sesiones_habilitadas(self.supervisor.user)
        self.assertTrue(permisos['pdh'])
        self.assertTrue(permisos['sanciones'])
        # Lo que no venga en el POST queda explícitamente apagado: un checkbox
        # sin marcar no se envía, así que ausencia = desmarcado.
        self.assertFalse(permisos['roles'])

    def test_codigos_inventados_no_se_guardan(self):
        self.client.force_login(self.admin.user)
        self.client.post(self.url(self.supervisor), {'sesiones': ['pdh', 'no_existe']})
        self.assertFalse(
            PermisoSesion.objects.filter(empleado=self.supervisor, sesion='no_existe').exists()
        )
