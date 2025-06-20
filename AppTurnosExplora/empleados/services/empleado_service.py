from django.db.models import Q
from empleados.models import Empleado, CompetenciaEmpleado

class EmpleadoService:
    @staticmethod
    def get_empleados_by_sala(sala_id):
        """
        Obtiene todos los empleados de una sala específica
        """
        return Empleado.objects.filter(competenciaempleado__sala_id=sala_id)  # type: ignore

    @staticmethod
    def buscar_empleados(query):
        """
        Búsqueda de empleados por nombre, apellido o número de empleado
        """
        return Empleado.objects.filter(Q(nombre__icontains=query) | Q(apellido__icontains=query) | Q(cedula__icontains=query))  # type: ignore

    @staticmethod
    def get_empleados_disponibles_turno(fecha, turno_id):
        """
        Obtiene los empleados disponibles para un turno específico en una fecha
        """
        return Empleado.objects.exclude(  turnos__fecha=fecha, turnos__id=turno_id)# type: ignore

    @staticmethod
    def get_salas_empleado(empleado_id):
        """
        Obtiene todas las salas asignadas a un empleado
        """
        return CompetenciaEmpleado.objects.filter(empleado_id=empleado_id).select_related('sala')  # type: ignore

    @staticmethod
    def validar_restricciones_turno(empleado_id, fecha, turno_id):
        """
        Valida si un empleado puede ser asignado a un turno específico
        considerando sus restricciones y reglas de negocio
        """
        empleado = Empleado.objects.get(id=empleado_id)  # type: ignore
        # Aquí irían las validaciones específicas
        # Por ejemplo:
        # - Verificar horas máximas semanales
        # - Verificar restricciones de horario
        # - Verificar permisos especiales
        return True  # Por ahora retornamos True 