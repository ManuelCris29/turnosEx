from django.core.exceptions import ValidationError  # type: ignore
from datetime import datetime
from empleados.models import Empleado


class SolicitudValidator:
    """Validador centralizado para solicitudes de cambio de turno"""

    @staticmethod
    def _to_date(fecha_str):
        if hasattr(fecha_str, 'strftime'):
            return fecha_str
        return datetime.strptime(str(fecha_str), '%Y-%m-%d').date()

    @staticmethod
    def validar_empleado_activo(empleado: Empleado):
        if not empleado or not getattr(empleado, 'activo', False):
            raise ValidationError('El empleado no está activo')

    @staticmethod
    def validar_no_mismo_empleado(solicitante: Empleado, receptor: Empleado):
        if solicitante.id == receptor.id:
            raise ValidationError('No puedes solicitar cambio contigo mismo')

    @staticmethod
    def validar_jornada_en_fecha(empleado: Empleado, fecha):
        # Importar aquí para evitar circular import
        from .solicitud_service import SolicitudService
        
        fecha_str = SolicitudValidator._to_date(fecha).strftime('%Y-%m-%d')
        jornada = SolicitudService.get_jornada_explorador_fecha(empleado.id, fecha_str)
        if not jornada:
            raise ValidationError('El empleado no tiene jornada asignada para esa fecha')

    @staticmethod
    def validar_duplicada_misma_fecha(solicitante: Empleado, receptor: Empleado, fecha):
        from solicitudes.models import SolicitudCambio
        existe = SolicitudCambio.objects.filter(
            explorador_solicitante=solicitante,
            explorador_receptor=receptor,
            estado='pendiente',
            fecha_cambio_turno=fecha
        ).exists()
        if existe:
            raise ValidationError('Ya existe una solicitud pendiente con este explorador para la misma fecha')

    # ===== VALIDACIONES ESPECÍFICAS PARA CT PERMANENTE =====
    
    @staticmethod
    def validar_fechas_cambio_permanente(fecha_inicio, fecha_fin=None):
        """
        Validar fechas para cambio permanente.
        
        Args:
            fecha_inicio: Fecha de inicio del cambio permanente
            fecha_fin: Fecha de fin del cambio permanente (opcional)
        """
        from datetime import date, datetime
        
        # Convertir a date si es string
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        if fecha_fin and isinstance(fecha_fin, str):
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Validar que fecha_inicio no sea en el pasado
        if fecha_inicio < date.today():
            raise ValidationError('La fecha de inicio no puede ser en el pasado')
        
        # Validar que fecha_fin sea posterior a fecha_inicio
        if fecha_fin and fecha_fin <= fecha_inicio:
            raise ValidationError('La fecha fin debe ser posterior a la fecha inicio')
    
    @staticmethod
    def validar_jornada_contraria(solicitante: Empleado, receptor: Empleado, fecha):
        """
        Validar que los empleados tengan jornadas contrarias.
        
        Args:
            solicitante: Empleado que solicita el cambio
            receptor: Empleado que recibe el cambio
            fecha: Fecha para verificar las jornadas
        """
        from .solicitud_service import SolicitudService
        
        # Obtener jornadas de ambos empleados
        jornada_solicitante = SolicitudService.get_jornada_explorador_fecha(solicitante.id, fecha)
        jornada_receptor = SolicitudService.get_jornada_explorador_fecha(receptor.id, fecha)
        
        if not jornada_solicitante or not jornada_receptor:
            raise ValidationError('Ambos empleados deben tener jornada asignada para esa fecha')
        
        # Verificar que tengan jornadas contrarias
        if jornada_solicitante.nombre == jornada_receptor.nombre:
            raise ValidationError('No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias')
    
    @staticmethod
    def validar_no_dia_mantenimiento(fecha):
        """
        Validar que no sea día de mantenimiento.
        
        Args:
            fecha: Fecha a validar
        """
        from datetime import datetime
        try:
            from turnos.models import DiaEspecial
            
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            
            # Verificar si es día de mantenimiento
            es_mantenimiento = DiaEspecial.objects.filter(
                fecha=fecha,
                tipo='mantenimiento'
            ).exists()
            
            if es_mantenimiento:
                raise ValidationError('No se pueden realizar cambios en días de mantenimiento')
                
        except ImportError:
            # Si no existe el modelo, no validar
            pass
    
    @staticmethod
    def validar_no_domingo_por_semana(fecha, es_cambio_permanente=False):
        """
        Validar que no se esté cambiando domingo por día de semana.
        Para CT PERMANENTE: No bloquear si hay domingos (se filtrarán automáticamente)
        
        Args:
            fecha: Fecha a validar
            es_cambio_permanente: Si es True, no bloquear domingos
        """
        from datetime import datetime
        
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
        
        # Para CT PERMANENTE: No validar domingos (se filtrarán en aplicar_cambios)
        if es_cambio_permanente:
            return True
        
        # Para CT normal: Mantener validación estricta
        if fecha.weekday() == 6:
            raise ValidationError('No se puede cambiar domingo por día de semana')
    
    @staticmethod
    def validar_no_festivo_por_semana(fecha, es_cambio_permanente=False):
        """
        Validar que no se esté cambiando festivo por día de semana.
        Para CT PERMANENTE: No bloquear si hay festivos (se filtrarán automáticamente)
        
        Args:
            fecha: Fecha a validar
            es_cambio_permanente: Si es True, no bloquear festivos
        """
        from datetime import datetime
        
        # Para CT PERMANENTE: No validar festivos (se filtrarán en aplicar_cambios)
        if es_cambio_permanente:
            return True
            
        try:
            from turnos.models import DiaEspecial
            
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            
            # Verificar si es festivo
            es_festivo = DiaEspecial.objects.filter(
                fecha=fecha,
                tipo='festivo'
            ).exists()
            
            if es_festivo:
                raise ValidationError('No se puede cambiar festivo por día de semana')
                
        except ImportError:
            # Si no existe el modelo, no validar
            pass
    
    @staticmethod
    def validar_no_cambio_permanente_superpuesto(solicitante: Empleado, receptor: Empleado, fecha_inicio, fecha_fin=None):
        """
        Validar que no haya cambios permanentes superpuestos.
        
        Args:
            solicitante: Empleado que solicita
            receptor: Empleado que recibe
            fecha_inicio: Fecha de inicio del cambio
            fecha_fin: Fecha de fin del cambio (opcional)
        """
        from datetime import datetime
        from solicitudes.models import SolicitudCambio, CambioPermanenteDetalle
        
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        if fecha_fin and isinstance(fecha_fin, str):
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Buscar cambios permanentes existentes entre estos empleados
        cambios_existentes = SolicitudCambio.objects.filter(
            explorador_solicitante=solicitante,
            explorador_receptor=receptor,
            tipo_cambio__nombre='CT PERMANENTE',
            estado__in=['pendiente', 'aprobada']
        ).select_related('cambio_permanente')
        
        for cambio in cambios_existentes:
            detalle = cambio.cambio_permanente
            if detalle:
                # Verificar superposición de fechas
                if fecha_fin:
                    # Si hay fecha fin, verificar que no se superponga
                    if (fecha_inicio <= detalle.fecha_fin or not detalle.fecha_fin) and \
                       (fecha_fin >= detalle.fecha_inicio):
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
                else:
                    # Si no hay fecha fin, verificar que no se superponga
                    if fecha_inicio <= (detalle.fecha_fin or datetime.now().date()) and \
                       fecha_inicio >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')


