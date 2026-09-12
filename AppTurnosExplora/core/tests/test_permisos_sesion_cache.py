"""
Caché de `sesiones_habilitadas`: TTL de una hora + invalidación al escribir
`PermisoSesion` (empleados/signals.py).

Fija dos comportamientos para que un refactor no los pierda:
1. La segunda consulta para el mismo usuario no vuelve a tocar la base de datos.
2. Cualquier escritura de `PermisoSesion` (creación o borrado, por la vista o
   por el admin de Django) invalida el caché de ese usuario de inmediato.
"""
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from core.permisos_sesion import sesiones_habilitadas
from empleados.models import Empleado, EmpleadoRole, PermisoSesion, Role


class SesionesHabilitadasCacheTest(TestCase):

    def setUp(self):
        cache.clear()
        rol_explorador = Role.objects.create(nombre=Role.EXPLORADOR)
        self.user = User.objects.create_user(username='cache_test', password='x')
        self.empleado = Empleado.objects.create(
            user=self.user, nombre='Cache', apellido='Test', cedula='999',
        )
        EmpleadoRole.objects.create(empleado=self.empleado, role=rol_explorador)

    def test_segunda_llamada_no_golpea_la_base_de_datos(self):
        sesiones_habilitadas(self.user)  # cache miss: calcula y guarda

        # Un User DISTINTO (misma fila) para descartar la memoización de
        # request y medir solo el hit de CacheService entre "peticiones".
        otro_objeto_mismo_user = User.objects.get(pk=self.user.pk)
        with self.assertNumQueries(0):
            resultado = sesiones_habilitadas(otro_objeto_mismo_user)

        self.assertFalse(resultado['pdh'])  # valor por defecto del explorador

    def test_memoizacion_de_request_evita_incluso_el_hit_de_cache(self):
        primero = sesiones_habilitadas(self.user)
        with self.assertNumQueries(0):
            segundo = sesiones_habilitadas(self.user)
        self.assertIs(primero, segundo)

    def test_crear_permisosesion_invalida_el_cache(self):
        sesiones_habilitadas(self.user)  # cachea pdh=False (valor por defecto)

        PermisoSesion.objects.create(empleado=self.empleado, sesion='pdh', habilitado=True)

        otro_objeto_mismo_user = User.objects.get(pk=self.user.pk)
        resultado = sesiones_habilitadas(otro_objeto_mismo_user)
        self.assertTrue(resultado['pdh'])

    def test_borrar_permisosesion_invalida_el_cache(self):
        permiso = PermisoSesion.objects.create(
            empleado=self.empleado, sesion='pdh', habilitado=True,
        )
        sesiones_habilitadas(self.user)  # cachea pdh=True

        permiso.delete()

        otro_objeto_mismo_user = User.objects.get(pk=self.user.pk)
        resultado = sesiones_habilitadas(otro_objeto_mismo_user)
        self.assertFalse(resultado['pdh'])  # vuelve al valor por defecto

    def test_staff_no_pasa_por_cache_service(self):
        """El admin ve todo sin queries ni caché: no hay nada que invalidar."""
        admin = User.objects.create_user(username='admin_cache', password='x', is_staff=True)
        with self.assertNumQueries(0):
            resultado = sesiones_habilitadas(admin)
        self.assertTrue(all(resultado.values()))
