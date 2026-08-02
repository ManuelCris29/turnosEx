"""
EmpleadoRepository — acceso a datos de empleados.

Centraliza todas las queries ORM relacionadas con Empleado y sus relaciones
(jornada asignada, roles, competencias, sanciones, restricciones).
Las vistas y servicios deben usar este repositorio en lugar de acceder
a .objects directamente.
"""
from __future__ import annotations

from typing import Optional
from django.db.models import QuerySet
from django.utils import timezone


class EmpleadoRepository:

    @staticmethod
    def activos() -> QuerySet:
        from empleados.models import Empleado
        return Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')

    @staticmethod
    def get_by_id(empleado_id: int):
        from empleados.models import Empleado
        try:
            return Empleado.objects.get(id=empleado_id)
        except Empleado.DoesNotExist:
            return None

    @staticmethod
    def supervisores_activos() -> QuerySet:
        from empleados.models import Empleado, Role
        return (
            Empleado.objects
            .filter(activo=True, empleadorole__role__nombre__iexact=Role.SUPERVISOR)
            .distinct()
        )

    @staticmethod
    def jornada_actual(empleado) -> Optional[str]:
        """Devuelve el nombre de la jornada vigente ('AM' o 'PM'), o None."""
        from turnos.models import AsignarJornadaExplorador
        asignacion = (
            AsignarJornadaExplorador.objects
            .filter(explorador=empleado)
            .order_by('-fecha_inicio')
            .first()
        )
        return asignacion.jornada.nombre if asignacion and asignacion.jornada else None

    @staticmethod
    def jornadas_por_empleados(empleado_ids: list) -> dict:
        """Devuelve {empleado_id: nombre_jornada} para una lista de IDs (evita N+1)."""
        from turnos.models import AsignarJornadaExplorador
        asignaciones = (
            AsignarJornadaExplorador.objects
            .filter(explorador_id__in=empleado_ids)
            .select_related('jornada', 'explorador')
            .order_by('explorador', '-fecha_inicio')
        )
        resultado = {}
        for a in asignaciones:
            if a.explorador_id not in resultado:
                resultado[a.explorador_id] = a.jornada.nombre if a.jornada else None
        return resultado

    @staticmethod
    def actualizar_jornada(empleado, nueva_jornada) -> None:
        from turnos.models import AsignarJornadaExplorador
        from django.utils import timezone
        AsignarJornadaExplorador.objects.filter(explorador=empleado).delete()
        AsignarJornadaExplorador.objects.create(
            explorador=empleado,
            jornada=nueva_jornada,
            fecha_inicio=timezone.localdate(),
        )

    @staticmethod
    def asignar_roles_y_salas(empleado, roles, salas) -> None:
        from empleados.models import EmpleadoRole, CompetenciaEmpleado
        EmpleadoRole.objects.filter(empleado=empleado).delete()
        for rol in roles:
            EmpleadoRole.objects.create(empleado=empleado, role=rol)
        CompetenciaEmpleado.objects.filter(empleado=empleado).delete()
        for sala in salas:
            CompetenciaEmpleado.objects.create(empleado=empleado, sala=sala)

    @staticmethod
    def crear_con_usuario(username: str, password: str, nombre: str, apellido: str,
                          cedula: str, jornada, roles=None, salas=None):
        from django.contrib.auth.models import User
        from empleados.models import Empleado, EmpleadoRole, CompetenciaEmpleado
        from turnos.models import AsignarJornadaExplorador
        from django.utils import timezone

        user = User.objects.create_user(username=username, password=password)
        empleado = Empleado.objects.create(
            user=user, nombre=nombre, apellido=apellido, cedula=cedula, activo=True
        )
        AsignarJornadaExplorador.objects.create(
            explorador=empleado, jornada=jornada, fecha_inicio=timezone.localdate()
        )
        for rol in (roles or []):
            EmpleadoRole.objects.create(empleado=empleado, role=rol)
        for sala in (salas or []):
            CompetenciaEmpleado.objects.create(empleado=empleado, sala=sala)
        return empleado

    @staticmethod
    def pagos_horas_pendientes(empleado_id: int) -> QuerySet:
        from permisos.models import PDH
        return PDH.objects.filter(tipo_registro='pago_horas', explorador_id=empleado_id)
