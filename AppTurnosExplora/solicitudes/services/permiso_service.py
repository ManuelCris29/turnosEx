from solicitudes.models import PermisoDetalle, SolicitudCambio
from empleados.models import Empleado


class PermisoService:
    @staticmethod
    def get_permisos_usuario(usuario):
        """
        Obtiene los permisos de un usuario específico
        """
        if hasattr(usuario, 'empleado'):
            return PermisoDetalle.objects.filter(
                solicitud__explorador_solicitante=usuario.empleado
            ).select_related('solicitud').order_by('-solicitud__fecha_solicitud')
        return PermisoDetalle.objects.none()

    @staticmethod
    def get_permisos_pendientes():
        """
        Obtiene todos los permisos pendientes
        """
        return PermisoDetalle.objects.filter(
            solicitud__estado='pendiente'
        ).select_related('solicitud').order_by('-solicitud__fecha_solicitud')

    @staticmethod
    def crear_permiso_detalle(solicitud, horas_solicitadas=0):
        """
        Crea un nuevo detalle de permiso
        """
        return PermisoDetalle.objects.create(
            solicitud=solicitud,
            horas_solicitadas=horas_solicitadas
        )

    @staticmethod
    def validar_permiso(empleado, fecha, horas_solicitadas):
        """
        Valida si un permiso es válido
        """
        # Verificar que el empleado esté activo
        if not empleado.activo:
            return False, "El empleado no está activo"
        
        # Verificar que las horas solicitadas sean válidas
        if horas_solicitadas <= 0:
            return False, "Las horas solicitadas deben ser mayores a 0"
        
        if horas_solicitadas > 24:
            return False, "Las horas solicitadas no pueden exceder 24 horas"
        
        # Aquí se pueden agregar más validaciones según las reglas de negocio
        # Por ejemplo: verificar límites de horas por semana, mes, etc.
        
        return True, "Permiso válido"

    @staticmethod
    def calcular_horas_acumuladas(empleado, fecha_inicio, fecha_fin):
        """
        Calcula las horas acumuladas de un empleado en un período
        """
        permisos = PermisoDetalle.objects.filter(
            solicitud__explorador_solicitante=empleado,
            solicitud__estado='aprobada',
            solicitud__fecha_solicitud__date__range=[fecha_inicio, fecha_fin]
        )
        
        total_horas = sum(permiso.horas_solicitadas for permiso in permisos)
        return total_horas 