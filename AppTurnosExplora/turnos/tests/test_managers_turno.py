"""
El soft-delete de `Turno` no puede esconder filas al navegar relaciones.

QUÉ PROTEGE
-----------
`Turno.objects` es un `TurnoActivoManager` que excluye los turnos anulados por
reprogramación. Es deliberado: así todas las lecturas activas —estado_dia, Mis Turnos,
consolidado, reportes— ignoran lo anulado sin filtrar en cada consulta.

Un manager que filtra tiene un peligro concreto, y la documentación de Django lo dice
sin rodeos (topics/db/managers, «Using managers for related object access»):

    «Django uses the `Model._base_manager` for accessing related objects [...] It is
    critical that base managers do not override `get_queryset` to filter out rows, as
    this would result in incomplete data when accessing related objects.»

Hoy `Turno` cumple, pero **por el comportamiento por defecto de Django, no por una
decisión escrita**: al no fijarse `Meta.base_manager_name`, Django crea un manager
plano y sin filtros para ese uso. Basta con que alguien añada
`base_manager_name = 'objects'` al `Meta` —un cambio que parece ordenar el modelo— para
que `solicitud.turno_origen` deje de encontrar un turno anulado y devuelva
`DoesNotExist` en vez de la fila. Sin error de sintaxis, sin aviso y sin test rojo.

Estos tests fijan esa propiedad para que ese cambio falle en el CI en vez de en
producción.

LO QUE NO SE PRUEBA AQUÍ
------------------------
Que `Turno.objects` esconda los anulados: de eso ya viven los tests de reprogramación.
Aquí solo se cubre el camino de las RELACIONES, que es el que no tenía red.
"""
from datetime import date

from django.contrib.auth.models import User
from django.db import models
from django.test import TestCase

from empleados.models import Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import Sala, Turno


class BaseManagerDeTurnoTest(TestCase):
    """La propiedad estructural, sin tocar la base de datos."""

    def test_el_base_manager_no_filtra(self):
        """
        Es la condición que exige la documentación de Django para un modelo con
        soft-delete. Si falla, el acceso por relación devuelve datos incompletos.
        """
        base = Turno._base_manager

        self.assertFalse(
            base.get_queryset().query.where,
            'El base manager de Turno filtra filas. Navegar una relación hacia un turno '
            'anulado dejará de encontrarlo. Revisa Meta.base_manager_name.')

    def test_el_base_manager_es_el_plano_que_crea_django(self):
        """
        Sin `Meta.base_manager_name`, Django fabrica un `Manager` plano para este uso. Si
        alguien lo apunta a `objects` —que sí filtra—, este test lo caza.
        """
        self.assertIsNone(Turno._meta.base_manager_name)
        self.assertIs(type(Turno._base_manager), models.Manager)
        self.assertTrue(Turno._base_manager.auto_created)

    def test_el_manager_por_defecto_si_filtra(self):
        """CONTROL: sin esto, los dos de arriba pasarían aunque el soft-delete no
        existiera, y estarían protegiendo nada."""
        self.assertTrue(Turno._default_manager.get_queryset().query.where)

    def test_all_objects_sigue_viendo_todo(self):
        """La salida para auditoría e historial. Si desaparece, no hay forma de leer un
        turno anulado por consulta directa."""
        self.assertFalse(Turno.all_objects.get_queryset().query.where)


class RelacionHaciaTurnoAnuladoTest(TestCase):
    """
    La comprobación con datos: un turno anulado sigue siendo alcanzable desde la
    solicitud que lo apunta.

    Es el escenario real de la advertencia. `SolicitudCambio` tiene DOS claves foráneas
    a `Turno` (`turno_origen` y `turno_destino`), y una solicitud vieja apunta
    perfectamente a un turno que después se anuló por una reprogramación: la pantalla de
    detalle y la auditoría tienen que poder mostrarlo.
    """

    def setUp(self):
        self.jornada = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00',
                                              hora_fin='14:00:00')
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)
        u = User.objects.create_user('emp.mgr', password='x')
        self.empleado = Empleado.objects.create(user=u, nombre='Emp', apellido='Mgr',
                                                cedula='9201', activo=True)
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')

    def test_una_solicitud_encuentra_su_turno_aunque_este_anulado(self):
        turno = Turno.objects.create(explorador=self.empleado, fecha=date(2026, 6, 1),
                                     jornada=self.jornada, sala=self.sala)
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.empleado, explorador_receptor=self.empleado,
            tipo_cambio=self.tipo, comentario='x', fecha_cambio_turno=date(2026, 6, 1),
            turno_origen=turno)

        Turno.all_objects.filter(pk=turno.pk).update(anulado=True)

        # Desapareció de las lecturas activas...
        self.assertFalse(Turno.objects.filter(pk=turno.pk).exists())
        # ...pero la solicitud que lo apunta sigue pudiendo leerlo.
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.turno_origen_id, turno.pk)
        self.assertEqual(solicitud.turno_origen.pk, turno.pk,
                         'La relación directa debe encontrar el turno anulado')
