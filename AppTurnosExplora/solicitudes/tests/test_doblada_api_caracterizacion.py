"""
Red de caracterizacion de las dos vistas SIN cubrir de `doblada_api.py`.

MEDICION que motiva este fichero (cobertura del CI, por linea):

    VerificarDobladaExistente ... 79 %  <- el get() de 342 lineas, ya cubierto
    ObtenerExploradoresDoblada ...  4 %  <- 2 de 47 sentencias
    ObtenerFechasDescanso ......   8 %  <- 2 de 23

Ese 4 % y ese 8 % son, otra vez, los imports y las lineas de `class` y `def`: la
cobertura funcional de ambas era CERO. Y no son secundarias — `solicitar_doblada.js`
llama a las dos: la primera puebla el selector de companeros (la lista sobre la que
el explorador elige a quien pedirle el favor) y la segunda marca en el calendario
los dias en que ya tiene libre.

Estos tests FIJAN lo que hacen hoy, no lo que deberian hacer. Es el paso previo a
tocarlas, igual que se hizo con `api_turno_jornada.py`.
"""
import json
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.models import DobladaDetalle, SolicitudCambio, TipoSolicitudCambio
from turnos.models import Turno


class BaseDobladaApi(TestCase):
    def setUp(self):
        self.sala = crear_sala()
        self.am = crear_jornada('AM')
        self.pm = crear_jornada('PM')
        self.yo = crear_empleado('Ana', 'Uno', jornada=self.am, sala=self.sala)
        self.otro = crear_empleado('Ben', 'Dos', jornada=self.pm, sala=self.sala)
        self.client.force_login(self.yo.user)
        self.tipo_doblada, _ = TipoSolicitudCambio.objects.get_or_create(
            nombre='DOBLADA', defaults={'activo': True})

    def _un_martes(self):
        d = date.today() + timedelta(days=14)
        while d.weekday() != 1:
            d += timedelta(days=1)
        return d

    def _pedir(self, url, **params):
        r = self.client.get(url, params)
        try:
            return r, json.loads(r.content)
        except Exception:
            return r, {}


