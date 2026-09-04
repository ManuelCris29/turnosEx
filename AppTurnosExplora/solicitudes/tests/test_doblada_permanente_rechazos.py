"""
Las ramas de RECHAZO del alta multi-compañero de la doblada permanente.

POR QUÉ ESTE ARCHIVO
--------------------
`_procesar_doblada_permanente_multi` son 236 líneas con 60 ramas: el segundo punto
caliente que señalaba la auditoría, y el único de los tres que CREA datos —transacción,
todo o nada y correos— en vez de solo leer.

Medida la cobertura sobre el artefacto del CI, estaba al 81%, y sus 23 líneas sin
cubrir eran casi todas lo mismo: **los rechazos**. El camino feliz y los choques de
fechas ya los cubría `DobladaPermanenteMultiCompaneroTest`; lo que nadie ejercitaba era
lo que el usuario ve cuando su solicitud NO se puede hacer.

Dos de esas ramas merecían nombre propio:

  - El prefijo `ErrorDelCompanero`. Existe porque una vez se anteponía el nombre del
    compañero a TODOS los rechazos, y "Ya tienes una solicitud pendiente" —que habla de
    quien envía— llegaba como "Isabel Parra: Ya tienes una solicitud pendiente": el
    usuario iba a cancelar la solicitud de Isabel a buscar un choque que era suyo. La
    corrección estaba escrita y sin una sola prueba.
  - El flujo ANTIGUO por día de la semana (`cesion_dia` en vez de `cesion_fecha`),
    entero sin cubrir. Sigue vivo en el código y sigue creando solicitudes.
"""
from datetime import timedelta
from unittest.mock import patch

from django.http import QueryDict

from solicitudes.services.errores_validacion import ErrorDelCompanero
from solicitudes.services.solicitud_factory import SolicitudFactory

from .test_doblada_permanente import DobladaPermanenteBaseTest


class _MultiCompaneroBase(DobladaPermanenteBaseTest):
    """Fixtures y helpers compartidos. Sin tests: las clases de abajo heredan de aquí y
    no unas de otras, para que sus casos no se ejecuten dos veces."""

    def setUp(self):
        super().setUp()
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator
        self.orch = SolicitudOrchestrator
        self.receptor2 = self._empleado('rec2.rech', '777', self.am)
        self.miercoles = self.lunes + timedelta(days=2)
        self.jueves = self.lunes + timedelta(days=3)

    # ------------------------------------------------------------------

    def _post(self, pares_cesion=(), pares_devolucion=(), **extra):
        q = QueryDict(mutable=True)
        q['comentarios'] = 'Prueba de rechazo'
        q['fecha_inicio'] = self.fi.strftime('%Y-%m-%d')
        q['fecha_fin'] = self.jueves.strftime('%Y-%m-%d')
        for f, c in pares_cesion:
            q.appendlist('cesion_fecha', f.strftime('%Y-%m-%d'))
            q.appendlist('cesion_fecha_companero', str(c))
        for f, c in pares_devolucion:
            q.appendlist('devolucion_fecha', f.strftime('%Y-%m-%d'))
            q.appendlist('devolucion_fecha_companero', str(c))
        for k, v in extra.items():
            q[k] = v
        return q

    def _procesar(self, post):
        return self.orch._procesar_doblada_permanente_multi(
            post, self.tipo, self.solicitante, post.get('comentarios'))

    def _valido(self):
        """El POST del caso que SÍ funciona: un compañero, un día que cede y uno que devuelve."""
        return self._post([(self.lunes, self.receptor.id)],
                          [(self.martes, self.receptor.id)])

    @staticmethod
    def _error(res):
        return res.como_payload().get('error', '')


