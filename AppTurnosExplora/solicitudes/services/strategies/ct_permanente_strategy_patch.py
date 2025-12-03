    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Get available employees for CT permanente with 'Best Match' logic.
        
        Args:
            fecha: Date string in YYYY-MM-DD format (start date)
            usuario_actual: Current user's empleado instance
            **kwargs:
                - fecha_fin: Date string (optional)
                - dias_seleccionados: Dict with 'dias_semana' and 'fechas_especificas'
            
        Returns:
            List of available empleados with compatibility metadata
        """
        try:
            from datetime import datetime
            from turnos.services.jornada_service import JornadaService
            from core.utils.jornada_utils import JornadaUtils
            from empleados.models import Jornada
            
            fecha_inicio_str = fecha
            fecha_fin_str = kwargs.get('fecha_fin')
            dias_seleccionados = kwargs.get('dias_seleccionados', {})
            
            # Si no hay rango o días seleccionados, usar comportamiento por defecto (solo fecha inicio)
            if not fecha_fin_str:
                return super().get_empleados_disponibles(fecha, usuario_actual)
            
            # Convertir fechas
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            
            # 1. Generar todas las fechas válidas del rango
            fechas_a_evaluar = self._generar_fechas_validas_params(
                fecha_inicio, 
                fecha_fin, 
                dias_seleccionados
            )
            
            if not fechas_a_evaluar:
                return []
            
            # 2. Obtener todos los empleados activos (candidatos base)
            servicio_disp = get_empleado_disponibilidad_service()
            # Usar fecha inicio solo para obtener la lista base, luego filtraremos
            candidatos_base = servicio_disp.get_empleados_disponibles(fecha_inicio_str, usuario_actual)
            
            # Mapa de compatibilidad: {empleado_id: {'compatibles': [], 'incompatibles': [], 'empleado': obj}}
            mapa_compatibilidad = {}
            for cand in candidatos_base:
                mapa_compatibilidad[cand.id] = {
                    'empleado': cand,
                    'dias_compatibles': [],
                    'dias_incompatibles': []
                }
            
            # 3. Evaluar día a día
            for fecha_eval in fechas_a_evaluar:
                # Obtener jornada del usuario actual para este día
                jornada_usuario = JornadaService.get_jornada_explorador_fecha(usuario_actual.id, fecha_eval)
                
                if not jornada_usuario:
                    # Si el usuario no tiene jornada, asumimos que no hay conflicto (o que no aplica)
                    # Pero para CT, ambos deben tener jornada. Si no tiene, no puede intercambiar.
                    # Marcar como incompatible para todos (o ignorar el día)
                    continue
                
                # Determinar jornada contraria necesaria
                nombre_contraria = 'PM' if jornada_usuario.nombre == 'AM' else 'AM'
                
                # Evaluar cada candidato
                for cand_id, info in mapa_compatibilidad.items():
                    # Obtener jornada del candidato
                    jornada_cand = JornadaService.get_jornada_explorador_fecha(cand_id, fecha_eval)
                    
                    es_compatible = False
                    if jornada_cand and jornada_cand.nombre == nombre_contraria:
                        es_compatible = True
                    
                    fecha_fmt = fecha_eval.strftime('%Y-%m-%d')
                    if es_compatible:
                        info['dias_compatibles'].append(fecha_fmt)
                    else:
                        info['dias_incompatibles'].append(fecha_fmt)
            
            # 4. Construir lista de resultados con metadatos
            resultados = []
            total_dias = len(fechas_a_evaluar)
            
            for info in mapa_compatibilidad.values():
                compatibles_count = len(info['dias_compatibles'])
                if compatibles_count > 0:
                    empleado = info['empleado']
                    # Inyectar metadatos en el objeto empleado (temporalmente para serialización)
                    empleado.compatibilidad_percent = int((compatibles_count / total_dias) * 100)
                    empleado.dias_compatibles = info['dias_compatibles']
                    empleado.dias_incompatibles = info['dias_incompatibles']
                    empleado.total_dias_rango = total_dias
                    resultados.append(empleado)
            
            # 5. Ordenar por porcentaje de compatibilidad descendente
            resultados.sort(key=lambda x: x.compatibilidad_percent, reverse=True)
            
            return resultados
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Error en get_empleados_disponibles CT PERMANENTE (Rango)")
            return []

    def _generar_fechas_validas_params(self, fecha_inicio: date, fecha_fin: date, dias_seleccionados: dict) -> List[date]:
        """
        Genera lista de fechas válidas basado en parámetros directos (no objeto DB).
        """
        fechas_validas: Set[date] = set()
        
        # Extraer listas del dict
        dias_semana_list = dias_seleccionados.get('dias_semana', [])
        fechas_especificas_list = dias_seleccionados.get('fechas_especificas', []) # Por si acaso
        
        # Lógica para días de semana
        if dias_semana_list:
            for dia_str in dias_semana_list:
                try:
                    dia_semana_buscado = int(dia_str)
                    fecha_actual = fecha_inicio
                    
                    # Avanzar al primer día correspondiente
                    dias_hasta = (dia_semana_buscado - fecha_actual.weekday()) % 7
                    if dias_hasta > 0:
                        fecha_actual += timedelta(days=dias_hasta)
                    
                    while fecha_actual <= fecha_fin:
                        # Solo lunes-viernes
                        if fecha_actual.weekday() < 5:
                            fechas_validas.add(fecha_actual)
                        fecha_actual += timedelta(days=7)
                except ValueError:
                    continue
        
        # Si no hay días seleccionados explícitos, usar rango completo (lunes-viernes)
        if not dias_semana_list and not fechas_especificas_list:
            fecha_actual = fecha_inicio
            while fecha_actual <= fecha_fin:
                if fecha_actual.weekday() < 5:
                    fechas_validas.add(fecha_actual)
                fecha_actual += timedelta(days=1)
                
        return sorted(list(fechas_validas))

    def _generar_fechas_validas(self, detalle: CambioPermanenteDetalle, fecha_fin: date) -> List[date]:
        """
        Wrapper para mantener compatibilidad con el método original que usa el objeto detalle.
        """
        dias_semana = []
        fechas_especificas = []
        
        for dia in detalle.dias.all():
            if dia.tipo == 'dia_semana' and dia.dia_semana is not None:
                dias_semana.append(dia.dia_semana)
            elif dia.tipo == 'fecha_especifica' and dia.fecha_especifica:
                fechas_especificas.append(dia.fecha_especifica)
                
        dias_seleccionados = {
            'dias_semana': dias_semana,
            'fechas_especificas': fechas_especificas
        }
        
        return self._generar_fechas_validas_params(detalle.fecha_inicio, fecha_fin, dias_seleccionados)