class ObtenerExploradoresDobladaTestCase(BaseDobladaApi):
    """
    Puebla el selector de companeros del formulario de doblada.

    Es la lista sobre la que el explorador elige a quien pedirle el favor: si
    devuelve de mas, se ofrece a alguien que no puede; si devuelve de menos,
    alguien valido queda invisible y no hay forma de saber por que.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('solicitudes:obtener_exploradores_doblada')

    def test_sin_fecha_responde_400(self):
        r, cuerpo = self._pedir(self.url)

        self.assertEqual(r.status_code, 400)
        self.assertEqual(cuerpo.get('code'), 'missing_fields')

    def test_sin_sesion_no_responde(self):
        self.client.logout()

        r = self.client.get(self.url, {'fecha': str(self._un_martes())})

        self.assertIn(r.status_code, (302, 403))

    def test_la_respuesta_trae_empleados_y_total_coherentes(self):
        # `total` lo lee el formulario para decidir si muestra la lista o el aviso
        # de "no hay companeros disponibles". Si se desincronizara de `empleados`,
        # la pantalla mentiria en uno de los dos sentidos.
        r, cuerpo = self._pedir(self.url, fecha=str(self._un_martes()))

        self.assertEqual(r.status_code, 200)
        self.assertIn('empleados', cuerpo)
        self.assertIsInstance(cuerpo['empleados'], list)
        self.assertEqual(cuerpo['total'], len(cuerpo['empleados']))

    def test_cada_empleado_trae_las_claves_que_pinta_el_selector(self):
        r, cuerpo = self._pedir(self.url, fecha=str(self._un_martes()),
                                incluir_descanso='1')

        for emp in cuerpo.get('empleados', []):
            self.assertIn('id', emp)
            self.assertIn('nombre', emp)
            self.assertIn('apellido', emp)

    def test_uno_nunca_se_ofrece_a_si_mismo(self):
        r, cuerpo = self._pedir(self.url, fecha=str(self._un_martes()),
                                incluir_descanso='1')

        ids = [e['id'] for e in cuerpo.get('empleados', [])]
        self.assertNotIn(self.yo.id, ids, 'el solicitante aparece en su propia lista')

    def test_sin_el_tipo_DOBLADA_activo_responde_404_y_no_lista_vacia(self):
        # Diferencia importante: una lista vacia el formulario la lee como "no hay
        # companeros disponibles hoy", que es una respuesta de negocio normal. Un
        # 404 dice otra cosa: el catalogo esta mal configurado. Confundirlos deja
        # al usuario esperando a que aparezca gente que nunca va a aparecer.
        self.tipo_doblada.activo = False
        self.tipo_doblada.save()

        r, cuerpo = self._pedir(self.url, fecha=str(self._un_martes()))

        self.assertEqual(r.status_code, 404)
        self.assertEqual(cuerpo.get('code'), 'not_found')

    def test_incluir_descanso_no_duplica_a_nadie(self):
        """
        La rama `incluir_descanso` anade a los que descansan DESPUES de la lista
        normal, comprobando `ids_ya_incluidos`. Sin esa comprobacion el mismo
        companero saldria dos veces en el desplegable.

        LIMITE CONOCIDO: no se logro montar el solapamiento que activa esa guarda
        (alguien que este a la vez en `empleados_disponibles` y en `en_descanso`).
        Quitando el `if emp.id not in ids_ya_incluidos` los tests siguen en verde,
        asi que esta comprobacion vale como red del INVARIANTE —la lista nunca trae
        ids repetidos— pero no como prueba de esa linea concreta. Queda anotado en
        vez de fingir una cobertura que no hay.
        """
        r, cuerpo = self._pedir(self.url, fecha=str(self._un_martes()),
                                incluir_descanso='1')

        ids = [e['id'] for e in cuerpo.get('empleados', [])]
        self.assertEqual(len(ids), len(set(ids)), f'ids repetidos: {ids}')

    def test_un_fallo_interno_sale_como_500_generico(self):
        from unittest.mock import patch

        with patch('solicitudes.views.doblada_api.SolicitudFactory.get_strategy',
                   side_effect=RuntimeError('boom')):
            r, cuerpo = self._pedir(self.url, fecha=str(self._un_martes()))

        self.assertEqual(r.status_code, 500)
        self.assertEqual(cuerpo.get('code'), 'internal_error')
        self.assertNotIn('boom', str(cuerpo), 'no debe filtrar el detalle del error')


class ObtenerFechasDescansoTestCase(BaseDobladaApi):
    """
    Marca en el calendario de la doblada los dias en que el usuario YA tiene libre.

    Su docstring explica que usa la fuente de verdad (`estado_mes`) justamente
    porque una consulta parcial dejaba a unos usuarios con dias marcados y a otros
    no. Estos tests fijan esa propiedad.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('solicitudes:obtener_fechas_descanso')

    def test_sin_sesion_no_responde(self):
        self.client.logout()

        r = self.client.get(self.url)

        self.assertIn(r.status_code, (302, 403))

    def test_devuelve_fechas_y_total_coherentes(self):
        r, cuerpo = self._pedir(self.url)

        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(cuerpo['fechas'], list)
        self.assertEqual(cuerpo['total'], len(cuerpo['fechas']))

    def test_las_fechas_vienen_en_formato_ISO(self):
        # `solicitar_doblada.js` las compara como cadenas contra las del
        # calendario. Otro formato no da error: simplemente no marca ningun dia.
        r, cuerpo = self._pedir(self.url)

        for f in cuerpo['fechas']:
            self.assertRegex(f, r'^\d{4}-\d{2}-\d{2}$')

    def test_un_dia_cedido_por_doblada_aparece_marcado(self):
        martes = self._un_martes()
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.yo, explorador_receptor=self.otro,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=martes, comentario='x')
        DobladaDetalle.objects.create(solicitud=sol, fecha_pago=martes + timedelta(days=7))

        _, cuerpo = self._pedir(self.url)

        self.assertIn(str(martes), cuerpo['fechas'])

    def test_un_dia_con_turno_real_NO_se_marca(self):
        """
        La capa L1 manda: si ese dia trabaja de verdad, no esta libre por mucho que
        haya una solicitud. Marcarlo ofreceria un dia que en realidad esta ocupado.

        MATIZ COMPROBADO, para que nadie lo lea de mas: este test NO ejerce el
        `not d.get('trabaja')` de la condicion. Medido con una sonda, en cuanto hay
        turno real `estado_dia` devuelve `fuente='turno'`, asi que el
        `fuente == 'solicitud'` ya lo excluye por si solo:

            sin turno real -> trabaja=False  fuente='solicitud'
            con turno real -> trabaja=True   fuente='turno'

        Es decir, el `not trabaja` es REDUNDANTE (la capa de solicitudes siempre
        responde trabaja=False). Se deja porque no estorba y documenta la
        intencion, pero conviene saber que quitarlo no rompe este test.
        """
        martes = self._un_martes()
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.yo, explorador_receptor=self.otro,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=martes, comentario='x')
        DobladaDetalle.objects.create(solicitud=sol, fecha_pago=martes + timedelta(days=7))
        Turno.objects.create(explorador=self.yo, fecha=martes, jornada=self.am,
                             sala=self.sala, tipo_cambio='DOBLADA')

        _, cuerpo = self._pedir(self.url)

        self.assertNotIn(str(martes), cuerpo['fechas'])

    def test_una_solicitud_no_aprobada_no_marca_nada(self):
        martes = self._un_martes()
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.yo, explorador_receptor=self.otro,
            tipo_cambio=self.tipo_doblada, estado='pendiente',
            fecha_cambio_turno=martes, comentario='x')
        DobladaDetalle.objects.create(solicitud=sol, fecha_pago=martes + timedelta(days=7))

        _, cuerpo = self._pedir(self.url)

        self.assertNotIn(str(martes), cuerpo['fechas'])

    def test_la_ventana_cubre_del_mes_pasado_a_seis_meses_vista(self):
        # Recorre 8 meses empezando por el anterior al actual. Es lo que necesita
        # el datepicker para que al navegar no aparezcan meses sin marcar.
        hoy = date.today()
        sol_fecha = hoy + timedelta(days=150)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.yo, explorador_receptor=self.otro,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=sol_fecha, comentario='x')
        DobladaDetalle.objects.create(solicitud=sol, fecha_pago=sol_fecha + timedelta(days=7))

        _, cuerpo = self._pedir(self.url)

        self.assertIn(str(sol_fecha), cuerpo['fechas'],
                      'un dia a cinco meses vista deberia entrar en la ventana')

    def test_un_fallo_interno_sale_como_500_generico(self):
        from unittest.mock import patch

        with patch('turnos.services.turno_service.TurnoService.estado_mes',
                   side_effect=RuntimeError('boom')):
            r, cuerpo = self._pedir(self.url)

        self.assertEqual(r.status_code, 500)
        self.assertEqual(cuerpo.get('code'), 'internal_error')
        self.assertNotIn('boom', str(cuerpo))