class RechazosMultiCompaneroTest(_MultiCompaneroBase):
    """Lo que ve el usuario cuando su solicitud NO se puede hacer."""

    def test_control_el_caso_valido_se_crea(self):
        """
        CONTROL. Sin esto, todos los tests de abajo podrían estar pasando porque el
        montaje está mal y CUALQUIER solicitud se rechaza.
        """
        res = self._procesar(self._valido())

        self.assertEqual(res.status, 201, res.como_payload())

    def test_sin_comentario_se_rechaza(self):
        post = self._valido()
        post['comentarios'] = '   '

        res = self._procesar(post)

        self.assertEqual(res.status, 400)
        self.assertIn('comentario', self._error(res))

    def test_sin_ningun_dia_de_cesion_se_rechaza(self):
        res = self._procesar(self._post([], []))

        self.assertEqual(res.status, 400)
        self.assertIn('al menos un día de cesión', self._error(res))

    def test_devolver_a_un_companero_que_no_te_cubre_se_rechaza(self):
        """
        Devolverle un día a alguien que no te cubrió ninguno no es una doblada permanente:
        es un favor suelto, y este formulario no lo hace.
        """
        post = self._post([(self.lunes, self.receptor.id)],
                          [(self.martes, self.receptor2.id)])

        res = self._procesar(post)

        self.assertEqual(res.status, 400)
        self.assertIn('un compañero que te cubra', self._error(res))

    def test_un_companero_inexistente_se_rechaza(self):
        post = self._post([(self.lunes, 999999)], [(self.martes, 999999)])

        res = self._procesar(post)

        self.assertEqual(res.status, 400)
        self.assertIn('no válido', self._error(res))

    def test_un_companero_sancionado_no_puede_participar(self):
        """
        Un sancionado no participa NI como compañero: si no, bastaría con que otro enviara
        la solicitud en su nombre para saltarse la sanción.
        """
        with patch.object(self.orch, '_refrescar_y_sancion',
                          side_effect=lambda emp: object() if emp == self.receptor else None):
            res = self._procesar(self._valido())

        self.assertEqual(res.status, 403)
        self.assertEqual(res.code, 'sancionado_receptor')
        self.assertIn(self.receptor.nombre, self._error(res))

    def test_el_nombre_del_companero_solo_se_antepone_a_lo_que_es_suyo(self):
        """
        LA REGRESIÓN QUE ESTO PROTEGE. Con varios compañeros en el mismo formulario hay que
        decir cuál falló, así que se antepone su nombre. Pero antes se anteponía a TODOS
        los rechazos, y "Ya tienes una solicitud pendiente" —que habla de quien ENVÍA—
        salía como "Isabel Parra: Ya tienes una solicitud pendiente"; el usuario iba a
        cancelar la solicitud de Isabel a buscar un choque que era suyo.

        Quien valida marca con `ErrorDelCompanero` las frases que son del compañero. Aquí
        se comprueban los dos lados de esa decisión.
        """
        # Del compañero: SÍ lleva su nombre delante.
        with patch.object(SolicitudFactory, 'validar_solicitud',
                          return_value=(False, ErrorDelCompanero('ya trabaja ese día'))):
            res = self._procesar(self._valido())

        self.assertEqual(res.status, 400)
        self.assertTrue(self._error(res).startswith(
            f'{self.receptor.nombre} {self.receptor.apellido}:'), self._error(res))

        # Del solicitante: NO lleva nombre, aunque salga del mismo bucle.
        with patch.object(SolicitudFactory, 'validar_solicitud',
                          return_value=(False, 'Ya tienes una solicitud pendiente')):
            res = self._procesar(self._valido())

        self.assertEqual(res.status, 400)
        self.assertEqual(self._error(res), 'Ya tienes una solicitud pendiente')
        self.assertNotIn(self.receptor.nombre, self._error(res))


class FlujoAntiguoPorDiaDeSemanaTest(_MultiCompaneroBase):
    """
    El flujo por DÍA DE LA SEMANA (`cesion_dia`), anterior al de fechas concretas.

    Sigue vivo en el código y sigue creando solicitudes, pero no lo cubría ningún test:
    el archivo entero se escribió sobre el flujo nuevo. Se ejercita aquí para que, si
    algún día se retira, se retire a propósito y no por accidente.
    """

    def _post_por_dia(self, pares_cesion, pares_devolucion):
        """pares_* = [(weekday, compañero_id)] — 0=lunes."""
        q = QueryDict(mutable=True)
        q['comentarios'] = 'Prueba flujo antiguo'
        q['fecha_inicio'] = self.fi.strftime('%Y-%m-%d')
        q['fecha_fin'] = self.jueves.strftime('%Y-%m-%d')
        for d, c in pares_cesion:
            q.appendlist('cesion_dia', str(d))
            q.appendlist('cesion_companero', str(c))
        for d, c in pares_devolucion:
            q.appendlist('devolucion_dia', str(d))
            q.appendlist('devolucion_companero', str(c))
        return q

    def test_el_flujo_por_dia_de_semana_sigue_creando(self):
        post = self._post_por_dia([(self.lunes.weekday(), self.receptor.id)],
                                  [(self.martes.weekday(), self.receptor.id)])

        res = self._procesar(post)

        self.assertEqual(res.status, 201, res.como_payload())

    def test_el_flujo_por_dia_tambien_exige_el_balance(self):
        """Las mismas reglas que el flujo de fechas, contadas en días en vez de fechas."""
        post = self._post_por_dia(
            [(self.lunes.weekday(), self.receptor.id),
             (self.miercoles.weekday(), self.receptor.id)],
            [(self.martes.weekday(), self.receptor.id)])

        res = self._procesar(post)

        self.assertEqual(res.status, 400)
        self.assertIn('misma cantidad de días', self._error(res))
