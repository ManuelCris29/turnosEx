"""
Servicio para gestionar días de temporada.
Responsabilidad única: Gestión de temporadas por año y mes.
"""
from django.db import transaction
from django.db.models import Q
from turnos.models import DiaEspecial
from datetime import date
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class TemporadaService:
    """
    Servicio para gestionar días de temporada.
    Permite crear, consultar y eliminar temporadas por año.
    """

    @staticmethod
    def obtener_dias_temporada_anio(anio: int) -> List[DiaEspecial]:
        """
        Obtiene todos los días de temporada de un año específico.
        
        Args:
            anio: Año a consultar
            
        Returns:
            Lista de objetos DiaEspecial que son temporadas del año especificado
        """
        return DiaEspecial.objects.filter(
            año_planificacion=anio,
            es_temporada=True,
            activo=True
        ).order_by('fecha')

    @staticmethod
    def obtener_dias_temporada_mes(anio: int, mes: int) -> List[DiaEspecial]:
        """
        Obtiene los días de temporada de un mes específico de un año.
        
        Args:
            anio: Año a consultar
            mes: Mes a consultar (1-12)
            
        Returns:
            Lista de objetos DiaEspecial que son temporadas del mes especificado
        """
        return DiaEspecial.objects.filter(
            año_planificacion=anio,
            mes=mes,
            es_temporada=True,
            activo=True
        ).order_by('fecha')

    @staticmethod
    def obtener_dias_temporada_por_mes(anio: int) -> Dict[int, List[int]]:
        """
        Obtiene los días de temporada agrupados por mes.
        
        Args:
            anio: Año a consultar
            
        Returns:
            Diccionario con mes como clave y lista de días como valor
            Ejemplo: {1: [15, 16, 20], 2: [10, 14]}
        """
        dias_temporada = TemporadaService.obtener_dias_temporada_anio(anio)
        resultado = {}
        
        for dia in dias_temporada:
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
    def guardar_temporadas_anual(
        anio: int, 
        dias_seleccionados: Dict[int, List[int]], 
        usuario=None
    ) -> tuple[bool, str]:
        """
        Guarda los días de temporada para un año específico.
        IMPORTANTE: Reemplaza todas las temporadas existentes del año.
        
        Args:
            anio: Año para el cual se guardan las temporadas
            dias_seleccionados: Diccionario con mes como clave y lista de días como valor
                               Ejemplo: {1: [15, 16, 20], 2: [10, 14]}
            usuario: Usuario que realiza la operación (opcional, para historial)
            
        Returns:
            Tupla (éxito, mensaje)
        """
        from core.services.cache_service import CacheService

        # Guarda contra dos guardados simultáneos del mismo año (dos pestañas, doble-clic):
        # el patrón es "borrar todo y recrear", así que sin este lock la segunda escritura
        # pisaría en silencio lo que la primera acababa de crear.
        clave_lock = f"temporadas_lock_{anio}"
        if not CacheService.acquire_lock(clave_lock, ttl=15):
            return False, f"Ya hay un guardado en curso para las temporadas del año {anio}. Espera unos segundos y reintenta."

        try:
            # Validar año
            if anio < 2000 or anio > 2100:
                return False, f"Año inválido: {anio}. Debe estar entre 2000 y 2100."

            # Eliminar todas las temporadas existentes del año
            TemporadaService.eliminar_temporadas_anio(anio)
            
            # Crear nuevos registros
            dias_creados = 0
            
            # Debug: Log de días seleccionados recibidos
            logger.info(f"Guardando temporadas para año {anio}. Días seleccionados: {dias_seleccionados}")
            
            if not dias_seleccionados:
                logger.warning("No hay días seleccionados para guardar")
                return False, "No se seleccionaron días de temporada."
            
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
                    if not TemporadaService._validar_dia_mes(anio, mes, dia):
                        logger.warning(f"Día inválido ignorado: {anio}-{mes:02d}-{dia:02d}")
                        continue
                    
                    try:
                        fecha = date(anio, mes, dia)
                        
                        # Verificar si ya existe un registro para esta fecha (festivo/mantenimiento)
                        # Si existe, no lo sobrescribimos, solo creamos si no existe
                        dia_existente = DiaEspecial.objects.filter(fecha=fecha).first()
                        
                        if dia_existente and not dia_existente.es_temporada:
                            # Si existe pero no es temporada, crear uno nuevo
                            DiaEspecial.objects.create(
                                fecha=fecha,
                                tipo='temporada',
                                descripcion='Día de temporada',
                                es_temporada=True,
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
                                tipo='temporada',
                                descripcion='Día de temporada',
                                es_temporada=True,
                                año_planificacion=anio,
                                mes=mes,
                                activo=True,
                                recurrente=False
                            )
                            dias_creados += 1
                        else:
                            # Ya existe y es temporada, actualizar
                            dia_existente.año_planificacion = anio
                            dia_existente.mes = mes
                            dia_existente.activo = True
                            dia_existente.save()
                            dias_creados += 1
                            
                    except ValueError as e:
                        logger.error(f"Error al crear fecha {anio}-{mes:02d}-{dia:02d}: {e}")
                        continue
            
            mensaje = f"Se guardaron {dias_creados} días de temporada para el año {anio}."
            return True, mensaje

        except Exception as e:
            logger.error(f"Error al guardar temporadas anual: {e}")
            return False, f"Error al guardar temporadas: {str(e)}"
        finally:
            CacheService.delete(clave_lock)

    @staticmethod
    @transaction.atomic
    def eliminar_temporadas_anio(anio: int) -> int:
        """
        Elimina todas las temporadas de un año específico.
        
        Args:
            anio: Año del cual eliminar las temporadas
            
        Returns:
            Número de registros eliminados
        """
        eliminados = DiaEspecial.objects.filter(
            año_planificacion=anio,
            es_temporada=True
        ).delete()[0]
        
        logger.info(f"Se eliminaron {eliminados} días de temporada del año {anio}")
        return eliminados

    @staticmethod
    def validar_fechas_temporada(anio: int, dias_seleccionados: Dict[int, List[int]]) -> tuple[bool, str]:
        """
        Valida que las fechas de temporada sean válidas.
        
        Args:
            anio: Año a validar
            dias_seleccionados: Diccionario con mes como clave y lista de días como valor
            
        Returns:
            Tupla (válido, mensaje_error)
        """
        if anio < 2000 or anio > 2100:
            return False, f"Año inválido: {anio}. Debe estar entre 2000 y 2100."
        
        for mes, dias in dias_seleccionados.items():
            if mes < 1 or mes > 12:
                return False, f"Mes inválido: {mes}. Debe estar entre 1 y 12."
            
            for dia in dias:
                if not TemporadaService._validar_dia_mes(anio, mes, dia):
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
    def obtener_anios_con_temporadas() -> List[int]:
        """
        Obtiene la lista de años que tienen temporadas configuradas.
        
        Returns:
            Lista de años ordenados de forma descendente
        """
        anios = DiaEspecial.objects.filter(
            es_temporada=True,
            activo=True
        ).values_list('año_planificacion', flat=True).distinct()
        
        return sorted(set(anios), reverse=True) if anios else []

    @staticmethod
    def tiene_temporadas_anio(anio: int) -> bool:
        """
        Verifica si un año tiene temporadas configuradas.
        
        Args:
            anio: Año a verificar
            
        Returns:
            True si el año tiene temporadas, False en caso contrario
        """
        return DiaEspecial.objects.filter(
            año_planificacion=anio,
            es_temporada=True,
            activo=True
        ).exists()

