"""
Servicio para gestionar días especiales (festivos y mantenimiento) por año.
Responsabilidad única: Gestión de festivos y mantenimiento por año y mes.
"""
from django.db import transaction
from django.db.models import Q
from turnos.models import DiaEspecial
from datetime import date, timedelta
from typing import List, Dict, Optional, Set
import logging
from turnos.services.temporada_service import TemporadaService
from core.utils.festivos_colombia import CalculadoraFestivos

logger = logging.getLogger(__name__)


class DiaEspecialService:
    """
    Servicio para gestionar días especiales (festivos y mantenimiento).
    Permite crear, consultar y eliminar días especiales por año y tipo.
    """

    @staticmethod
    def obtener_dias_por_tipo_anio(tipo: str, anio: int) -> List[DiaEspecial]:
        """
        Obtiene todos los días especiales de un tipo y año específico.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a consultar
            
        Returns:
            Lista de objetos DiaEspecial del tipo y año especificados
        """
        return DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            activo=True
        ).exclude(es_temporada=True).order_by('fecha')

    @staticmethod
    def obtener_dias_por_tipo_mes(tipo: str, anio: int, mes: int) -> List[DiaEspecial]:
        """
        Obtiene los días especiales de un tipo, mes y año específicos.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a consultar
            mes: Mes a consultar (1-12)
            
        Returns:
            Lista de objetos DiaEspecial del tipo, mes y año especificados
        """
        return DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            mes=mes,
            activo=True
        ).exclude(es_temporada=True).order_by('fecha')

    @staticmethod
    def obtener_dias_por_tipo_por_mes(tipo: str, anio: int) -> Dict[int, List[int]]:
        """
        Obtiene los días especiales agrupados por mes.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a consultar
            
        Returns:
            Diccionario con mes como clave y lista de días como valor
            Ejemplo: {1: [15, 16, 20], 2: [10, 14]}
        """
        dias_especiales = DiaEspecialService.obtener_dias_por_tipo_anio(tipo, anio)
        resultado = {}
        
        for dia in dias_especiales:
            mes = dia.mes or dia.fecha.month
            dia_numero = dia.fecha.day
            
            if mes not in resultado:
                resultado[mes] = []
            resultado[mes].append(dia_numero)
        
        # Ordenar los días de cada mes
        for mes in resultado:
            resultado[mes].sort()
        
        return resultado

    @staticmethod
    @transaction.atomic
    def guardar_dias_especiales_anual(
        tipo: str,
        anio: int,
        dias_seleccionados: Dict[int, List[int]],
        descripcion: str = "",
        usuario=None
    ) -> tuple[bool, str]:
        """
        Guarda los días especiales para un tipo y año específicos.
        IMPORTANTE: Reemplaza todos los días existentes del mismo tipo y año.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año para el cual se guardan los días
            dias_seleccionados: Diccionario con mes como clave y lista de días como valor
                               Ejemplo: {1: [15, 16, 20], 2: [10, 14]}
            descripcion: Descripción general para todos los días
            usuario: Usuario que realiza la operación (opcional, para historial)
            
        Returns:
            Tupla (éxito, mensaje)
        """
        try:
            # Validar tipo
            if tipo not in ['festivo', 'mantenimiento']:
                return False, f"Tipo inválido: {tipo}. Debe ser 'festivo' o 'mantenimiento'."
            
            # Validar año (solo mínimo para evitar años históricos muy antiguos)
            if anio < 2000:
                return False, f"Año inválido: {anio}. Debe ser mayor o igual a 2000."
            
            # Eliminar todos los días existentes del tipo y año
            DiaEspecialService.eliminar_dias_por_tipo_anio(tipo, anio)
            
            # Crear nuevos registros
            dias_creados = 0
            
            logger.info(f"Guardando días {tipo} para año {anio}. Días seleccionados: {dias_seleccionados}")
            
            if not dias_seleccionados:
                logger.warning("No hay días seleccionados para guardar")
                return False, f"No se seleccionaron días de {tipo}."
            
            # Usar descripción por defecto si no se proporciona
            if not descripcion:
                descripcion = f"Día de {tipo}"
            
            for mes, dias in dias_seleccionados.items():
                if not dias:  # Si no hay días seleccionados para este mes, continuar
                    continue
                
                # Convertir mes a int si viene como string (del JSON)
                try:
                    mes = int(mes)
                except (ValueError, TypeError):
                    logger.warning(f"Mes inválido (no es número): {mes}")
                    continue
                
                # Validar mes
                if mes < 1 or mes > 12:
                    logger.warning(f"Mes inválido ignorado: {mes}")
                    continue
                
                for dia in dias:
                    # Convertir día a int si viene como string
                    try:
                        dia = int(dia)
                    except (ValueError, TypeError):
                        logger.warning(f"Día inválido (no es número): {dia}")
                        continue
                    
                    # Validar día según el mes
                    if not DiaEspecialService._validar_dia_mes(anio, mes, dia):
                        logger.warning(f"Día inválido ignorado: {anio}-{mes:02d}-{dia:02d}")
                        continue
                    
                    try:
                        fecha = date(anio, mes, dia)
                        
                        # Verificar si ya existe un registro para esta fecha (otro tipo o temporada)
                        dia_existente = DiaEspecial.objects.filter(fecha=fecha).first()
                        
                        if dia_existente and dia_existente.es_temporada:
                            # Si existe y es temporada, crear uno nuevo (no sobrescribir temporadas)
                            DiaEspecial.objects.create(
                                fecha=fecha,
                                tipo=tipo,
                                descripcion=descripcion,
                                es_temporada=False,
                                año_planificacion=anio,
                                mes=mes,
                                activo=True,
                                recurrente=False
                            )
                            dias_creados += 1
                        elif dia_existente and dia_existente.tipo != tipo:
                            # Si existe pero es otro tipo, crear uno nuevo
                            DiaEspecial.objects.create(
                                fecha=fecha,
                                tipo=tipo,
                                descripcion=descripcion,
                                es_temporada=False,
                                año_planificacion=anio,
                                mes=mes,
                                activo=True,
                                recurrente=False
                            )
                            dias_creados += 1
                        elif not dia_existente:
                            # Si no existe, crear nuevo
                            DiaEspecial.objects.create(
                                fecha=fecha,
                                tipo=tipo,
                                descripcion=descripcion,
                                es_temporada=False,
                                año_planificacion=anio,
                                mes=mes,
                                activo=True,
                                recurrente=False
                            )
                            dias_creados += 1
                        else:
                            # Ya existe y es del mismo tipo, actualizar
                            dia_existente.descripcion = descripcion
                            dia_existente.año_planificacion = anio
                            dia_existente.mes = mes
                            dia_existente.activo = True
                            dia_existente.save()
                            dias_creados += 1
                            
                    except ValueError as e:
                        logger.error(f"Error al crear fecha {anio}-{mes:02d}-{dia:02d}: {e}")
                        continue
            
            mensaje = f"Se guardaron {dias_creados} días de {tipo} para el año {anio}."
            return True, mensaje
            
        except Exception as e:
            logger.error(f"Error al guardar días especiales anual: {e}")
            return False, f"Error al guardar días especiales: {str(e)}"

    @staticmethod
    @transaction.atomic
    def eliminar_dias_por_tipo_anio(tipo: str, anio: int) -> int:
        """
        Elimina todos los días especiales de un tipo y año específicos.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año del cual eliminar los días
            
        Returns:
            Número de registros eliminados
        """
        eliminados = DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            es_temporada=False
        ).delete()[0]
        
        logger.info(f"Se eliminaron {eliminados} días de {tipo} del año {anio}")
        return eliminados

    @staticmethod
    def validar_fechas_dia_especial(tipo: str, anio: int, dias_seleccionados: Dict[int, List[int]]) -> tuple[bool, str]:
        """
        Valida que las fechas de días especiales sean válidas.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a validar
            dias_seleccionados: Diccionario con mes como clave y lista de días como valor
            
        Returns:
            Tupla (válido, mensaje_error)
        """
        if tipo not in ['festivo', 'mantenimiento']:
            return False, f"Tipo inválido: {tipo}. Debe ser 'festivo' o 'mantenimiento'."
        
        if anio < 2000 or anio > 2100:
            return False, f"Año inválido: {anio}. Debe estar entre 2000 y 2100."
        
        for mes, dias in dias_seleccionados.items():
            if mes < 1 or mes > 12:
                return False, f"Mes inválido: {mes}. Debe estar entre 1 y 12."
            
            for dia in dias:
                if not DiaEspecialService._validar_dia_mes(anio, mes, dia):
                    return False, f"Día inválido: {dia} para el mes {mes} del año {anio}."
        
        return True, ""

    @staticmethod
    def _validar_dia_mes(anio: int, mes: int, dia: int) -> bool:
        """
        Valida que un día sea válido para un mes y año específicos.
        Considera años bisiestos.
        
        Args:
            anio: Año
            mes: Mes (1-12)
            dia: Día
            
        Returns:
            True si el día es válido, False en caso contrario
        """
        try:
            fecha = date(anio, mes, dia)
            # Si la fecha se crea correctamente, el día es válido
            return fecha.month == mes and fecha.day == dia
        except ValueError:
            return False

    @staticmethod
    def obtener_anios_con_tipo(tipo: str) -> List[int]:
        """
        Obtiene la lista de años que tienen días especiales del tipo especificado configurados.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            
        Returns:
            Lista de años ordenados de forma descendente
        """
        anios = DiaEspecial.objects.filter(
            tipo=tipo,
            activo=True,
            es_temporada=False
        ).values_list('año_planificacion', flat=True).distinct()
        
        return sorted(set(anios), reverse=True) if anios else []

    @staticmethod
    def tiene_dias_tipo_anio(tipo: str, anio: int) -> bool:
        """
        Verifica si un año tiene días especiales del tipo especificado configurados.
        
        Args:
            tipo: Tipo de día especial ('festivo' o 'mantenimiento')
            anio: Año a verificar
            
        Returns:
            True si el año tiene días del tipo, False en caso contrario
        """
        return DiaEspecial.objects.filter(
            tipo=tipo,
            año_planificacion=anio,
            activo=True,
            es_temporada=False
        ).exists()

    @staticmethod
    @transaction.atomic
    def generar_festivos_automaticos(anio: int) -> Dict[int, List[int]]:
        """
        Genera automáticamente los festivos colombianos para un año dado y
        los persiste en la tabla DiaEspecial (tipo = 'festivo').

        - Usa CalculadoraFestivos (Ley Emiliani) como fuente principal.
        - No elimina festivos existentes: solo asegura que todos los festivos
          calculados existan como registros activos.
        - Respeta días de temporada (no los sobreescribe).

        Returns:
            Diccionario {mes: [dias]} para usar directamente en el calendario.
        """
        # Validar año mínimo (solo para evitar años históricos muy antiguos)
        if anio < 2000:
            error_msg = f"Año inválido: {anio}. Debe ser mayor o igual a 2000."
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Generando festivos automáticos para el año {anio}")

        # Obtener festivos calculados (lista de {'fecha': date, 'descripcion': str})
        festivos_calculados = CalculadoraFestivos.calcular_festivos(anio)

        # Cargar festivos ya existentes de BD para este año
        festivos_existentes = DiaEspecialService.obtener_dias_por_tipo_anio('festivo', anio)
        fechas_existentes: Set[date] = {f.fecha for f in festivos_existentes}

        resultado: Dict[int, List[int]] = {}

        for festivo in festivos_calculados:
            fecha_festivo: date = festivo['fecha']
            descripcion: str = festivo.get('descripcion') or 'Día festivo'

            # Solo procesar fechas del año solicitado (por seguridad)
            if fecha_festivo.year != anio:
                continue

            mes = fecha_festivo.month
            dia = fecha_festivo.day

            # Construir resultado agrupado por mes
            if mes not in resultado:
                resultado[mes] = []
            if dia not in resultado[mes]:
                resultado[mes].append(dia)

            # Si ya existe un DiaEspecial para esa fecha y año, no duplicar
            if fecha_festivo in fechas_existentes:
                continue

            # Verificar si hay un registro existente (otro tipo o temporada)
            dia_existente = DiaEspecial.objects.filter(fecha=fecha_festivo).first()

            # Si es día de temporada, NO lo tocamos ni creamos un nuevo festivo separado,
            # para no mezclar conceptos en la misma fecha.
            if dia_existente and dia_existente.es_temporada:
                logger.info(
                    f"Fecha {fecha_festivo} es temporada; se omite creación de festivo automático."
                )
                continue

            # Crear nuevo registro de festivo
            DiaEspecial.objects.create(
                fecha=fecha_festivo,
                tipo='festivo',
                descripcion=descripcion,
                es_temporada=False,
                año_planificacion=anio,
                mes=mes,
                activo=True,
                recurrente=False,
            )

        # Ordenar días de cada mes
        for mes in resultado:
            resultado[mes].sort()

        logger.info(
            f"Generación automática de festivos para {anio} completada. "
            f"Meses con festivos: {list(resultado.keys())}"
        )

        return resultado

    @staticmethod
    def calcular_dias_mantenimiento_automatico(anio: int) -> Dict[int, List[int]]:
        """
        Calcula automáticamente los días de mantenimiento para un año según las reglas:
        - Primer día hábil de cada semana (Lunes-Viernes)
        - Si el lunes es festivo, pasa al siguiente día hábil (martes, miércoles, etc.)
        - Si el lunes es temporada, NO se asigna día de mantenimiento esa semana
        - Si el lunes NO es temporada, se asigna como día de mantenimiento (si no es festivo)
        - Si el lunes es festivo pero no temporada, se busca el siguiente día hábil que no sea festivo ni temporada
        
        Args:
            anio: Año para el cual calcular los días de mantenimiento
            
        Returns:
            Diccionario con mes como clave y lista de días como valor
            Ejemplo: {1: [6, 13, 20, 27], 2: [2, 9, 16, 23]}
        """
        # Obtener todos los festivos del año
        festivos = DiaEspecialService.obtener_dias_por_tipo_anio('festivo', anio)
        fechas_festivos: Set[date] = {f.fecha for f in festivos}
        
        # Obtener todos los días de temporada del año
        temporadas = TemporadaService.obtener_dias_temporada_anio(anio)
        fechas_temporadas: Set[date] = {t.fecha for t in temporadas}
        
        # Inicializar resultado
        resultado: Dict[int, List[int]] = {}
        
        # Obtener el primer día del año
        fecha_actual = date(anio, 1, 1)
        
        # Avanzar hasta el primer lunes del año
        # weekday(): 0=Lunes, 1=Martes, ..., 6=Domingo
        # Si no es lunes, calcular días hasta el siguiente lunes
        if fecha_actual.weekday() != 0:  # Si no es lunes
            # Calcular días hasta el siguiente lunes
            # Si es domingo (6), avanzamos 1 día; si es martes (1), avanzamos 6 días, etc.
            dias_hasta_lunes = (7 - fecha_actual.weekday()) % 7
            fecha_actual += timedelta(days=dias_hasta_lunes)
        
        # Recorrer todas las semanas del año
        while fecha_actual.year == anio:
            # Verificar si el LUNES (primer día hábil) es temporada
            lunes_es_temporada = fecha_actual in fechas_temporadas
            
            # Si el lunes NO es temporada, calcular el día de mantenimiento
            if not lunes_es_temporada:
                dia_mantenimiento = None
                
                # Buscar el primer día hábil de la semana (Lunes-Viernes) que:
                # 1. NO sea festivo
                # 2. NO sea temporada
                for dia_semana in range(5):  # Lunes (0) a Viernes (4)
                    fecha_candidata = fecha_actual + timedelta(days=dia_semana)
                    
                    # Verificar que no se salga del año
                    if fecha_candidata.year != anio:
                        break
                    
                    # Si no es festivo Y no es temporada, este es el día de mantenimiento
                    if fecha_candidata not in fechas_festivos and fecha_candidata not in fechas_temporadas:
                        dia_mantenimiento = fecha_candidata
                        break
                
                # Si se encontró un día de mantenimiento, agregarlo al resultado
                if dia_mantenimiento:
                    mes = dia_mantenimiento.month
                    dia = dia_mantenimiento.day
                    
                    if mes not in resultado:
                        resultado[mes] = []
                    resultado[mes].append(dia)
            
            # Avanzar a la siguiente semana (7 días)
            fecha_actual += timedelta(days=7)
        
        # Ordenar los días de cada mes
        for mes in resultado:
            resultado[mes].sort()
        
        logger.info(f"Calculados {sum(len(dias) for dias in resultado.values())} días de mantenimiento automático para el año {anio}")
        
        return resultado

