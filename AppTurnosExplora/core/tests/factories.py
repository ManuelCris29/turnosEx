"""
Factories de test compartidas: FUNCIONES PLANAS, no fixtures de pytest.

POR QUÉ FUNCIONES Y NO FIXTURES
-------------------------------
La auditoría proponía un `conftest.py` con fixtures compartidos. No sirve aquí:
67 archivos de esta suite usan `django.test.TestCase` y solo uno usa
`@pytest.mark.django_db`. Las fixtures de pytest NO son accesibles desde
`TestCase.setUp`, así que habrían cubierto al 1 % de la suite.

Una función plana se llama igual desde un `setUp`, desde un test suelto o desde
una fixture de pytest si algún día hace falta. Es el mínimo común denominador.

QUÉ RESUELVE
------------
55 archivos repiten el mismo montaje de User + Empleado y 40 el de Jornada. Esa
duplicación no es solo fea: cada copia elige sus propias cédulas y nombres de
usuario, que son ÚNICOS en la base, y al añadir un test nuevo es fácil chocar con
una cédula ya usada por otro archivo. Aquí los identificadores se generan solos.

CÓMO SE USA
-----------
    from core.tests.factories import crear_par_contrario, crear_jornada

    class MiTest(TestCase):
        def setUp(self):
            self.solicitante, self.receptor, self.sala = crear_par_contrario()

Todas las funciones devuelven objetos ya guardados y aceptan `**extra` para
sobrescribir cualquier campo, de modo que un test que necesite algo raro no tenga
que abandonar la factory.
"""
from datetime import date, time
from itertools import count

from django.contrib.auth.models import User

from empleados.models import CompetenciaEmpleado, Empleado
from turnos.models import AsignarJornadaExplorador, Jornada, Sala, Turno

# Contador de proceso para cédulas y nombres de usuario. Evita el choque de
# UNIQUE entre archivos de test, que es el fallo más común al añadir tests
# nuevos a esta suite. Con pytest-xdist cada worker es un proceso distinto y
# usa una base propia (sufijo _gwN), así que no hace falta coordinarlos.
_seq = count(1)

FECHA_ALTA = date(2025, 1, 1)  # anterior a cualquier fecha que usen los tests


def crear_jornada(nombre='AM', hora_inicio=None, hora_fin=None, **extra):
    """
    Jornada por nombre. `Jornada.nombre` es ÚNICO, así que se reutiliza la que ya
    exista en vez de reventar: dos llamadas a crear_jornada('AM') en el mismo
    test devuelven la misma jornada, que es lo que quiere quien la pide.
    """
    horarios = {
        'AM': (time(6, 0), time(14, 0)),
        'PM': (time(14, 0), time(22, 0)),
    }
    defecto_inicio, defecto_fin = horarios.get(nombre.upper(), (time(8, 0), time(16, 0)))
    jornada, _ = Jornada.objects.get_or_create(
        nombre=nombre,
        defaults={
            'hora_inicio': hora_inicio or defecto_inicio,
            'hora_fin': hora_fin or defecto_fin,
            **extra,
        },
    )
    return jornada


def crear_sala(nombre=None, **extra):
    return Sala.objects.create(nombre=nombre or f'Sala {next(_seq)}',
                               **{'activo': True, **extra})


def crear_empleado(nombre='Emp', apellido='Uno', jornada=None, sala=None,
                   fecha_alta=FECHA_ALTA, **extra):
    """
    Empleado con su User asociado, y opcionalmente su jornada y su competencia.

    La cédula y el nombre de usuario se generan solos para no chocar con los de
    otro archivo de test. Pásalos explícitamente solo si el test los comprueba.
    """
    n = next(_seq)
    campos = {
        'nombre': nombre,
        'apellido': apellido,
        'cedula': f'9{n:07d}',
        'email': f'emp{n}@test.local',
        'activo': True,
        **extra,
    }
    usuario = User.objects.create_user(username=f'emp{n}', password='clave-de-test')
    empleado = Empleado.objects.create(user=usuario, **campos)

    if jornada is not None:
        AsignarJornadaExplorador.objects.create(
            explorador=empleado, jornada=jornada, fecha_inicio=fecha_alta)
    if sala is not None:
        CompetenciaEmpleado.objects.create(empleado=empleado, sala=sala)

    return empleado


def crear_par_contrario(sala=None, fecha_alta=FECHA_ALTA):
    """
    El montaje más repetido de la suite: dos exploradores con jornadas CONTRARIAS
    (AM y PM) y competencia en la misma sala. Es la precondición de casi todo
    CAMBIO TURNO, porque el intercambio exige jornadas opuestas.

    Devuelve (empleado_am, empleado_pm, sala).
    """
    sala = sala or crear_sala()
    am = crear_empleado('Sol', 'AM', jornada=crear_jornada('AM'),
                        sala=sala, fecha_alta=fecha_alta)
    pm = crear_empleado('Rec', 'PM', jornada=crear_jornada('PM'),
                        sala=sala, fecha_alta=fecha_alta)
    return am, pm, sala


def crear_turno(empleado, fecha, jornada=None, sala=None, **extra):
    """Turno REAL (capa L1). Es lo que manda sobre la jornada asignada."""
    return Turno.objects.create(
        explorador=empleado,
        fecha=fecha,
        jornada=jornada or crear_jornada('AM'),
        sala=sala or crear_sala(),
        **extra,
    )
