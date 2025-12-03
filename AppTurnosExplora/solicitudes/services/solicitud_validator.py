from django.core.exceptions import ValidationError  # type: ignore
from django.db import models
from datetime import datetime
from empleados.models import Empleado


class SolicitudValidator:
    """Validador centralizado para solicitudes de cambio de turno"""

    @staticmethod
    def _to_date(fecha_str):
        """DEPRECATED: Usar core.utils.date_utils.DateUtils.parse_date()"""
        from core.utils.date_utils import DateUtils
        return DateUtils.parse_date(fecha_str)

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
        fecha_str = SolicitudValidator._to_date(fecha).strftime('%Y-%m-%d')
        from turnos.services.jornada_service import JornadaService
        jornada = JornadaService.get_jornada_explorador_fecha(empleado.id, fecha_str)
        if not jornada:
            raise ValidationError('El empleado no tiene jornada asignada para esa fecha')

    @staticmethod
    def validar_duplicada_misma_fecha(solicitante: Empleado, receptor: Empleado, fecha):
        """
        Valida que no exista una solicitud pendiente del mismo par (solicitante-receptor-fecha).
        
        FASE 1.13: Esta validación permite que múltiples solicitantes envíen solicitudes
        al mismo receptor para la misma fecha (First-Come, First-Served).
        Solo previene que el mismo solicitante envíe múltiples solicitudes al mismo receptor.
        
        Ejemplos permitidos:
        - A→X, fecha 15/12 → ✅ Permite
        - B→X, fecha 15/12 → ✅ Permite (diferente solicitante)
        - C→X, fecha 15/12 → ✅ Permite (diferente solicitante)
        
        Ejemplos rechazados:
        - A→X, fecha 15/12 (segunda vez) → ❌ Rechaza (mismo par)
        """
        from solicitudes.models import SolicitudCambio
        existe = SolicitudCambio.objects.filter(
            explorador_solicitante=solicitante,
            explorador_receptor=receptor,
            estado='pendiente',
            fecha_cambio_turno=fecha
        ).exists()
        if existe:
            raise ValidationError('Ya existe una solicitud pendiente tuya con este explorador para la misma fecha')

    # ===== VALIDACIONES ESPECÍFICAS PARA CT PERMANENTE =====
    
    @staticmethod
    def validar_fechas_cambio_permanente(fecha_inicio, fecha_fin=None):
        """
        Validar fechas para cambio permanente.
        
        Args:
            fecha_inicio: Fecha de inicio del cambio permanente
            fecha_fin: Fecha de fin del cambio permanente (OBLIGATORIA según reglas de negocio)
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
        
        # Validar que fecha_fin sea obligatoria
        if not fecha_fin:
            raise ValidationError('La fecha fin es obligatoria para cambios permanentes')
        
        # Validar que fecha_fin sea posterior a fecha_inicio
        if fecha_fin <= fecha_inicio:
            raise ValidationError('La fecha fin debe ser posterior a la fecha inicio')
    
    @staticmethod
    def validar_jornada_contraria(solicitante: Empleado, receptor: Empleado, fecha, jornada_solicitante=None, jornada_receptor=None):
        """
        Validar que los empleados tengan jornadas contrarias.
        
        OPTIMIZACIÓN: Si se proporcionan las jornadas como parámetro, no se vuelven a consultar.
        Esto evita consultas duplicadas cuando ya se obtuvieron en validar_jornada_en_fecha.
        
        Args:
            solicitante: Empleado que solicita el cambio
            receptor: Empleado que recibe el cambio
            fecha: Fecha para verificar las jornadas
            jornada_solicitante: (Opcional) Jornada del solicitante ya obtenida
            jornada_receptor: (Opcional) Jornada del receptor ya obtenida
        """
        from turnos.services.jornada_service import JornadaService
        
        # Obtener jornadas solo si no se proporcionaron como parámetro
        if jornada_solicitante is None:
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha)
        if jornada_receptor is None:
            jornada_receptor = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha)
        
        # NOTA: No validamos existencia aquí porque se garantiza que se llama después de validar_jornada_en_fecha
        # Si las jornadas son None, es un error de programación, no de validación de negocio
        
        # Verificar que tengan jornadas contrarias
        if jornada_solicitante and jornada_receptor and jornada_solicitante.nombre == jornada_receptor.nombre:
            raise ValidationError('No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias')
    
    @staticmethod
    def validar_no_dia_mantenimiento(fecha):
        """
        Validar que no sea día de mantenimiento.
        
        Args:
            fecha: Fecha a validar (puede ser string YYYY-MM-DD o date object)
            
        Raises:
            ValidationError: Si la fecha es un día de mantenimiento activo
        """
        from datetime import datetime
        try:
            from turnos.models import DiaEspecial
            
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            
            # Verificar si es día de mantenimiento activo
            es_mantenimiento = DiaEspecial.objects.filter(
                fecha=fecha,
                tipo='mantenimiento',
                activo=True
            ).exclude(es_temporada=True).exists()
            
            if es_mantenimiento:
                # Obtener descripción del día de mantenimiento para mensaje más informativo
                dia_mantenimiento = DiaEspecial.objects.filter(
                    fecha=fecha,
                    tipo='mantenimiento',
                    activo=True
                ).exclude(es_temporada=True).first()
                
                descripcion = dia_mantenimiento.descripcion if dia_mantenimiento and dia_mantenimiento.descripcion else 'Día de mantenimiento'
                raise ValidationError(f'No se pueden realizar cambios de turno en días de mantenimiento. {descripcion}')
                
        except ImportError:
            # Si no existe el modelo, no validar
            pass
        except ValueError:
            # Si la fecha no es válida, no validar (otra validación la manejará)
            pass
    
    @staticmethod
    def validar_no_temporada(fecha):
        """
        Validar que no sea día de temporada.
        
        Args:
            fecha: Fecha a validar (puede ser string YYYY-MM-DD o date object)
            
        Raises:
            ValidationError: Si la fecha es un día de temporada activo
        """
        from datetime import datetime
        try:
            from turnos.models import DiaEspecial
            
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            
            # Verificar si es día de temporada activo
            es_temporada = DiaEspecial.objects.filter(
                fecha=fecha,
                es_temporada=True,
                activo=True
            ).exists()
            
            if es_temporada:
                # Obtener descripción del día de temporada para mensaje más informativo
                dia_temporada = DiaEspecial.objects.filter(
                    fecha=fecha,
                    es_temporada=True,
                    activo=True
                ).first()
                
                descripcion = dia_temporada.descripcion if dia_temporada and dia_temporada.descripcion else 'Día de temporada'
                raise ValidationError(f'No se pueden realizar cambios permanentes en días de temporada. {descripcion}')
                
        except ImportError:
            # Si no existe el modelo, no validar
            pass
        except ValueError:
            # Si la fecha no es válida, no validar (otra validación la manejará)
            pass
    
    @staticmethod
    def validar_no_domingo_por_semana(fecha, es_cambio_permanente=False):
        """
        Validar que no se esté cambiando domingo por día de semana.
        Para CT PERMANENTE: NO permitir domingos (regla de negocio estricta)
        
        Args:
            fecha: Fecha a validar
            es_cambio_permanente: Si es True, validar estrictamente (NO permitir domingos)
        """
        from datetime import datetime
        
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
        
        # Para CT PERMANENTE: Validar estrictamente (NO permitir domingos)
        if es_cambio_permanente:
            if fecha.weekday() == 6:
                raise ValidationError('No se pueden realizar cambios permanentes en domingos')
            return True
        
        # Para CT normal: Mantener validación estricta
        if fecha.weekday() == 6:
            raise ValidationError('No se puede cambiar domingo por día de semana')
    
    @staticmethod
    def validar_no_sabado(fecha, es_cambio_permanente=False):
        """
        Validar que no se esté cambiando sábado.
        Para CT PERMANENTE: NO permitir sábados (regla de negocio estricta - solo lunes-viernes)
        
        Args:
            fecha: Fecha a validar
            es_cambio_permanente: Si es True, validar estrictamente (NO permitir sábados)
        """
        from datetime import datetime
        
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
        
        # Para CT PERMANENTE: Validar estrictamente (NO permitir sábados)
        if es_cambio_permanente:
            if fecha.weekday() == 5:  # Sábado
                raise ValidationError('No se pueden realizar cambios permanentes en sábados. Solo se permiten lunes a viernes.')
            return True
        
        # Para CT normal: No validar sábados (pueden ser válidos en otros tipos)
        return True
    
    @staticmethod
    def validar_no_festivo_por_semana(fecha, es_cambio_permanente=False):
        """
        Validar que no se esté cambiando festivo por día de semana.
        Para CT PERMANENTE: NO permitir festivos (regla de negocio estricta)
        
        Para Cambio Turno (CT): El sistema ya filtra en get_empleados_jornada_contraria
        para mostrar solo exploradores que tienen jornada en esa fecha (incluyendo festivos).
        Por lo tanto, si un explorador aparece en la lista, ya tiene jornada en esa fecha.
        
        Args:
            fecha: Fecha a validar
            es_cambio_permanente: Si es True, validar estrictamente (NO permitir festivos)
        """
        from datetime import datetime
        
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
        
        # Para CT PERMANENTE: Validar estrictamente (NO permitir festivos)
        if es_cambio_permanente:
            try:
                from turnos.models import DiaEspecial
                es_festivo = DiaEspecial.objects.filter(
                    fecha=fecha, 
                    tipo='festivo', 
                    activo=True
                ).exists()
                if es_festivo:
                    raise ValidationError('No se pueden realizar cambios permanentes en días festivos')
            except ImportError:
                pass
            return True
            
        # Para CT: No hay restricción adicional aquí porque get_empleados_jornada_contraria
        # ya filtra correctamente para mostrar solo exploradores con jornada en esa fecha
        pass
    
    @staticmethod
    def validar_no_dia_descanso(explorador: Empleado, fecha):
        """
        Validar que el explorador no esté descansando en la fecha especificada.
        
        Args:
            explorador: Empleado a validar
            fecha: Fecha a validar (puede ser string YYYY-MM-DD o date object)
            
        Raises:
            ValidationError: Si el explorador está descansando en esa fecha
        """
        from datetime import datetime
        try:
            from core.utils.jornada_utils import JornadaUtils
            from turnos.services.jornada_service import JornadaService
            
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            
            # Obtener jornada base del explorador
            jornada_base = JornadaService.get_jornada_explorador_fecha(explorador.id, fecha.strftime('%Y-%m-%d'))
            
            if not jornada_base:
                raise ValidationError(f'El explorador no tiene jornada asignada para el {fecha.strftime("%d/%m/%Y")}')
            
            # Calcular jornada del día
            jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
            
            # Si la jornada del día es "Descanso", el explorador está descansando
            if jornada_dia == "Descanso":
                raise ValidationError(f'No se pueden realizar cambios cuando el explorador está descansando el {fecha.strftime("%d/%m/%Y")}')
                
        except ImportError:
            # Si no existe el módulo, no validar
            pass
        except ValueError as e:
            # Si la fecha no es válida o hay otro error, propagar
            raise ValidationError(str(e))
    
    @staticmethod
    def validar_dias_seleccionados_permanente(fecha_inicio, fecha_fin, dias_seleccionados):
        """
        Validar que haya al menos un día seleccionado y que todos estén dentro del rango.
        
        Args:
            fecha_inicio: Fecha de inicio del cambio permanente
            fecha_fin: Fecha de fin del cambio permanente
            dias_seleccionados: Dict con 'dias_semana' (lista de ints)
            
        Raises:
            ValidationError: Si no hay días seleccionados o son inválidos
        """
        dias_seleccionados = dias_seleccionados or {}
        dias_semana = dias_seleccionados.get('dias_semana', [])
        
        # Validar que haya al menos un día seleccionado (lunes-viernes)
        if not dias_semana:
            raise ValidationError('Debe seleccionar al menos un día de la semana (lunes a viernes) para el cambio permanente.')
        
        # Validar que los días de semana sean lunes-viernes (0-4)
        dias_invalidos = [int(d) for d in dias_semana if int(d) < 0 or int(d) > 4]
        if dias_invalidos:
            raise ValidationError('Los cambios permanentes solo se pueden realizar de lunes a viernes (0=Lunes, 4=Viernes).')
    
    @staticmethod
    def validar_rango_completo_cambio_permanente(explorador_solicitante: Empleado, explorador_receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None):
        """
        Validar todos los días del rango (o días seleccionados) para cambio permanente.
        
        Valida que ningún día sea:
        - Domingo
        - Festivo
        - Día de mantenimiento
        - Día de descanso del explorador
        
        Args:
            explorador_solicitante: Empleado solicitante
            explorador_receptor: Empleado receptor
            fecha_inicio: Fecha de inicio
            fecha_fin: Fecha de fin
            dias_seleccionados: Dict con días seleccionados (opcional)
            
        Raises:
            ValidationError: Si algún día del rango no es válido
        """
        from datetime import datetime, timedelta
        
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        if isinstance(fecha_fin, str):
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Generar lista de fechas a validar
        fechas_a_validar = []
        
        if dias_seleccionados:
            # Validar solo días de semana seleccionados (lunes-viernes)
            dias_semana = [int(d) for d in dias_seleccionados.get('dias_semana', [])]
            
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                weekday = fecha_actual.weekday()
                if weekday in dias_semana and weekday < 5:
                    fechas_a_validar.append(fecha_actual)
                fecha_actual += timedelta(days=1)
        else:
            # Validar rango completo (retrocompatibilidad)
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                fechas_a_validar.append(fecha_actual)
                fecha_actual += timedelta(days=1)
        
        # Validar cada fecha
        for fecha in fechas_a_validar:
            # Validar domingo
            if fecha.weekday() == 6:
                raise ValidationError(f'No se pueden realizar cambios permanentes en domingos ({fecha.strftime("%d/%m/%Y")})')
            
            # Validar sábado - CT PERMANENTE solo permite lunes-viernes
            if fecha.weekday() == 5:
                raise ValidationError(f'No se pueden realizar cambios permanentes en sábados ({fecha.strftime("%d/%m/%Y")}). Solo se permiten lunes a viernes.')
            
            # Validar festivo
            SolicitudValidator.validar_no_festivo_por_semana(fecha, es_cambio_permanente=True)
            
            # Validar mantenimiento
            SolicitudValidator.validar_no_dia_mantenimiento(fecha)
            
            # Validar temporada
            SolicitudValidator.validar_no_temporada(fecha)
            
            # Validar día de descanso del solicitante
            SolicitudValidator.validar_no_dia_descanso(explorador_solicitante, fecha)
            
            # Validar día de descanso del receptor
            SolicitudValidator.validar_no_dia_descanso(explorador_receptor, fecha)
    
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
        # Verificar en ambas direcciones: solicitante->receptor y receptor->solicitante
        cambios_existentes = SolicitudCambio.objects.filter(
            (
                (models.Q(explorador_solicitante=solicitante) & models.Q(explorador_receptor=receptor)) |
                (models.Q(explorador_solicitante=receptor) & models.Q(explorador_receptor=solicitante))
            ),
            tipo_cambio__nombre='CT PERMANENTE',
            estado__in=['pendiente', 'aprobada']
        ).select_related('cambio_permanente')
        
        for cambio in cambios_existentes:
            detalle = cambio.cambio_permanente
            if detalle:
                # Lógica correcta de superposición de rangos:
                # Dos rangos [a1, b1] y [a2, b2] se superponen si: a1 <= b2 AND b1 >= a2
                # Si b1 o b2 es None, significa que el rango es indefinido (hasta el futuro)
                
                fecha_fin_existente = detalle.fecha_fin
                fecha_fin_nueva = fecha_fin
                
                # Si el cambio existente no tiene fecha fin, se considera indefinido (hasta el futuro)
                # Si el cambio nuevo no tiene fecha fin, también se considera indefinido
                
                # Verificar superposición:
                # - Si ambos tienen fecha fin: fecha_inicio <= fecha_fin_existente AND fecha_fin_nueva >= detalle.fecha_inicio
                # - Si existente no tiene fecha fin: fecha_inicio >= detalle.fecha_inicio (cualquier fecha nueva se superpone)
                # - Si nuevo no tiene fecha fin: fecha_inicio <= (fecha_fin_existente o futuro) AND fecha_inicio >= detalle.fecha_inicio
                
                if fecha_fin_existente is None:
                    # Cambio existente es indefinido: cualquier fecha nueva que sea >= fecha_inicio_existente se superpone
                    if fecha_inicio >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
                elif fecha_fin_nueva is None:
                    # Cambio nuevo es indefinido: se superpone si fecha_inicio <= fecha_fin_existente
                    if fecha_inicio <= fecha_fin_existente and fecha_inicio >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
                else:
                    # Ambos tienen fecha fin: verificar superposición estándar
                    if fecha_inicio <= fecha_fin_existente and fecha_fin_nueva >= detalle.fecha_inicio:
                        raise ValidationError('Ya existe un cambio permanente superpuesto entre estos empleados')
    
    # ===== VALIDACIONES ESPECÍFICAS PARA CAMBIO TURNO (CT) =====
    
    @staticmethod
    def validar_no_doblada_activa(empleado: Empleado, fecha):
        """
        Validar que el empleado no tenga una doblada activa (aprobada) para la fecha especificada.
        
        Si un explorador tiene doblada aprobada para una fecha, no puede realizar cambios de turno
        con otros exploradores para esa misma fecha.
        
        Args:
            empleado: Empleado a validar
            fecha: Fecha a validar (puede ser string o date)
            
        Raises:
            ValidationError: Si el empleado tiene una doblada aprobada para esa fecha
        """
        from datetime import datetime
        from solicitudes.models import SolicitudCambio
        
        # Convertir fecha a date si es string
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
        elif hasattr(fecha, 'strftime'):
            fecha = fecha
        else:
            # Si no se puede convertir, no validar (evitar errores)
            return
        
        # Buscar solicitudes de doblada aprobadas para este empleado y fecha
        doblada_activa = SolicitudCambio.objects.filter(
            explorador_solicitante=empleado,
            tipo_cambio__nombre='DOBLADA',
            fecha_cambio_turno=fecha,
            estado='aprobada'
        ).exists()
        
        if doblada_activa:
            raise ValidationError(
                f'No se puede realizar cambio de turno. El explorador tiene una doblada aprobada para el {fecha.strftime("%d/%m/%Y")}'
            )


