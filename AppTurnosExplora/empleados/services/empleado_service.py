from django.db.models import Q

from empleados.models import Empleado


class EmpleadoService:
    @staticmethod
    def get_empleados_by_sala(sala_id):
        """
        Obtiene todos los empleados de una sala específica
        OPTIMIZACIÓN: Pre-cargar relaciones para evitar N+1
        """
        return (
            Empleado.objects
            .filter(competenciaempleado__sala_id=sala_id)
            .select_related('supervisor', 'user')
            .prefetch_related(
                'competenciaempleado_set__sala',
                'empleadorole_set__role',
            )
        )  # type: ignore

    @staticmethod
    def buscar_empleados(query):
        """
        Búsqueda de empleados por nombre, apellido o número de empleado
        OPTIMIZACIÓN: Pre-cargar relaciones para evitar N+1
        """
        return (
            Empleado.objects
            .filter(Q(nombre__icontains=query) | Q(apellido__icontains=query) | Q(cedula__icontains=query))
            .select_related('supervisor', 'user')
            .prefetch_related(
                'competenciaempleado_set__sala',
                'empleadorole_set__role',
            )
        )  # type: ignore

