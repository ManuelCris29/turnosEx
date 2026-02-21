from django.core.exceptions import ValidationError  # type: ignore
from django.db import models
from datetime import datetime
from empleados.models import Empleado


class SolicitudValidator:
    """Validador centralizado para solicitudes de cambio de turno"""

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
        from core.utils.date_utils import DateUtils
        fecha_obj = DateUtils.parse_date(fecha)
        fecha_str = fecha_obj.strftime('%Y-%m-%d')
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
    def validar_jornada_contraria_rango_permanente(solicitante: Empleado, receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None):
        """
        Validar que haya al menos un día en el rango donde las jornadas REALES sean contrarias.
        
        Esta función evalúa día a día en el rango (o días seleccionados) usando las jornadas
        REALES de cada explorador (considera cambios aprobados previos).
        
        Args:
            solicitante: Empleado que solicita el cambio
            receptor: Empleado que recibe el cambio
            fecha_inicio: Fecha de inicio del rango
            fecha_fin: Fecha de fin del rango
            dias_seleccionados: Dict con 'dias_semana' (lista de ints) o 'fechas_especificas' (lista de strings)
            
        Raises:
            ValidationError: Si no hay ningún día en el rango donde las jornadas sean contrarias
        """
        from datetime import datetime, timedelta
        from turnos.services.jornada_service import JornadaService
        
        # Convertir fechas a date si son strings
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        if isinstance(fecha_fin, str):
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Generar lista de fechas a evaluar
        fechas_a_evaluar = []
        
        if dias_seleccionados:
            fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
            dias_semana = dias_seleccionados.get('dias_semana', [])
            
            # Si hay fechas específicas, usarlas
            if fechas_especificas:
                for fecha_str in fechas_especificas:
                    try:
                        if isinstance(fecha_str, str):
                            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                        else:
                            fecha_obj = fecha_str
                        # Solo lunes-viernes
                        if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                            fechas_a_evaluar.append(fecha_obj)
                    except (ValueError, TypeError):
                        continue
            # Si hay días de semana, generar fechas
            elif dias_semana:
                fecha_actual = fecha_inicio
                while fecha_actual <= fecha_fin:
                    if fecha_actual.weekday() in dias_semana and fecha_actual.weekday() < 5:
                        fechas_a_evaluar.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
        
        # Si no hay días seleccionados, usar rango completo (solo lunes-viernes)
        if not fechas_a_evaluar:
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                    fechas_a_evaluar.append(fecha_actual)
                fecha_actual += timedelta(days=1)
        
        # Evaluar cada fecha para verificar jornadas contrarias
        dias_con_jornadas_contrarias = 0
        
        for fecha in fechas_a_evaluar:
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha)
            jornada_receptor = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha)
            
            # Si ambos tienen jornada y son contrarias, contar este día
            if jornada_solicitante and jornada_receptor:
                if jornada_solicitante.nombre != jornada_receptor.nombre:
                    dias_con_jornadas_contrarias += 1
        
        # Si no hay ningún día con jornadas contrarias, rechazar
        if dias_con_jornadas_contrarias == 0:
            raise ValidationError(
                'No se puede realizar el cambio permanente. '
                'No se encontraron días en el rango donde los empleados tengan jornadas contrarias. '
                'Los empleados deben tener jornadas opuestas (AM ↔ PM) en al menos un día del rango.'
            )
    
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
    def validar_no_sabado_ct_sencillo(fecha):
        """
        Validar que no se esté cambiando sábado en Cambio de Turno Sencillo.
        
        Args:
            fecha: Fecha a validar
        """
        from datetime import datetime
        
        if isinstance(fecha, str):
            fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
        
        if fecha.weekday() == 5:  # Sábado
            raise ValidationError('No se puede cambiar sábado por día de semana')
    
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
            dias_seleccionados: Dict con 'dias_semana' (lista de ints) o 'fechas_especificas' (lista de strings YYYY-MM-DD)
            
        Raises:
            ValidationError: Si no hay días seleccionados o son inválidos
        """
        from datetime import datetime
        
        dias_seleccionados = dias_seleccionados or {}
        dias_semana = dias_seleccionados.get('dias_semana', [])
        fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
        
        # Validar que haya al menos un día seleccionado (dias_semana o fechas_especificas)
        if not dias_semana and not fechas_especificas:
            raise ValidationError('Debe seleccionar al menos un día de la semana (lunes a viernes) para el cambio permanente.')
        
        # Validar días de semana si existen
        if dias_semana:
            # Validar que los días de semana sean lunes-viernes (0-4)
            dias_invalidos = [int(d) for d in dias_semana if int(d) < 0 or int(d) > 4]
            if dias_invalidos:
                raise ValidationError('Los cambios permanentes solo se pueden realizar de lunes a viernes (0=Lunes, 4=Viernes).')
        
        # Validar fechas específicas si existen
        if fechas_especificas:
            # Convertir fecha_inicio y fecha_fin a date si son strings
            if isinstance(fecha_inicio, str):
                fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            if isinstance(fecha_fin, str):
                fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            
            # Validar que todas las fechas estén dentro del rango
            fechas_fuera_rango = []
            for fecha_str in fechas_especificas:
                try:
                    if isinstance(fecha_str, str):
                        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                    else:
                        fecha_obj = fecha_str
                    
                    if fecha_obj < fecha_inicio or fecha_obj > fecha_fin:
                        fechas_fuera_rango.append(fecha_str)
                    
                    # Validar que no sea sábado ni domingo
                    if fecha_obj.weekday() >= 5:
                        raise ValidationError(f'Los cambios permanentes solo se pueden realizar de lunes a viernes. La fecha {fecha_str} es {"sábado" if fecha_obj.weekday() == 5 else "domingo"}.')
                except (ValueError, TypeError):
                    raise ValidationError(f'Fecha inválida en fechas específicas: {fecha_str}')
            
            if fechas_fuera_rango:
                raise ValidationError(f'Las siguientes fechas están fuera del rango seleccionado: {", ".join(fechas_fuera_rango)}')
    
    @staticmethod
    def validar_rango_completo_cambio_permanente(explorador_solicitante: Empleado, explorador_receptor: Empleado, fecha_inicio, fecha_fin, dias_seleccionados=None):
        """
        Validar que haya al menos un día válido en el rango (o días seleccionados) para cambio permanente.
        
        Los días inválidos se excluyen automáticamente (festivos, mantenimiento, descansos).
        Solo se rechaza la solicitud si NO hay ningún día válido en el rango.
        
        Días inválidos (se excluyen automáticamente):
        - Domingo
        - Sábado
        - Festivo
        - Día de mantenimiento
        - Día de temporada
        - Día de descanso del explorador
        
        Args:
            explorador_solicitante: Empleado solicitante
            explorador_receptor: Empleado receptor
            fecha_inicio: Fecha de inicio
            fecha_fin: Fecha de fin
            dias_seleccionados: Dict con días seleccionados (opcional)
            
        Raises:
            ValidationError: Si no hay ningún día válido en el rango
        """
        from datetime import datetime, timedelta
        
        if isinstance(fecha_inicio, str):
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
        if isinstance(fecha_fin, str):
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
        
        # Generar lista de fechas candidatas
        fechas_candidatas = []
        
        if dias_seleccionados:
            fechas_especificas = dias_seleccionados.get('fechas_especificas', [])
            dias_semana = dias_seleccionados.get('dias_semana', [])
            
            # Si hay fechas específicas, usarlas directamente (compatibilidad parcial)
            if fechas_especificas:
                for fecha_str in fechas_especificas:
                    try:
                        if isinstance(fecha_str, str):
                            fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                        else:
                            fecha_obj = fecha_str
                        # Solo agregar si está dentro del rango y es lunes-viernes
                        if fecha_inicio <= fecha_obj <= fecha_fin and fecha_obj.weekday() < 5:
                            fechas_candidatas.append(fecha_obj)
                    except (ValueError, TypeError):
                        continue
            # Si hay días de semana, generar fechas
            elif dias_semana:
                dias_semana_int = [int(d) for d in dias_semana]
                fecha_actual = fecha_inicio
                while fecha_actual <= fecha_fin:
                    weekday = fecha_actual.weekday()
                    if weekday in dias_semana_int and weekday < 5:
                        fechas_candidatas.append(fecha_actual)
                    fecha_actual += timedelta(days=1)
        else:
            # Validar rango completo (retrocompatibilidad) - solo lunes-viernes
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:  # Solo lunes-viernes
                    fechas_candidatas.append(fecha_actual)
                fecha_actual += timedelta(days=1)
        
        # Filtrar fechas válidas (excluir festivos, mantenimiento, descansos, etc.)
        fechas_validas = []
        
        for fecha in fechas_candidatas:
            # Validar domingo (no debería llegar aquí si ya filtramos, pero por seguridad)
            if fecha.weekday() == 6:
                continue
            
            # Validar sábado (no debería llegar aquí si ya filtramos, pero por seguridad)
            if fecha.weekday() == 5:
                continue
            
            # Verificar si es festivo
            es_festivo = False
            try:
                from turnos.models import DiaEspecial
                es_festivo = DiaEspecial.objects.filter(
                    fecha=fecha, 
                    tipo='festivo', 
                    activo=True
                ).exists()
            except ImportError:
                pass
            
            if es_festivo:
                continue  # Excluir festivo, pero no rechazar toda la solicitud
            
            # Verificar si es mantenimiento
            es_mantenimiento = False
            try:
                from turnos.models import DiaEspecial
                es_mantenimiento = DiaEspecial.objects.filter(
                    fecha=fecha,
                    tipo='mantenimiento',
                    activo=True
                ).exclude(es_temporada=True).exists()
            except ImportError:
                pass
            
            if es_mantenimiento:
                continue  # Excluir mantenimiento
            
            # Verificar si es temporada
            es_temporada = False
            try:
                from turnos.models import DiaEspecial
                es_temporada = DiaEspecial.objects.filter(
                    fecha=fecha,
                    es_temporada=True,
                    activo=True
                ).exists()
            except ImportError:
                pass
            
            if es_temporada:
                continue  # Excluir temporada
            
            # Verificar si es día de descanso del solicitante
            es_descanso_solicitante = False
            try:
                from core.utils.jornada_utils import JornadaUtils
                from turnos.services.jornada_service import JornadaService
                
                jornada_base = JornadaService.get_jornada_explorador_fecha(
                    explorador_solicitante.id, 
                    fecha.strftime('%Y-%m-%d')
                )
                if jornada_base:
                    jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
                    es_descanso_solicitante = (jornada_dia == "Descanso")
            except Exception:
                pass
            
            if es_descanso_solicitante:
                continue  # Excluir día de descanso del solicitante
            
            # Verificar si es día de descanso del receptor
            es_descanso_receptor = False
            try:
                from core.utils.jornada_utils import JornadaUtils
                from turnos.services.jornada_service import JornadaService
                
                jornada_base = JornadaService.get_jornada_explorador_fecha(
                    explorador_receptor.id, 
                    fecha.strftime('%Y-%m-%d')
                )
                if jornada_base:
                    jornada_dia = JornadaUtils.calcular_jornada_dia(jornada_base.nombre, fecha)
                    es_descanso_receptor = (jornada_dia == "Descanso")
            except Exception:
                pass
            
            if es_descanso_receptor:
                continue  # Excluir día de descanso del receptor
            
            # Si llegamos aquí, la fecha es válida
            fechas_validas.append(fecha)
        
        # Validar que haya al menos un día válido
        if not fechas_validas:
            raise ValidationError(
                'No se encontraron días válidos en el rango seleccionado. '
                'Todos los días son festivos, de mantenimiento, temporada, o días de descanso.'
            )
    
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
        Validar que el empleado no tenga una doblada activa (AM + PM) para la fecha especificada.
        
        Si un explorador tiene doblada para una fecha (ya sea como solicitante o receptor),
        no puede realizar cambios de turno adicionales para esa misma fecha.
        
        Esta validación busca directamente en turnos_turno para detectar si el empleado
        tiene AM + PM en la fecha, sin importar cómo llegó a tener esa doblada.
        
        Args:
            empleado: Empleado a validar
            fecha: Fecha a validar (puede ser string o date)
            
        Raises:
            ValidationError: Si el empleado tiene una doblada (AM + PM) para esa fecha
        """
        from datetime import datetime
        from turnos.models import Turno
        
        # Convertir fecha a date si es string
        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        elif hasattr(fecha, 'strftime'):
            fecha_obj = fecha
        else:
            # Si no se puede convertir, no validar (evitar errores)
            return
        
        # CORRECCIÓN: Buscar directamente en turnos_turno si tiene AM + PM (doblada real)
        # Esto detecta dobladas sin importar si el empleado fue solicitante o receptor
        turnos = Turno.objects.filter(
            explorador=empleado,
            fecha=fecha_obj
        ).select_related('jornada')
        
        jornadas = [t.jornada.nombre.upper() for t in turnos]
        
        # Si tiene AM + PM, es una doblada real (jornada completa)
        if 'AM' in jornadas and 'PM' in jornadas:
            raise ValidationError(
                (
                    'No se puede realizar un Cambio de Turno Sencillo porque el explorador ya tiene '
                    'una jornada doblada (AM + PM) para el '
                    f'{fecha_obj.strftime("%d/%m/%Y")}. '
                    'Este tipo de caso debe gestionarse mediante la Solicitud de Dobladas.'
                )
            )
    
    # ===== VALIDACIONES ESPECÍFICAS PARA FESTIVOS Y ROTACIÓN =====
    
    @staticmethod
    def es_festivo_semana(fecha):
        """
        Verifica si una fecha es un festivo activo de lunes a viernes.
        
        Args:
            fecha: Fecha a verificar (date o string YYYY-MM-DD)
            
        Returns:
            bool: True si es festivo de lunes a viernes, False en caso contrario
        """
        from datetime import datetime
        from turnos.models import DiaEspecial
        
        if isinstance(fecha, str):
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
        else:
            fecha_obj = fecha
        
        # Verificar que sea lunes a viernes (weekday 0-4)
        if fecha_obj.weekday() > 4:
            return False
        
        return DiaEspecial.objects.filter(
            fecha=fecha_obj,
            tipo__iexact='festivo',
            activo=True
        ).exists()

    # ===== VALIDACIONES DE CAMPOS DE TEXTO =====
    
    @staticmethod
    def validar_comentario_obligatorio(comentario: str, contexto: str = 'la solicitud'):
        """
        Valida que el comentario no esté vacío.
        
        Args:
            comentario: Texto recibido desde el formulario.
            contexto: Texto descriptivo para el mensaje de error.
        
        Raises:
            ValidationError: Si el comentario está vacío o solo tiene espacios.
        """
        from django.core.exceptions import ValidationError
        
        if not comentario or not str(comentario).strip():
            raise ValidationError(f'Debes ingresar un comentario para {contexto}.')
    
    @staticmethod
    def validar_festivos_mismo_mes(fecha1, fecha2):
        """
        Valida que dos fechas festivas sean del mismo mes calendario.
        Se usa para restringir cambios/pagos de dobladas entre festivos.
        
        Regla de negocio:
        - Los cambios de turno y pagos de dobladas entre festivos solo se permiten
          cuando ambas fechas festivas pertenecen al mismo mes calendario.
        
        Args:
            fecha1: Primera fecha (date o string YYYY-MM-DD)
            fecha2: Segunda fecha (date o string YYYY-MM-DD)
            
        Raises:
            ValidationError: Si alguna fecha no es festivo de semana o si no son del mismo mes
        """
        from datetime import datetime
        
        if isinstance(fecha1, str):
            fecha1_obj = datetime.strptime(fecha1, '%Y-%m-%d').date()
        else:
            fecha1_obj = fecha1
            
        if isinstance(fecha2, str):
            fecha2_obj = datetime.strptime(fecha2, '%Y-%m-%d').date()
        else:
            fecha2_obj = fecha2
        
        # Verificar que ambas sean festivos de semana
        if not SolicitudValidator.es_festivo_semana(fecha1_obj):
            raise ValidationError(
                f'La fecha {fecha1_obj.strftime("%d/%m/%Y")} no es un festivo de lunes a viernes.'
            )
        
        if not SolicitudValidator.es_festivo_semana(fecha2_obj):
            raise ValidationError(
                f'La fecha {fecha2_obj.strftime("%d/%m/%Y")} no es un festivo de lunes a viernes.'
            )
        
        # Validar que sean del mismo mes calendario
        if fecha1_obj.year != fecha2_obj.year or fecha1_obj.month != fecha2_obj.month:
            raise ValidationError(
                f'Los cambios y pagos de dobladas entre festivos solo se permiten cuando ambas fechas '
                f'pertenecen al mismo mes. Las fechas {fecha1_obj.strftime("%d/%m/%Y")} y '
                f'{fecha2_obj.strftime("%d/%m/%Y")} están en meses diferentes.'
            )
    
    # ===== VALIDACIONES ESPECÍFICAS PARA DOBLADA =====
    
    @staticmethod
    def validar_acuerdo_previo_obligatorio(fecha_cesion, fecha_pago, fecha_creacion_solicitud=None):
        """
        Validar que existe un acuerdo previo obligatorio para la doblada.
        
        Reglas:
        - fecha_pago es obligatoria
        - fecha_pago debe ser posterior a la fecha de creación de la solicitud
        - fecha_pago puede ser ANTES de fecha_cesion (el receptor puede pagar antes)
        
        Args:
            fecha_cesion: Fecha en que se cede la jornada
            fecha_pago: Fecha acordada para pagar
            fecha_creacion_solicitud: Fecha de creación de la solicitud (opcional, si no se proporciona usa hoy)
        
        Raises:
            ValidationError: Si no se cumple el acuerdo previo
        """
        from datetime import date
        from core.utils.date_utils import DateUtils
        
        if not fecha_pago:
            raise ValidationError('La fecha de pago es obligatoria. No existen dobladas abiertas.')
        
        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        
        # Si no se proporciona fecha_creacion_solicitud, usar hoy
        if fecha_creacion_solicitud:
            fecha_creacion_obj = DateUtils.parse_date(fecha_creacion_solicitud)
        else:
            fecha_creacion_obj = date.today()
        
        # Validar que fecha_pago sea posterior a fecha_creacion_solicitud
        if fecha_pago_obj <= fecha_creacion_obj:
            raise ValidationError(
                f'La fecha de pago ({fecha_pago_obj.strftime("%d/%m/%Y")}) debe ser posterior a la fecha de creación de la solicitud ({fecha_creacion_obj.strftime("%d/%m/%Y")})'
            )
    
    @staticmethod
    def validar_fecha_pago_diferente_cesion(fecha_cesion, fecha_pago):
        """
        Validar que fecha_pago sea diferente a fecha_cesion.

        Regla: No se puede pagar el mismo día que se cede la jornada.
        El pago puede ser ANTES o DESPUÉS de la cesión, pero nunca el mismo día.

        Ejemplo válido: cedo el 28/02, pago el 20/02 (antes está permitido).
        Ejemplo inválido: cedo el 20/02, pago el 20/02 (mismo día → bloqueado).

        Raises:
            ValidationError: Si fecha_pago == fecha_cesion
        """
        from core.utils.date_utils import DateUtils
        fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)
        fecha_pago_obj = DateUtils.parse_date(fecha_pago)

        if fecha_pago_obj == fecha_cesion_obj:
            raise ValidationError(
                f'La fecha de pago ({fecha_pago_obj.strftime("%d/%m/%Y")}) no puede ser '
                f'la misma que la fecha de cesión ({fecha_cesion_obj.strftime("%d/%m/%Y")}). '
                'Si cedes tu jornada ese día, no puedes trabajar y descansar al mismo tiempo.'
            )

    @staticmethod
    def validar_jornadas_contrarias_doblada(solicitante: Empleado, receptor: Empleado, fecha, jornada_cedida=None):
        """
        Validar que las jornadas sean contrarias para una doblada.
        
        Reglas:
        - Si solicitante tiene AM → receptor debe tener PM
        - Si solicitante tiene PM → receptor debe tener AM
        - Si solicitante está en doblada → puede solicitar a AM o PM según jornada_cedida
        
        Args:
            solicitante: Explorador que solicita la doblada
            receptor: Explorador que cubrirá la doblada
            fecha: Fecha de la doblada
            jornada_cedida: 'AM' o 'PM' (opcional, si solicitante está en doblada)
        
        Raises:
            ValidationError: Si las jornadas no son contrarias
        """
        from core.utils.date_utils import DateUtils
        from turnos.services.jornada_service import JornadaService
        from turnos.models import Turno
        
        fecha_obj = DateUtils.parse_date(fecha)
        fecha_str = fecha_obj.strftime('%Y-%m-%d')
        
        # Obtener jornada del solicitante
        jornada_solicitante = JornadaService.get_jornada_explorador_fecha(solicitante.id, fecha_str)
        
        # Si solicitante está en doblada, usar jornada_cedida
        if jornada_cedida:
            # Verificar si realmente está en doblada (tiene AM y PM)
            turnos_solicitante = Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_obj
            ).select_related('jornada')
            
            jornadas_solicitante = [t.jornada.nombre.upper() for t in turnos_solicitante]
            tiene_doblada = 'AM' in jornadas_solicitante and 'PM' in jornadas_solicitante
            
            if tiene_doblada:
                jornada_a_ceder = jornada_cedida.upper()
            else:
                # No está en doblada, usar jornada predeterminada
                if not jornada_solicitante:
                    raise ValidationError('El solicitante no tiene jornada asignada para esa fecha')
                jornada_a_ceder = jornada_solicitante.nombre.upper()
        else:
            # No hay jornada_cedida, usar jornada predeterminada
            if not jornada_solicitante:
                raise ValidationError('El solicitante no tiene jornada asignada para esa fecha')
            jornada_a_ceder = jornada_solicitante.nombre.upper()
        
        # Obtener jornada del receptor
        jornada_receptor = JornadaService.get_jornada_explorador_fecha(receptor.id, fecha_str)
        if not jornada_receptor:
            raise ValidationError('El receptor no tiene jornada asignada para esa fecha')
        
        jornada_receptor_nombre = jornada_receptor.nombre.upper()
        
        # Validar que sean contrarias
        if jornada_a_ceder == 'AM' and jornada_receptor_nombre != 'PM':
            raise ValidationError(
                f'Para ceder jornada AM, el receptor debe tener jornada PM. El receptor tiene {jornada_receptor_nombre}'
            )
        elif jornada_a_ceder == 'PM' and jornada_receptor_nombre != 'AM':
            raise ValidationError(
                f'Para ceder jornada PM, el receptor debe tener jornada AM. El receptor tiene {jornada_receptor_nombre}'
            )
    
    @staticmethod
    def validar_no_triple_turno(receptor: Empleado, fecha):
        """
        Validar que el receptor no tenga doblada activa (evitar triple turno).
        
        Args:
            receptor: Explorador receptor
            fecha: Fecha a validar
        
        Raises:
            ValidationError: Si el receptor ya tiene doblada activa
        """
        SolicitudValidator.validar_no_doblada_activa(receptor, fecha)
    
    @staticmethod
    def validar_dias_especiales_doblada(fecha):
        """
        Validar que la fecha no sea domingo ni mantenimiento.
        
        Los festivos de lunes a viernes y los días de temporada están permitidos
        (se pueden realizar solicitudes de doblada en temporada).

        Reglas:
        - No doblada en domingos ni mantenimiento.
        - Festivos (lunes a viernes) y temporada: permitidos.

        Args:
            fecha: Fecha a validar

        Raises:
            ValidationError: Si la fecha es domingo o mantenimiento
        """
        from core.utils.date_utils import DateUtils
        from turnos.models import DiaEspecial

        fecha_obj = DateUtils.parse_date(fecha)

        if fecha_obj.weekday() == 6:
            raise ValidationError('No se puede realizar doblada en domingos')

        if DiaEspecial.objects.filter(
            fecha=fecha_obj,
            tipo='mantenimiento',
            activo=True
        ).exists():
            raise ValidationError('No se puede realizar doblada en días de mantenimiento')

        # NOTA: Días de temporada y festivos de semana están permitidos para doblada
    
    @staticmethod
    def validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion):
        """
        Caso A: La fecha de pago debe estar dentro del mismo mes calendario
        que la fecha de cesión.

        Regla de negocio: El pago puede ser antes o después de la cesión,
        pero siempre dentro del mismo mes. No se puede pagar en un mes diferente
        al mes en que se cede la jornada.

        Ejemplos:
        - Cesión 20/03/2026 → Pago 05/03/2026 ✓ (ambos en marzo, pago anticipado)
        - Cesión 20/03/2026 → Pago 28/02/2026 ✗ (febrero ≠ marzo)
        - Cesión 20/03/2026 → Pago 25/03/2026 ✓ (ambos en marzo)

        Args:
            fecha_pago: Fecha de pago (string o date)
            fecha_cesion: Fecha de cesión de la jornada (string o date)

        Raises:
            ValidationError: Si la fecha de pago está en un mes diferente al de la cesión
        """
        from core.utils.date_utils import DateUtils

        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        fecha_cesion_obj = DateUtils.parse_date(fecha_cesion)

        if fecha_pago_obj.year != fecha_cesion_obj.year or fecha_pago_obj.month != fecha_cesion_obj.month:
            raise ValidationError(
                f'La fecha de pago ({fecha_pago_obj.strftime("%d/%m/%Y")}) debe estar en el mismo mes '
                f'que la fecha de cesión ({fecha_cesion_obj.strftime("%d/%m/%Y")}). '
                f'Ambas fechas deben pertenecer al mes {fecha_cesion_obj.strftime("%m/%Y")}.'
            )

    @staticmethod
    def validar_receptor_sin_solicitud_pendiente_en_fecha(receptor: Empleado, fecha_cesion):
        """
        Caso C: El receptor no puede tener ninguna solicitud pendiente (sin aprobar ni cancelar)
        para la misma fecha de cesión.

        Regla de negocio: Una solicitud pendiente puede aprobarse o cancelarse después.
        Mientras esté pendiente, no se puede enviar otra solicitud que involucre al receptor
        para esa misma fecha, ya que podría generar conflictos al aprobarse ambas.

        Args:
            receptor: Empleado receptor de la doblada
            fecha_cesion: Fecha de cesión (string o date)

        Raises:
            ValidationError: Si el receptor ya tiene una solicitud pendiente en esa fecha
        """
        from datetime import datetime
        from django.db import models as db_models
        from solicitudes.models import SolicitudCambio

        if isinstance(fecha_cesion, str):
            fecha_cesion_obj = datetime.strptime(fecha_cesion, '%Y-%m-%d').date()
        else:
            fecha_cesion_obj = fecha_cesion

        tiene_pendiente = SolicitudCambio.objects.filter(
            db_models.Q(explorador_solicitante=receptor) | db_models.Q(explorador_receptor=receptor),
            estado='pendiente',
            fecha_cambio_turno=fecha_cesion_obj
        ).exists()

        if tiene_pendiente:
            raise ValidationError(
                f'El compañero receptor ya tiene una solicitud pendiente para el '
                f'{fecha_cesion_obj.strftime("%d/%m/%Y")}. '
                'Debe esperar a que esa solicitud sea aprobada o cancelada antes de '
                'enviar una nueva para esa misma fecha.'
            )

    @staticmethod
    def validar_solicitante_sin_solicitud_pendiente_en_fecha(solicitante: Empleado, fecha_cesion):
        """
        Caso D: El solicitante no puede tener ninguna solicitud pendiente para la misma
        fecha de cesión.

        Regla de negocio: Una solicitud pendiente puede aprobarse después y generar
        conflictos si simultáneamente otra solicitud para la misma fecha se aprueba.

        Args:
            solicitante: Empleado solicitante de la doblada
            fecha_cesion: Fecha de cesión (string o date)

        Raises:
            ValidationError: Si el solicitante ya tiene una solicitud pendiente en esa fecha
        """
        from datetime import datetime
        from django.db import models as db_models
        from solicitudes.models import SolicitudCambio

        if isinstance(fecha_cesion, str):
            fecha_cesion_obj = datetime.strptime(fecha_cesion, '%Y-%m-%d').date()
        else:
            fecha_cesion_obj = fecha_cesion

        tiene_pendiente = SolicitudCambio.objects.filter(
            db_models.Q(explorador_solicitante=solicitante) | db_models.Q(explorador_receptor=solicitante),
            estado='pendiente',
            fecha_cambio_turno=fecha_cesion_obj
        ).exists()

        if tiene_pendiente:
            raise ValidationError(
                f'Ya tienes una solicitud pendiente para el {fecha_cesion_obj.strftime("%d/%m/%Y")}. '
                'Debes esperar a que sea aprobada o cancelada antes de enviar '
                'una nueva solicitud para esa misma fecha.'
            )

    @staticmethod
    def es_dia_temporada(fecha) -> bool:
        """
        Helper: verifica si una fecha es día de temporada activo.

        Args:
            fecha: Fecha a verificar (string o date)

        Returns:
            True si es temporada, False en caso contrario
        """
        from datetime import datetime
        try:
            from turnos.models import DiaEspecial
            if isinstance(fecha, str):
                fecha = datetime.strptime(fecha, '%Y-%m-%d').date()
            return DiaEspecial.objects.filter(
                fecha=fecha,
                es_temporada=True,
                activo=True
            ).exists()
        except Exception:
            return False

    @staticmethod
    def validar_receptor_no_descansa_por_doblada_en_pago(receptor: Empleado, fecha_pago):
        """
        Caso F: El receptor no puede estar descansando en la fecha de pago por
        haber cedido su propia jornada (doblada aprobada como solicitante).

        Regla de negocio: Si el receptor ya cedió su jornada ese día (doblada aprobada),
        está descansando y no puede trabajar para pagar otra doblada.

        Args:
            receptor: Empleado que sería el receptor del pago
            fecha_pago: Fecha de pago (string o date)

        Raises:
            ValidationError: Si el receptor ya descansa por una doblada aprobada en fecha_pago
        """
        from datetime import datetime
        from solicitudes.models import SolicitudCambio

        if isinstance(fecha_pago, str):
            fecha_pago_obj = datetime.strptime(fecha_pago, '%Y-%m-%d').date()
        else:
            fecha_pago_obj = fecha_pago

        descansa_por_doblada = SolicitudCambio.objects.filter(
            explorador_solicitante=receptor,
            tipo_cambio__nombre='DOBLADA',
            estado='aprobada',
            fecha_cambio_turno=fecha_pago_obj
        ).exists()

        if descansa_por_doblada:
            raise ValidationError(
                f'El compañero receptor ya cedió su jornada el {fecha_pago_obj.strftime("%d/%m/%Y")} '
                '(tiene una doblada aprobada como solicitante en esa fecha) y estará descansando. '
                'No puede trabajar para pagar otra doblada el mismo día que está descansando.'
            )

    @staticmethod
    def validar_coincidencia_jornadas_pago(deudor: Empleado, acreedor: Empleado, fecha_pago):
        """
        Validar caso crítico: coincidencia de jornadas al pagar deuda.
        
        Si deudor y acreedor tienen la misma jornada en fecha de pago (ya sea de turno asignado
        o jornada predeterminada), no se puede pagar trabajando dos veces la misma jornada.
        
        La validación considera:
        1. Primero: Turnos asignados en tabla turnos_turno para esa fecha
        2. Si no hay turno: Jornada predeterminada de AsignarJornadaExplorador
        
        Args:
            deudor: Explorador deudor
            acreedor: Explorador acreedor
            fecha_pago: Fecha de pago
        
        Returns:
            dict con:
                - coinciden: bool
                - jornada_comun: str ('AM' o 'PM') si coinciden
                - requiere_cambio_turno: bool
        """
        import logging
        from core.utils.date_utils import DateUtils
        from turnos.services.jornada_service import JornadaService
        from turnos.models import Turno
        
        logger = logging.getLogger(__name__)
        
        fecha_pago_obj = DateUtils.parse_date(fecha_pago)
        fecha_pago_str = fecha_pago_obj.strftime('%Y-%m-%d')
        
        # Obtener todos los turnos del deudor en fecha de pago para detectar dobladas
        turnos_deudor = Turno.objects.filter(explorador=deudor, fecha=fecha_pago_obj).select_related('jornada')
        turnos_acreedor = Turno.objects.filter(explorador=acreedor, fecha=fecha_pago_obj).select_related('jornada')
        
        # Verificar si el deudor tiene doblada (AM y PM en la misma fecha)
        jornadas_deudor = [t.jornada.nombre.upper() for t in turnos_deudor]
        tiene_doblada_deudor = 'AM' in jornadas_deudor and 'PM' in jornadas_deudor
        
        # Si el deudor tiene doblada, puede pagar cualquier deuda (tiene ambas jornadas)
        if tiene_doblada_deudor:
            logger.info("Validación coincidencia jornadas pago - Deudor tiene doblada", extra={
                'deudor_id': deudor.id,
                'deudor_nombre': f"{deudor.nombre} {deudor.apellido}",
                'fecha_pago': fecha_pago_str,
                'jornadas_deudor': jornadas_deudor
            })
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False
            }
        
        # Obtener jornadas (ya considera turnos primero, luego predeterminada)
        jornada_deudor = JornadaService.get_jornada_explorador_fecha(deudor.id, fecha_pago_str)
        jornada_acreedor = JornadaService.get_jornada_explorador_fecha(acreedor.id, fecha_pago_str)
        
        # Verificar si hay turnos asignados para diagnosticar la fuente
        turno_deudor = turnos_deudor.first()
        turno_acreedor = turnos_acreedor.first()
        
        fuente_deudor = 'Turno asignado' if turno_deudor else 'Jornada predeterminada'
        fuente_acreedor = 'Turno asignado' if turno_acreedor else 'Jornada predeterminada'
        
        # Logging detallado para diagnóstico
        logger.info("Validación coincidencia jornadas pago - Inicio", extra={
            'deudor_id': deudor.id,
            'deudor_nombre': f"{deudor.nombre} {deudor.apellido}",
            'acreedor_id': acreedor.id,
            'acreedor_nombre': f"{acreedor.nombre} {acreedor.apellido}",
            'fecha_pago': fecha_pago_str,
            'jornada_deudor': jornada_deudor.nombre if jornada_deudor else None,
            'jornada_acreedor': jornada_acreedor.nombre if jornada_acreedor else None,
            'fuente_deudor': fuente_deudor,
            'fuente_acreedor': fuente_acreedor,
            'turno_deudor_id': turno_deudor.id if turno_deudor else None,
            'turno_acreedor_id': turno_acreedor.id if turno_acreedor else None,
            'tiene_doblada_deudor': tiene_doblada_deudor,
            'jornadas_deudor': jornadas_deudor
        })
        
        if not jornada_deudor or not jornada_acreedor:
            logger.warning("Validación coincidencia jornadas pago - Sin jornada", extra={
                'deudor_tiene_jornada': jornada_deudor is not None,
                'acreedor_tiene_jornada': jornada_acreedor is not None
            })
            return {
                'coinciden': False,
                'jornada_comun': None,
                'requiere_cambio_turno': False
            }
        
        coinciden = jornada_deudor.nombre.upper() == jornada_acreedor.nombre.upper()
        
        resultado = {
            'coinciden': coinciden,
            'jornada_comun': jornada_deudor.nombre.upper() if coinciden else None,
            'requiere_cambio_turno': coinciden
        }
        
        # Logging del resultado
        if coinciden:
            logger.warning("Validación coincidencia jornadas pago - COINCIDENCIA DETECTADA", extra={
                'jornada_comun': resultado['jornada_comun'],
                'deudor': f"{deudor.nombre} {deudor.apellido}",
                'acreedor': f"{acreedor.nombre} {acreedor.apellido}",
                'fecha_pago': fecha_pago_str,
                'fuente_deudor': fuente_deudor,
                'fuente_acreedor': fuente_acreedor
            })
        else:
            logger.info("Validación coincidencia jornadas pago - Jornadas contrarias (OK)", extra={
                'jornada_deudor': jornada_deudor.nombre,
                'jornada_acreedor': jornada_acreedor.nombre
            })
        
        return resultado


