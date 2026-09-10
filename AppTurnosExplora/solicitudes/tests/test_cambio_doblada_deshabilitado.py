"""
CAMBIO DESCANSO entre semana / «Cambio de doblada» APAGADO.

El sub-flujo se apagó sin borrar su código: la tarjeta del formulario lleva la clase
`disabled`, pero eso es solo la capa visual —se quita desde DevTools, y una pestaña
abierta desde antes del despliegue conserva el HTML y el JS anteriores—, así que el
POST con `submodalidad_semana=cambio_doblada` puede llegar igual al servidor. El
`choices` del modelo tampoco frena nada: Django no lo valida en `.save()`.

El interruptor real es `SUBMODALIDADES_SEMANA_DESHABILITADAS`, comprobado en
`validar_solicitud`, que es por donde pasan TANTO la creación como la re-validación
al aprobar. Estos tests fijan las tres cosas que importan:

1. el envío se rechaza,
2. una solicitud que se hubiera colado antes del apagado tampoco se puede aprobar,
3. el apagón NO se derrama sobre las otras sub-modalidades de la semana.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado, Jornada
from solicitudes.models import DobladaDetalle, SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.strategies import cambio_descanso_strategy as mod
from solicitudes.services.strategies.cambio_descanso_strategy import CambioDescansoStrategy
from turnos.models import AsignarJornadaExplorador, Sala


class CambioDobladaDeshabilitadoTest(TestCase):
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO DESCANSO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala CDobOff', activo=True)

        self.solicitante = self._empleado('sol.cdoff', 'Sol', '9401', self.am)
        self.receptor = self._empleado('rec.cdoff', 'Rec', '9402', self.pm)

        # Miércoles y jueves de la semana que viene: entre semana (la rama que dispara
        # la guarda) y sin festivos, que en la base de test está vacía.
        hoy = timezone.localdate()
        lunes = hoy - timedelta(days=hoy.weekday()) + timedelta(days=7)
        self.cesion = lunes + timedelta(days=2)
        self.pago = lunes + timedelta(days=3)

        self.strat = CambioDescansoStrategy()

    def _empleado(self, username, nombre, cedula, jornada):
        u = User.objects.create_user(username=username, password='x')
        e = Empleado.objects.create(user=u, nombre=nombre, apellido='Test',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _datos(self, **over):
        d = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'tipo_cambio': self.tipo,
            'comentario': 'Prueba',
            'fecha_cambio_turno': self.cesion.strftime('%Y-%m-%d'),
            'fecha_pago': self.pago.strftime('%Y-%m-%d'),
            'submodalidad_semana': 'cambio_doblada',
        }
        d.update(over)
        return d

    # ------------------------------------------------------------------ envío

    def test_envio_rechazado_aunque_el_post_traiga_la_submodalidad(self):
        """Saltarse la tarjeta deshabilitada no sirve: la guarda está en el servidor."""
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok, "El cambio de doblada está apagado: no puede validar")
        self.assertIn('deshabilitado', msg.lower())

    def test_el_mensaje_nombra_la_opcion_apagada_y_no_deja_al_usuario_atascado(self):
        """
        El texto sale de los `choices` del modelo, no escrito a mano: así sigue siendo
        verdad si se apaga o reactiva otra sub-modalidad. Debe decir CUÁL está apagada
        —si no, el usuario no sabe qué tarjeta dejar de tocar— y hacia dónde ir.
        """
        _, msg = self.strat.validar_solicitud(self._datos())
        etiqueta = dict(DobladaDetalle.SUBMODALIDAD_SEMANA_CHOICES)['cambio_doblada']
        self.assertIn(etiqueta, msg)
        self.assertIn('otra de las opciones', msg.lower())

    # ------------------------------------------------------- aprobación (LIFO)

    def test_una_solicitud_colada_antes_del_apagado_tampoco_se_aprueba(self):
        """
        El caso real: una pestaña abierta desde antes del despliegue creó la solicitud.
        Se construye por ORM a propósito —es una fila que YA existe— y se comprueba que
        la re-validación al aprobar la para. Sin esto, el supervisor la aprobaría y la
        doblada se materializaría por el flujo que se acaba de cerrar.
        """
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo,
            estado='PENDIENTE',
            fecha_cambio_turno=self.cesion,
            comentario='Prueba',
        )
        DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=self.pago,
            submodalidad_semana='cambio_doblada',
        )

        ok, msg = self.strat.revalidar_para_aprobar(sol)
        self.assertFalse(ok, "Una solicitud de un sub-flujo apagado no se puede aprobar")
        self.assertIn('deshabilitado', msg.lower())

    # ------------------------------------------------------------ no se derrama

    def test_las_otras_submodalidades_no_quedan_apagadas(self):
        """
        La guarda debe tocar SOLO lo que está en el conjunto. Las demás sub-modalidades
        fallarán aquí por falta de temporada configurada, y eso está bien: lo que se fija
        es que NO fallen con el mensaje del apagado.
        """
        for sub in ('intercambio_dia', 'jornadas_partidas', 'cobertura_misma_semana'):
            with self.subTest(submodalidad=sub):
                _, msg = self.strat.validar_solicitud(self._datos(submodalidad_semana=sub))
                self.assertNotIn('deshabilitado', msg.lower())

    def test_el_interruptor_es_el_conjunto_y_no_un_literal_suelto(self):
        """
        Si alguien reactiva el sub-flujo sacándolo del conjunto, la guarda debe soltarlo.
        Esto fija que el apagado se controla desde un solo sitio.
        """
        self.assertIn('cambio_doblada', mod.SUBMODALIDADES_SEMANA_DESHABILITADAS)

        original = mod.SUBMODALIDADES_SEMANA_DESHABILITADAS
        mod.SUBMODALIDADES_SEMANA_DESHABILITADAS = frozenset()
        try:
            _, msg = self.strat.validar_solicitud(self._datos())
        finally:
            mod.SUBMODALIDADES_SEMANA_DESHABILITADAS = original
        self.assertNotIn('deshabilitado', msg.lower())
